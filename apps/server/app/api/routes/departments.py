from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, get_db, permission_user
from app.api.schemas import DepartmentCreate, DepartmentUpdate
from server_core.models import Department, Document, User

router = APIRouter(prefix="/departments", tags=["departments"])


def _payload(department: Department):
    return {"id": department.id, "name": department.name}


@router.get("")
def list_departments(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_payload(item) for item in db.scalars(select(Department).order_by(Department.name)).all()]


@router.post("")
def create_department(body: DepartmentCreate, db: Session = Depends(get_db),
                      _: User = Depends(permission_user("department.manage"))):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Department name cannot be blank")
    if db.scalar(select(Department.id).where(Department.name == name)):
        raise HTTPException(409, "Department name already exists")
    department = Department(id=str(uuid4()), name=name)
    db.add(department)
    db.commit()
    return _payload(department)


@router.put("/{department_id}")
def update_department(department_id: str, body: DepartmentUpdate, db: Session = Depends(get_db),
                      _: User = Depends(permission_user("department.manage"))):
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(404, "Department not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Department name cannot be blank")
    duplicate = db.scalar(select(Department.id).where(
        Department.name == name, Department.id != department_id,
    ))
    if duplicate:
        raise HTTPException(409, "Department name already exists")
    department.name = name
    db.commit()
    return _payload(department)


@router.delete("/{department_id}")
def delete_department(department_id: str, db: Session = Depends(get_db),
                      _: User = Depends(permission_user("department.manage"))):
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(404, "Department not found")
    if db.scalar(select(User.id).where(User.department_id == department_id).limit(1)) or \
            db.scalar(select(Document.id).where(Document.department_id == department_id).limit(1)):
        raise HTTPException(409, "Department is assigned to users or documents")
    db.delete(department)
    db.commit()
    return {"status": "deleted"}
