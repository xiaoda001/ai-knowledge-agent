from sqlalchemy import select
from sqlalchemy.orm import Session

from server_core.acl import authorized_documents
from server_core.models import KnowledgeBase, KnowledgeBaseMember, User


def accessible_knowledge_bases(db: Session, user: User) -> list[KnowledgeBase]:
    return db.scalars(
        select(KnowledgeBase)
        .join(KnowledgeBaseMember, KnowledgeBaseMember.knowledge_base_id == KnowledgeBase.id)
        .where(KnowledgeBaseMember.user_id == user.id)
        .order_by(KnowledgeBase.name)
    ).all()


def count_accessible_knowledge_bases(db: Session, user: User) -> int:
    return len(accessible_knowledge_bases(db, user))


def count_visible_documents(db: Session, user: User, knowledge_base_name: str) -> int | None:
    """Count ready documents visible under the same ACL used by retrieval."""
    requested_name = knowledge_base_name.strip().casefold()
    if not requested_name:
        return None
    base = next((item for item in accessible_knowledge_bases(db, user)
                 if item.name.strip().casefold() == requested_name), None)
    if base is None:
        return None
    return len(authorized_documents(db, user, base.id))
