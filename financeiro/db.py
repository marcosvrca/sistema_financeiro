from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from financeiro.config import SQLITE_PATH, using_postgres
from financeiro.conn import get_conn, is_unique_violation, q
from financeiro.metrics import Indicadores, ResumoMensal
from financeiro.parser import LinhaExtrato, categoria_por_historico
from financeiro.schema import SCHEMA_POSTGRES, SCHEMA_SQLITE


def _default_db() -> Path:
    return SQLITE_PATH


def _sum_credito() -> str:
    return "COALESCE(SUM(credito), 0)" if using_postgres() else "COALESCE(SUM(CAST(credito AS REAL)), 0)"


def _sum_debito() -> str:
    return "COALESCE(SUM(debito), 0)" if using_postgres() else "COALESCE(SUM(CAST(debito AS REAL)), 0)"


def _mes_expr(alias: str = "data") -> str:
    if using_postgres():
        return f"to_char({alias}, 'YYYY-MM')"
    return f"substr({alias}, 1, 7)"


def _hash_linha(r: LinhaExtrato) -> str:
    from hashlib import sha256

    s = f"{r.data.isoformat()}|{r.historico}|{r.docto}|{r.credito}|{r.debito}|{r.saldo}"
    return sha256(s.encode("utf-8")).hexdigest()


def _d(val: Any) -> Decimal:
    if val is None:
        return Decimal(0)
    return Decimal(str(val))


def _row_val(row: Any, key: str) -> Any:
    if hasattr(row, "keys"):
        return row[key]
    return row[key]


