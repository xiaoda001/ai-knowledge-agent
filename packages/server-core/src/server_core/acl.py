from sqlalchemy import select
from sqlalchemy.orm import Session

from server_core.models import Document, KnowledgeBaseMember, Role, User, UserRole


PERMISSIONS = {
    "chat.use": "使用 AI 聊天",
    "document.read": "查看授权文档和原文",
    "knowledge_base.create": "创建知识库",
    "knowledge_base.manage": "编辑和删除知识库",
    "member.manage": "创建成员并管理成员关系",
    "document.upload": "上传和管理知识文档",
    "file.upload": "上传常规文件",
    "role.manage": "创建和配置角色",
    "department.manage": "管理部门目录",
}


def user_permissions(db: Session, user: User) -> set[str]:
    if user.is_admin:
        return set(PERMISSIONS)
    roles = db.scalars(select(Role).join(UserRole, UserRole.role_id == Role.id)
                       .where(UserRole.user_id == user.id)).all()
    permissions = {permission for role in roles for permission in (role.permissions or [])}
    if "document.upload" in permissions:
        permissions.add("document.read")
    return permissions


def user_role_names(db: Session, user: User) -> set[str]:
    assigned = set(db.scalars(select(Role.name).join(UserRole, UserRole.role_id == Role.id)
                              .where(UserRole.user_id == user.id)).all())
    return assigned | set(user.roles or [])


def has_permission(db: Session, user: User, permission: str) -> bool:
    return permission in user_permissions(db, user)


def is_kb_member(db: Session, user: User, kb_id: str) -> bool:
    return db.scalar(select(KnowledgeBaseMember.id).where(
        KnowledgeBaseMember.user_id == user.id,
        KnowledgeBaseMember.knowledge_base_id == kb_id,
    )) is not None


def authorized_documents(db: Session, user: User, kb_id: str) -> list[Document]:
    """Resolve ACLs before retrieval. Missing user/document attributes fail closed."""
    if not user.active:
        return []
    if not is_kb_member(db, user, kb_id):
        return []
    candidates = db.scalars(select(Document).where(
        Document.knowledge_base_id == kb_id,
        Document.status == "ready",
    )).all()
    roles = user_role_names(db, user)
    allowed = []
    for doc in candidates:
        if doc.access_scope == "knowledge_base":
            allowed.append(doc)
            continue
        if user.department_id is None or user.clearance is None:
            continue
        if doc.department_id is None or doc.classification_level is None:
            continue
        if doc.department_id != user.department_id or doc.classification_level > user.clearance:
            continue
        required = set(doc.allowed_roles or [])
        if required and not roles.intersection(required):
            continue
        allowed.append(doc)
    return allowed


def can_view_document(db: Session, user: User, document: Document) -> bool:
    if not user.active or not is_kb_member(db, user, document.knowledge_base_id):
        return False
    if document.access_scope == "knowledge_base":
        return True
    if user.department_id is None or user.clearance is None:
        return False
    if document.department_id is None or document.classification_level is None:
        return False
    if document.department_id != user.department_id or document.classification_level > user.clearance:
        return False
    required = set(document.allowed_roles or [])
    return not required or bool(user_role_names(db, user).intersection(required))
