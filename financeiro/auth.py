from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

AUTH_SECRET = os.environ.get("AUTH_SECRET", "altere-em-producao-financas-pro")
SESSION_MAX_SECONDS = 60 * 60 * 12
INACTIVITY_TIMEOUT_SECONDS = 60 * 15


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"{AUTH_SECRET}:pw:{password}".encode()).hexdigest()


USERS_BY_EMAIL: dict[str, dict[str, Any]] = {
    "marcosviniciusrdca2@gmail.com": {
        "id": "marcos",
        "nome": "Marcos Vinicius",
        "password_hash": _hash_password("250922"),
    },
    "vitoriasrochapereira@gmail.com": {
        "id": "vitoria",
        "nome": "Vitória Rocha Pereira",
        "password_hash": _hash_password("250922"),
    },
}

USERS_BY_ID = {u["id"]: {**u, "email": email} for email, u in USERS_BY_EMAIL.items()}


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    user = USERS_BY_EMAIL.get(email.strip().lower())
    if not user:
        return None
    if not secrets.compare_digest(user["password_hash"], _hash_password(password)):
        return None
    return user


def create_access_token(
    user_id: str,
    email: str,
    *,
    issued_at: int | None = None,
    last_activity: int | None = None,
) -> str:
    now = int(time.time())
    iat = issued_at if issued_at is not None else now
    lat = last_activity if last_activity is not None else now
    payload = {
        "sub": user_id,
        "email": email,
        "iat": iat,
        "lat": lat,
        "exp": iat + SESSION_MAX_SECONDS,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _session_times(payload: dict[str, Any]) -> tuple[int, int, int]:
    now = int(time.time())
    iat = int(payload.get("iat", now))
    lat = int(payload.get("lat", iat))
    return now, iat, lat


def _session_valid(payload: dict[str, Any]) -> bool:
    now, iat, lat = _session_times(payload)
    if int(payload.get("exp", 0)) < now:
        return False
    if now - iat > SESSION_MAX_SECONDS:
        return False
    if now - lat > INACTIVITY_TIMEOUT_SECONDS:
        return False
    return True


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        user_id = payload.get("sub")
        if not user_id or user_id not in USERS_BY_ID:
            return None
        if not _session_valid(payload):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def refresh_token_activity(payload: dict[str, Any]) -> str | None:
    if not _session_valid(payload):
        return None
    now = int(time.time())
    iat = int(payload["iat"])
    if now - iat > SESSION_MAX_SECONDS:
        return None
    return create_access_token(
        payload["sub"],
        payload["email"],
        issued_at=iat,
        last_activity=now,
    )


def validate_token(token: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    payload = decode_access_token(token)
    if not payload:
        return None
    base = USERS_BY_ID[payload["sub"]]
    user = {
        "id": base["id"],
        "nome": base["nome"],
        "email": base["email"],
    }
    return payload, user


def user_from_token(token: str) -> dict[str, Any] | None:
    result = validate_token(token)
    if not result:
        return None
    return result[1]