def _migrate(conn: Any) -> None:
    """Aplica alterações em bancos já existentes."""
    if using_postgres():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS importacoes_extrato (
                id SERIAL PRIMARY KEY,
                criado_em TIMESTAMPTZ DEFAULT NOW(),
                qtd_lidas INTEGER NOT NULL DEFAULT 0,
                qtd_inseridas INTEGER NOT NULL DEFAULT 0,
                qtd_duplicadas INTEGER NOT NULL DEFAULT 0,
                data_min DATE,
                data_max DATE
            )
            """
        )
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'movimentos' AND column_name = 'importacao_id'
            """
        ).fetchone()
        tem_mov = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'movimentos'
            """
        ).fetchone()
        if tem_mov:
            if not row:
                conn.execute(
                    "ALTER TABLE movimentos ADD COLUMN importacao_id INTEGER REFERENCES importacoes_extrato(id)"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_movimentos_importacao ON movimentos(importacao_id)"
            )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS importacoes_extrato (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criado_em TEXT DEFAULT (datetime('now')),
                qtd_lidas INTEGER NOT NULL DEFAULT 0,
                qtd_inseridas INTEGER NOT NULL DEFAULT 0,
                qtd_duplicadas INTEGER NOT NULL DEFAULT 0,
                data_min TEXT,
                data_max TEXT
            )
            """
        )
        tem_mov = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movimentos'"
        ).fetchone()
        if tem_mov:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(movimentos)").fetchall()}
            if "importacao_id" not in cols:
                conn.execute(
                    "ALTER TABLE movimentos ADD COLUMN importacao_id INTEGER REFERENCES importacoes_extrato(id)"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_movimentos_importacao ON movimentos(importacao_id)"
            )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracao (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
        """
    )


def _skip_schema_stmt(stmt: str) -> bool:
    """Índice em importacao_id só após migração (bancos antigos não têm a coluna)."""
    return "idx_movimentos_importacao" in stmt


def init_db(db_path: Path | str | None = None) -> None:
    schema = SCHEMA_POSTGRES if using_postgres() else SCHEMA_SQLITE
    with get_conn(db_path) as conn:
        if using_postgres():
            for stmt in schema.split(";"):
                s = stmt.strip()
                if s and not _skip_schema_stmt(s):
                    conn.execute(s)
        else:
            parts = [p.strip() for p in schema.split(";") if p.strip() and not _skip_schema_stmt(p)]
            for s in parts:
                conn.execute(s)
        _migrate(conn)


def inserir_movimentos(
    db_path: Path | str | None = None,
    linhas: list[LinhaExtrato] | None = None,
    categorizar: Callable[[str], str] | None = None,
) -> tuple[int, int, int | None]:
    if linhas is None:
        linhas = []
    cat_fn = categorizar or categoria_por_historico
    inseridos = 0
    ignorados = 0
    if not linhas:
        return 0, 0, None

    datas = [r.data for r in linhas]
    data_min, data_max = min(datas), max(datas)

    if using_postgres():
        insert_sql = """
            INSERT INTO movimentos (data, historico, docto, credito, debito, saldo, categoria, hash_linha, importacao_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash_linha) DO NOTHING
        """
    else:
        insert_sql = """
            INSERT OR IGNORE INTO movimentos (data, historico, docto, credito, debito, saldo, categoria, hash_linha, importacao_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    importacao_id: int | None = None
    with get_conn(db_path) as conn:
        cur_imp = conn.execute(
            q(
                """
            INSERT INTO importacoes_extrato (qtd_lidas, qtd_inseridas, qtd_duplicadas, data_min, data_max)
            VALUES (?, 0, 0, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO importacoes_extrato (qtd_lidas, qtd_inseridas, qtd_duplicadas, data_min, data_max)
            VALUES (?, 0, 0, ?, ?)
            """
            ),
            (len(linhas), data_min.isoformat(), data_max.isoformat()),
        )
        if using_postgres():
            importacao_id = int(cur_imp.fetchone()["id"])
        else:
            importacao_id = int(cur_imp.lastrowid)

        for r in linhas:
            h = _hash_linha(r)
            cred = r.credito if using_postgres() else (str(r.credito) if r.credito is not None else None)
            deb = r.debito if using_postgres() else (str(r.debito) if r.debito is not None else None)
            sal = r.saldo if using_postgres() else (str(r.saldo) if r.saldo is not None else None)
            params = (
                r.data.isoformat(),
                r.historico,
                r.docto,
                cred,
                deb,
                sal,
                cat_fn(r.historico),
                h,
                importacao_id,
            )
            cur = conn.execute(insert_sql if using_postgres() else q(insert_sql), params)
            if cur.rowcount and cur.rowcount > 0:
                inseridos += 1
            else:
                ignorados += 1

        conn.execute(
            q(
                """
            UPDATE importacoes_extrato
            SET qtd_inseridas = ?, qtd_duplicadas = ?
            WHERE id = ?
            """
            ),
            (inseridos, ignorados, importacao_id),
        )
    return inseridos, ignorados, importacao_id


def listar_importacoes_extrato(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = list(
            conn.execute(
                q(
                    """
                SELECT i.id, i.criado_em, i.qtd_lidas, i.qtd_inseridas, i.qtd_duplicadas,
                       i.data_min, i.data_max,
                       (SELECT COUNT(*) FROM movimentos m WHERE m.importacao_id = i.id) AS qtd_movimentos
                FROM importacoes_extrato i
                ORDER BY i.id DESC
                """
                )
            ).fetchall()
        )
        legado = conn.execute(
            q("SELECT COUNT(*) AS n FROM movimentos WHERE importacao_id IS NULL")
        ).fetchone()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "criado_em": str(r["criado_em"])[:19] if r["criado_em"] else None,
                "qtd_lidas": r["qtd_lidas"],
                "qtd_inseridas": r["qtd_inseridas"],
                "qtd_duplicadas": r["qtd_duplicadas"],
                "data_min": str(r["data_min"])[:10] if r["data_min"] else None,
                "data_max": str(r["data_max"])[:10] if r["data_max"] else None,
                "qtd_movimentos": r["qtd_movimentos"],
                "legado": False,
            }
        )
    n_legado = int(legado["n"]) if legado else 0
    if n_legado > 0:
        with get_conn(db_path) as conn:
            rng = conn.execute(
                q(
                    """
                SELECT MIN(data) AS mi, MAX(data) AS ma
                FROM movimentos WHERE importacao_id IS NULL
                """
                )
            ).fetchone()
        out.append(
            {
                "id": 0,
                "criado_em": None,
                "qtd_lidas": n_legado,
                "qtd_inseridas": n_legado,
                "qtd_duplicadas": 0,
                "data_min": str(rng["mi"])[:10] if rng and rng["mi"] else None,
                "data_max": str(rng["ma"])[:10] if rng and rng["ma"] else None,
                "qtd_movimentos": n_legado,
                "legado": True,
            }
        )
    return out


def excluir_importacao_extrato(db_path: Path | str | None = None, importacao_id: int = 0) -> int:
    with get_conn(db_path) as conn:
        if importacao_id == 0:
            cur = conn.execute(q("DELETE FROM movimentos WHERE importacao_id IS NULL"))
        else:
            cur = conn.execute(
                q("DELETE FROM movimentos WHERE importacao_id = ?"), (importacao_id,)
            )
            conn.execute(q("DELETE FROM importacoes_extrato WHERE id = ?"), (importacao_id,))
        return cur.rowcount or 0


def recategorizar_movimentos(db_path: Path | str | None = None) -> int:
    """Reaplica categoria_por_historico em todos os movimentos do extrato. Retorna quantidade atualizada."""
    from financeiro.parser import categoria_por_historico

    atualizados = 0
    with get_conn(db_path) as conn:
        rows = conn.execute(q("SELECT id, historico FROM movimentos")).fetchall()
        for row in rows:
            cat = categoria_por_historico(row["historico"])
            cur = conn.execute(
                q("UPDATE movimentos SET categoria = ? WHERE id = ?"),
                (cat, row["id"]),
            )
            if cur.rowcount and cur.rowcount > 0:
                atualizados += cur.rowcount
    return atualizados


def listar_contas_fixas(db_path: Path | str | None = None, apenas_ativas: bool = True) -> list[Any]:
    sql = "SELECT * FROM contas_fixas"
    if apenas_ativas:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY dia_vencimento, nome"
    with get_conn(db_path) as conn:
        return list(conn.execute(sql).fetchall())


def salvar_conta_fixa(
    db_path: Path | str | None = None,
    nome: str = "",
    valor: Decimal = Decimal(0),
    categoria: str = "Contas fixas",
    dia_vencimento: int | None = None,
    historico_contem: str | None = None,
    observacao: str | None = None,
    conta_id: int | None = None,
) -> None:
    v = valor if using_postgres() else str(valor)
    with get_conn(db_path) as conn:
        if conta_id:
            conn.execute(
                q(
                    """
                UPDATE contas_fixas
                SET nome=?, valor=?, dia_vencimento=?, categoria=?, historico_contem=?, observacao=?
                WHERE id=?
                """
                ),
                (nome, v, dia_vencimento, categoria, historico_contem, observacao, conta_id),
            )
        else:
            conn.execute(
                q(
                    """
                INSERT INTO contas_fixas (nome, valor, dia_vencimento, categoria, historico_contem, observacao)
                VALUES (?, ?, ?, ?, ?, ?)
                """
                ),
                (nome, v, dia_vencimento, categoria, historico_contem, observacao),
            )


def atualizar_conta_fixa(
    db_path: Path | str | None = None,
    conta_id: int = 0,
    nome: str = "",
    valor: Decimal = Decimal(0),
    categoria: str = "Contas fixas",
    dia_vencimento: int | None = None,
    historico_contem: str | None = None,
    observacao: str | None = None,
) -> bool:
    v = valor if using_postgres() else str(valor)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            q(
                """
            UPDATE contas_fixas
            SET nome = ?, valor = ?, dia_vencimento = ?, categoria = ?, historico_contem = ?, observacao = ?
            WHERE id = ? AND ativo = 1
            """
            ),
            (nome, v, dia_vencimento, categoria, historico_contem, observacao, conta_id),
        )
        return bool(cur.rowcount)


