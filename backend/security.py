import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(48)
SESSIONS: dict[str, dict] = {}


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        return hmac.compare_digest(raw[16:], hashlib.pbkdf2_hmac("sha256", password.encode(), raw[:16], 310_000))
    except Exception:
        return False


def new_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    SESSIONS[token] = {"user_id": user_id, "csrf": csrf, "created": time.time()}
    return token, csrf


def session_user(token: str | None):
    if not token:
        return None
    session = SESSIONS.get(token)
    if not session or time.time() - session["created"] > 43_200:
        SESSIONS.pop(token, None)
        return None
    return session


def check_csrf(token: str | None, supplied: str | None) -> bool:
    session = session_user(token)
    return bool(session and supplied and hmac.compare_digest(session["csrf"], supplied))
