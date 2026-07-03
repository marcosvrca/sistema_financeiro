from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from financeiro.config import SQLITE_PATH, user_postgres_schema, user_sqlite_path, using_postgres
from financeiro.context import current_user_id
from financeiro.permissions import TenantContextRequired


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


def _resolve_sqlite_path(db_path: Path | str | None, *, require_tenant: bool) -> Path:
    if db_path is not None:
        return Path(db_path)
    uid = current_user_id.get()
    if not uid:
        if require_tenant:
            raise TenantContextRequired(
                "Acesso ao banco sem usuário autenticado. Operação bloqueada por segurança."
            )
        return SQLITE_PATH
    return user_sqlite_path(uid)


def _apply_postgres_tenant(conn: Any, uid: str) -> None:
    """Isola o tenant no PostgreSQL sem fallback para o schema public de outro usuário."""
    schema = user_postgres_schema(uid)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.execute(f'SET search_path TO "{schema}"')


@contextmanager
def get_conn(
    db_path: Path | str | None = None,
    *,
    require_tenant: bool = True,
) -> Iterator[Any]:
    if using_postgres():
        import psycopg
        from psycopg.rows import dict_row

        from financeiro.config import database_url

        uid = current_user_id.get()
        if not uid:
            if require_tenant:
                raise TenantContextRequired(
                    "Acesso ao banco sem usuário autenticado. Operação bloqueada por segurança."
                )
        with psycopg.connect(database_url(), row_factory=dict_row) as conn:
            if uid:
                _apply_postgres_tenant(conn, uid)
            yield conn
            conn.commit()
    else:
        path = _resolve_sqlite_path(db_path, require_tenant=require_tenant)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
