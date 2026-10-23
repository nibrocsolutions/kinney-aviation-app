"""Password hashing and signed-in sessions.

Passwords are stored with scrypt. The cookie carries a random token; only its
SHA-256 hash is kept in the database. Mutating requests must send
X-Kinney-Request so a cross-site form cannot use the cookie.
"""

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AuthSession, User

COOKIE = "kinney_session"
HEADER = "x-kinney-request"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_ATTEMPT_LIMIT = 10
_ATTEMPT_WINDOW = 15 * 60
_attempts: dict[str, list[float]] = {}
_dummy_hash: str | None = None

USERNAME = re.compile(r"[a-z][a-z0-9._-]{2,31}")
CLOCK = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


@dataclass(frozen=True)
class Principal:
    id: int
    username: str
    display_name: str
    role: str


def reset_login_limits() -> None:
    _attempts.clear()


def normalize_username(value: str) -> str:
    text = value.strip().lower()
    if USERNAME.fullmatch(text) is None:
        raise ValueError("Use 3-32 characters: a letter first, then letters, numbers, dots, or hyphens.")
    return text


def normalize_display_name(value: str) -> str:
    text = value.strip()
    if not text or len(text) > 80:
        raise ValueError("Enter a name up to 80 characters.")
    return text


def normalize_password(value: str) -> str:
    if len(value) < 10 or len(value) > 200:
        raise ValueError("Use a password of at least 10 characters.")
    return value


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n_text, r_text, p_text, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        n_value = int(n_text)
        if n_value < 2**12 or n_value > 2**15:
            return False
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=n_value,
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def _dummy() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("kinney-aviation-dummy-secret")
    return _dummy_hash


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def login_blocked(request: Request) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _attempts.get(_client_key(request), []) if now - stamp < _ATTEMPT_WINDOW]
    _attempts[_client_key(request)] = recent
    return len(recent) >= _ATTEMPT_LIMIT


def record_login_failure(request: Request) -> None:
    _attempts.setdefault(_client_key(request), []).append(time.monotonic())


def clear_login_failures(request: Request) -> None:
    _attempts.pop(_client_key(request), None)


def authenticate(db: Session, username: str, password: str) -> User | None:
    try:
        normalized = normalize_username(username)
    except ValueError:
        normalized = ""
    user = db.scalar(select(User).where(User.username == normalized)) if normalized else None
    stored = user.password_hash if user is not None else _dummy()
    matches = verify_password(password, stored)
    if user is None or not matches or not user.active:
        return None
    return user


def start_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=_now() + timedelta(days=settings.session_days),
        )
    )
    return token


def revoke_sessions(db: Session, user_id: int) -> None:
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user_id))
    for row in rows:
        db.delete(row)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE,
        value=token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.session_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_secure,
    )


def principal_from_token(token: str | None) -> Principal | None:
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    db = SessionLocal()
    try:
        row = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest))
        if row is None:
            return None
        if row.expires_at <= _now():
            db.delete(row)
            db.commit()
            return None
        user = db.get(User, row.user_id)
        if user is None or not user.active:
            return None
        return Principal(user.id, user.username, user.display_name, user.role)
    finally:
        db.close()


def reject_missing_header(request: Request) -> None:
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.headers.get(HEADER) != "1":
        raise HTTPException(status_code=403, detail="This request was rejected.")


def require_user(request: Request) -> Principal:
    reject_missing_header(request)
    principal = principal_from_token(request.cookies.get(COOKIE))
    if principal is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    request.state.user = principal
    return principal


def require_admin(request: Request) -> Principal:
    principal = require_user(request)
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return principal
