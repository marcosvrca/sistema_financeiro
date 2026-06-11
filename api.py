"""
API REST + painel web. Execute via Docker ou: uvicorn api:app --reload --port 8080
"""

from __future__ import annotations

import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from financeiro.config import SQLITE_PATH, using_postgres
from financeiro.db import (
    FiltroVisao,
    _d,
    atualizar_lancamento_manual,
    calcular_indicadores,
    desativar_conta_fixa,
    excluir_importacao_extrato,
    excluir_lancamento_manual,
    init_db,
    inserir_lancamento_manual,
    inserir_movimentos,
    listar_bancos_extrato,
    listar_importacoes_extrato,
    recategorizar_movimentos,
    intervalo_dados,
    listar_consolidado,
    listar_contas_fixas,
    listar_contas_fixas_mes,
    listar_lancamentos_manuais,
    resumo_mensal,
    resumo_por_categoria,
    atualizar_conta_fixa,
    resumo_salario_contas_fixas,
    salvar_conta_fixa,
    salvar_conta_fixa_mes,
    salvar_salario_mensal,
    saldo_disponivel,
    total_contas_fixas_previsto,
    ultimo_saldo,
)
from financeiro.numbers import parse_br_decimal, parse_decimal_valor
from financeiro.parser import (
    CATEGORIAS_SUGERIDAS,
    categoria_por_historico,
    detectar_banco_extrato,
    parse_extrato_texto,
)
from financeiro.features import (
    TIPOS_ATIVO_INVEST,
    analise_503020,
    calendario_vencimentos,
    comparativo_meses,
    copiar_orcamento_mes,
    definir_tags_lancamento,
    desativar_divida,
    desativar_projeto,
    dre_pessoal,
    aportar_meta,
    aportar_projeto,
    definir_valor_meta,
    definir_valor_projeto,
    excluir_meta,
    excluir_regra_categoria,
    exportar_movimentos_csv,
    listar_ativos,
    listar_contas_bancarias,
    listar_dividas,
    listar_metas,
    listar_metas_alocacao,
    listar_movimentos_investimento,
    listar_projetos,
    listar_regras_categoria,
    listar_tags,
    obter_notificacoes_email,
    obter_regra_503020,
    obter_reserva_multiplicador,
    orcamento_com_alertas,
    registrar_mov_investimento,
    resumo_alertas_sistema,
    resumo_investimentos,
    resumo_reserva_emergencia,
    salvar_ativo,
    salvar_conta_bancaria,
    salvar_divida,
    salvar_meta,
    salvar_meta_alocacao,
    salvar_notificacoes_email,
    salvar_projeto,
    salvar_regra_503020,
    salvar_regra_categoria,
    salvar_reserva_multiplicador,
    salvar_tag,
    sugestao_quitacao_dividas,
    tags_do_lancamento,
    desativar_cartao_credito,
    listar_cartoes_credito,
    listar_compras_cartao,
    registrar_compra_cartao,
    resumo_cartoes_credito,
    salvar_cartao_credito,
)
from financeiro.db import salvar_orcamento, obter_salario_mensal

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
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        raise HTTPException(400, f"Data inválida: {s!r} (use AAAA-MM-DD).") from None


def _parse_mes(s: str | None) -> str:
    ref = (s or date.today().strftime("%Y-%m")).strip()
    if len(ref) != 7 or ref[4] != "-":
        raise HTTPException(400, f"Mês inválido: {s!r} (use AAAA-MM).")
    try:
        y, m = int(ref[:4]), int(ref[5:7])
        if m < 1 or m > 12:
            raise ValueError
    except ValueError:
        raise HTTPException(400, f"Mês inválido: {s!r} (use AAAA-MM).") from None
    return ref


def _parse_filtro(
    banco: str | None = None,
    importacao_id: int | None = None,
    incluir_manuais: str | None = None,
) -> FiltroVisao | None:
    tem_banco = bool(banco and banco.strip())
    tem_imp = importacao_id is not None
    if not tem_banco and not tem_imp:
        if incluir_manuais is None:
            return None
        return FiltroVisao(incluir_manuais=incluir_manuais in ("1", "true", "True"))
    inc = incluir_manuais in ("1", "true", "True") if incluir_manuais is not None else False
    return FiltroVisao(
        banco=banco.strip() if tem_banco else None,
        importacao_id=importacao_id if tem_imp else None,
        incluir_manuais=inc,
    )