def desativar_conta_fixa(db_path: Path | str | None = None, conta_id: int = 0) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("UPDATE contas_fixas SET ativo = 0 WHERE id = ?"), (conta_id,))


def inserir_lancamento_manual(
    db_path: Path | str | None = None,
    data_mov: date | None = None,
    descricao: str = "",
    valor: Decimal = Decimal(0),
    tipo: str = "saida",
    categoria: str = "Outros",
) -> int:
    if tipo not in ("entrada", "saida"):
        raise ValueError("tipo deve ser 'entrada' ou 'saida'")
    if data_mov is None:
        data_mov = date.today()
    v = valor if using_postgres() else str(valor)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            q(
                """
            INSERT INTO lancamentos_manuais (data, descricao, valor, tipo, categoria)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO lancamentos_manuais (data, descricao, valor, tipo, categoria)
            VALUES (?, ?, ?, ?, ?)
            """
            ),
            (data_mov.isoformat(), descricao, v, tipo, categoria),
        )
        if using_postgres():
            row = cur.fetchone()
            return int(row["id"])
        return int(cur.lastrowid)


def listar_lancamentos_manuais(
    data_ini: date | None = None,
    data_fim: date | None = None,
    db_path: Path | str | None = None,
) -> list[Any]:
    sql = "SELECT * FROM lancamentos_manuais WHERE 1=1"
    params: list[Any] = []
    if data_ini:
        sql += " AND data >= ?"
        params.append(data_ini.isoformat())
    if data_fim:
        sql += " AND data <= ?"
        params.append(data_fim.isoformat())
    sql += " ORDER BY data DESC, id DESC"
    with get_conn(db_path) as conn:
        return list(conn.execute(q(sql), params).fetchall())


