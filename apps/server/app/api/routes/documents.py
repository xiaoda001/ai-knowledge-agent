from pathlib import Path

import chromadb
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, permission_user
from app.services.document_ingestion import upload_knowledge_document
from app.services.knowledge_classifier import classify_knowledge_upload
from server_core.acl import can_view_document, is_kb_member
from server_core.config import settings
from server_core.models import Chunk, Document, User
from worker_app.extract import extract_document_text

router = APIRouter(tags=["documents"])


@router.get("/documents/{doc_id}/status")
def document_status(doc_id: str, db: Session = Depends(get_db), user: User = Depends(permission_user("document.read"))):
    doc = db.get(Document, doc_id)
    if doc is None or not can_view_document(db, user, doc):
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "status": doc.status, "error": doc.error_message}


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_knowledge_document_route(kb_id: str, file: UploadFile = File(...), department_id: str | None = Form(None),
                          classification_level: int | None = Form(None), allowed_roles: str = Form(""),
                          db: Session = Depends(get_db), user: User = Depends(permission_user("document.upload"))):
    return await upload_knowledge_document(db, user, kb_id, file, department_id,
                                           classification_level, allowed_roles)


def _manageable_document(db: Session, user: User, doc_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or not is_kb_member(db, user, doc.knowledge_base_id):
        raise HTTPException(404, "Document not found")
    if doc.status in {"queued", "processing"}:
        raise HTTPException(409, "Wait for document indexing to finish before changing it")
    return doc


@router.post("/documents/{doc_id}/expire")
def expire_document(doc_id: str, db: Session = Depends(get_db), user: User = Depends(permission_user("document.upload"))):
    doc = _manageable_document(db, user, doc_id)
    doc.status = "expired"
    db.commit()
    return {"id": doc.id, "status": doc.status}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db), user: User = Depends(permission_user("document.upload"))):
    doc = _manageable_document(db, user, doc_id)
    try:
        collection = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port).get_or_create_collection("knowledge_chunks")
        collection.delete(where={"document_id": doc.id})
    except Exception as exc:
        raise HTTPException(503, "Document index could not be removed; document was kept") from exc
    path = Path(doc.storage_path)
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    db.delete(doc)
    db.commit()
    path.unlink(missing_ok=True)
    return {"id": doc_id, "status": "deleted"}


@router.post("/knowledge-bases/classify-upload")
async def classify_upload(file: UploadFile = File(...), db: Session = Depends(get_db),
                         user: User = Depends(permission_user("document.upload"))):
    return await classify_knowledge_upload(db, user, file)


@router.get("/documents/{doc_id}/source")
def source(doc_id: str, db: Session = Depends(get_db), user: User = Depends(permission_user("document.read"))):
    doc = db.get(Document, doc_id)
    if doc is None or not can_view_document(db, user, doc):
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "filename": doc.filename, "markdown": extract_document_text(doc.storage_path)}
