from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import jwt


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def sign_access_token(*, jwt_secret: str, sub: str, role: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def sign_refresh_token(*, jwt_secret: str, sub: str, role: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def verify_token(*, jwt_secret: str, token: str) -> dict:
    return jwt.decode(token, jwt_secret, algorithms=["HS256"])