def atualizar_lancamento_manual(
    db_path: Path | str | None = None,
    lanc_id: int = 0,
    data_mov: date | None = None,
    descricao: str = "",
    valor: Decimal = Decimal(0),
    tipo: str = "saida",
    categoria: str = "Outros",
) -> bool:
    if tipo not in ("entrada", "saida"):
        raise ValueError("tipo deve ser 'entrada' ou 'saida'")
    if data_mov is None:
        data_mov = date.today()
    v = valor if using_postgres() else str(valor)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            q(
                """
            UPDATE lancamentos_manuais
            SET data = ?, descricao = ?, valor = ?, tipo = ?, categoria = ?
            WHERE id = ?
            """
            ),
            (data_mov.isoformat(), descricao, v, tipo, categoria, lanc_id),
        )
        return bool(cur.rowcount)


def excluir_lancamento_manual(db_path: Path | str | None = None, lanc_id: int = 0) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("DELETE FROM lancamentos_manuais WHERE id = ?"), (lanc_id,))


def salvar_orcamento(
    db_path: Path | str | None = None, mes: str = "", categoria: str = "", limite: Decimal = Decimal(0)
) -> None:
    lim = limite if using_postgres() else str(limite)
    with get_conn(db_path) as conn:
        conn.execute(
            q(
                """
            INSERT INTO orcamento_mensal (mes, categoria, limite)
            VALUES (?, ?, ?)
            ON CONFLICT(mes, categoria) DO UPDATE SET limite = excluded.limite
            """
            ),
            (mes, categoria, lim),
        )


def listar_orcamento_mes(db_path: Path | str | None = None, mes: str = "") -> list[Any]:
    with get_conn(db_path) as conn:
        return list(
            conn.execute(
                q("SELECT categoria, limite FROM orcamento_mensal WHERE mes = ? ORDER BY categoria"),
                (mes,),
            ).fetchall()
        )


def _padroes_fixas(db_path: Path | str | None) -> list[tuple[str | None, Decimal]]:
    rows = listar_contas_fixas(db_path, apenas_ativas=True)
    return [(r["historico_contem"], _d(r["valor"])) for r in rows]


def _eh_gasto_fixo(historico: str, debito: Decimal, padroes: list[tuple[str | None, Decimal]]) -> bool:
    h_up = historico.upper()
    for texto, valor_ref in padroes:
        if texto and texto.upper() in h_up:
            return True
        if valor_ref > 0 and debito == valor_ref:
            return True
    return False


