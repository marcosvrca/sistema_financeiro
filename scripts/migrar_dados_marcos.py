"""
Copia todos os dados do banco local (Docker Postgres) para o schema public
do usuário Marcos Vinicius no Postgres de produção (Railway).

Uso:
  set PROD_DATABASE_URL=postgresql://...
  python scripts/migrar_dados_marcos.py

Ou crie .env.prod na raiz do projeto com:
  PROD_DATABASE_URL=postgresql://...
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCAL_URL = os.environ.get(
    "LOCAL_DATABASE_URL",
    "postgresql://financeiro:financeiro@localhost:5433/financeiro",
)

# Ordem respeitando chaves estrangeiras (pais antes dos filhos).
TABLES = [
    "importacoes_extrato",
    "movimentos",
    "contas_fixas",
    "contas_fixas_mes",
    "lancamentos_manuais",
    "orcamento_mensal",
    "configuracao",
    "regras_categoria",
    "contas_bancarias",
    "tags",
    "metas_alocacao",
    "ativos_investimento",
    "cartoes_credito",
    "metas_financeiras",
    "projetos",
    "dividas",
    "movimentos_investimento",
    "lancamento_tags",
    "compras_cartao",
]


def _load_prod_url() -> str:
    url = os.environ.get("PROD_DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            return "postgresql://" + url[len("postgres://") :]
        return url
    env_file = ROOT / ".env.prod"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("PROD_DATABASE_URL="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val.startswith("postgres://"):
                    return "postgresql://" + val[len("postgres://") :]
                return val
    raise SystemExit(
        "Defina PROD_DATABASE_URL (variável de ambiente ou arquivo .env.prod na raiz)."
    )


def _counts(conn, schema: str = "public") -> dict[str, int]:
    out: dict[str, int] = {}
    for table in TABLES:
        row = conn.execute(f'SELECT COUNT(*) AS n FROM "{schema}"."{table}"').fetchone()
        out[table] = int(row["n"] if isinstance(row, dict) else row[0])
    return out


def _copy_table(src, dst, table: str) -> int:
    rows = src.execute(f'SELECT * FROM public."{table}"').fetchall()
    if not rows:
        dst.execute(f'TRUNCATE TABLE public."{table}" RESTART IDENTITY CASCADE')
        return 0

    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    dst.execute(f'TRUNCATE TABLE public."{table}" RESTART IDENTITY CASCADE')
    sql = f'INSERT INTO public."{table}" ({col_list}) VALUES ({placeholders})'
    for row in rows:
        dst.execute(sql, [row[c] for c in cols])

    seq_row = dst.execute(
        "SELECT pg_get_serial_sequence(%s, 'id') AS seq",
        (f"public.{table}",),
    ).fetchone()
    seq = seq_row["seq"] if seq_row and seq_row["seq"] else None
    if seq:
        dst.execute(
            f'SELECT setval(%s, COALESCE((SELECT MAX(id) FROM public."{table}"), 1), true)',
            (seq,),
        )
    return len(rows)


def _ensure_schema(prod_url: str) -> None:
    """Garante tabelas no destino (schema public / Marcos)."""
    os.environ["DATABASE_URL"] = prod_url
    from financeiro.context import current_user_id
    from financeiro.db import init_db

    token = current_user_id.set("marcos")
    try:
        init_db()
    finally:
        current_user_id.reset(token)


def main() -> None:
    import psycopg
    from psycopg.rows import dict_row

    prod_url = _load_prod_url()
    print("Origem :", LOCAL_URL.split("@")[-1])
    print("Destino:", prod_url.split("@")[-1])
    print("Schema destino: public (Marcos Vinicius)")

        with psycopg.connect(LOCAL_URL, row_factory=dict_row, connect_timeout=15) as src:
        before_src = _counts(src)
        total_src = sum(before_src.values())
        print(f"\nRegistros na origem: {total_src}")
        for t, n in before_src.items():
            if n:
                print(f"  {t}: {n}")

        if total_src == 0:
            print("Nada para migrar.")
            return

        _ensure_schema(prod_url)
        with psycopg.connect(prod_url, row_factory=dict_row, connect_timeout=30) as dst:
            dst.execute("SET session_replication_role = replica")
            try:
                copied = 0
                for table in TABLES:
                    n = _copy_table(src, dst, table)
                    if n:
                        print(f"  -> {table}: {n} registros")
                    copied += n
                dst.commit()
            finally:
                dst.execute("SET session_replication_role = origin")

            after_dst = _counts(dst)
            print(f"\nTotal migrado: {copied} registros")
            print("Destino após migração:")
            for t, n in after_dst.items():
                if n:
                    print(f"  {t}: {n}")

    print("\nMigração concluída.")


if __name__ == "__main__":
    main()
