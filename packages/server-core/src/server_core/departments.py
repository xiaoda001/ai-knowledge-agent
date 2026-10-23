"""Small startup migration helpers for the first-class department directory."""

from sqlalchemy import inspect, text

from server_core.db import SessionLocal
from server_core.models import Department, Document, User


def ensure_department_schema(engine) -> None:
    """Backfill legacy free-text department values and add MySQL FK constraints."""
    inspector = inspect(engine)
    if "departments" not in inspector.get_table_names():
        return

    with SessionLocal() as db:
        legacy_ids = set(db.query(User.department_id).filter(User.department_id.is_not(None)).all())
        legacy_ids.update(db.query(Document.department_id).filter(Document.department_id.is_not(None)).all())
        department_ids = {row[0] for row in legacy_ids if row[0] and row[0].strip()}
        existing = set(db.query(Department.id).all())
        existing_ids = {row[0] for row in existing}
        for department_id in sorted(department_ids - existing_ids):
            # Preserve existing ACL values exactly as directory IDs; admins can
            # rename the display label after migration without changing access.
            db.add(Department(id=department_id, name=department_id))
        db.commit()

    if engine.dialect.name != "mysql":
        return
    constraints = {
        (table, column): name
        for table, column, name in (
            ("users", "department_id", "fk_users_department"),
            ("documents", "department_id", "fk_documents_department"),
        )
    }
    for (table, column), name in constraints.items():
        if table not in inspector.get_table_names():
            continue
        foreign_keys = inspector.get_foreign_keys(table)
        if any(column in item.get("constrained_columns", [])
               and item.get("referred_table") == "departments" for item in foreign_keys):
            continue
        with engine.begin() as connection:
            connection.execute(text(
                f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` "
                f"FOREIGN KEY (`{column}`) REFERENCES `departments` (`id`)"
            ))