def resumo_por_categoria(
    data_ini: date | None = None,
    data_fim: date | None = None,
    db_path: Path | str | None = None,
    incluir_manuais: bool = True,
) -> list[tuple[str, Decimal, Decimal]]:
    sql = f"""
        SELECT categoria, {_sum_credito()} AS c, {_sum_debito()} AS d
        FROM movimentos WHERE 1=1
    """
    params: list[Any] = []
    if data_ini:
        sql += " AND data >= ?"
        params.append(data_ini.isoformat())
    if data_fim:
        sql += " AND data <= ?"
        params.append(data_fim.isoformat())
    sql += " GROUP BY categoria"
    agg: dict[str, tuple[Decimal, Decimal]] = {}
    with get_conn(db_path) as conn:
        for row in conn.execute(q(sql), params).fetchall():
            agg[row["categoria"]] = (_d(row["c"]), _d(row["d"]))

    if incluir_manuais:
        sql_m = "SELECT categoria, tipo, valor FROM lancamentos_manuais WHERE 1=1"
        p_m: list[Any] = []
        if data_ini:
            sql_m += " AND data >= ?"
            p_m.append(data_ini.isoformat())
        if data_fim:
            sql_m += " AND data <= ?"
            p_m.append(data_fim.isoformat())
        with get_conn(db_path) as conn:
            for row in conn.execute(q(sql_m), p_m).fetchall():
                cat = row["categoria"]
                c, d = agg.get(cat, (Decimal(0), Decimal(0)))
                val = _d(row["valor"])
                if row["tipo"] == "entrada":
                    c += val
                else:
                    d += val
                agg[cat] = (c, d)

    return [
        (cat, c, d)
        for cat, (c, d) in sorted(agg.items(), key=lambda x: x[1][1], reverse=True)
    ]


def resumo_mensal(
    data_ini: date | None = None,
    data_fim: date | None = None,
    db_path: Path | str | None = None,
) -> list[ResumoMensal]:
    mes_col = _mes_expr("data")
    sql = f"""
        SELECT {mes_col} AS mes, {_sum_credito()} AS c, {_sum_debito()} AS d
        FROM movimentos WHERE 1=1
    """
    params: list[Any] = []
    if data_ini:
        sql += " AND data >= ?"
        params.append(data_ini.isoformat())
    if data_fim:
        sql += " AND data <= ?"
        params.append(data_fim.isoformat())
    sql += f" GROUP BY {mes_col}"

    buckets: dict[str, tuple[Decimal, Decimal]] = {}
    with get_conn(db_path) as conn:
        for row in conn.execute(q(sql), params).fetchall():
            buckets[str(row["mes"])] = (_d(row["c"]), _d(row["d"]))

    sql_m = f"SELECT {mes_col} AS mes, tipo, valor FROM lancamentos_manuais WHERE 1=1"
    p_m: list[Any] = []
    if data_ini:
        sql_m += " AND data >= ?"
        p_m.append(data_ini.isoformat())
    if data_fim:
        sql_m += " AND data <= ?"
        p_m.append(data_fim.isoformat())
    with get_conn(db_path) as conn:
        for row in conn.execute(q(sql_m), p_m).fetchall():
            mes = str(row["mes"])
            c, d = buckets.get(mes, (Decimal(0), Decimal(0)))
            val = _d(row["valor"])
            if row["tipo"] == "entrada":
                c += val
            else:
                d += val
            buckets[mes] = (c, d)

    return [
        ResumoMensal(mes=m, creditos=c, debitos=d, liquido=c - d)
        for m, (c, d) in sorted(buckets.items())
    ]


def ultimo_saldo(db_path: Path | str | None = None) -> Decimal | None:
    cond = "saldo IS NOT NULL" if using_postgres() else "saldo IS NOT NULL AND saldo != ''"
    with get_conn(db_path) as conn:
        row = conn.execute(
            q(
                f"""
            SELECT saldo FROM movimentos
            WHERE {cond}
            ORDER BY data DESC, id DESC
            LIMIT 1
            """
            )
        ).fetchone()
    if not row or row["saldo"] is None:
        return None
    return _d(row["saldo"])


