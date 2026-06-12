"""
Funcionalidades estendidas: investimentos, metas, dívidas, orçamento avançado,
calendário, regras de categoria, exportação, DRE e comparativos.
"""

from __future__ import annotations

import calendar
import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from financeiro.config import using_postgres
from financeiro.conn import get_conn, q
from financeiro.db import (
    _d,
    _row_val,
    listar_contas_fixas,
    listar_contas_fixas_mes,
    listar_orcamento_mes,
    obter_config,
    resumo_por_categoria,
    salvar_config,
    salvar_orcamento,
    total_contas_fixas_previsto,
    saldo_disponivel,
    ultimo_saldo,
)
from financeiro.parser import CATEGORIAS_SUGERIDAS, categoria_por_historico
from financeiro.schema_extras import SCHEMA_EXTRAS, SCHEMA_EXTRAS_POSTGRES

CHAVE_RESERVA_MULT = "reserva_multiplicador_meses"
CHAVE_REGRA_503020 = "regra_503020"
CHAVE_NOTIF_EMAIL = "notificacoes_email"

CATEGORIAS_ESSENCIAIS = {
    "Moradia",
    "Contas fixas (utilidades)",
    "Alimentação",
    "Mercado",
    "Saúde",
    "Educação",
    "Transporte",
    "Gasolina",
    "Contas fixas",
}

TIPOS_ATIVO_INVEST = [
    "Renda fixa",
    "Ações",
    "FIIs",
    "Tesouro",
    "Previdência",
    "Cripto",
    "Outros",
]


def _default_db() -> Path | None:
    return None


def _val_store(v: Decimal) -> Any:
    return v if using_postgres() else str(v)