class LancamentoIn(BaseModel):
    data: str = Field(..., description="AAAA-MM-DD")
    descricao: str
    valor: str
    tipo: str = Field(..., pattern="^(entrada|saida)$")
    categoria: str = "Outros"


class ExtratoIn(BaseModel):
    texto: str
    banco: str | None = None


class ContaFixaIn(BaseModel):
    nome: str
    valor: str
    categoria: str = "Contas fixas (utilidades)"
    dia_vencimento: int | None = None
    historico_contem: str | None = None
    observacao: str | None = None


class SalarioMensalIn(BaseModel):
    valor: str


class ContaFixaMesIn(BaseModel):
    mes: str
    valor: str
    pago: bool = False
    data_pagamento: str | None = None
    observacao: str | None = None


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
    last_err: Exception | None = None
    for attempt in range(8):
        try:
            init_db()
            return
        except Exception as exc:
            last_err = exc
            if not using_postgres() or attempt == 7:
                break
            time.sleep(min(2**attempt, 10))
    if last_err:
        raise last_err


@app.get("/")
def pagina_inicial() -> FileResponse:
    return FileResponse(PAINEL)


@app.get("/api/health")
def health() -> dict:
    from financeiro.conn import get_conn

    banco = "postgresql" if using_postgres() else "sqlite"
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"ok": True, "banco": banco}
    except Exception as exc:
        raise HTTPException(503, f"Banco indisponível: {exc}") from exc


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
def indicadores(
    de: str | None = None,
    ate: str | None = None,
    banco: str | None = None,
    importacao_id: int | None = None,
    incluir_manuais: str | None = None,
) -> dict:
    di, df = _parse_date(de), _parse_date(ate)
    filtro = _parse_filtro(banco, importacao_id, incluir_manuais)
    ind = calcular_indicadores(di, df, filtro=filtro)
    saldo, origem = saldo_disponivel(filtro=filtro)
    return {
        "entradas": str(ind.total_creditos),
        "saidas": str(ind.total_debitos),
        "liquido": str(ind.saldo_liquido),
        "saldo_extrato": str(saldo),
        "saldo_origem": origem,
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
            "saldo_extrato": _fmt_br(saldo),
            "gastos_fixos": _fmt_br(ind.total_fixas),
            "gastos_variaveis": _fmt_br(ind.total_variaveis),
            "contas_fixas_previsto": _fmt_br(total_contas_fixas_previsto()),
        },
    }


@app.get("/api/resumo/mensal")
def api_resumo_mensal(
    de: str | None = None,
    ate: str | None = None,
    banco: str | None = None,
    importacao_id: int | None = None,
    incluir_manuais: str | None = None,
) -> list[dict]:
    filtro = _parse_filtro(banco, importacao_id, incluir_manuais)
    rows = resumo_mensal(_parse_date(de), _parse_date(ate), filtro=filtro)
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
def api_resumo_categorias(
    de: str | None = None,
    ate: str | None = None,
    banco: str | None = None,
    importacao_id: int | None = None,
    incluir_manuais: str | None = None,
) -> list[dict]:
    filtro = _parse_filtro(banco, importacao_id, incluir_manuais)
    return [
        {"categoria": cat, "entrada": float(c), "saida": float(d)}
        for cat, c, d in resumo_por_categoria(_parse_date(de), _parse_date(ate), filtro=filtro)
    ]


@app.get("/api/movimentos")
def api_movimentos(
    de: str | None = None,
    ate: str | None = None,
    banco: str | None = None,
    importacao_id: int | None = None,
    incluir_manuais: str | None = None,
) -> list[dict]:
    filtro = _parse_filtro(banco, importacao_id, incluir_manuais)
    out = []
    for r in listar_consolidado(_parse_date(de), _parse_date(ate), filtro=filtro):
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
    if not excluir_lancamento_manual(lanc_id=lanc_id):
        raise HTTPException(404, "Lançamento não encontrado.")
    return {"ok": True}


