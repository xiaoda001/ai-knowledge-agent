from datetime import datetime
from pathlib import Path

import chromadb
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, get_db, permission_user
from app.api.schemas import KnowledgeBaseMemoryInput, KnowledgeBaseUpdate
from server_core.acl import can_view_document, authorized_documents, is_kb_member
from server_core.config import settings
from server_core.document_versions import document_version_states
from server_core.models import (
    Chunk, Department, Document, KnowledgeBase, KnowledgeBaseMember, KnowledgeBaseMemory, Role, User, UserRole,
)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("")
def list_kbs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": kb.id, "name": kb.name, "description": kb.description or ""} for kb in db.scalars(
        select(KnowledgeBase).join(KnowledgeBaseMember).where(KnowledgeBaseMember.user_id == user.id)
    ).all()]


@router.post("")
def create_kb(name: str, description: str = "", db: Session = Depends(get_db), admin: User = Depends(permission_user("knowledge_base.create"))):
    name = name.strip()
    if not name or len(name) > 190:
        raise HTTPException(422, "Knowledge base name must be 1–190 characters")
    if db.scalar(select(KnowledgeBase.id).where(KnowledgeBase.name == name)):
        raise HTTPException(409, "Knowledge base name already exists")
    kb = KnowledgeBase(name=name, description=description.strip()[:1000], created_by=admin.id)
    db.add(kb)
    db.flush()
    db.add(KnowledgeBaseMember(knowledge_base_id=kb.id, user_id=admin.id))
    db.commit()
    return {"id": kb.id, "name": kb.name, "description": kb.description or ""}


@router.put("/{kb_id}")
def update_kb(kb_id: str, body: KnowledgeBaseUpdate, db: Session = Depends(get_db),
              actor: User = Depends(permission_user("knowledge_base.manage"))):
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or not is_kb_member(db, actor, kb_id):
        raise HTTPException(404, "Knowledge base not found")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Knowledge base name cannot be blank")
        duplicate = db.scalar(select(KnowledgeBase.id).where(
            KnowledgeBase.name == name, KnowledgeBase.id != kb_id,
        ))
        if duplicate:
            raise HTTPException(409, "Knowledge base name already exists")
        kb.name = name
    kb.description = body.description.strip()[:1000]
    db.commit()
    return {"id": kb.id, "name": kb.name, "description": kb.description}


@router.delete("/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_db),
              actor: User = Depends(permission_user("knowledge_base.manage"))):
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or not is_kb_member(db, actor, kb_id):
        raise HTTPException(404, "Knowledge base not found")
    documents = db.scalars(select(Document).where(Document.knowledge_base_id == kb_id)).all()
    if any(document.status in {"queued", "processing"} for document in documents):
        raise HTTPException(409, "Wait for document indexing to finish before deleting this knowledge base")
    paths = [Path(document.storage_path) for document in documents]
    if documents:
        try:
            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
            collection = client.get_or_create_collection("knowledge_chunks")
            collection.delete(where={"knowledge_base_id": kb_id})
        except Exception as exc:
            raise HTTPException(503, "Knowledge vectors could not be removed; knowledge base was kept") from exc
    document_ids = [document.id for document in documents]
    if document_ids:
        db.execute(delete(Chunk).where(Chunk.document_id.in_(document_ids)))
        db.execute(delete(Document).where(Document.id.in_(document_ids)))
    db.execute(delete(KnowledgeBaseMemory).where(KnowledgeBaseMemory.knowledge_base_id == kb_id))
    db.execute(delete(KnowledgeBaseMember).where(KnowledgeBaseMember.knowledge_base_id == kb_id))
    db.delete(kb)
    db.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    return {"status": "deleted"}


def _require_kb_member(db: Session, actor: User, kb_id: str):
    if db.get(KnowledgeBase, kb_id) is None or not is_kb_member(db, actor, kb_id):
        raise HTTPException(404, "Knowledge base not found")


