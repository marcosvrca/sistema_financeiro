from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "data" / "financeiro.db"
USERS_DATA_DIR = ROOT / "data" / "users"


def user_sqlite_path(user_id: str) -> Path:
    """Marcos mantém o banco legado; demais usuários têm arquivo próprio."""
    if user_id == "marcos":
        return SQLITE_PATH
    return USERS_DATA_DIR / f"{user_id}.db"


def user_postgres_schema(user_id: str) -> str:
    """Marcos usa o schema public (dados legados); demais usuários têm schema dedicado."""
    if user_id == "marcos":
        return "public"
    return f"fin_{user_id}"


def database_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    # Railway/Heroku usam postgres://; psycopg aceita ambos, mas normalizamos por segurança.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def using_postgres() -> bool:
    url = database_url()
    return bool(url and url.startswith("postgres"))
