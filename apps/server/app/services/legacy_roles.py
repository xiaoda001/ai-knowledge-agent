from sqlalchemy import select, text
from sqlalchemy.orm import Session

from server_core.db import engine
from server_core.models import Role, User, UserRole


LEGACY_READ_ONLY_ROLE_ID = "00000000-0000-4000-8000-000000000001"
LEGACY_READ_ONLY_ROLE_NAME = "只读成员（兼容迁移）"
LEGACY_READ_ONLY_PERMISSIONS = ["chat.use", "document.read"]
LOCK_NAME = "knowledge_legacy_role_migration"


def ensure_legacy_read_only_role() -> None:
    """Seed a reserved least-privilege role and assign it to legacy roleless members."""
    connection = engine.connect()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)
    lock_acquired = False
    try:
        lock_acquired = connection.execute(text("SELECT GET_LOCK(:name, 30)"), {"name": LOCK_NAME}).scalar() == 1
        if not lock_acquired:
            raise RuntimeError("Could not acquire the legacy role migration lock")
        connection.commit()

        role = db.get(Role, LEGACY_READ_ONLY_ROLE_ID)
        name_match = db.scalar(select(Role).where(Role.name == LEGACY_READ_ONLY_ROLE_NAME))
        if role is None:
            if name_match is not None:
                raise RuntimeError("Reserved legacy role name is already in use")
            role = Role(id=LEGACY_READ_ONLY_ROLE_ID, name=LEGACY_READ_ONLY_ROLE_NAME,
                        description="系统兼容角色：仅允许使用 AI 聊天和查看授权资料。",
                        permissions=LEGACY_READ_ONLY_PERMISSIONS)
            db.add(role)
            db.flush()
        elif role.name != LEGACY_READ_ONLY_ROLE_NAME or set(role.permissions or []) != set(LEGACY_READ_ONLY_PERMISSIONS):
            raise RuntimeError("Reserved legacy read-only role was modified; refusing automatic migration")
        elif name_match is not None and name_match.id != role.id:
            raise RuntimeError("Reserved legacy role name is already in use")

        roleless_members = db.scalars(
            select(User).where(
                User.is_admin.is_(False),
                ~select(UserRole.id).where(UserRole.user_id == User.id).exists(),
            )
        ).all()
        db.add_all([UserRole(user_id=user.id, role_id=role.id) for user in roleless_members])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        try:
            if lock_acquired:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})
                connection.commit()
        finally:
            connection.close()
