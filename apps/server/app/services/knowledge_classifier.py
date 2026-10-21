import math
import re
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from server_core.acl import is_kb_member
from server_core.config import settings
from server_core.embeddings import embed_texts
from server_core.models import Document, KnowledgeBase, KnowledgeBaseMember, User
from worker_app.extract import extract_document_text


SUPPORTED_EXTENSIONS = {".md", ".txt", ".csv", ".pdf", ".docx", ".xlsx", ".pptx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _terms(text: str) -> set[str]:
    found: set[str] = set()
    for part in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            found.update(part[index:index + 2] for index in range(len(part) - 1))
            if len(part) == 1:
                found.add(part)
        else:
            found.add(part)
    return found


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


async def classify_knowledge_upload(db: Session, user: User, file: UploadFile) -> dict:
    filename = Path((file.filename or "").replace("\\", "/")).name.strip()
    extension = Path(filename).suffix.lower()
    if not filename or extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "Supported knowledge files: PDF, DOCX, XLSX, PPTX, TXT, CSV, MD")

    libraries = db.scalars(
        select(KnowledgeBase).join(KnowledgeBaseMember)
        .where(KnowledgeBaseMember.user_id == user.id)
        .order_by(KnowledgeBase.name)
    ).all()
    libraries = [library for library in libraries if is_kb_member(db, user, library.id)]
    if not libraries:
        raise HTTPException(404, "No accessible knowledge base")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f".classify-{uuid4()}{extension}"
    size = 0
    try:
        with temp_path.open("wb") as output:
            while data := await file.read(64 * 1024):
                size += len(data)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Knowledge file exceeds 20 MiB")
                output.write(data)
        text = extract_document_text(temp_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not read document text: {str(exc)[:180]}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()

    if not text.strip():
        raise HTTPException(422, "No text could be extracted from this file")

    library_ids = [library.id for library in libraries]
    recent_names = {library.id: [] for library in libraries}
    rows = db.execute(
        select(Document.knowledge_base_id, Document.filename)
        .where(Document.knowledge_base_id.in_(library_ids))
        .order_by(Document.created_at.desc()).limit(min(600, len(library_ids) * 12))
    ).all()
    for library_id, document_filename in rows:
        if len(recent_names[library_id]) < 12:
            recent_names[library_id].append(Path(document_filename).stem)

    profiles = []
    for library in libraries:
        profile = " ".join(filter(None, [
            library.name,
            library.description,
            "已有资料主题 " + " ".join(recent_names[library.id]) if recent_names[library.id] else "",
        ]))
        profiles.append(profile)

    method = "keywords"
    dense_scores: list[float] | None = None
    try:
        vectors = embed_texts([text[:4000], *profiles])
        dense_scores = [(_cosine(vectors[0], vector) + 1) / 2 for vector in vectors[1:]]
        method = "embeddings"
    except Exception:
        pass

    text_terms = _terms(filename + " " + text[:4000])
    keyword_scores = []
    for profile in profiles:
        profile_terms = _terms(profile)
        keyword_scores.append(len(text_terms & profile_terms) / max(1, len(profile_terms)))

    scores = [
        (dense_scores[index] * 0.85 + keyword_scores[index] * 0.15)
        if dense_scores is not None else keyword_scores[index]
        for index in range(len(libraries))
    ]
    ranking = sorted(range(len(libraries)), key=lambda index: scores[index], reverse=True)
    top = ranking[0]
    second_score = scores[ranking[1]] if len(ranking) > 1 else -1
    if len(libraries) == 1:
        mode = "auto"
    elif dense_scores is not None:
        mode = "auto" if scores[top] >= 0.76 and scores[top] - second_score >= 0.07 else "confirm"
    else:
        mode = "auto" if keyword_scores[top] >= 0.45 and keyword_scores[top] - second_score >= 0.15 else "confirm"

    recommendations = [{
        "id": libraries[index].id,
        "name": libraries[index].name,
        "description": libraries[index].description or "",
        "score": round(scores[index], 3),
    } for index in ranking[:3]]
    return {"mode": mode, "method": method, "recommendations": recommendations}
