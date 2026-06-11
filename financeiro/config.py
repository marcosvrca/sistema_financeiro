from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "data" / "financeiro.db"


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
