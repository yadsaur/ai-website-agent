from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request, Response
from sqlalchemy.orm import Session

from backend.config import (
    AUTH_COOKIE_MAX_AGE_SECONDS,
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    AUTH_SECRET_KEY,
    GUEST_COOKIE_MAX_AGE_SECONDS,
    GUEST_COOKIE_NAME,
)
from backend.models import User

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390_000


@dataclass
class ViewerContext:
    user: User | None
    guest_session_id: str


def _sign_value(payload: dict[str, Any]) -> str:
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    signature = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded_payload}.{signature}"


def _unsign_value(raw_value: str) -> dict[str, Any] | None:
    try:
        encoded_payload, signature = raw_value.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload_json = base64.urlsafe_b64decode(encoded_payload.encode("ascii")).decode("utf-8")
        return json.loads(payload_json)
    except Exception:
        return None


def generate_guest_session_id() -> str:
    return "guest_" + secrets.token_urlsafe(24)


def get_guest_session_id(request: Request) -> str | None:
    value = request.cookies.get(GUEST_COOKIE_NAME)
    return value.strip() if value else None


def ensure_guest_session_id(request: Request, response: Response | None = None) -> str:
    guest_session_id = get_guest_session_id(request)
    if guest_session_id:
        return guest_session_id

    guest_session_id = generate_guest_session_id()
    if response is not None:
        response.set_cookie(
            GUEST_COOKIE_NAME,
            guest_session_id,
            max_age=GUEST_COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            secure=AUTH_COOKIE_SECURE,
            samesite=AUTH_COOKIE_SAMESITE,
            path="/",
        )
    return guest_session_id


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_value: str) -> bool:
    try:
        algorithm, iterations_str, salt_hex, digest_hex = stored_value.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        salt = bytes.fromhex(salt_hex)
        iterations = int(iterations_str)
        expected = bytes.fromhex(digest_hex)
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def create_auth_token(user: User) -> str:
    payload = {"user_id": user.id, "issued_at": int(datetime.utcnow().timestamp())}
    return _sign_value(payload)


def set_auth_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        create_auth_token(user),
        max_age=AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


def get_current_user(request: Request, db: Session) -> User | None:
    raw_cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not raw_cookie:
        return None

    payload = _unsign_value(raw_cookie)
    if not payload:
        return None

    user_id = str(payload.get("user_id", "")).strip()
    if not user_id:
        return None
    return db.get(User, user_id)


def build_viewer_context(request: Request, db: Session, response: Response | None = None) -> ViewerContext:
    user = get_current_user(request, db)
    guest_session_id = ensure_guest_session_id(request, response=response)
    return ViewerContext(user=user, guest_session_id=guest_session_id)

