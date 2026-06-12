"""Aplica seed de dados do usuário Marcos (schema public) no Postgres."""

from __future__ import annotations

import os
import re
from pathlib import Path

from financeiro.config import using_postgres
from financeiro.context import current_user_id
from financeiro.conn import get_conn

ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = ROOT / "scripts" / "dados_marcos.sql"

TABLES = [
    "lancamento_tags",
    "contas_fixas_mes",
    "lancamentos_manuais",
    "movimentos",
    "compras_cartao",
    "movimentos_investimento",
    "contas_fixas",
    "metas_financeiras",
    "projetos",
    "dividas",
    "orcamento_mensal",
    "configuracao",
    "regras_categoria",
    "contas_bancarias",
    "tags",
    "metas_alocacao",
    "ativos_investimento",
    "cartoes_credito",
    "importacoes_extrato",
]


def _sql_statements(raw: str) -> list[str]:
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        if s.startswith("\\"):
            continue
        if s.upper().startswith("SET ") or s.upper().startswith("SELECT PG_CATALOG"):
            continue
        if s.startswith("ALTER TABLE"):
            continue
        lines.append(line)
    blob = "\n".join(lines)
    parts = re.split(r";\s*\n", blob)
    return [p.strip() + ";" for p in parts if p.strip() and not p.strip().startswith("--")]


def apply_marcos_seed_if_requested() -> int:
    if os.environ.get("APPLY_SEED_MARCO") != "1":
        return 0
    if not using_postgres():
        return 0
    if not SEED_FILE.is_file():
        return 0

    token = current_user_id.set("marcos")
    applied = 0
    try:
        with get_conn() as conn:
            conn.execute("SET session_replication_role = replica")
            for table in TABLES:
                conn.execute(f'TRUNCATE TABLE public."{table}" RESTART IDENTITY CASCADE')
            for stmt in _sql_statements(SEED_FILE.read_text(encoding="utf-8")):
                conn.execute(stmt)
                applied += 1
            for table in TABLES:
                has_id = conn.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s AND column_name = 'id'
                    """,
                    (table,),
                ).fetchone()
                if not has_id:
                    continue
                seq_row = conn.execute(
                    "SELECT pg_get_serial_sequence(%s, 'id') AS seq",
                    (f"public.{table}",),
                ).fetchone()
                seq = seq_row["seq"] if seq_row and seq_row["seq"] else None
                if seq:
                    conn.execute(
                        f'SELECT setval(%s, COALESCE((SELECT MAX(id) FROM public."{table}"), 1), true)',
                        (seq,),
                    )
            conn.execute("SET session_replication_role = origin")
    finally:
        current_user_id.reset(token)
    return applied