def calcular_indicadores(
    data_ini: date | None = None,
    data_fim: date | None = None,
    db_path: Path | str | None = None,
) -> Indicadores:
    q_mov = "SELECT data, historico, credito, debito FROM movimentos WHERE 1=1"
    params: list[Any] = []
    if data_ini:
        q_mov += " AND data >= ?"
        params.append(data_ini.isoformat())
    if data_fim:
        q_mov += " AND data <= ?"
        params.append(data_fim.isoformat())

    with get_conn(db_path) as conn:
        movs = list(conn.execute(q(q_mov), params).fetchall())
        q_man = "SELECT tipo, valor FROM lancamentos_manuais WHERE 1=1"
        p_man: list[Any] = []
        if data_ini:
            q_man += " AND data >= ?"
            p_man.append(data_ini.isoformat())
        if data_fim:
            q_man += " AND data <= ?"
            p_man.append(data_fim.isoformat())
        mans = list(conn.execute(q(q_man), p_man).fetchall())

    padroes = _padroes_fixas(db_path)
    total_c = Decimal(0)
    total_d = Decimal(0)
    total_fixas = Decimal(0)
    total_variaveis = Decimal(0)
    maior_deb: Decimal | None = None
    qtd_deb = 0
    soma_deb = Decimal(0)
    dias_gasto: set[str] = set()

    for m in movs:
        cred = _d(m["credito"]) if m["credito"] else Decimal(0)
        deb = _d(m["debito"]) if m["debito"] else Decimal(0)
        total_c += cred
        total_d += deb
        data_s = str(m["data"])[:10]
        if deb > 0:
            qtd_deb += 1
            soma_deb += deb
            dias_gasto.add(data_s)
            if maior_deb is None or deb > maior_deb:
                maior_deb = deb
            if _eh_gasto_fixo(m["historico"], deb, padroes):
                total_fixas += deb
            else:
                total_variaveis += deb

    man_ent = sum((_d(r["valor"]) for r in mans if r["tipo"] == "entrada"), Decimal(0))
    man_sai = sum((_d(r["valor"]) for r in mans if r["tipo"] == "saida"), Decimal(0))
    total_c += man_ent
    total_d += man_sai
    total_variaveis += man_sai

    ticket = (soma_deb / qtd_deb) if qtd_deb else None
    ndias = len(dias_gasto) or None
    media_dia = (total_d / ndias) if ndias else None
    base_class = total_fixas + total_variaveis
    pct_f = (total_fixas / base_class * 100) if base_class else None
    pct_v = (total_variaveis / base_class * 100) if base_class else None

    return Indicadores(
        total_creditos=total_c,
        total_debitos=total_d,
        saldo_liquido=total_c - total_d,
        qtd_movimentos=len(movs) + len(mans),
        qtd_debitos=qtd_deb,
        maior_debito=maior_deb,
        ticket_medio_debito=ticket,
        media_diaria_gastos=media_dia,
        pct_fixas=pct_f,
        pct_variaveis=pct_v,
        total_fixas=total_fixas,
        total_variaveis=total_variaveis,
        total_manuais_entrada=man_ent,
        total_manuais_saida=man_sai,
    )


def total_contas_fixas_previsto(db_path: Path | str | None = None) -> Decimal:
    rows = listar_contas_fixas(db_path, apenas_ativas=True)
    return sum((_d(r["valor"]) for r in rows), Decimal(0))


CHAVE_SALARIO_MENSAL = "salario_mensal"


def obter_config(chave: str, db_path: Path | str | None = None) -> str | None:
    with get_conn(db_path) as conn:
        row = conn.execute(q("SELECT valor FROM configuracao WHERE chave = ?"), (chave,)).fetchone()
    return row["valor"] if row else None


def salvar_config(chave: str, valor: str, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            q(
                """
            INSERT INTO configuracao (chave, valor) VALUES (?, ?)
            ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
            """
            ),
            (chave, valor),
        )


