from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from financeiro.config import SQLITE_PATH, user_postgres_schema, user_sqlite_path, using_postgres
from financeiro.context import current_user_id


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
            uid = current_user_id.get()
            if uid:
                schema = user_postgres_schema(uid)
                conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                conn.execute(f'SET search_path TO "{schema}", public')
            yield conn
            conn.commit()
    else:
        if db_path is not None:
            path = Path(db_path)
        elif current_user_id.get():
            path = user_sqlite_path(current_user_id.get())
        else:
            path = SQLITE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
