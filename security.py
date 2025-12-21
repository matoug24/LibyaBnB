# security.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from passlib.context import CryptContext

# If you also use JWT anywhere in your codebase, keep these imports.
# If you don't use JWT, leaving them here is harmless.
from jose import jwt

# ---------------------------
# Password hashing (bcrypt)
# ---------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.
    """
    return pwd_context.hash(password)

hash_password = get_password_hash

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    """
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------
# Optional JWT helpers
# (keep only if you need JWT)
# ---------------------------
# IMPORTANT: change these in production
SECRET_KEY = "CHANGE_ME_TO_A_RANDOM_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token with an expiry.
    """
    to_encode = dict(data)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
