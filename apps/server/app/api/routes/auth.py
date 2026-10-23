from fastapi import APIRouter, Depends, Form
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, get_db
from app.services.auth import token_for, verify_password
from server_core.acl import user_permissions, user_role_names
from server_core.config import settings
from server_core.models import Department, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.active or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": token_for(user), "token_type": "bearer", "expires_in": settings.jwt_minutes * 60}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    department = db.get(Department, user.department_id) if user.department_id else None
    return {"id": user.id, "nickname": user.nickname or user.username, "username": user.username, "is_admin": user.is_admin,
            "department_id": user.department_id, "department_name": department.name if department else None,
            "clearance": user.clearance, "roles": sorted(user_role_names(db, user)),
            "permissions": sorted(user_permissions(db, user))}
