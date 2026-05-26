from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "data" / "financeiro.db"


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def using_postgres() -> bool:
    url = database_url()
    return bool(url and url.startswith("postgres"))
