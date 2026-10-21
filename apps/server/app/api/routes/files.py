import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, get_db, permission_user
from server_core.config import settings
from server_core.models import StoredFile, User

router = APIRouter(prefix="/files", tags=["files"])
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 20 * 1024 * 1024


def _file_payload(item: StoredFile) -> dict:
    return {
        "id": item.id,
        "filename": item.filename,
        "media_type": item.media_type,
        "size_bytes": item.size_bytes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("")
def list_files(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(StoredFile).order_by(StoredFile.created_at.desc())
    if not user.is_admin:
        query = query.where(StoredFile.owner_id == user.id)
    return [_file_payload(item) for item in db.scalars(query).all()]


@router.post("")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db),
                      user: User = Depends(permission_user("file.upload"))):
    raw_name = (file.filename or "").replace("\\", "/")
    filename = Path(raw_name).name.strip()
    suffix = Path(filename).suffix.lower()
    if not filename or len(filename) > 255:
        raise HTTPException(422, "A filename of at most 255 characters is required")
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "This file type is not supported")

    directory = Path(settings.upload_dir) / "regular"
    directory.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid4())
    destination = directory / f"{file_id}{suffix}"
    temporary = directory / f"{file_id}{suffix}.part"
    size = 0
    try:
        with temporary.open("wb") as output:
            while data := await file.read(64 * 1024):
                size += len(data)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(413, "File exceeds 20 MiB")
                output.write(data)
        if size == 0:
            raise HTTPException(422, "Empty files cannot be uploaded")
        temporary.replace(destination)
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        record = StoredFile(id=file_id, owner_id=user.id, filename=filename,
                            storage_path=str(destination), media_type=media_type, size_bytes=size)
        db.add(record)
        db.commit()
        db.refresh(record)
        return _file_payload(record)
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/{file_id}/download")
def download_file(file_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(StoredFile, file_id)
    if item is None or (not user.is_admin and item.owner_id != user.id):
        raise HTTPException(404, "File not found")
    path = Path(item.storage_path)
    if not path.is_file():
        raise HTTPException(404, "File content not found")
    return FileResponse(path, media_type=item.media_type, filename=item.filename)
