from collections.abc import Generator

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.services.auth import ensure_jwt_secret
from server_core.db import SessionLocal
from server_core.acl import has_permission
from server_core.models import User

oauth = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(token: str = Depends(oauth), db: Session = Depends(get_db)) -> User:
    secret = ensure_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        user = db.get(User, payload["sub"])
        if user is None or not user.active:
            raise ValueError("inactive")
        return user
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired token") from exc


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Administrator required")
    return user


def permission_user(permission: str):
    def check(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if not has_permission(db, user, permission):
            raise HTTPException(403, f"Permission required: {permission}")
        return user
    return check
