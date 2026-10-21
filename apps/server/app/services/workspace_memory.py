from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.chat_context import token_count, truncate_text_to_token_budget
from server_core.acl import is_kb_member
from server_core.config import settings
from server_core.models import KnowledgeBase, KnowledgeBaseMemory, User


def load_workspace_memory(db: Session, user: User, knowledge_base_ids: list[str]) -> str:
    """Load bounded, explicitly maintained notes from currently authorized selected libraries."""
    allowed_ids = [kb_id for kb_id in dict.fromkeys(knowledge_base_ids)
                   if is_kb_member(db, user, kb_id)]
    if not allowed_ids:
        return ""

    bases = db.scalars(select(KnowledgeBase).where(KnowledgeBase.id.in_(allowed_ids))).all()
    names = {base.id: base.name for base in bases}
    notes = db.scalars(select(KnowledgeBaseMemory).where(
        KnowledgeBaseMemory.knowledge_base_id.in_(allowed_ids),
    ).order_by(KnowledgeBaseMemory.knowledge_base_id,
               KnowledgeBaseMemory.created_at, KnowledgeBaseMemory.id)).all()

    sections = []
    used_tokens = 0
    for item in notes:
        prefix = f"[{names.get(item.knowledge_base_id, '知识库')}] {item.title}: "
        available = settings.memory_workspace_token_budget - used_tokens
        prefix_tokens = token_count(prefix)
        if available <= prefix_tokens:
            break
        max_content_tokens = available - prefix_tokens
        line = ""
        while max_content_tokens > 0:
            clipped_content = truncate_text_to_token_budget(item.content, max_content_tokens)
            line = prefix + clipped_content
            if token_count(line) <= available:
                break
            max_content_tokens -= 1
        if not line or max_content_tokens == 0:
            continue
        sections.append(line)
        used_tokens += token_count(line)
        if used_tokens >= settings.memory_workspace_token_budget:
            break

    return "\n".join(sections)
