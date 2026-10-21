from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, get_db, permission_user
from app.api.schemas import RoleCreate, RoleUpdate
from app.services.legacy_roles import LEGACY_READ_ONLY_ROLE_ID, LEGACY_READ_ONLY_ROLE_NAME
from server_core.acl import PERMISSIONS, user_permissions
from server_core.models import Role, User

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("")
def list_roles(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": role.id, "name": role.name, "description": role.description,
             "permissions": role.permissions or [], "is_system": role.id == LEGACY_READ_ONLY_ROLE_ID}
            for role in db.scalars(select(Role).order_by(Role.name)).all()]


@router.post("")
def create_role(payload: RoleCreate, db: Session = Depends(get_db),
                actor: User = Depends(permission_user("role.manage"))):
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "Role name is required")
    if name == LEGACY_READ_ONLY_ROLE_NAME:
        raise HTTPException(422, "This role name is reserved")
    if db.scalar(select(Role.id).where(Role.name == name)):
        raise HTTPException(409, "Role name already exists")
    invalid = sorted(set(payload.permissions) - set(PERMISSIONS))
    if invalid:
        raise HTTPException(422, f"Unknown permissions: {', '.join(invalid)}")
    if not actor.is_admin and not set(payload.permissions).issubset(user_permissions(db, actor)):
        raise HTTPException(403, "You cannot grant permissions you do not have")
    role = Role(name=name, description=payload.description.strip(),
                permissions=list(dict.fromkeys(payload.permissions)))
    db.add(role)
    db.commit()
    return {"id": role.id, "name": role.name, "description": role.description,
            "permissions": role.permissions}


@router.put("/{role_id}")
def update_role(role_id: str, payload: RoleUpdate, db: Session = Depends(get_db),
                actor: User = Depends(permission_user("role.manage"))):
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "Role not found")
    if role.id == LEGACY_READ_ONLY_ROLE_ID:
        raise HTTPException(403, "System roles cannot be changed")
    invalid = sorted(set(payload.permissions) - set(PERMISSIONS))
    if invalid:
        raise HTTPException(422, f"Unknown permissions: {', '.join(invalid)}")
    if not actor.is_admin and not set(payload.permissions).issubset(user_permissions(db, actor)):
        raise HTTPException(403, "You cannot grant permissions you do not have")
    role.description = payload.description.strip()
    role.permissions = list(dict.fromkeys(payload.permissions))
    db.commit()
    return {"id": role.id, "name": role.name, "description": role.description,
            "permissions": role.permissions, "is_system": False}


@router.get("/permissions")
def list_permissions(_: User = Depends(current_user)):
    return [{"key": key, "label": label} for key, label in PERMISSIONS.items()]
