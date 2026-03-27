from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key_b64 = (os.environ.get("ENCRYPTION_KEY_BASE64") or "").strip()
    if not key_b64:
        raise RuntimeError("ENCRYPTION_KEY_BASE64 is required")

    raw = base64.b64decode(key_b64)
    if len(raw) != 32:
        raise RuntimeError("ENCRYPTION_KEY_BASE64 must decode to 32 bytes")

    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_to_b64(plaintext: str) -> str:
    if plaintext is None:
        return ""
    p = plaintext.strip()
    if not p:
        return ""
    f = _get_fernet()
    return f.encrypt(p.encode("utf-8")).decode("utf-8")


def decrypt_from_b64(ciphertext_b64: str) -> str:
    c = (ciphertext_b64 or "").strip()
    if not c:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(c.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""
