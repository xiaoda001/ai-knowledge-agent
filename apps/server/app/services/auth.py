import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from server_core.config import settings
from server_core.models import User


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split("$", 1)
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return secrets.compare_digest(key.hex(), key_hex)
    except (ValueError, TypeError):
        return False


def ensure_jwt_secret() -> str:
    secret = settings.jwt_secret
    if len(secret.encode("utf-8")) < 32 or "replace-" in secret.lower():
        raise HTTPException(503, "JWT_SECRET must be configured with at least 32 random bytes")
    return secret


def token_for(user: User) -> str:
    secret = ensure_jwt_secret()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_minutes)
    return jwt.encode({"sub": user.id, "exp": expires}, secret, algorithm="HS256")
