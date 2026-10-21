from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, permission_user
from app.api.schemas import UserCreate, UserRolesUpdate
from app.services.auth import password_hash
from server_core.acl import user_permissions
from server_core.models import Role, User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(permission_user("member.manage"))):
    users = db.scalars(select(User).where(User.is_admin.is_(False), User.active.is_(True))
                       .order_by(User.username)).all()
    role_rows = db.execute(select(UserRole.user_id, UserRole.role_id, Role.name)
                           .join(Role, Role.id == UserRole.role_id)
                           .where(UserRole.user_id.in_([user.id for user in users]))).all() if users else []
    roles_by_user = {user.id: [] for user in users}
    for user_id, role_id, role_name in role_rows:
        roles_by_user[user_id].append((role_id, role_name))
    return [{"id": user.id, "username": user.username,
             "roles": sorted(role_name for _, role_name in roles_by_user[user.id]),
             "role_ids": [role_id for role_id, _ in roles_by_user[user.id]]}
            for user in users]


@router.post("/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(permission_user("member.manage"))):
    username = payload.username.strip()
    department_id = payload.department_id.strip()
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, "Username already exists")
    if not username or len(payload.password) < 12 or payload.clearance < 0 or not department_id:
        raise HTTPException(422, "Username, department, non-negative clearance, and 12-character password are required")
    role_ids = set(payload.role_ids)
    selected_roles = db.scalars(select(Role).where(Role.id.in_(role_ids))).all()
    if len(selected_roles) != len(role_ids) or not selected_roles:
        raise HTTPException(422, "Select roles from the role catalog")
    granted_permissions = {permission for role in selected_roles for permission in (role.permissions or [])}
    if not actor.is_admin and not granted_permissions.issubset(user_permissions(db, actor)):
        raise HTTPException(403, "You cannot assign permissions you do not have")
    user = User(username=username, password_hash=password_hash(payload.password), department_id=department_id,
                clearance=payload.clearance, roles=[], is_admin=False)
    db.add(user)
    db.flush()
    db.add_all([UserRole(user_id=user.id, role_id=role.id) for role in selected_roles])
    db.commit()
    return {"id": user.id, "username": user.username}


@router.put("/users/{user_id}/roles")
def update_user_roles(user_id: str, payload: UserRolesUpdate, db: Session = Depends(get_db),
                      actor: User = Depends(permission_user("member.manage"))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    selected_ids = set(payload.role_ids)
    selected_roles = db.scalars(select(Role).where(Role.id.in_(selected_ids))).all()
    if len(selected_roles) != len(selected_ids):
        raise HTTPException(422, "Select roles from the role catalog")
    granted_permissions = {permission for role in selected_roles for permission in (role.permissions or [])}
    if not actor.is_admin and not granted_permissions.issubset(user_permissions(db, actor)):
        raise HTTPException(403, "You cannot assign permissions you do not have")
    db.query(UserRole).filter(UserRole.user_id == user.id).delete(synchronize_session=False)
    db.add_all([UserRole(user_id=user.id, role_id=role.id) for role in selected_roles])
    db.commit()
    return {"id": user.id, "roles": sorted(role.name for role in selected_roles)}