def migrate_extras(conn: Any) -> None:
    schema = SCHEMA_EXTRAS_POSTGRES if using_postgres() else SCHEMA_EXTRAS
    for stmt in schema.split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)
    if not using_postgres():
        tem_mov = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movimentos'"
        ).fetchone()
        if tem_mov:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(movimentos)").fetchall()}
            if "conta_bancaria_id" not in cols:
                conn.execute(
                    "ALTER TABLE movimentos ADD COLUMN conta_bancaria_id INTEGER REFERENCES contas_bancarias(id)"
                )
    else:
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'movimentos' AND column_name = 'conta_bancaria_id'
            """
        ).fetchone()
        if not row:
            conn.execute(
                "ALTER TABLE movimentos ADD COLUMN conta_bancaria_id INTEGER REFERENCES contas_bancarias(id)"
            )


# --- Categorização ---


def listar_regras_categoria(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q("SELECT id, padrao, categoria, prioridade FROM regras_categoria ORDER BY prioridade DESC, id")
        ).fetchall()
    return [
        {
            "id": r["id"],
            "padrao": r["padrao"],
            "categoria": r["categoria"],
            "prioridade": r["prioridade"],
        }
        for r in rows
    ]


def salvar_regra_categoria(
    padrao: str,
    categoria: str,
    prioridade: int = 0,
    regra_id: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    with get_conn(db_path) as conn:
        if regra_id:
            conn.execute(
                q(
                    "UPDATE regras_categoria SET padrao=?, categoria=?, prioridade=? WHERE id=?"
                ),
                (padrao.strip(), categoria, prioridade, regra_id),
            )
            return regra_id
        cur = conn.execute(
            q(
                """
            INSERT INTO regras_categoria (padrao, categoria, prioridade) VALUES (?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q("INSERT INTO regras_categoria (padrao, categoria, prioridade) VALUES (?, ?, ?)"),
            (padrao.strip(), categoria, prioridade),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def excluir_regra_categoria(regra_id: int, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("DELETE FROM regras_categoria WHERE id = ?"), (regra_id,))


def categoria_efetiva(historico: str, db_path: Path | str | None = None) -> str:
    h = historico.upper()
    for r in listar_regras_categoria(db_path):
        if r["padrao"].upper() in h:
            return r["categoria"]
    return categoria_por_historico(historico)


# --- Calendário ---


def calendario_vencimentos(ano: int, mes: int, db_path: Path | str | None = None) -> dict[str, Any]:
    contas = listar_contas_fixas(db_path, apenas_ativas=True)
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    itens: list[dict[str, Any]] = []
    total = Decimal(0)
    for c in contas:
        dia = int(c["dia_vencimento"] or 1)
        dia = min(dia, ultimo_dia)
        val = _d(c["valor"])
        total += val
        itens.append(
            {
                "id": c["id"],
                "nome": c["nome"],
                "dia": dia,
                "data": date(ano, mes, dia).isoformat(),
                "valor": val,
                "categoria": c["categoria"],
            }
        )
    itens.sort(key=lambda x: x["dia"])
    hoje = date.today()
    ate_meio = sum((i["valor"] for i in itens if i["dia"] <= 15), Decimal(0))
    saldo, origem = saldo_disponivel(db_path)
    return {
        "ano": ano,
        "mes": mes,
        "itens": itens,
        "total_mes": total,
        "vence_ate_dia_15": ate_meio,
        "qtd": len(itens),
        "saldo_extrato": saldo,
        "saldo_origem": origem,
    }


# --- Orçamento avançado ---


def _mes_limites(mes: str) -> tuple[date, date]:
    di = date.fromisoformat(f"{mes}-01")
    if mes[5:7] == "12":
        df = date(int(mes[:4]), 12, 31)
    else:
        prox = date(int(mes[:4]), int(mes[5:7]) + 1, 1)
        df = date.fromordinal(prox.toordinal() - 1)
    return di, df


def orcamento_com_alertas(mes: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    di, df = _mes_limites(mes)
    gastos = {c: d for c, _, d in resumo_por_categoria(di, df)}
    hoje = date.today()
    dia_atual = hoje.day if hoje.strftime("%Y-%m") == mes else df.day
    dias_no_mes = df.day
    ritmo_esperado = Decimal(dia_atual) / Decimal(dias_no_mes) if dias_no_mes else Decimal(1)

    linhas: list[dict[str, Any]] = []
    for row in listar_orcamento_mes(db_path, mes):
        cat = row["categoria"]
        limite = _d(row["limite"])
        gasto = gastos.get(cat, Decimal(0))
        pct = (gasto / limite * 100) if limite else Decimal(0)
        alerta = "ok"
        if limite and gasto > limite:
            alerta = "estourado"
        elif limite and pct >= 80:
            alerta = "atencao"
        projecao = None
        if dia_atual > 0 and gasto > 0:
            projecao = (gasto / Decimal(dia_atual) * Decimal(dias_no_mes)).quantize(Decimal("0.01"))
        linhas.append(
            {
                "categoria": cat,
                "limite": limite,
                "gasto": gasto,
                "saldo": limite - gasto,
                "pct": float(pct),
                "alerta": alerta,
                "projecao_mes": projecao,
                "ritmo_pct": float(ritmo_esperado * 100),
            }
        )
    return linhas


def copiar_orcamento_mes(origem: str, destino: str, db_path: Path | str | None = None) -> int:
    n = 0
    for row in listar_orcamento_mes(db_path, origem):
        salvar_orcamento(db_path, destino, row["categoria"], _d(row["limite"]))
        n += 1
    return n


# --- Metas / reserva ---


def obter_reserva_multiplicador(db_path: Path | str | None = None) -> int:
    raw = obter_config(CHAVE_RESERVA_MULT, db_path)
    if raw is None:
        return 6
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def salvar_reserva_multiplicador(n: int, db_path: Path | str | None = None) -> None:
    salvar_config(CHAVE_RESERVA_MULT, str(max(1, n)), db_path)


def resumo_reserva_emergencia(db_path: Path | str | None = None) -> dict[str, Any]:
    mult = obter_reserva_multiplicador(db_path)
    fixas = total_contas_fixas_previsto(db_path)
    meta_valor = fixas * mult
    saldo, origem = saldo_disponivel(db_path)
    pct = (saldo / meta_valor * 100) if meta_valor else Decimal(0)
    return {
        "multiplicador_meses": mult,
        "despesa_mensal_ref": fixas,
        "meta_reserva": meta_valor,
        "saldo_atual": saldo,
        "saldo_origem": origem,
        "pct_atingido": float(pct.quantize(Decimal("0.01"))),
        "falta": max(meta_valor - saldo, Decimal(0)),
    }


def listar_metas(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(q("SELECT * FROM metas_financeiras ORDER BY id")).fetchall()
    out = []
    for r in rows:
        alvo = _d(r["valor_alvo"]) if r["valor_alvo"] else None
        atual = _d(r["valor_atual"])
        pct = float((atual / alvo * 100).quantize(Decimal("0.01"))) if alvo and alvo > 0 else None
        falta = max(alvo - atual, Decimal(0)) if alvo is not None else None
        out.append(
            {
                "id": r["id"],
                "tipo": r["tipo"],
                "nome": r["nome"],
                "valor_alvo": alvo,
                "valor_atual": atual,
                "multiplicador_meses": r["multiplicador_meses"],
                "prazo": str(r["prazo"])[:10] if r["prazo"] else None,
                "pct": pct,
                "falta": falta,
            }
        )
    return out


def obter_meta(meta_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    for m in listar_metas(db_path):
        if m["id"] == meta_id:
            return m
    return None


def aportar_meta(meta_id: int, valor: Decimal, db_path: Path | str | None = None) -> dict[str, Any]:
    """Soma um aporte ao valor já acumulado da meta."""
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")
    meta = obter_meta(meta_id, db_path)
    if meta is None:
        raise LookupError("Meta não encontrada.")
    novo = meta["valor_atual"] + valor
    with get_conn(db_path) as conn:
        conn.execute(
            q("UPDATE metas_financeiras SET valor_atual = ? WHERE id = ?"),
            (_val_store(novo), meta_id),
        )
    atualizado = obter_meta(meta_id, db_path)
    assert atualizado is not None
    return atualizado


def definir_valor_meta(
    meta_id: int, valor_atual: Decimal, db_path: Path | str | None = None
) -> dict[str, Any]:
    """Define o total acumulado (substitui o valor atual)."""
    if valor_atual < 0:
        raise ValueError("Valor acumulado não pode ser negativo.")
    meta = obter_meta(meta_id, db_path)
    if meta is None:
        raise LookupError("Meta não encontrada.")
    with get_conn(db_path) as conn:
        conn.execute(
            q("UPDATE metas_financeiras SET valor_atual = ? WHERE id = ?"),
            (_val_store(valor_atual), meta_id),
        )
    atualizado = obter_meta(meta_id, db_path)
    assert atualizado is not None
    return atualizado


def salvar_meta(
    nome: str,
    tipo: str,
    valor_alvo: Decimal | None = None,
    valor_atual: Decimal = Decimal(0),
    multiplicador_meses: int | None = None,
    prazo: date | None = None,
    meta_id: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    pr = prazo.isoformat() if prazo else None
    with get_conn(db_path) as conn:
        if meta_id:
            conn.execute(
                q(
                    """
                UPDATE metas_financeiras
                SET nome=?, tipo=?, valor_alvo=?, valor_atual=?, multiplicador_meses=?, prazo=?
                WHERE id=?
                """
                ),
                (
                    nome,
                    tipo,
                    _val_store(valor_alvo) if valor_alvo is not None else None,
                    _val_store(valor_atual),
                    multiplicador_meses,
                    pr,
                    meta_id,
                ),
            )
            return meta_id
        cur = conn.execute(
            q(
                """
            INSERT INTO metas_financeiras (nome, tipo, valor_alvo, valor_atual, multiplicador_meses, prazo)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO metas_financeiras (nome, tipo, valor_alvo, valor_atual, multiplicador_meses, prazo)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            ),
            (
                nome,
                tipo,
                _val_store(valor_alvo) if valor_alvo is not None else None,
                _val_store(valor_atual),
                multiplicador_meses,
                pr,
            ),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def excluir_meta(meta_id: int, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("DELETE FROM metas_financeiras WHERE id = ?"), (meta_id,))


# --- Projetos / sonhos ---


def listar_projetos(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q("SELECT * FROM projetos WHERE ativo = 1 ORDER BY id DESC")
        ).fetchall()
    out = []
    for r in rows:
        alvo = _d(r["valor_alvo"])
        acum = _d(r["valor_acumulado"])
        pct = float((acum / alvo * 100).quantize(Decimal("0.01"))) if alvo > 0 else 0.0
        out.append(
            {
                "id": r["id"],
                "nome": r["nome"],
                "valor_alvo": alvo,
                "valor_acumulado": acum,
                "aporte_mensal": _d(r["aporte_mensal"]) if r["aporte_mensal"] else None,
                "prazo": str(r["prazo"])[:10] if r["prazo"] else None,
                "pct": pct,
                "falta": max(alvo - acum, Decimal(0)),
            }
        )
    return out


def salvar_projeto(
    nome: str,
    valor_alvo: Decimal,
    valor_acumulado: Decimal = Decimal(0),
    aporte_mensal: Decimal | None = None,
    prazo: date | None = None,
    projeto_id: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    pr = prazo.isoformat() if prazo else None
    with get_conn(db_path) as conn:
        if projeto_id:
            conn.execute(
                q(
                    """
                UPDATE projetos SET nome=?, valor_alvo=?, valor_acumulado=?, aporte_mensal=?, prazo=?
                WHERE id=?
                """
                ),
                (
                    nome,
                    _val_store(valor_alvo),
                    _val_store(valor_acumulado),
                    _val_store(aporte_mensal) if aporte_mensal is not None else None,
                    pr,
                    projeto_id,
                ),
            )
            return projeto_id
        cur = conn.execute(
            q(
                """
            INSERT INTO projetos (nome, valor_alvo, valor_acumulado, aporte_mensal, prazo)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO projetos (nome, valor_alvo, valor_acumulado, aporte_mensal, prazo)
            VALUES (?, ?, ?, ?, ?)
            """
            ),
            (
                nome,
                _val_store(valor_alvo),
                _val_store(valor_acumulado),
                _val_store(aporte_mensal) if aporte_mensal is not None else None,
                pr,
            ),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def desativar_projeto(projeto_id: int, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("UPDATE projetos SET ativo = 0 WHERE id = ?"), (projeto_id,))


def obter_projeto(projeto_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    for p in listar_projetos(db_path):
        if p["id"] == projeto_id:
            return p
    return None


def aportar_projeto(projeto_id: int, valor: Decimal, db_path: Path | str | None = None) -> dict[str, Any]:
    """Soma um aporte ao valor acumulado do projeto."""
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")
    proj = obter_projeto(projeto_id, db_path)
    if proj is None:
        raise LookupError("Projeto não encontrado.")
    novo = proj["valor_acumulado"] + valor
    with get_conn(db_path) as conn:
        conn.execute(
            q("UPDATE projetos SET valor_acumulado = ? WHERE id = ?"),
            (_val_store(novo), projeto_id),
        )
    atualizado = obter_projeto(projeto_id, db_path)
    assert atualizado is not None
    return atualizado


def definir_valor_projeto(
    projeto_id: int, valor_acumulado: Decimal, db_path: Path | str | None = None
) -> dict[str, Any]:
    if valor_acumulado < 0:
        raise ValueError("Valor acumulado não pode ser negativo.")
    proj = obter_projeto(projeto_id, db_path)
    if proj is None:
        raise LookupError("Projeto não encontrado.")
    with get_conn(db_path) as conn:
        conn.execute(
            q("UPDATE projetos SET valor_acumulado = ? WHERE id = ?"),
            (_val_store(valor_acumulado), projeto_id),
        )
    atualizado = obter_projeto(projeto_id, db_path)
    assert atualizado is not None
    return atualizado


# --- Dívidas ---


def listar_dividas(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(q("SELECT * FROM dividas WHERE ativo = 1 ORDER BY id")).fetchall()
    out = []
    for r in rows:
        total = _d(r["valor_total"])
        pago = _d(r["valor_pago"])
        restante = max(total - pago, Decimal(0))
        pct = float((pago / total * 100).quantize(Decimal("0.01"))) if total > 0 else 0.0
        out.append(
            {
                "id": r["id"],
                "nome": r["nome"],
                "valor_total": total,
                "valor_pago": pago,
                "restante": restante,
                "taxa_mensal": float(_d(r["taxa_mensal"])) if r["taxa_mensal"] else None,
                "parcelas": r["parcelas"],
                "parcelas_pagas": r["parcelas_pagas"],
                "estrategia": r["estrategia"],
                "pct": pct,
            }
        )
    return out


def salvar_divida(
    nome: str,
    valor_total: Decimal,
    valor_pago: Decimal = Decimal(0),
    taxa_mensal: Decimal | None = None,
    parcelas: int | None = None,
    parcelas_pagas: int = 0,
    estrategia: str = "minimo",
    divida_id: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    with get_conn(db_path) as conn:
        if divida_id:
            conn.execute(
                q(
                    """
                UPDATE dividas SET nome=?, valor_total=?, valor_pago=?, taxa_mensal=?,
                parcelas=?, parcelas_pagas=?, estrategia=? WHERE id=?
                """
                ),
                (
                    nome,
                    _val_store(valor_total),
                    _val_store(valor_pago),
                    _val_store(taxa_mensal) if taxa_mensal is not None else None,
                    parcelas,
                    parcelas_pagas,
                    estrategia,
                    divida_id,
                ),
            )
            return divida_id
        cur = conn.execute(
            q(
                """
            INSERT INTO dividas (nome, valor_total, valor_pago, taxa_mensal, parcelas, parcelas_pagas, estrategia)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO dividas (nome, valor_total, valor_pago, taxa_mensal, parcelas, parcelas_pagas, estrategia)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            ),
            (
                nome,
                _val_store(valor_total),
                _val_store(valor_pago),
                _val_store(taxa_mensal) if taxa_mensal is not None else None,
                parcelas,
                parcelas_pagas,
                estrategia,
            ),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def desativar_divida(divida_id: int, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("UPDATE dividas SET ativo = 0 WHERE id = ?"), (divida_id,))


def sugestao_quitacao_dividas(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Ordena por menor saldo (bola de neve) ou maior taxa (avalanche)."""
    dividas = listar_dividas(db_path)
    snowball = sorted(dividas, key=lambda d: d["restante"])
    avalanche = sorted(
        dividas,
        key=lambda d: (d["taxa_mensal"] or 0),
        reverse=True,
    )
    return [
        {"metodo": "bola_de_neve", "ordem": [d["nome"] for d in snowball]},
        {"metodo": "avalanche", "ordem": [d["nome"] for d in avalanche]},
    ]


# --- Investimentos ---


def listar_ativos(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q("SELECT * FROM ativos_investimento WHERE ativo = 1 ORDER BY nome")
        ).fetchall()
    return [
        {
            "id": r["id"],
            "nome": r["nome"],
            "tipo": r["tipo"],
            "instituicao": r["instituicao"],
            "valor_atual": _d(r["valor_atual"]),
        }
        for r in rows
    ]


def salvar_ativo(
    nome: str,
    tipo: str,
    valor_atual: Decimal = Decimal(0),
    instituicao: str | None = None,
    ativo_id: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    with get_conn(db_path) as conn:
        if ativo_id:
            conn.execute(
                q(
                    "UPDATE ativos_investimento SET nome=?, tipo=?, instituicao=?, valor_atual=? WHERE id=?"
                ),
                (nome, tipo, instituicao, _val_store(valor_atual), ativo_id),
            )
            return ativo_id
        cur = conn.execute(
            q(
                """
            INSERT INTO ativos_investimento (nome, tipo, instituicao, valor_atual)
            VALUES (?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                "INSERT INTO ativos_investimento (nome, tipo, instituicao, valor_atual) VALUES (?, ?, ?, ?)"
            ),
            (nome, tipo, instituicao, _val_store(valor_atual)),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def registrar_mov_investimento(
    ativo_id: int,
    data_mov: date,
    tipo: str,
    valor: Decimal,
    observacao: str | None = None,
    db_path: Path | str | None = None,
) -> int:
    if tipo not in ("aporte", "resgate", "rendimento"):
        raise ValueError("tipo inválido")
    with get_conn(db_path) as conn:
        cur = conn.execute(
            q(
                """
            INSERT INTO movimentos_investimento (ativo_id, data, tipo, valor, observacao)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO movimentos_investimento (ativo_id, data, tipo, valor, observacao)
            VALUES (?, ?, ?, ?, ?)
            """
            ),
            (ativo_id, data_mov.isoformat(), tipo, _val_store(valor), observacao),
        )
        row = conn.execute(
            q("SELECT valor_atual FROM ativos_investimento WHERE id = ?"), (ativo_id,)
        ).fetchone()
        atual = _d(row["valor_atual"])
        if tipo == "aporte" or tipo == "rendimento":
            novo = atual + valor
        else:
            novo = max(atual - valor, Decimal(0))
        conn.execute(
            q("UPDATE ativos_investimento SET valor_atual = ? WHERE id = ?"),
            (_val_store(novo), ativo_id),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def listar_movimentos_investimento(
    ativo_id: int | None = None, db_path: Path | str | None = None
) -> list[dict[str, Any]]:
    sql = """
        SELECT m.id, m.ativo_id, m.data, m.tipo, m.valor, m.observacao, a.nome AS ativo_nome
        FROM movimentos_investimento m
        JOIN ativos_investimento a ON a.id = m.ativo_id
        WHERE 1=1
    """
    params: list[Any] = []
    if ativo_id:
        sql += " AND m.ativo_id = ?"
        params.append(ativo_id)
    sql += " ORDER BY m.data DESC, m.id DESC"
    with get_conn(db_path) as conn:
        rows = conn.execute(q(sql), params).fetchall()
    return [
        {
            "id": r["id"],
            "ativo_id": r["ativo_id"],
            "ativo_nome": r["ativo_nome"],
            "data": str(r["data"])[:10],
            "tipo": r["tipo"],
            "valor": _d(r["valor"]),
            "observacao": r["observacao"],
        }
        for r in rows
    ]


def resumo_investimentos(db_path: Path | str | None = None) -> dict[str, Any]:
    ativos = listar_ativos(db_path)
    total = sum((a["valor_atual"] for a in ativos), Decimal(0))
    por_tipo: dict[str, Decimal] = {}
    for a in ativos:
        por_tipo[a["tipo"]] = por_tipo.get(a["tipo"], Decimal(0)) + a["valor_atual"]
    hoje = date.today()
    mes = hoje.strftime("%Y-%m")
    aportes_mes = Decimal(0)
    rend_mes = Decimal(0)
    mes_col = "to_char(data, 'YYYY-MM')" if using_postgres() else "substr(data, 1, 7)"
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q(
                f"""
            SELECT tipo, valor FROM movimentos_investimento
            WHERE {mes_col} = ?
            """
            ),
            (mes,),
        ).fetchall()
    for r in rows:
        v = _d(r["valor"])
        if r["tipo"] == "aporte":
            aportes_mes += v
        elif r["tipo"] == "rendimento":
            rend_mes += v
    aloc = listar_metas_alocacao(db_path)
    return {
        "patrimonio_total": total,
        "por_tipo": {k: float(v) for k, v in por_tipo.items()},
        "aportes_mes": aportes_mes,
        "rendimentos_mes": rend_mes,
        "qtd_ativos": len(ativos),
        "alocacao_meta": aloc,
    }


def listar_metas_alocacao(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(q("SELECT tipo_ativo, percentual FROM metas_alocacao ORDER BY tipo_ativo")).fetchall()
    return [{"tipo_ativo": r["tipo_ativo"], "percentual": float(_d(r["percentual"]))} for r in rows]


def salvar_meta_alocacao(tipo_ativo: str, percentual: Decimal, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            q(
                """
            INSERT INTO metas_alocacao (tipo_ativo, percentual) VALUES (?, ?)
            ON CONFLICT(tipo_ativo) DO UPDATE SET percentual = excluded.percentual
            """
            ),
            (tipo_ativo, _val_store(percentual)),
        )


# --- Tags ---


def listar_tags(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(q("SELECT id, nome FROM tags ORDER BY nome")).fetchall()
    return [{"id": r["id"], "nome": r["nome"]} for r in rows]


def salvar_tag(nome: str, db_path: Path | str | None = None) -> int:
    with get_conn(db_path) as conn:
        try:
            cur = conn.execute(
                q("INSERT INTO tags (nome) VALUES (?) RETURNING id")
                if using_postgres()
                else q("INSERT INTO tags (nome) VALUES (?)"),
                (nome.strip(),),
            )
            if using_postgres():
                return int(cur.fetchone()["id"])
            return int(cur.lastrowid)
        except Exception:
            row = conn.execute(q("SELECT id FROM tags WHERE nome = ?"), (nome.strip(),)).fetchone()
            return int(row["id"])


def tags_do_lancamento(lancamento_id: int, db_path: Path | str | None = None) -> list[str]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q(
                """
            SELECT t.nome FROM tags t
            JOIN lancamento_tags lt ON lt.tag_id = t.id
            WHERE lt.lancamento_id = ?
            """
            ),
            (lancamento_id,),
        ).fetchall()
    return [r["nome"] for r in rows]


def definir_tags_lancamento(
    lancamento_id: int, nomes: list[str], db_path: Path | str | None = None
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("DELETE FROM lancamento_tags WHERE lancamento_id = ?"), (lancamento_id,))
        for nome in nomes:
            nome = nome.strip()
            if not nome:
                continue
            row = conn.execute(q("SELECT id FROM tags WHERE nome = ?"), (nome,)).fetchone()
            if row:
                tid = int(row["id"])
            else:
                cur = conn.execute(
                    q(
                        "INSERT INTO tags (nome) VALUES (?) RETURNING id"
                        if using_postgres()
                        else q("INSERT INTO tags (nome) VALUES (?)")
                    ),
                    (nome,),
                )
                tid = int(cur.fetchone()["id"]) if using_postgres() else int(cur.lastrowid)
            if using_postgres():
                conn.execute(
                    q(
                        """
                    INSERT INTO lancamento_tags (lancamento_id, tag_id) VALUES (?, ?)
                    ON CONFLICT (lancamento_id, tag_id) DO NOTHING
                    """
                    ),
                    (lancamento_id, tid),
                )
            else:
                conn.execute(
                    q("INSERT OR IGNORE INTO lancamento_tags (lancamento_id, tag_id) VALUES (?, ?)"),
                    (lancamento_id, tid),
                )


# --- Contas bancárias ---


def listar_contas_bancarias(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q("SELECT id, nome, tipo, ativo FROM contas_bancarias WHERE ativo = 1 ORDER BY nome")
        ).fetchall()
    return [
        {"id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "ativo": bool(r["ativo"])} for r in rows
    ]


def salvar_conta_bancaria(
    nome: str, tipo: str = "corrente", conta_id: int | None = None, db_path: Path | str | None = None
) -> int:
    with get_conn(db_path) as conn:
        if conta_id:
            conn.execute(
                q("UPDATE contas_bancarias SET nome=?, tipo=? WHERE id=?"),
                (nome, tipo, conta_id),
            )
            return conta_id
        cur = conn.execute(
            q(
                "INSERT INTO contas_bancarias (nome, tipo) VALUES (?, ?) RETURNING id"
            )
            if using_postgres()
            else q("INSERT INTO contas_bancarias (nome, tipo) VALUES (?, ?)"),
            (nome, tipo),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


# --- Cartão de crédito ---


def _add_months(yyyy_mm: str, n: int) -> str:
    y, m = int(yyyy_mm[:4]), int(yyyy_mm[5:7])
    idx = y * 12 + (m - 1) + n
    yy, mm = divmod(idx, 12)
    return f"{yy}-{mm + 1:02d}"


def _mes_atual() -> str:
    return date.today().strftime("%Y-%m")


def listar_cartoes_credito(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q("SELECT * FROM cartoes_credito WHERE ativo = 1 ORDER BY nome")
        ).fetchall()
    return [
        {
            "id": r["id"],
            "nome": r["nome"],
            "bandeira": r["bandeira"],
            "dia_vencimento": int(r["dia_vencimento"]),
            "dia_fechamento": int(r["dia_fechamento"]) if r["dia_fechamento"] else None,
            "limite": _d(r["limite"]) if r["limite"] is not None else None,
        }
        for r in rows
    ]


def salvar_cartao_credito(
    nome: str,
    dia_vencimento: int,
    bandeira: str | None = None,
    dia_fechamento: int | None = None,
    limite: Decimal | None = None,
    cartao_id: int | None = None,
    db_path: Path | str | None = None,
) -> int:
    with get_conn(db_path) as conn:
        if cartao_id:
            conn.execute(
                q(
                    """
                UPDATE cartoes_credito
                SET nome=?, bandeira=?, dia_vencimento=?, dia_fechamento=?, limite=?
                WHERE id=?
                """
                ),
                (
                    nome,
                    bandeira,
                    dia_vencimento,
                    dia_fechamento,
                    _val_store(limite) if limite is not None else None,
                    cartao_id,
                ),
            )
            return cartao_id
        cur = conn.execute(
            q(
                """
            INSERT INTO cartoes_credito (nome, bandeira, dia_vencimento, dia_fechamento, limite)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO cartoes_credito (nome, bandeira, dia_vencimento, dia_fechamento, limite)
            VALUES (?, ?, ?, ?, ?)
            """
            ),
            (
                nome,
                bandeira,
                dia_vencimento,
                dia_fechamento,
                _val_store(limite) if limite is not None else None,
            ),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def desativar_cartao_credito(cartao_id: int, db_path: Path | str | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(q("UPDATE cartoes_credito SET ativo = 0 WHERE id = ?"), (cartao_id,))


def registrar_compra_cartao(
    cartao_id: int,
    descricao: str,
    valor_total: Decimal,
    parcelas: int,
    data_compra: date,
    primeira_fatura: str,
    observacao: str | None = None,
    db_path: Path | str | None = None,
) -> int:
    if parcelas < 1:
        raise ValueError("Parcelas deve ser maior que zero.")
    with get_conn(db_path) as conn:
        cur = conn.execute(
            q(
                """
            INSERT INTO compras_cartao
            (cartao_id, descricao, valor_total, parcelas, data_compra, primeira_fatura, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """
            )
            if using_postgres()
            else q(
                """
            INSERT INTO compras_cartao
            (cartao_id, descricao, valor_total, parcelas, data_compra, primeira_fatura, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            ),
            (
                cartao_id,
                descricao,
                _val_store(valor_total),
                parcelas,
                data_compra.isoformat(),
                primeira_fatura,
                observacao,
            ),
        )
        if using_postgres():
            return int(cur.fetchone()["id"])
        return int(cur.lastrowid)


def listar_compras_cartao(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            q(
                """
            SELECT c.*, cc.nome AS cartao_nome
            FROM compras_cartao c
            JOIN cartoes_credito cc ON cc.id = c.cartao_id
            WHERE cc.ativo = 1
            ORDER BY c.data_compra DESC, c.id DESC
            """
            )
        ).fetchall()
    out: list[dict[str, Any]] = []
    mes = _mes_atual()
    for r in rows:
        primeira = str(r["primeira_fatura"])[:7]
        total_parcelas = int(r["parcelas"])
        idx_atual = 0
        if mes >= primeira:
            y1, m1 = int(primeira[:4]), int(primeira[5:7])
            y2, m2 = int(mes[:4]), int(mes[5:7])
            idx_atual = (y2 - y1) * 12 + (m2 - m1)
        pagas = min(max(idx_atual, 0), total_parcelas)
        restantes = max(total_parcelas - pagas, 0)
        parc_valor = (_d(r["valor_total"]) / Decimal(total_parcelas)).quantize(Decimal("0.01"))
        proxima_fatura = _add_months(primeira, pagas) if restantes > 0 else None
        out.append(
            {
                "id": r["id"],
                "cartao_id": r["cartao_id"],
                "cartao_nome": r["cartao_nome"],
                "descricao": r["descricao"],
                "valor_total": _d(r["valor_total"]),
                "parcelas": total_parcelas,
                "parcela_valor": parc_valor,
                "parcelas_pagas": pagas,
                "parcelas_restantes": restantes,
                "data_compra": str(r["data_compra"])[:10],
                "primeira_fatura": primeira,
                "proxima_fatura": proxima_fatura,
                "observacao": r["observacao"],
            }
        )
    return out


def resumo_cartoes_credito(db_path: Path | str | None = None) -> dict[str, Any]:
    cartoes = listar_cartoes_credito(db_path)
    compras = listar_compras_cartao(db_path)
    mes = _mes_atual()
    total_fatura_mes = Decimal(0)
    total_aberto = Decimal(0)
    for c in compras:
        total_aberto += c["parcela_valor"] * Decimal(c["parcelas_restantes"])
        if c["proxima_fatura"] == mes:
            total_fatura_mes += c["parcela_valor"]

    hoje = date.today()
    alertas: list[dict[str, Any]] = []
    for c in cartoes:
        dia = c["dia_vencimento"]
        venc = date(hoje.year, hoje.month, min(dia, calendar.monthrange(hoje.year, hoje.month)[1]))
        if venc < hoje:
            nm = hoje.month + 1
            ny = hoje.year + (1 if nm == 13 else 0)
            nm = 1 if nm == 13 else nm
            venc = date(ny, nm, min(dia, calendar.monthrange(ny, nm)[1]))
        faltam = (venc - hoje).days
        if faltam <= 7:
            alertas.append(
                {
                    "cartao": c["nome"],
                    "dias_para_vencer": faltam,
                    "vencimento": venc.isoformat(),
                }
            )
    return {
        "qtd_cartoes": len(cartoes),
        "qtd_compras": len(compras),
        "fatura_mes": total_fatura_mes,
        "total_em_aberto": total_aberto,
        "alertas_vencimento": sorted(alertas, key=lambda x: x["dias_para_vencer"]),
    }


# --- 50/30/20 ---


def obter_regra_503020(db_path: Path | str | None = None) -> dict[str, int]:
    raw = obter_config(CHAVE_REGRA_503020, db_path)
    if not raw:
        return {"necessidades": 50, "desejos": 30, "poupanca": 20}
    try:
        d = json.loads(raw)
        return {
            "necessidades": int(d.get("necessidades", 50)),
            "desejos": int(d.get("desejos", 30)),
            "poupanca": int(d.get("poupanca", 20)),
        }
    except (json.JSONDecodeError, TypeError):
        return {"necessidades": 50, "desejos": 30, "poupanca": 20}


def salvar_regra_503020(necessidades: int, desejos: int, poupanca: int, db_path: Path | str | None = None) -> None:
    salvar_config(
        CHAVE_REGRA_503020,
        json.dumps({"necessidades": necessidades, "desejos": desejos, "poupanca": poupanca}),
        db_path,
    )


def analise_503020(mes: str, salario: Decimal, db_path: Path | str | None = None) -> dict[str, Any]:
    regra = obter_regra_503020(db_path)
    di, df = _mes_limites(mes)
    gastos = {c: d for c, _, d in resumo_por_categoria(di, df)}
    essencial = sum((gastos.get(c, Decimal(0)) for c in CATEGORIAS_ESSENCIAIS if c in gastos), Decimal(0))
    outros = sum((d for c, d in gastos.items() if c not in CATEGORIAS_ESSENCIAIS), Decimal(0))
    total_gasto = essencial + outros
    return {
        "mes": mes,
        "salario": float(salario),
        "regra_pct": regra,
        "ideal": {
            "necessidades": float(salario * Decimal(regra["necessidades"]) / 100),
            "desejos": float(salario * Decimal(regra["desejos"]) / 100),
            "poupanca": float(salario * Decimal(regra["poupanca"]) / 100),
        },
        "realizado": {
            "necessidades": float(essencial),
            "desejos": float(outros),
            "poupanca": float(max(salario - total_gasto, Decimal(0))),
        },
        "total_gastos": float(total_gasto),
    }


# --- Comparativo e DRE ---


def comparativo_meses(mes: str, db_path: Path | str | None = None) -> dict[str, Any]:
    y, m = int(mes[:4]), int(mes[5:7])
    if m == 1:
        ant = f"{y - 1}-12"
    else:
        ant = f"{y}-{m - 1:02d}"

    def totais(ref: str) -> tuple[Decimal, Decimal]:
        di, df = _mes_limites(ref)
        ent = Decimal(0)
        sai = Decimal(0)
        for _, c, d in resumo_por_categoria(di, df):
            ent += c
            sai += d
        return ent, sai

    e_at, s_at = totais(mes)
    e_ant, s_ant = totais(ant)
    var_ent = e_at - e_ant
    var_sai = s_at - s_ant
    return {
        "mes_atual": mes,
        "mes_anterior": ant,
        "atual": {"entradas": float(e_at), "saidas": float(s_at), "liquido": float(e_at - s_at)},
        "anterior": {"entradas": float(e_ant), "saidas": float(s_ant), "liquido": float(e_ant - s_ant)},
        "variacao": {
            "entradas": float(var_ent),
            "saidas": float(var_sai),
            "liquido": float((e_at - s_at) - (e_ant - s_ant)),
        },
    }


def dre_pessoal(
    data_ini: date | None, data_fim: date | None, db_path: Path | str | None = None
) -> dict[str, Any]:
    res = resumo_por_categoria(data_ini, data_fim, db_path)
    receitas = Decimal(0)
    essenciais = Decimal(0)
    discricionarias = Decimal(0)
    for cat, ent, sai in res:
        receitas += ent
        if cat in CATEGORIAS_ESSENCIAIS or cat == "Salário / renda":
            essenciais += sai
        else:
            discricionarias += sai
    despesas = essenciais + discricionarias
    return {
        "receitas": float(receitas),
        "despesas_essenciais": float(essenciais),
        "despesas_discricionarias": float(discricionarias),
        "total_despesas": float(despesas),
        "resultado": float(receitas - despesas),
        "margem_pct": float((receitas - despesas) / receitas * 100) if receitas else None,
    }


# --- Export ---


def exportar_movimentos_csv(
    data_ini: date | None,
    data_fim: date | None,
    db_path: Path | str | None = None,
    filtro: Any = None,
) -> str:
    from financeiro.db import listar_consolidado

    rows = listar_consolidado(data_ini, data_fim, db_path, filtro=filtro)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["data", "descricao", "entrada", "saida", "categoria", "origem"])
    for r in rows:
        w.writerow(
            [
                r["data"],
                r["descricao"],
                str(r["credito"]) if r["credito"] else "",
                str(r["debito"]) if r["debito"] else "",
                r["categoria"],
                r["origem"],
            ]
        )
    return buf.getvalue()


def obter_notificacoes_email(db_path: Path | str | None = None) -> str:
    return obter_config(CHAVE_NOTIF_EMAIL, db_path) or ""


def salvar_notificacoes_email(email: str, db_path: Path | str | None = None) -> None:
    salvar_config(CHAVE_NOTIF_EMAIL, email.strip(), db_path)


_MESES_ABREV = ("", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")


def _urgencia_vencimento(dias: int) -> tuple[str, str]:
    if dias < 0:
        return "vencido", "danger"
    if dias == 0:
        return "hoje", "danger"
    if dias <= 3:
        return "urgente", "warn"
    if dias <= 7:
        return "proximo", "info"
    return "futuro", "ok"


def alertas_vencimentos_dashboard(
    mes: str | None = None,
    db_path: Path | str | None = None,
    *,
    janela_dias: int = 14,
    max_itens: int = 12,
) -> dict[str, Any]:
    """Vencimentos estruturados para o dashboard (contas fixas e cartões)."""
    hoje = date.today()
    ref_mes = mes or hoje.strftime("%Y-%m")
    ano, mes_num = int(ref_mes[:4]), int(ref_mes[5:7])
    mes_label = _MESES_ABREV[mes_num]

    itens: list[dict[str, Any]] = []
    dados_mes = listar_contas_fixas_mes(ref_mes, db_path)
    for row in dados_mes["itens"]:
        if row["status"] == "pago":
            continue
        venc = date.fromisoformat(str(row["vencimento"])[:10])
        dias = (venc - hoje).days
        urgencia, nivel = _urgencia_vencimento(dias)
        if dias > janela_dias and urgencia != "vencido":
            continue
        itens.append(
            {
                "tipo": "conta_fixa",
                "id": row["conta_fixa_id"],
                "nome": row["nome"],
                "valor": str(row["valor_real"]),
                "vencimento": row["vencimento"],
                "dia": row["dia"],
                "mes_label": mes_label,
                "dias": dias,
                "urgencia": urgencia,
                "nivel": nivel,
                "status": row["status"],
                "categoria": row["categoria"],
            }
        )

    cart_resumo = resumo_cartoes_credito(db_path)
    for alerta in cart_resumo.get("alertas_vencimento", []):
        venc = date.fromisoformat(str(alerta["vencimento"])[:10])
        dias = int(alerta["dias_para_vencer"])
        urgencia, nivel = _urgencia_vencimento(dias)
        itens.append(
            {
                "tipo": "cartao",
                "id": None,
                "nome": alerta["cartao"],
                "valor": None,
                "vencimento": alerta["vencimento"],
                "dia": venc.day,
                "mes_label": _MESES_ABREV[venc.month],
                "dias": dias,
                "urgencia": urgencia,
                "nivel": nivel,
                "status": "a_pagar",
                "categoria": "Cartão de crédito",
            }
        )

    ordem = {"vencido": 0, "hoje": 1, "urgente": 2, "proximo": 3, "futuro": 4}
    itens.sort(key=lambda x: (ordem.get(x["urgencia"], 9), x["dias"], x["nome"]))
    visiveis = itens[:max_itens]

    total_pendente = Decimal(0)
    qtd_vencido = qtd_hoje = qtd_proximos = 0
    for row in itens:
        if row["valor"] is not None:
            total_pendente += _d(row["valor"])
        if row["urgencia"] == "vencido":
            qtd_vencido += 1
        elif row["urgencia"] == "hoje":
            qtd_hoje += 1
        elif row["dias"] <= 7:
            qtd_proximos += 1

    return {
        "mes": ref_mes,
        "itens": visiveis,
        "total_itens": len(itens),
        "tem_mais": len(itens) > len(visiveis),
        "resumo": {
            "vencidos": qtd_vencido,
            "hoje": qtd_hoje,
            "proximos_7_dias": qtd_proximos,
            "total_pendente": str(total_pendente.quantize(Decimal("0.01"))),
            "total_mes_contas": str(dados_mes["resumo"]["total_a_pagar"]),
        },
    }


def resumo_alertas_gerais(mes: str, db_path: Path | str | None = None) -> list[dict[str, str]]:
    """Alertas de orçamento e reserva (sem vencimentos)."""
    alertas: list[dict[str, str]] = []
    for o in orcamento_com_alertas(mes, db_path):
        if o["alerta"] == "estourado":
            alertas.append(
                {
                    "nivel": "danger",
                    "texto": f"Orçamento estourado em {o['categoria']} ({o['pct']:.0f}%).",
                }
            )
        elif o["alerta"] == "atencao":
            alertas.append(
                {
                    "nivel": "warn",
                    "texto": f"{o['categoria']} acima de 80% do limite.",
                }
            )
    reserva = resumo_reserva_emergencia(db_path)
    if reserva["pct_atingido"] < 50 and reserva["meta_reserva"] > 0:
        alertas.append(
            {
                "nivel": "warn",
                "texto": f"Reserva de emergência em {reserva['pct_atingido']:.0f}% da meta.",
            }
        )
    return alertas


def resumo_alertas_sistema(mes: str, db_path: Path | str | None = None) -> list[dict[str, str]]:
    """Alertas agregados (compatível com telas legadas)."""
    alertas = resumo_alertas_gerais(mes, db_path)
    venc = alertas_vencimentos_dashboard(mes, db_path, janela_dias=7, max_itens=3)
    for item in venc["itens"]:
        dias = item["dias"]
        if dias < 0:
            texto = f"Venceu há {abs(dias)} dia(s): {item['nome']}"
            nivel = "danger"
        elif dias == 0:
            texto = f"Vence hoje: {item['nome']}"
            nivel = "danger"
        else:
            valor_txt = f" ({item['valor']})" if item["valor"] else ""
            texto = f"Vence em {dias} dia(s): {item['nome']}{valor_txt}"
            nivel = item["nivel"]
        alertas.append({"nivel": nivel, "texto": texto})
    return alertas
