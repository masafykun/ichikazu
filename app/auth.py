import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-ichikazu-dev")
JWT_ALG = "HS256"
TOKEN_DAYS = 30


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


def make_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def new_api_key() -> str:
    return "ick_" + secrets.token_urlsafe(24)


def _user_from_token(token: str, db: Session):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = int(payload.get("sub"))
    except Exception:
        return None
    return db.query(User).filter(User.id == uid).first()


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    return auth[7:].strip() if auth.startswith("Bearer ") else ""


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    user = _user_from_token(token, db) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)):
    token = _bearer(request)
    return _user_from_token(token, db) if token else None


def is_pro(user) -> bool:
    return bool(user) and getattr(user, "plan", "free") == "pro"
