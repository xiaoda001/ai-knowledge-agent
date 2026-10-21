from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from server_core.acl import is_kb_member, user_role_names
from server_core.config import settings
from server_core.models import Document, User
from worker_app.tasks import ingest_document


async def upload_knowledge_document(db: Session, user: User, kb_id: str, file: UploadFile,
                                    department_id: str | None = None, classification_level: int | None = None,
                                    allowed_roles: str = ""):
    if not is_kb_member(db, user, kb_id):
        raise HTTPException(403, "Knowledge base access denied")
    filename = Path((file.filename or "").replace("\\", "/")).name.strip()
    extension = Path(filename).suffix.lower()
    if not filename or extension not in {".md", ".txt", ".csv", ".pdf", ".docx", ".xlsx", ".pptx"}:
        raise HTTPException(415, "Supported knowledge files: PDF, DOCX, XLSX, PPTX, TXT, CSV, MD")
    if len(filename) > 255:
        raise HTTPException(422, "Filename must be at most 255 characters")

    has_document_acl = department_id is not None or classification_level is not None or bool(allowed_roles)
    roles = []
    access_scope = "knowledge_base"
    if has_document_acl:
        department_id = (department_id or "").strip()
        if not department_id or classification_level is None or classification_level < 0:
            raise HTTPException(422, "Document department and non-negative classification are required")
        roles = [role.strip() for role in allowed_roles.split(",") if role.strip()]
        if (department_id != user.department_id or user.clearance is None or classification_level > user.clearance
                or (roles and not set(roles).intersection(user_role_names(db, user)))):
            raise HTTPException(403, "Document ACL must stay within the uploader's department, clearance, and roles")
        access_scope = "document_acl"

    doc_id = str(uuid4())
    path = Path(settings.upload_dir) / f"{doc_id}{extension}"
    size = 0
    try:
        with path.open("wb") as output:
            while data := await file.read(64 * 1024):
                size += len(data)
                if size > 20 * 1024 * 1024:
                    raise HTTPException(413, "Knowledge file exceeds 20 MiB")
                output.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    document = Document(id=doc_id, knowledge_base_id=kb_id, filename=filename,
                        storage_path=str(path), department_id=department_id,
                        classification_level=classification_level, allowed_roles=roles,
                        access_scope=access_scope)
    db.add(document)
    db.commit()
    try:
        ingest_document.delay(doc_id)
    except Exception as exc:
        db.delete(document)
        db.commit()
        path.unlink(missing_ok=True)
        raise HTTPException(503, "Document queue is unavailable") from exc
    return {"id": doc_id, "status": "queued"}


upload_markdown_document = upload_knowledge_document
