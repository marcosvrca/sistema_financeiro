from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from financeiro.config import SQLITE_PATH, using_postgres


def q(sql: str) -> str:
    """Converte placeholders ? para %s no PostgreSQL."""
    if using_postgres():
        return sql.replace("?", "%s")
    return sql


def is_unique_violation(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        from psycopg import errors

        return isinstance(exc, errors.UniqueViolation)
    except ImportError:
        return False


@contextmanager
def get_conn(db_path: Path | str | None = None) -> Iterator[Any]:
    if using_postgres():
        import psycopg
        from psycopg.rows import dict_row

        from financeiro.config import database_url

        with psycopg.connect(database_url(), row_factory=dict_row) as conn:
            yield conn
            conn.commit()
    else:
        path = Path(db_path) if db_path else SQLITE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