def _memory_payload(item: KnowledgeBaseMemory):
    return {"id": item.id, "knowledge_base_id": item.knowledge_base_id,
            "title": item.title, "content": item.content,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


@router.get("/{kb_id}/memories")
def list_kb_memories(kb_id: str, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_kb_member(db, actor, kb_id)
    items = db.scalars(select(KnowledgeBaseMemory).where(
        KnowledgeBaseMemory.knowledge_base_id == kb_id,
    ).order_by(KnowledgeBaseMemory.created_at, KnowledgeBaseMemory.id)).all()
    return [_memory_payload(item) for item in items]


@router.post("/{kb_id}/memories")
def create_kb_memory(kb_id: str, body: KnowledgeBaseMemoryInput, db: Session = Depends(get_db),
                     actor: User = Depends(permission_user("knowledge_base.manage"))):
    _require_kb_member(db, actor, kb_id)
    title, content = body.title.strip(), body.content.strip()
    if not title or not content:
        raise HTTPException(422, "Memory title and content cannot be blank")
    count = db.scalar(select(func.count()).select_from(KnowledgeBaseMemory).where(
        KnowledgeBaseMemory.knowledge_base_id == kb_id,
    ))
    if count >= 50:
        raise HTTPException(409, "A knowledge base can have at most 50 memory notes")
    item = KnowledgeBaseMemory(knowledge_base_id=kb_id, title=title, content=content,
                               created_by=actor.id, updated_by=actor.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _memory_payload(item)


@router.put("/{kb_id}/memories/{memory_id}")
def update_kb_memory(kb_id: str, memory_id: str, body: KnowledgeBaseMemoryInput,
                     db: Session = Depends(get_db),
                     actor: User = Depends(permission_user("knowledge_base.manage"))):
    _require_kb_member(db, actor, kb_id)
    item = db.get(KnowledgeBaseMemory, memory_id)
    if item is None or item.knowledge_base_id != kb_id:
        raise HTTPException(404, "Memory not found")
    title, content = body.title.strip(), body.content.strip()
    if not title or not content:
        raise HTTPException(422, "Memory title and content cannot be blank")
    item.title, item.content, item.updated_by = title, content, actor.id
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _memory_payload(item)


@router.delete("/{kb_id}/memories/{memory_id}")
def delete_kb_memory(kb_id: str, memory_id: str, db: Session = Depends(get_db),
                     actor: User = Depends(permission_user("knowledge_base.manage"))):
    _require_kb_member(db, actor, kb_id)
    item = db.get(KnowledgeBaseMemory, memory_id)
    if item is None or item.knowledge_base_id != kb_id:
        raise HTTPException(404, "Memory not found")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@router.post("/{kb_id}/members/{user_id}")
def add_member(kb_id: str, user_id: str, db: Session = Depends(get_db), actor: User = Depends(permission_user("member.manage"))):
    if not actor.is_admin and not is_kb_member(db, actor, kb_id):
        raise HTTPException(404, "Knowledge base not found")
    if db.get(KnowledgeBase, kb_id) is None or db.get(User, user_id) is None:
        raise HTTPException(404, "Knowledge base or user not found")
    if db.scalar(select(KnowledgeBaseMember.id).where(
        KnowledgeBaseMember.knowledge_base_id == kb_id, KnowledgeBaseMember.user_id == user_id
    )):
        return {"status": "already_member"}
    db.add(KnowledgeBaseMember(knowledge_base_id=kb_id, user_id=user_id))
    db.commit()
    return {"status": "added"}


@router.get("/{kb_id}/members")
def list_members(kb_id: str, db: Session = Depends(get_db), actor: User = Depends(permission_user("member.manage"))):
    if db.get(KnowledgeBase, kb_id) is None or (not actor.is_admin and not is_kb_member(db, actor, kb_id)):
        raise HTTPException(404, "Knowledge base not found")
    rows = db.execute(select(User, KnowledgeBaseMember).join(
        KnowledgeBaseMember, KnowledgeBaseMember.user_id == User.id
    ).where(KnowledgeBaseMember.knowledge_base_id == kb_id)).all()
    members = []
    for user, _membership in rows:
        role_rows = db.scalars(select(Role).join(UserRole, UserRole.role_id == Role.id)
                               .where(UserRole.user_id == user.id)).all()
        members.append({"id": user.id, "nickname": user.nickname or user.username,
                        "username": user.username, "department_id": user.department_id,
                        "clearance": user.clearance, "roles": [role.name for role in role_rows],
                        "role_ids": [role.id for role in role_rows]})
    return members


@router.delete("/{kb_id}/members/{user_id}")
def remove_member(kb_id: str, user_id: str, db: Session = Depends(get_db),
                  actor: User = Depends(permission_user("member.manage"))):
    if db.get(KnowledgeBase, kb_id) is None or (not actor.is_admin and not is_kb_member(db, actor, kb_id)):
        raise HTTPException(404, "Knowledge base not found")
    membership = db.scalar(select(KnowledgeBaseMember).where(
        KnowledgeBaseMember.knowledge_base_id == kb_id,
        KnowledgeBaseMember.user_id == user_id,
    ))
    if membership is None:
        raise HTTPException(404, "Knowledge base member not found")
    db.delete(membership)
    db.commit()
    return {"status": "removed"}


@router.get("/{kb_id}/documents")
def list_documents(kb_id: str, db: Session = Depends(get_db), user: User = Depends(permission_user("document.read"))):
    if not is_kb_member(db, user, kb_id):
        raise HTTPException(404, "Knowledge base not found")
    rows = db.scalars(select(Document).where(Document.knowledge_base_id == kb_id)).all()
    version_states = document_version_states(rows)
    department_ids = {doc.department_id for doc in rows if doc.department_id}
    departments = {item.id: item.name for item in db.scalars(
        select(Department).where(Department.id.in_(department_ids))
    ).all()} if department_ids else {}
    return [{"id": doc.id, "filename": doc.filename, "status": doc.status,
             "version_status": version_states[doc.id],
             "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
             "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
             "created_at": doc.created_at.isoformat() if doc.created_at else None,
             "access_scope": doc.access_scope, "department_id": doc.department_id,
             "department_name": departments.get(doc.department_id),
             "classification_level": doc.classification_level,
             "allowed_roles": doc.allowed_roles or [],
             "error": doc.error_message if user.is_admin else None}
            for doc in rows if user.is_admin or can_view_document(db, user, doc)]
