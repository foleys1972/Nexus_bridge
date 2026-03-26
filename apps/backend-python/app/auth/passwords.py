from __future__ import annotations

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _bcrypt_safe_secret(password: str) -> str:
    b = password.encode("utf-8")
    if len(b) <= 72:
        return password
    return b[:72].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_safe_secret(password))


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(_bcrypt_safe_secret(password), password_hash)
