import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import APP_SECRET
from app.database import get_db
from app.models import User


def hash_password(password: str) -> str:
    return hashlib.sha256(f"bmkg-salt::{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def create_token(user: User, ttl_seconds: int = 86400) -> str:
    payload = {
        "uid": user.id,
        "username": user.username,
        "role": user.role,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    sig = hmac.new(APP_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def decode_token(token: str) -> dict:
    try:
        b64, sig = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid") from exc

    expected = hmac.new(APP_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signature token tidak valid")

    try:
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Payload token rusak") from exc

    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesi login telah berakhir")
    return payload


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autentikasi diperlukan")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    user = db.query(User).filter(User.id == payload.get("uid")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Pengguna tidak ditemukan")
    return user


def require_roles(*allowed_roles: str):
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Akses ditolak untuk peran '{current_user.role}'. Diperlukan: {', '.join(allowed_roles)}.",
            )
        return current_user

    return _dependency
