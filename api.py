"""
API REST + painel web. Execute via Docker ou: uvicorn api:app --reload --port 8080
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from financeiro.config import SQLITE_PATH, using_postgres
from financeiro.db import (
    _d,
    atualizar_lancamento_manual,
    calcular_indicadores,
    desativar_conta_fixa,
    excluir_importacao_extrato,
    excluir_lancamento_manual,
    init_db,
    inserir_lancamento_manual,
    inserir_movimentos,
    listar_importacoes_extrato,
    recategorizar_movimentos,
    intervalo_dados,
    listar_consolidado,
    listar_contas_fixas,
    listar_lancamentos_manuais,
    resumo_mensal,
    resumo_por_categoria,
    atualizar_conta_fixa,
    resumo_salario_contas_fixas,
    salvar_conta_fixa,
    salvar_salario_mensal,
    total_contas_fixas_previsto,
    ultimo_saldo,
)
from financeiro.numbers import parse_br_decimal
from financeiro.parser import CATEGORIAS_SUGERIDAS, categoria_por_historico, parse_extrato_texto

ROOT = Path(__file__).resolve().parent
PAINEL = ROOT / "painel.html"


def _fmt_br(val: Decimal | None) -> str:
    if val is None:
        return "—"
    q = val.quantize(Decimal("0.01"))
    neg = q < 0
    q = abs(q)
    cents = int(q * 100)
    whole, frac = divmod(cents, 100)
    s = str(whole)
    chunks: list[str] = []
    while s:
        chunks.append(s[-3:])
        s = s[:-3]
    return ("-" if neg else "") + ".".join(reversed(chunks)) + f",{frac:02d}"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s[:10])


class LancamentoIn(BaseModel):
    data: str = Field(..., description="AAAA-MM-DD")
    descricao: str
    valor: str
    tipo: str = Field(..., pattern="^(entrada|saida)$")
    categoria: str = "Outros"


class ExtratoIn(BaseModel):
    texto: str


class ContaFixaIn(BaseModel):
    nome: str
    valor: str
    categoria: str = "Contas fixas (utilidades)"
    dia_vencimento: int | None = None
    historico_contem: str | None = None
    observacao: str | None = None


class SalarioMensalIn(BaseModel):
    valor: str


app = FastAPI(title="Sistema financeiro", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    if not using_postgres():
        SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/")
def pagina_inicial() -> FileResponse:
    return FileResponse(PAINEL)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "banco": "postgresql" if using_postgres() else "sqlite"}


@app.get("/api/categorias")
def categorias() -> list[str]:
    return CATEGORIAS_SUGERIDAS


@app.get("/api/periodo")
def periodo() -> dict:
    mi, ma = intervalo_dados()
    return {
        "de": mi.isoformat() if mi else None,
        "ate": ma.isoformat() if ma else None,
    }


@app.get("/api/indicadores")
def indicadores(de: str | None = None, ate: str | None = None) -> dict:
    di, df = _parse_date(de), _parse_date(ate)
    ind = calcular_indicadores(di, df)
    return {
        "entradas": str(ind.total_creditos),
        "saidas": str(ind.total_debitos),
        "liquido": str(ind.saldo_liquido),
        "saldo_extrato": str(ultimo_saldo()) if ultimo_saldo() is not None else None,
        "gastos_fixos": str(ind.total_fixas),
        "gastos_variaveis": str(ind.total_variaveis),
        "pct_fixas": float(ind.pct_fixas) if ind.pct_fixas is not None else None,
        "pct_variaveis": float(ind.pct_variaveis) if ind.pct_variaveis is not None else None,
        "ticket_medio_debito": str(ind.ticket_medio_debito) if ind.ticket_medio_debito else None,
        "media_diaria_gastos": str(ind.media_diaria_gastos) if ind.media_diaria_gastos else None,
        "maior_debito": str(ind.maior_debito) if ind.maior_debito else None,
        "qtd_movimentos": ind.qtd_movimentos,
        "contas_fixas_previsto": str(total_contas_fixas_previsto()),
        "manuais_entrada": str(ind.total_manuais_entrada),
        "manuais_saida": str(ind.total_manuais_saida),
        "fmt": {
            "entradas": _fmt_br(ind.total_creditos),
            "saidas": _fmt_br(ind.total_debitos),
            "liquido": _fmt_br(ind.saldo_liquido),
            "saldo_extrato": _fmt_br(ultimo_saldo()),
            "gastos_fixos": _fmt_br(ind.total_fixas),
            "gastos_variaveis": _fmt_br(ind.total_variaveis),
            "contas_fixas_previsto": _fmt_br(total_contas_fixas_previsto()),
        },
    }


@app.get("/api/resumo/mensal")
def api_resumo_mensal(de: str | None = None, ate: str | None = None) -> list[dict]:
    rows = resumo_mensal(_parse_date(de), _parse_date(ate))
    return [
        {
            "mes": r.mes,
            "entradas": float(r.creditos),
            "saidas": float(r.debitos),
            "liquido": float(r.liquido),
        }
        for r in rows
    ]


@app.get("/api/resumo/categorias")
def api_resumo_categorias(de: str | None = None, ate: str | None = None) -> list[dict]:
    return [
        {"categoria": cat, "entrada": float(c), "saida": float(d)}
        for cat, c, d in resumo_por_categoria(_parse_date(de), _parse_date(ate))
    ]


@app.get("/api/movimentos")
def api_movimentos(de: str | None = None, ate: str | None = None) -> list[dict]:
    out = []
    for r in listar_consolidado(_parse_date(de), _parse_date(ate)):
        out.append(
            {
                **r,
                "credito": float(r["credito"]) if r["credito"] is not None else None,
                "debito": float(r["debito"]) if r["debito"] is not None else None,
                "saldo": float(r["saldo"]) if r["saldo"] is not None else None,
            }
        )
    return out


@app.post("/api/lancamentos")
def criar_lancamento(body: LancamentoIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or not body.descricao.strip():
        raise HTTPException(400, "Descrição e valor válido são obrigatórios.")
    d = _parse_date(body.data)
    if d is None:
        raise HTTPException(400, "Data inválida (use AAAA-MM-DD).")
    lid = inserir_lancamento_manual(
        data_mov=d, descricao=body.descricao.strip(), valor=v, tipo=body.tipo, categoria=body.categoria
    )
    return {"id": lid, "ok": True}


@app.put("/api/lancamentos/{lanc_id}")
def editar_lancamento(lanc_id: int, body: LancamentoIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or not body.descricao.strip():
        raise HTTPException(400, "Descrição e valor válido são obrigatórios.")
    d = _parse_date(body.data)
    if d is None:
        raise HTTPException(400, "Data inválida (use AAAA-MM-DD).")
    ok = atualizar_lancamento_manual(
        lanc_id=lanc_id,
        data_mov=d,
        descricao=body.descricao.strip(),
        valor=v,
        tipo=body.tipo,
        categoria=body.categoria,
    )
    if not ok:
        raise HTTPException(404, "Lançamento não encontrado.")
    return {"ok": True}


@app.delete("/api/lancamentos/{lanc_id}")
def remover_lancamento(lanc_id: int) -> dict:
    excluir_lancamento_manual(lanc_id=lanc_id)
    return {"ok": True}


@app.get("/api/lancamentos/recentes")
def lancamentos_recentes(limite: int = 8) -> list[dict]:
    rows = listar_lancamentos_manuais()[:limite]
    return [
        {
            "id": r["id"],
            "data": str(r["data"])[:10],
            "descricao": r["descricao"],
            "valor": float(_d(r["valor"])),
            "tipo": r["tipo"],
            "categoria": r["categoria"],
        }
        for r in rows
    ]


@app.post("/api/recategorizar")
def api_recategorizar() -> dict:
    n = recategorizar_movimentos()
    return {"ok": True, "atualizados": n}


@app.post("/api/extrato/importar")
def importar_extrato(body: ExtratoIn) -> dict:
    linhas = parse_extrato_texto(body.texto)
    if not linhas:
        raise HTTPException(
            400,
            "Nenhuma linha válida encontrada. Formatos aceitos: "
            "Nubank (CSV: Data,Valor,Identificador,Descrição) ou "
            "Bradesco (texto com ';' e colunas de crédito/débito).",
        )
    ins, dup, imp_id = inserir_movimentos(linhas=linhas, categorizar=categoria_por_historico)
    recat = recategorizar_movimentos()
    return {
        "lidas": len(linhas),
        "inseridas": ins,
        "duplicadas": dup,
        "importacao_id": imp_id,
        "recategorizados": recat,
    }


@app.get("/api/extratos")
def api_listar_extratos() -> list[dict]:
    return listar_importacoes_extrato()


@app.delete("/api/extratos/{importacao_id}")
def api_excluir_extrato(importacao_id: int) -> dict:
    removidos = excluir_importacao_extrato(importacao_id=importacao_id)
    if removidos == 0 and importacao_id != 0:
        raise HTTPException(404, "Importação não encontrada ou já excluída.")
    return {"ok": True, "movimentos_removidos": removidos}


def _planejamento_fixas_payload() -> dict:
    r = resumo_salario_contas_fixas()
    sal = r["salario_mensal"]
    fix = r["total_contas_fixas"]
    contas = [
        {
            "id": row["id"],
            "nome": row["nome"],
            "valor": float(_d(row["valor"])),
            "dia_vencimento": row["dia_vencimento"],
            "categoria": row["categoria"],
        }
        for row in listar_contas_fixas(apenas_ativas=True)
    ]
    return {
        "salario_mensal": float(sal) if sal is not None else None,
        "total_contas_fixas": float(fix),
        "saldo": float(r["saldo"]) if r["saldo"] is not None else None,
        "sobra": float(r["sobra"]) if r["sobra"] is not None else None,
        "falta": float(r["falta"]) if r["falta"] is not None else None,
        "pct_comprometido": float(r["pct_comprometido"]) if r["pct_comprometido"] is not None else None,
        "qtd_contas_ativas": r["qtd_contas_ativas"],
        "contas": contas,
        "fmt": {
            "salario_mensal": _fmt_br(sal),
            "total_contas_fixas": _fmt_br(fix),
            "saldo": _fmt_br(r["saldo"]),
            "sobra": _fmt_br(r["sobra"]),
            "falta": _fmt_br(r["falta"]),
        },
    }


@app.get("/api/contas-fixas/planejamento")
def api_planejamento_fixas() -> dict:
    return _planejamento_fixas_payload()


@app.put("/api/salario-mensal")
def api_salvar_salario(body: SalarioMensalIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or v <= 0:
        raise HTTPException(400, "Informe um salário mensal válido maior que zero.")
    salvar_salario_mensal(v)
    return {"ok": True, "planejamento": _planejamento_fixas_payload()}


@app.get("/api/contas-fixas")
def api_contas_fixas() -> list[dict]:
    return [
        {
            "id": r["id"],
            "nome": r["nome"],
            "valor": float(_d(r["valor"])),
            "dia_vencimento": r["dia_vencimento"],
            "categoria": r["categoria"],
            "historico_contem": r["historico_contem"],
            "observacao": r["observacao"],
            "ativo": bool(r["ativo"]),
        }
        for r in listar_contas_fixas(apenas_ativas=False)
    ]


@app.post("/api/contas-fixas")
def criar_conta_fixa(body: ContaFixaIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or not body.nome.strip():
        raise HTTPException(400, "Nome e valor são obrigatórios.")
    salvar_conta_fixa(
        nome=body.nome.strip(),
        valor=v,
        categoria=body.categoria,
        dia_vencimento=body.dia_vencimento,
        historico_contem=body.historico_contem,
        observacao=body.observacao,
    )
    return {"ok": True}


@app.put("/api/contas-fixas/{conta_id}")
def editar_conta_fixa(conta_id: int, body: ContaFixaIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or not body.nome.strip():
        raise HTTPException(400, "Nome e valor são obrigatórios.")
    ok = atualizar_conta_fixa(
        conta_id=conta_id,
        nome=body.nome.strip(),
        valor=v,
        categoria=body.categoria,
        dia_vencimento=body.dia_vencimento,
        historico_contem=body.historico_contem,
        observacao=body.observacao,
    )
    if not ok:
        raise HTTPException(404, "Conta fixa não encontrada ou inativa.")
    return {"ok": True, "planejamento": _planejamento_fixas_payload()}


@app.delete("/api/contas-fixas/{conta_id}")
def api_desativar_conta(conta_id: int) -> dict:
    desativar_conta_fixa(conta_id=conta_id)
    return {"ok": True}