@app.get("/api/lancamentos")
def listar_lancamentos(de: str | None = None, ate: str | None = None) -> list[dict]:
    rows = listar_lancamentos_manuais(_parse_date(de), _parse_date(ate))
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
    banco = (body.banco or "").strip() or detectar_banco_extrato(body.texto)
    ins, dup, imp_id = inserir_movimentos(
        linhas=linhas, categorizar=categoria_por_historico, banco=banco
    )
    recat = recategorizar_movimentos()
    return {
        "lidas": len(linhas),
        "inseridas": ins,
        "duplicadas": dup,
        "importacao_id": imp_id,
        "banco": banco,
        "recategorizados": recat,
    }


@app.get("/api/extratos")
def api_listar_extratos() -> list[dict]:
    return listar_importacoes_extrato()


@app.get("/api/extratos/bancos")
def api_bancos_extrato() -> list[dict]:
    return listar_bancos_extrato()


@app.post("/api/extrato/detectar-banco")
def api_detectar_banco(body: ExtratoIn) -> dict:
    if not body.texto.strip():
        raise HTTPException(400, "Texto do extrato vazio.")
    return {"banco": detectar_banco_extrato(body.texto)}


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


def _contas_fixas_mes_payload(mes: str) -> dict:
    try:
        payload = listar_contas_fixas_mes(mes)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    r = payload["resumo"]
    return {
        **payload,
        "resumo": {
            **{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()},
            "fmt": {
                "total_cadastro": _fmt_br(Decimal(str(r["total_cadastro"]))),
                "total_real": _fmt_br(Decimal(str(r["total_real"]))),
                "total_pago": _fmt_br(Decimal(str(r["total_pago"]))),
                "total_a_pagar": _fmt_br(Decimal(str(r["total_a_pagar"]))),
                "total_vencido": _fmt_br(Decimal(str(r["total_vencido"]))),
            },
        },
        "itens": [
            {
                **item,
                "valor_cadastro": float(item["valor_cadastro"]),
                "valor_real": float(item["valor_real"]),
            }
            for item in payload["itens"]
        ],
    }


@app.get("/api/contas-fixas/mes")
def api_contas_fixas_mes(mes: str | None = None) -> dict:
    ref = _parse_mes(mes)
    return _contas_fixas_mes_payload(ref)


