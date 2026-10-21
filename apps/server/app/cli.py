import getpass

from sqlalchemy import select, text

from app.services.auth import password_hash
from server_core.db import Base, SessionLocal, engine
from server_core.models import User


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    lock_name = "knowledge_bootstrap_admin"
    lock_acquired = False
    try:
        lock_acquired = db.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}) == 1
        if not lock_acquired:
            raise SystemExit("Another administrator bootstrap is already running.")
        if db.scalar(select(User.id).where(User.is_admin.is_(True))):
            raise SystemExit("An administrator already exists; bootstrap is one-time only.")
        username = input("Initial admin username: ").strip()
        department_id = input("Admin department ID: ").strip()
        clearance = int(input("Admin maximum classification level: ").strip())
        roles = [item.strip() for item in input("Admin roles (comma separated): ").split(",") if item.strip()]
        password = getpass.getpass("Initial admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if not username or not department_id or clearance < 0 or len(password) < 12 or password != confirm:
            raise SystemExit("Username/department are required; clearance must be non-negative; passwords must match and be at least 12 characters.")
        db.add(User(username=username, password_hash=password_hash(password), is_admin=True, active=True,
                    department_id=department_id, clearance=clearance, roles=roles))
        db.commit()
        print("Initial administrator created.")
    finally:
        if lock_acquired:
            db.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
        db.close()


if __name__ == "__main__":
    main()