def obter_salario_mensal(db_path: Path | str | None = None) -> Decimal | None:
    raw = obter_config(CHAVE_SALARIO_MENSAL, db_path)
    if raw is None or raw == "":
        return None
    return _d(raw)


def salvar_salario_mensal(valor: Decimal, db_path: Path | str | None = None) -> None:
    salvar_config(CHAVE_SALARIO_MENSAL, str(valor), db_path)


def resumo_salario_contas_fixas(db_path: Path | str | None = None) -> dict[str, Any]:
    salario = obter_salario_mensal(db_path)
    total_fixas = total_contas_fixas_previsto(db_path)
    saldo: Decimal | None = None
    sobra: Decimal | None = None
    falta: Decimal | None = None
    pct_comprometido: Decimal | None = None
    if salario is not None:
        saldo = salario - total_fixas
        if saldo >= 0:
            sobra = saldo
        else:
            falta = abs(saldo)
        if salario > 0:
            pct_comprometido = (total_fixas / salario * 100).quantize(Decimal("0.01"))
    return {
        "salario_mensal": salario,
        "total_contas_fixas": total_fixas,
        "saldo": saldo,
        "sobra": sobra,
        "falta": falta,
        "pct_comprometido": pct_comprometido,
        "qtd_contas_ativas": len(listar_contas_fixas(db_path, apenas_ativas=True)),
    }


def listar_movimentos(
    data_ini: date | None = None,
    data_fim: date | None = None,
    categoria: str | None = None,
    db_path: Path | str | None = None,
) -> list[Any]:
    sql = "SELECT id, data, historico, docto, credito, debito, saldo, categoria FROM movimentos WHERE 1=1"
    params: list[Any] = []
    if data_ini:
        sql += " AND data >= ?"
        params.append(data_ini.isoformat())
    if data_fim:
        sql += " AND data <= ?"
        params.append(data_fim.isoformat())
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)
    sql += " ORDER BY data DESC, id DESC"
    with get_conn(db_path) as conn:
        return list(conn.execute(q(sql), params).fetchall())


def listar_consolidado(
    data_ini: date | None = None,
    data_fim: date | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Extrato + lançamentos manuais em uma lista ordenada por data."""
    itens: list[dict[str, Any]] = []
    for r in listar_movimentos(data_ini, data_fim, db_path=db_path):
        itens.append(
            {
                "id": f"e-{r['id']}",
                "data": str(r["data"])[:10],
                "descricao": r["historico"],
                "credito": _d(r["credito"]) if r["credito"] else None,
                "debito": _d(r["debito"]) if r["debito"] else None,
                "saldo": _d(r["saldo"]) if r.get("saldo") else None,
                "categoria": r["categoria"],
                "origem": "extrato",
                "tipo_lanc": None,
            }
        )
    for r in listar_lancamentos_manuais(data_ini, data_fim, db_path):
        val = _d(r["valor"])
        itens.append(
            {
                "id": f"m-{r['id']}",
                "data": str(r["data"])[:10],
                "descricao": r["descricao"],
                "credito": val if r["tipo"] == "entrada" else None,
                "debito": val if r["tipo"] == "saida" else None,
                "saldo": None,
                "categoria": r["categoria"],
                "origem": "manual",
                "tipo_lanc": r["tipo"],
                "manual_id": r["id"],
            }
        )
    itens.sort(key=lambda x: (x["data"], x["id"]), reverse=True)
    return itens


def intervalo_dados(db_path: Path | str | None = None) -> tuple[date | None, date | None]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            q(
                """
            SELECT MIN(d) AS mi, MAX(d) AS ma FROM (
                SELECT data AS d FROM movimentos
                UNION ALL
                SELECT data AS d FROM lancamentos_manuais
            ) t
            """
            )
        ).fetchone()
    if not row or not row["mi"]:
        return None, None
    mi = row["mi"]
    ma = row["ma"]
    if hasattr(mi, "isoformat"):
        return mi, ma
    return date.fromisoformat(str(mi)[:10]), date.fromisoformat(str(ma)[:10])