@app.put("/api/contas-fixas/mes/{conta_fixa_id}")
def api_salvar_conta_fixa_mes(conta_fixa_id: int, body: ContaFixaMesIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or v < 0:
        raise HTTPException(400, "Informe um valor válido.")
    dp: date | None = None
    if body.data_pagamento:
        dp = _parse_date(body.data_pagamento)
        if dp is None:
            raise HTTPException(400, "Data de pagamento inválida.")
    try:
        salvar_conta_fixa_mes(
            conta_fixa_id=conta_fixa_id,
            mes=body.mes,
            valor_real=v,
            pago=body.pago,
            data_pagamento=dp,
            observacao=body.observacao,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "mes": _contas_fixas_mes_payload(body.mes)}


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


# --- Planejamento e orçamento ---


class OrcamentoIn(BaseModel):
    mes: str
    categoria: str
    limite: str


class CopiarOrcamentoIn(BaseModel):
    origem: str
    destino: str


class Regra503020In(BaseModel):
    necessidades: int = 50
    desejos: int = 30
    poupanca: int = 20


class RegraCategoriaIn(BaseModel):
    padrao: str
    categoria: str
    prioridade: int = 10


class MetaIn(BaseModel):
    nome: str
    tipo: str = "geral"
    valor_alvo: str | None = None
    valor_atual: str = "0"
    multiplicador_meses: int | None = None
    prazo: str | None = None


class ProjetoIn(BaseModel):
    nome: str
    valor_alvo: str
    valor_acumulado: str = "0"
    aporte_mensal: str | None = None
    prazo: str | None = None


class DividaIn(BaseModel):
    nome: str
    valor_total: str
    valor_pago: str = "0"
    taxa_mensal: str | None = None
    parcelas: int | None = None
    parcelas_pagas: int = 0
    estrategia: str = "minimo"


class AtivoIn(BaseModel):
    nome: str
    tipo: str
    valor_atual: str = "0"
    instituicao: str | None = None


class MovInvestIn(BaseModel):
    ativo_id: int
    data: str
    tipo: str = Field(..., pattern="^(aporte|rendimento|resgate)$")
    valor: str
    observacao: str | None = None


class AlocacaoIn(BaseModel):
    tipo_ativo: str
    percentual: str


class CartaoCreditoIn(BaseModel):
    nome: str
    bandeira: str | None = None
    dia_vencimento: int
    dia_fechamento: int | None = None
    limite: str | None = None


class CompraCartaoIn(BaseModel):
    cartao_id: int
    descricao: str
    valor_total: str
    parcelas: int = 1
    data_compra: str
    primeira_fatura: str
    observacao: str | None = None


class ContaBancoIn(BaseModel):
    nome: str
    tipo: str = "corrente"


class TagIn(BaseModel):
    nome: str


class TagsLancIn(BaseModel):
    tags: list[str]


class NotifIn(BaseModel):
    email: str


class ReservaMultIn(BaseModel):
    multiplicador: int


class AporteIn(BaseModel):
    valor: str


class ValorAcumuladoIn(BaseModel):
    valor: str


@app.get("/api/calendario")
def api_calendario(mes: str | None = None) -> dict:
    ref = _parse_mes(mes)
    y, m = int(ref[:4]), int(ref[5:7])
    cal = calendario_vencimentos(y, m)
    return {
        **cal,
        "total_mes": float(cal["total_mes"]),
        "vence_ate_dia_15": float(cal["vence_ate_dia_15"]),
        "saldo_extrato": float(cal["saldo_extrato"]),
        "saldo_origem": cal["saldo_origem"],
        "itens": [
            {**i, "valor": float(i["valor"])} for i in cal["itens"]
        ],
    }


@app.get("/api/orcamento")
def api_orcamento(mes: str | None = None) -> list[dict]:
    ref = _parse_mes(mes)
    rows = orcamento_com_alertas(ref)
    return [
        {
            **r,
            "limite": float(r["limite"]),
            "gasto": float(r["gasto"]),
            "saldo": float(r["saldo"]),
            "projecao_mes": float(r["projecao_mes"]) if r["projecao_mes"] else None,
        }
        for r in rows
    ]


@app.post("/api/orcamento")
def api_salvar_orcamento(body: OrcamentoIn) -> dict:
    v = parse_br_decimal(body.limite)
    if v is None:
        raise HTTPException(400, "Limite inválido.")
    salvar_orcamento(None, body.mes, body.categoria, v)
    return {"ok": True}


@app.post("/api/orcamento/copiar")
def api_copiar_orcamento(body: CopiarOrcamentoIn) -> dict:
    n = copiar_orcamento_mes(body.origem, body.destino)
    return {"ok": True, "copiados": n}


@app.get("/api/regra-503020")
def api_get_503020() -> dict:
    return obter_regra_503020()


@app.put("/api/regra-503020")
def api_put_503020(body: Regra503020In) -> dict:
    salvar_regra_503020(body.necessidades, body.desejos, body.poupanca)
    return {"ok": True}


@app.get("/api/analise-503020")
def api_analise_503020(mes: str | None = None) -> dict:
    ref = _parse_mes(mes)
    sal = obter_salario_mensal()
    if sal is None:
        raise HTTPException(400, "Cadastre o salário mensal primeiro.")
    return analise_503020(ref, sal)


@app.get("/api/comparativo")
def api_comparativo(mes: str | None = None) -> dict:
    ref = _parse_mes(mes)
    return comparativo_meses(ref)


@app.get("/api/dre")
def api_dre(de: str | None = None, ate: str | None = None) -> dict:
    return dre_pessoal(_parse_date(de), _parse_date(ate))


@app.get("/api/reserva")
def api_reserva() -> dict:
    r = resumo_reserva_emergencia()
    return {
        "multiplicador_meses": r["multiplicador_meses"],
        "despesa_mensal_ref": float(r["despesa_mensal_ref"]),
        "meta_reserva": float(r["meta_reserva"]),
        "saldo_atual": float(r["saldo_atual"]),
        "saldo_origem": r["saldo_origem"],
        "pct_atingido": r["pct_atingido"],
        "falta": float(r["falta"]),
    }


@app.put("/api/reserva/multiplicador")
def api_reserva_mult(body: ReservaMultIn) -> dict:
    salvar_reserva_multiplicador(body.multiplicador)
    return {"ok": True, "reserva": api_reserva()}


@app.get("/api/metas")
def api_listar_metas() -> list[dict]:
    return [
        {
            **m,
            "valor_alvo": float(m["valor_alvo"]) if m["valor_alvo"] is not None else None,
            "valor_atual": float(m["valor_atual"]),
            "falta": float(m["falta"]) if m["falta"] is not None else None,
        }
        for m in listar_metas()
    ]


@app.post("/api/metas")
def api_criar_meta(body: MetaIn) -> dict:
    va = parse_br_decimal(body.valor_alvo) if body.valor_alvo else None
    vc = parse_br_decimal(body.valor_atual) or Decimal(0)
    pr = _parse_date(body.prazo)
    mid = salvar_meta(body.nome, body.tipo, va, vc, body.multiplicador_meses, pr)
    return {"ok": True, "id": mid}


@app.delete("/api/metas/{meta_id}")
def api_del_meta(meta_id: int) -> dict:
    excluir_meta(meta_id)
    return {"ok": True}


@app.post("/api/metas/{meta_id}/aporte")
def api_aportar_meta(meta_id: int, body: AporteIn) -> dict:
    v = parse_br_decimal(body.valor) or parse_decimal_valor(body.valor)
    if v is None or v <= 0:
        raise HTTPException(400, "Informe um valor válido maior que zero.")
    try:
        meta = aportar_meta(meta_id, v)
    except LookupError:
        raise HTTPException(404, "Meta não encontrada.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "ok": True,
        "meta": {
            **meta,
            "valor_alvo": float(meta["valor_alvo"]) if meta["valor_alvo"] is not None else None,
            "valor_atual": float(meta["valor_atual"]),
            "falta": float(meta["falta"]) if meta["falta"] is not None else None,
        },
    }


@app.put("/api/metas/{meta_id}/acumulado")
def api_definir_acumulado_meta(meta_id: int, body: ValorAcumuladoIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or v < 0:
        raise HTTPException(400, "Informe um valor acumulado válido.")
    try:
        meta = definir_valor_meta(meta_id, v)
    except LookupError:
        raise HTTPException(404, "Meta não encontrada.")
    return {
        "ok": True,
        "meta": {
            **meta,
            "valor_alvo": float(meta["valor_alvo"]) if meta["valor_alvo"] is not None else None,
            "valor_atual": float(meta["valor_atual"]),
            "falta": float(meta["falta"]) if meta["falta"] is not None else None,
        },
    }


@app.get("/api/projetos")
def api_projetos() -> list[dict]:
    return [
        {
            **p,
            "valor_alvo": float(p["valor_alvo"]),
            "valor_acumulado": float(p["valor_acumulado"]),
            "aporte_mensal": float(p["aporte_mensal"]) if p["aporte_mensal"] else None,
            "falta": float(p["falta"]),
        }
        for p in listar_projetos()
    ]


@app.post("/api/projetos")
def api_criar_projeto(body: ProjetoIn) -> dict:
    va = parse_br_decimal(body.valor_alvo)
    vc = parse_br_decimal(body.valor_acumulado) or Decimal(0)
    am = parse_br_decimal(body.aporte_mensal) if body.aporte_mensal else None
    if va is None:
        raise HTTPException(400, "Valor alvo inválido.")
    pid = salvar_projeto(body.nome, va, vc, am, _parse_date(body.prazo))
    return {"ok": True, "id": pid}


@app.delete("/api/projetos/{projeto_id}")
def api_del_projeto(projeto_id: int) -> dict:
    desativar_projeto(projeto_id)
    return {"ok": True}


@app.post("/api/projetos/{projeto_id}/aporte")
def api_aportar_projeto(projeto_id: int, body: AporteIn) -> dict:
    v = parse_br_decimal(body.valor) or parse_decimal_valor(body.valor)
    if v is None or v <= 0:
        raise HTTPException(400, "Informe um valor válido maior que zero.")
    try:
        proj = aportar_projeto(projeto_id, v)
    except LookupError:
        raise HTTPException(404, "Projeto não encontrado.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "ok": True,
        "projeto": {
            **proj,
            "valor_alvo": float(proj["valor_alvo"]),
            "valor_acumulado": float(proj["valor_acumulado"]),
            "falta": float(proj["falta"]),
        },
    }


@app.put("/api/projetos/{projeto_id}/acumulado")
def api_definir_acumulado_projeto(projeto_id: int, body: ValorAcumuladoIn) -> dict:
    v = parse_br_decimal(body.valor)
    if v is None or v < 0:
        raise HTTPException(400, "Informe um valor acumulado válido.")
    try:
        proj = definir_valor_projeto(projeto_id, v)
    except LookupError:
        raise HTTPException(404, "Projeto não encontrado.")
    return {
        "ok": True,
        "projeto": {
            **proj,
            "valor_alvo": float(proj["valor_alvo"]),
            "valor_acumulado": float(proj["valor_acumulado"]),
            "falta": float(proj["falta"]),
        },
    }


@app.get("/api/dividas")
def api_dividas() -> list[dict]:
    return [
        {
            **d,
            "valor_total": float(d["valor_total"]),
            "valor_pago": float(d["valor_pago"]),
            "restante": float(d["restante"]),
        }
        for d in listar_dividas()
    ]


@app.post("/api/dividas")
def api_criar_divida(body: DividaIn) -> dict:
    vt = parse_br_decimal(body.valor_total)
    vp = parse_br_decimal(body.valor_pago) or Decimal(0)
    tx = parse_br_decimal(body.taxa_mensal) if body.taxa_mensal else None
    if vt is None:
        raise HTTPException(400, "Valor total inválido.")
    did = salvar_divida(body.nome, vt, vp, tx, body.parcelas, body.parcelas_pagas, body.estrategia)
    return {"ok": True, "id": did}


@app.delete("/api/dividas/{divida_id}")
def api_del_divida(divida_id: int) -> dict:
    desativar_divida(divida_id)
    return {"ok": True}


@app.get("/api/dividas/sugestao")
def api_sugestao_dividas() -> list[dict]:
    return sugestao_quitacao_dividas()


@app.get("/api/investimentos/resumo")
def api_inv_resumo() -> dict:
    r = resumo_investimentos()
    return {
        "patrimonio_total": float(r["patrimonio_total"]),
        "por_tipo": r["por_tipo"],
        "aportes_mes": float(r["aportes_mes"]),
        "rendimentos_mes": float(r["rendimentos_mes"]),
        "qtd_ativos": r["qtd_ativos"],
        "alocacao_meta": r["alocacao_meta"],
        "tipos": TIPOS_ATIVO_INVEST,
    }


@app.get("/api/investimentos/ativos")
def api_inv_ativos() -> list[dict]:
    return [{**a, "valor_atual": float(a["valor_atual"])} for a in listar_ativos()]


@app.post("/api/investimentos/ativos")
def api_criar_ativo(body: AtivoIn) -> dict:
    v = parse_br_decimal(body.valor_atual) or Decimal(0)
    aid = salvar_ativo(body.nome, body.tipo, v, body.instituicao)
    return {"ok": True, "id": aid}


@app.get("/api/investimentos/movimentos")
def api_inv_movs(ativo_id: int | None = None) -> list[dict]:
    return [{**m, "valor": float(m["valor"])} for m in listar_movimentos_investimento(ativo_id)]


@app.post("/api/investimentos/movimentos")
def api_reg_mov_inv(body: MovInvestIn) -> dict:
    v = parse_br_decimal(body.valor)
    d = _parse_date(body.data)
    if v is None or d is None:
        raise HTTPException(400, "Data e valor válidos são obrigatórios.")
    try:
        mid = registrar_mov_investimento(body.ativo_id, d, body.tipo, v, body.observacao)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "id": mid}


@app.put("/api/investimentos/alocacao")
def api_alocacao(body: AlocacaoIn) -> dict:
    p = parse_br_decimal(body.percentual)
    if p is None:
        raise HTTPException(400, "Percentual inválido.")
    salvar_meta_alocacao(body.tipo_ativo, p)
    return {"ok": True}


@app.get("/api/cartoes/resumo")
def api_cartoes_resumo() -> dict:
    r = resumo_cartoes_credito()
    return {
        "qtd_cartoes": r["qtd_cartoes"],
        "qtd_compras": r["qtd_compras"],
        "fatura_mes": float(r["fatura_mes"]),
        "total_em_aberto": float(r["total_em_aberto"]),
        "alertas_vencimento": r["alertas_vencimento"],
    }


@app.get("/api/cartoes")
def api_listar_cartoes() -> list[dict]:
    return [
        {
            **c,
            "limite": float(c["limite"]) if c["limite"] is not None else None,
        }
        for c in listar_cartoes_credito()
    ]


@app.post("/api/cartoes")
def api_criar_cartao(body: CartaoCreditoIn) -> dict:
    limite = parse_br_decimal(body.limite) if body.limite else None
    cid = salvar_cartao_credito(
        nome=body.nome.strip(),
        bandeira=body.bandeira,
        dia_vencimento=body.dia_vencimento,
        dia_fechamento=body.dia_fechamento,
        limite=limite,
    )
    return {"ok": True, "id": cid}


@app.delete("/api/cartoes/{cartao_id}")
def api_desativar_cartao(cartao_id: int) -> dict:
    desativar_cartao_credito(cartao_id)
    return {"ok": True}


@app.get("/api/cartoes/compras")
def api_listar_compras_cartao() -> list[dict]:
    return [
        {
            **c,
            "valor_total": float(c["valor_total"]),
            "parcela_valor": float(c["parcela_valor"]),
        }
        for c in listar_compras_cartao()
    ]


@app.post("/api/cartoes/compras")
def api_registrar_compra_cartao(body: CompraCartaoIn) -> dict:
    valor = parse_br_decimal(body.valor_total) or parse_decimal_valor(body.valor_total)
    d = _parse_date(body.data_compra)
    if valor is None or valor <= 0 or d is None:
        raise HTTPException(400, "Valor e data válidos são obrigatórios.")
    if not body.primeira_fatura or len(body.primeira_fatura) != 7:
        raise HTTPException(400, "Primeira fatura deve estar no formato AAAA-MM.")
    cid = registrar_compra_cartao(
        cartao_id=body.cartao_id,
        descricao=body.descricao.strip(),
        valor_total=valor,
        parcelas=max(body.parcelas, 1),
        data_compra=d,
        primeira_fatura=body.primeira_fatura,
        observacao=body.observacao,
    )
    return {"ok": True, "id": cid}


@app.get("/api/regras-categoria")
def api_regras() -> list[dict]:
    return listar_regras_categoria()


@app.post("/api/regras-categoria")
def api_criar_regra(body: RegraCategoriaIn) -> dict:
    if not body.padrao.strip():
        raise HTTPException(400, "Padrão obrigatório.")
    rid = salvar_regra_categoria(body.padrao, body.categoria, body.prioridade)
    recategorizar_movimentos()
    return {"ok": True, "id": rid}


@app.delete("/api/regras-categoria/{regra_id}")
def api_del_regra(regra_id: int) -> dict:
    excluir_regra_categoria(regra_id)
    recategorizar_movimentos()
    return {"ok": True}


@app.get("/api/contas-bancarias")
def api_contas_banco() -> list[dict]:
    return listar_contas_bancarias()


@app.post("/api/contas-bancarias")
def api_criar_conta_banco(body: ContaBancoIn) -> dict:
    cid = salvar_conta_bancaria(body.nome, body.tipo)
    return {"ok": True, "id": cid}


@app.get("/api/tags")
def api_tags() -> list[dict]:
    return listar_tags()


@app.post("/api/tags")
def api_criar_tag(body: TagIn) -> dict:
    tid = salvar_tag(body.nome)
    return {"ok": True, "id": tid}


@app.put("/api/lancamentos/{lanc_id}/tags")
def api_tags_lanc(lanc_id: int, body: TagsLancIn) -> dict:
    definir_tags_lancamento(lanc_id, body.tags)
    return {"ok": True, "tags": tags_do_lancamento(lanc_id)}


@app.get("/api/notificacoes")
def api_get_notif() -> dict:
    return {"email": obter_notificacoes_email()}


@app.put("/api/notificacoes")
def api_put_notif(body: NotifIn) -> dict:
    salvar_notificacoes_email(body.email)
    return {"ok": True}


@app.get("/api/alertas")
def api_alertas(mes: str | None = None) -> list[dict]:
    ref = _parse_mes(mes)
    return resumo_alertas_sistema(ref)


@app.get("/api/export/movimentos")
def api_export(
    de: str | None = None,
    ate: str | None = None,
    banco: str | None = None,
    importacao_id: int | None = None,
    incluir_manuais: str | None = None,
) -> PlainTextResponse:
    filtro = _parse_filtro(banco, importacao_id, incluir_manuais)
    csv_data = exportar_movimentos_csv(_parse_date(de), _parse_date(ate), filtro=filtro)
    return PlainTextResponse(csv_data, media_type="text/csv; charset=utf-8")
