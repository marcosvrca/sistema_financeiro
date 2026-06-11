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
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30


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


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        user_id = payload.get("sub")
        if not user_id or user_id not in USERS_BY_ID:
            return None
        return payload
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def user_from_token(token: str) -> dict[str, Any] | None:
    payload = decode_access_token(token)
    if not payload:
        return None
    base = USERS_BY_ID.get(payload["sub"])
    if not base:
        return None
    return {
        "id": base["id"],
        "nome": base["nome"],
        "email": base["email"],
    }
