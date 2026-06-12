"""
Painel financeiro completo: extrato, contas fixas, lançamentos manuais e dashboard.
Execute: streamlit run app.py
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from financeiro.auth import authenticate
from financeiro.config import user_sqlite_path
from financeiro.context import current_user_id
from financeiro.db import (
    atualizar_lancamento_manual,
    calcular_indicadores,
    desativar_conta_fixa,
    excluir_importacao_extrato,
    excluir_lancamento_manual,
    init_db,
    inserir_lancamento_manual,
    inserir_movimentos,
    intervalo_dados,
    listar_contas_fixas,
    listar_importacoes_extrato,
    resumo_salario_contas_fixas,
    salvar_salario_mensal,
    listar_lancamentos_manuais,
    listar_movimentos,
    listar_orcamento_mes,
    recategorizar_movimentos,
    resumo_mensal,
    resumo_por_categoria,
    atualizar_conta_fixa,
    salvar_conta_fixa,
    salvar_orcamento,
    saldo_disponivel,
    total_contas_fixas_previsto,
    ultimo_saldo,
)
from financeiro.ui_tabs import tab_config, tab_dividas, tab_investimentos, tab_metas, tab_planejamento, tab_reserva
from financeiro.parser import (
    CATEGORIAS_SUGERIDAS,
    categoria_por_historico,
    detectar_banco_extrato,
    parse_extrato_texto,
)

ROOT = Path(__file__).resolve().parent

_PREMIUM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: "Plus Jakarta Sans", sans-serif !important; }
.stApp {
  background: linear-gradient(180deg, #060910 0%, #0a0f1a 50%, #080c14 100%);
}
[data-testid="stSidebar"] {
  background: rgba(17, 24, 39, 0.95) !important;
  border-right: 1px solid rgba(255,255,255,0.08);
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 { color: #d4af37 !important; }
h1, h2, h3 { letter-spacing: -0.02em; }
[data-testid="stMetric"] {
  background: rgba(26, 35, 50, 0.65);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  padding: 0.85rem 1rem;
  box-shadow: 0 8px 32px rgba(0,0,0,0.25);
}
[data-testid="stMetric"] label { color: #94a3b8 !important; font-size: 0.72rem !important;
  text-transform: uppercase; letter-spacing: 0.04em; }
[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: #f1f5f9 !important; font-weight: 700 !important;
}
.stTabs [data-baseweb="tab-list"] {
  gap: 0.35rem;
  background: transparent;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.stTabs [data-baseweb="tab"] {
  background: rgba(26, 35, 50, 0.5);
  border-radius: 10px 10px 0 0;
  border: 1px solid rgba(255,255,255,0.06);
  color: #94a3b8;
  font-weight: 500;
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, rgba(212,175,55,0.2), rgba(212,175,55,0.05)) !important;
  color: #f1f5f9 !important;
  border-color: rgba(212,175,55,0.3) !important;
}
div[data-testid="stForm"] {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  padding: 1rem;
  background: rgba(26, 35, 50, 0.4);
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #e8c547, #a67c00) !important;
  color: #0a0f1a !important;
  border: none !important;
  font-weight: 600 !important;
  border-radius: 10px !important;
}
.stButton > button[kind="primary"]:hover {
  box-shadow: 0 6px 20px rgba(212, 175, 55, 0.35);
}
</style>
"""
EXEMPLO_PATH = ROOT / "data" / "exemplo_extrato.txt"


def _db_path() -> Path:
    uid = st.session_state.get("user_id")
    return user_sqlite_path(uid) if uid else ROOT / "data" / "financeiro.db"


_LOGIN_CSS = """
<style>
.login-wrap {
  max-width: 400px;
  margin: 4rem auto;
  padding: 2rem;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(26, 35, 50, 0.55);
}
</style>
"""


def _tela_login() -> bool:
    """Retorna True quando o usuário está autenticado."""
    if st.session_state.get("user_id"):
        return True

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown("## seOrganize")
    st.caption("Entre com sua conta para acessar seus dados.")

    with st.form("login"):
        email = st.text_input("E-mail", placeholder="seu@email.com")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            user = authenticate(email, senha)
            if not user:
                st.error("E-mail ou senha incorretos.")
            else:
                st.session_state.user_id = user["id"]
                st.session_state.user_nome = user["nome"]
                st.rerun()
    return False


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
    int_br = ".".join(reversed(chunks))
    out = f"{int_br},{frac:02d}"
    return ("-" if neg else "") + out


def _parse_valor(s: str) -> Decimal | None:
    from financeiro.numbers import parse_br_decimal

    return parse_br_decimal(s)


def _filtro_periodo() -> tuple[date, date]:
    mi, ma = intervalo_dados()
    hoje = date.today()
    default_ini = mi or date(hoje.year, hoje.month, 1)
    default_fim = ma or hoje
    c1, c2 = st.sidebar.columns(2)
    with c1:
        di = st.date_input("De", value=default_ini, key="filtro_de")
    with c2:
        df = st.date_input("Até", value=default_fim, key="filtro_ate")
    if di > df:
        st.sidebar.warning("Data inicial maior que a final; ajuste o período.")
    return di, df


def _tab_dashboard(di: date, df: date) -> None:
    db = _db_path()
    ind = calcular_indicadores(di, df, db)
    saldo_banco, origem_saldo = saldo_disponivel(db)
    previsto_fixas = total_contas_fixas_previsto()

    st.subheader("Indicadores do período")
    r1 = st.columns(4)
    r1[0].metric("Entradas (créditos)", _fmt_br(ind.total_creditos))
    r1[1].metric("Saídas (débitos)", _fmt_br(ind.total_debitos))
    r1[2].metric("Resultado líquido", _fmt_br(ind.saldo_liquido))
    r1[3].metric(
        "Saldo disponível",
        _fmt_br(saldo_banco),
        help="Coluna saldo do extrato ou, se indisponível (ex.: Nubank CSV), entradas − saídas.",
    )

    r2 = st.columns(4)
    r2[0].metric("Gastos fixos (estim.)", _fmt_br(ind.total_fixas))
    r2[1].metric("Gastos variáveis", _fmt_br(ind.total_variaveis))
    r2[2].metric(
        "Contas fixas cadastradas / mês",
        _fmt_br(previsto_fixas),
        help="Soma dos valores das contas fixas ativas no cadastro",
    )
    r2[3].metric("Ticket médio (débito)", _fmt_br(ind.ticket_medio_debito))

    r3 = st.columns(4)
    if ind.pct_fixas is not None:
        r3[0].metric("% fixas nos débitos", f"{ind.pct_fixas:.1f}%")
        r3[1].metric("% variáveis nos débitos", f"{ind.pct_variaveis:.1f}%")
    r3[2].metric("Maior débito", _fmt_br(ind.maior_debito))
    r3[3].metric("Média diária de gastos", _fmt_br(ind.media_diaria_gastos))

    plan = resumo_salario_contas_fixas(db)
    if plan["salario_mensal"] is not None or plan["total_contas_fixas"] > 0:
        st.caption("Salário x contas fixas (mensal)")
        rf = st.columns(4)
        rf[0].metric(
            "Salário fixo",
            _fmt_br(plan["salario_mensal"]) if plan["salario_mensal"] is not None else "—",
        )
        rf[1].metric("Contas fixas (prev.)", _fmt_br(plan["total_contas_fixas"]))
        if plan["salario_mensal"] is None:
            rf[2].metric("Sobra / falta", "—")
        elif plan["sobra"] is not None:
            rf[2].metric("Sobra estimada", _fmt_br(plan["sobra"]))
        else:
            rf[2].metric("Falta no mês", _fmt_br(plan["falta"]))
        rf[3].metric(
            "% do salário",
            f"{plan['pct_comprometido']:.1f}%" if plan["pct_comprometido"] is not None else "—",
        )

    if ind.total_manuais_entrada or ind.total_manuais_saida:
        st.caption(
            f"Lançamentos manuais no período: entradas {_fmt_br(ind.total_manuais_entrada)} · "
            f"saídas {_fmt_br(ind.total_manuais_saida)}"
        )

    mensal = resumo_mensal(di, df)
    if mensal:
        st.subheader("Evolução mensal")
        df_chart = pd.DataFrame(
            {
                "Mês": [m.mes for m in mensal],
                "Entradas": [float(m.creditos) for m in mensal],
                "Saídas": [float(m.debitos) for m in mensal],
                "Líquido": [float(m.liquido) for m in mensal],
            }
        )
        c1, c2 = st.columns(2)
        with c1:
            st.bar_chart(df_chart.set_index("Mês")[["Entradas", "Saídas"]])
        with c2:
            st.line_chart(df_chart.set_index("Mês")[["Líquido"]])

    res = resumo_por_categoria(di, df)
    if res:
        st.subheader("Distribuição por categoria (saídas)")
        top = sorted(res, key=lambda x: x[2], reverse=True)[:10]
        df_cat = pd.DataFrame(
            {"Categoria": [c for c, _, _ in top], "Débito": [float(d) for _, _, d in top]}
        )
        st.bar_chart(df_cat.set_index("Categoria"))


def _tab_importar() -> None:
    st.write("Cole o extrato exportado do banco ou envie um arquivo `.txt` / `.csv`.")
    up = st.file_uploader("Arquivo de extrato", type=["txt", "csv"])
    default_txt = EXEMPLO_PATH.read_text(encoding="utf-8") if EXEMPLO_PATH.exists() else ""
    texto_upload = ""
    if up:
        texto_upload = up.read().decode("utf-8", errors="replace")
    texto = st.text_area("Conteúdo do extrato", value=texto_upload or default_txt, height=280)
    if st.button("Processar e gravar no banco", type="primary"):
        linhas = parse_extrato_texto(texto)
        if not linhas:
            st.warning("Nenhuma linha com data (dd/mm/aaaa) foi encontrada.")
        else:
            banco = detectar_banco_extrato(texto)
            ins, dup, _ = inserir_movimentos(_db_path(), linhas, categoria_por_historico, banco=banco)
            recategorizar_movimentos(_db_path())
            st.success(
                f"{len(linhas)} linhas lidas; {ins} novas gravadas; {dup} duplicadas ignoradas."
                + (f" Banco: {banco}." if banco else "")
            )


def _tab_movimentos(di: date, df: date) -> None:
    cats = [""] + sorted({r["categoria"] for r in listar_movimentos()})
    cat_f = st.selectbox("Filtrar categoria", cats, format_func=lambda x: x or "Todas")
    rows = listar_movimentos(di, df, cat_f or None)
    if not rows:
        st.info("Sem movimentos no período.")
        return
    st.dataframe(
        [
            {
                "Data": r["data"],
                "Histórico": r["historico"],
                "Docto.": r["docto"],
                "Crédito": _fmt_br(_parse_valor(r["credito"])) if r["credito"] else "",
                "Débito": _fmt_br(_parse_valor(r["debito"])) if r["debito"] else "",
                "Saldo": _fmt_br(_parse_valor(r["saldo"])) if r["saldo"] else "",
                "Categoria": r["categoria"],
            }
            for r in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _tab_resumo(di: date, df: date) -> None:
    res = resumo_por_categoria(di, df)
    if not res:
        st.info("Sem dados no período.")
        return
    tot_c = sum((c for _, c, _ in res), Decimal(0))
    tot_d = sum((d for _, _, d in res), Decimal(0))
    m1, m2, m3 = st.columns(3)
    m1.metric("Total entradas", _fmt_br(tot_c))
    m2.metric("Total saídas", _fmt_br(tot_d))
    m3.metric("Líquido", _fmt_br(tot_c - tot_d))
    st.table(
        [{"Categoria": cat, "Entrada": _fmt_br(c), "Saída": _fmt_br(d)} for cat, c, d in res]
    )





def _render_planejamento_salario() -> None:
    res = resumo_salario_contas_fixas(_db_path())
    with st.form("salario_mensal"):
        st.subheader("Salário fixo mensal")
        sal_txt = st.text_input(
            "Quanto você recebe por mês (R$)",
            value=_fmt_br(res["salario_mensal"]) if res["salario_mensal"] is not None else "",
            placeholder="5.000,00",
        )
        if st.form_submit_button("Salvar salário", type="primary"):
            v = _parse_valor(sal_txt)
            if v is None or v <= 0:
                st.error("Informe um salário válido maior que zero.")
            else:
                salvar_salario_mensal(v, _db_path())
                st.success("Salário salvo.")
                st.rerun()

    if res["salario_mensal"] is None:
        st.info("Cadastre seu salário para ver quanto sobra ou falta após as contas fixas.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Salário mensal", _fmt_br(res["salario_mensal"]))
    c2.metric("Contas fixas (previsto)", _fmt_br(res["total_contas_fixas"]))
    if res["sobra"] is not None:
        c3.metric("Sobra no mês", _fmt_br(res["sobra"]), delta="disponível", delta_color="normal")
        c4.metric("% comprometido", f"{res['pct_comprometido']:.1f}%")
    else:
        c3.metric("Falta no mês", _fmt_br(res["falta"]), delta="déficit", delta_color="inverse")
        c4.metric("% comprometido", f"{res['pct_comprometido']:.1f}%")
    if res["pct_comprometido"] is not None:
        pct = min(float(res["pct_comprometido"]), 100.0)
        st.progress(pct / 100.0, text=f"Contas fixas consomem {res['pct_comprometido']:.1f}% do salário")
    st.divider()


def _tab_contas_fixas() -> None:
    st.caption(
        "Cadastre seu salário e as despesas recorrentes (aluguel, internet, etc.). "
        "Use **texto no histórico** para o sistema classificar débitos do extrato como gasto fixo."
    )
    _render_planejamento_salario()
    with st.form("nova_conta_fixa"):
        nome = st.text_input("Nome", placeholder="Ex.: Internet fibra")
        valor = st.text_input("Valor mensal (R$)", placeholder="99,90")
        dia = st.number_input("Dia de vencimento (opcional)", min_value=1, max_value=31, value=10)
        cat = st.selectbox("Categoria", CATEGORIAS_SUGERIDAS, index=2)
        hist = st.text_input(
            "Contém no histórico do banco (opcional)",
            placeholder="Ex.: INTERNET",
            help="Se o extrato trouxer essa palavra no histórico, o débito entra como gasto fixo",
        )
        obs = st.text_input("Observação")
        if st.form_submit_button("Salvar conta fixa"):
            v = _parse_valor(valor)
            if not nome or v is None:
                st.error("Informe nome e valor válido.")
            else:
                salvar_conta_fixa(_db_path(), nome, v, cat, int(dia), hist or None, obs or None)
                st.success("Conta fixa salva.")
                st.rerun()

    if "edit_conta_fixa_id" not in st.session_state:
        st.session_state.edit_conta_fixa_id = None

    edit_cx = st.session_state.edit_conta_fixa_id
    if edit_cx is not None:
        alvo = next(
            (r for r in listar_contas_fixas(_db_path(), apenas_ativas=False) if r["id"] == edit_cx and r["ativo"]),
            None,
        )
        if alvo is None:
            st.session_state.edit_conta_fixa_id = None
            st.rerun()
        st.subheader("Editar conta fixa")
        with st.form("edit_conta_fixa"):
            nome_e = st.text_input("Nome", value=alvo["nome"], key="edit_cx_nome")
            valor_e = st.text_input(
                "Valor mensal (R$)",
                value=_fmt_br(_parse_valor(alvo["valor"])),
                key="edit_cx_val",
            )
            dia_e = st.number_input(
                "Dia de vencimento",
                min_value=1,
                max_value=31,
                value=int(alvo["dia_vencimento"] or 5),
                key="edit_cx_dia",
            )
            cat_e = st.selectbox(
                "Categoria",
                CATEGORIAS_SUGERIDAS,
                index=CATEGORIAS_SUGERIDAS.index(alvo["categoria"])
                if alvo["categoria"] in CATEGORIAS_SUGERIDAS
                else 0,
                key="edit_cx_cat",
            )
            hist_e = st.text_input(
                "Contém no histórico do banco",
                value=alvo["historico_contem"] or "",
                key="edit_cx_hist",
            )
            obs_e = st.text_input("Observação", value=alvo["observacao"] or "", key="edit_cx_obs")
            c_ok, c_cancel = st.columns(2)
            salvar_e = c_ok.form_submit_button("Salvar alterações", type="primary")
            cancelar_e = c_cancel.form_submit_button("Cancelar")
            if cancelar_e:
                st.session_state.edit_conta_fixa_id = None
                st.rerun()
            if salvar_e:
                v = _parse_valor(valor_e)
                if not nome_e or v is None:
                    st.error("Informe nome e valor válido.")
                elif atualizar_conta_fixa(
                    _db_path(),
                    edit_cx,
                    nome_e,
                    v,
                    cat_e,
                    int(dia_e),
                    hist_e or None,
                    obs_e or None,
                ):
                    st.session_state.edit_conta_fixa_id = None
                    st.success("Conta fixa atualizada.")
                    st.rerun()
                else:
                    st.error("Conta fixa não encontrada.")
        st.divider()

    rows = listar_contas_fixas(_db_path(), apenas_ativas=False)
    st.subheader("Contas fixas cadastradas")
    if not rows:
        st.info("Nenhuma conta fixa cadastrada.")
        st.metric("Total previsto (contas ativas)", _fmt_br(total_contas_fixas_previsto(_db_path())))
        return
    for r in rows:
        cols = st.columns([3, 1, 1, 1])
        status = "ativa" if r["ativo"] else "inativa"
        cols[0].write(
            f"**{r['nome']}** ({status}) — {_fmt_br(_parse_valor(r['valor']))}/mês · "
            f"venc. dia {r['dia_vencimento'] or '—'} · {r['categoria']}"
        )
        if r["historico_contem"]:
            cols[0].caption(f"Histórico contém: `{r['historico_contem']}`")
        if r["ativo"]:
            if cols[2].button("Editar", key=f"edit_cx_{r['id']}"):
                st.session_state.edit_conta_fixa_id = r["id"]
                st.rerun()
            if cols[3].button("Desativar", key=f"off_{r['id']}"):
                desativar_conta_fixa(_db_path(), r["id"])
                st.rerun()
    res = resumo_salario_contas_fixas(_db_path())
    st.metric("Total previsto (contas ativas)", _fmt_br(res["total_contas_fixas"]))
    if res["salario_mensal"] is not None:
        if res["sobra"] is not None:
            st.success(f"Sobra estimada após contas fixas: {_fmt_br(res['sobra'])}")
        else:
            st.error(f"As contas fixas ultrapassam o salário em {_fmt_br(res['falta'])}")


def _tab_manuais(di: date, df: date) -> None:
    st.caption("Registre entradas e saídas que ainda não aparecem no extrato (dinheiro, outro banco, etc.).")
    with st.form("lanc_manual"):
        d = st.date_input("Data", value=date.today())
        desc = st.text_input("Descrição")
        val = st.text_input("Valor (R$)", placeholder="150,00")
        tipo = st.radio("Tipo", ["entrada", "saida"], horizontal=True)
        cat = st.selectbox("Categoria", CATEGORIAS_SUGERIDAS)
        if st.form_submit_button("Incluir lançamento"):
            v = _parse_valor(val)
            if not desc or v is None:
                st.error("Preencha descrição e valor.")
            else:
                inserir_lancamento_manual(_db_path(), d, desc, v, tipo, cat)
                st.success("Lançamento incluído.")
                st.rerun()

    if "edit_lanc_id" not in st.session_state:
        st.session_state.edit_lanc_id = None

    edit_id = st.session_state.edit_lanc_id
    if edit_id is not None:
        alvo = next((r for r in listar_lancamentos_manuais(di, df) if r["id"] == edit_id), None)
        if alvo is None:
            st.session_state.edit_lanc_id = None
            st.rerun()
        st.subheader("Editar lançamento")
        with st.form("edit_lanc_manual"):
            d = st.date_input("Data", value=date.fromisoformat(str(alvo["data"])[:10]), key="edit_lanc_data")
            desc = st.text_input("Descrição", value=alvo["descricao"], key="edit_lanc_desc")
            val = st.text_input(
                "Valor (R$)",
                value=_fmt_br(_parse_valor(alvo["valor"])),
                key="edit_lanc_val",
            )
            tipo = st.radio(
                "Tipo",
                ["entrada", "saida"],
                index=0 if alvo["tipo"] == "entrada" else 1,
                horizontal=True,
                key="edit_lanc_tipo",
            )
            cat = st.selectbox(
                "Categoria",
                CATEGORIAS_SUGERIDAS,
                index=CATEGORIAS_SUGERIDAS.index(alvo["categoria"])
                if alvo["categoria"] in CATEGORIAS_SUGERIDAS
                else 0,
                key="edit_lanc_cat",
            )
            c_ok, c_cancel = st.columns(2)
            salvar = c_ok.form_submit_button("Salvar alterações", type="primary")
            cancelar = c_cancel.form_submit_button("Cancelar")
            if cancelar:
                st.session_state.edit_lanc_id = None
                st.rerun()
            if salvar:
                v = _parse_valor(val)
                if not desc or v is None:
                    st.error("Preencha descrição e valor.")
                elif atualizar_lancamento_manual(
                    _db_path(), edit_id, d, desc, v, tipo, cat
                ):
                    st.session_state.edit_lanc_id = None
                    st.success("Lançamento atualizado.")
                    st.rerun()
                else:
                    st.error("Lançamento não encontrado.")
        st.divider()

    rows = listar_lancamentos_manuais(di, df)
    if not rows:
        st.info("Nenhum lançamento manual no período.")
        return
    for r in rows:
        c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
        sinal = "+" if r["tipo"] == "entrada" else "−"
        c1.write(f"{r['data']} · **{r['descricao']}** · {r['categoria']}")
        c2.write(f"{sinal} {_fmt_br(_parse_valor(r['valor']))}")
        if c3.button("Editar", key=f"edit_man_{r['id']}"):
            st.session_state.edit_lanc_id = r["id"]
            st.rerun()
        if c4.button("Excluir", key=f"del_man_{r['id']}"):
            excluir_lancamento_manual(_db_path(), r["id"])
            st.rerun()


def _tab_extratos() -> None:
    st.caption("Cada importação de extrato fica registrada aqui. Excluir remove todos os movimentos daquele import.")
    rows = listar_importacoes_extrato(_db_path())
    if not rows:
        st.info("Nenhum extrato importado ainda.")
        return
    for r in rows:
        cols = st.columns([4, 2, 1])
        if r["legado"]:
            titulo = f"**Importação antiga** (sem registro de lote)"
        else:
            quando = r["criado_em"] or "—"
            titulo = f"**Importação #{r['id']}** · {quando}"
        periodo = ""
        if r["data_min"] and r["data_max"]:
            periodo = f" · período {r['data_min']} a {r['data_max']}"
        cols[0].write(
            f"{titulo}{periodo}\n\n"
            f"Lidas: {r['qtd_lidas']} · gravadas: {r['qtd_inseridas']} · "
            f"duplicadas: {r['qtd_duplicadas']} · movimentos no banco: {r['qtd_movimentos']}"
        )
        key = f"del_imp_{r['id']}"
        if cols[2].button("Excluir extrato", key=key, type="secondary"):
            n = excluir_importacao_extrato(_db_path(), r["id"])
            st.success(f"Extrato excluído ({n} movimentos removidos).")
            st.rerun()


def _tab_orcamento() -> None:
    hoje = date.today()
    mes = st.text_input("Mês (AAAA-MM)", value=hoje.strftime("%Y-%m"))
    with st.form("orc"):
        cat = st.selectbox("Categoria", CATEGORIAS_SUGERIDAS, key="orc_cat")
        lim = st.text_input("Limite de gasto (R$)")
        if st.form_submit_button("Definir limite"):
            v = _parse_valor(lim)
            if v is None:
                st.error("Valor inválido.")
            else:
                salvar_orcamento(_db_path(), mes, cat, v)
                st.success("Orçamento salvo.")
                st.rerun()

    orc = listar_orcamento_mes(_db_path(), mes)
    if not orc:
        st.info("Sem limites definidos para este mês.")
        return

    di = date.fromisoformat(f"{mes}-01")
    if mes[5:7] == "12":
        df = date(int(mes[:4]), 12, 31)
    else:
        prox = date(int(mes[:4]), int(mes[5:7]) + 1, 1)
        df = date.fromordinal(prox.toordinal() - 1)

    gastos = {c: d for c, _, d in resumo_por_categoria(di, df)}
    linhas = []
    for row in orc:
        cat = row["categoria"]
        limite = _parse_valor(row["limite"]) or Decimal(0)
        gasto = gastos.get(cat, Decimal(0))
        pct = (gasto / limite * 100) if limite else Decimal(0)
        linhas.append(
            {
                "Categoria": cat,
                "Limite": _fmt_br(limite),
                "Gasto": _fmt_br(gasto),
                "Uso %": f"{pct:.0f}%",
                "Saldo": _fmt_br(limite - gasto),
            }
        )
    st.table(linhas)


def main() -> None:
    st.set_page_config(
        page_title="seOrganize",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_PREMIUM_CSS, unsafe_allow_html=True)

    if not _tela_login():
        return

    uid = st.session_state.user_id
    ctx = current_user_id.set(uid)
    try:
        _run_app()
    finally:
        current_user_id.reset(ctx)


def _run_app() -> None:
    st.markdown("## seOrganize")
    st.caption(
        "Extrato · contas fixas · orçamento · reserva · metas · investimentos · planejamento"
    )

    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    init_db(db)

    nome = st.session_state.get("user_nome", "")
    st.sidebar.markdown(f"**{nome}**")
    if st.sidebar.button("Sair"):
        for key in ("user_id", "user_nome"):
            st.session_state.pop(key, None)
        st.rerun()
    st.sidebar.divider()
    st.sidebar.markdown("### Período de análise")
    di, df = _filtro_periodo()
    st.sidebar.divider()
    st.sidebar.markdown(
        "**Dica:** cadastre contas fixas com palavras do histórico do banco "
        "para separar gastos fixos e variáveis no dashboard."
    )

    tabs = st.tabs(
        [
            "Dashboard",
            "Importar extrato",
            "Extratos",
            "Movimentos",
            "Resumo",
            "Contas fixas",
            "Lançamentos manuais",
            "Orçamento",
            "Planejamento",
            "Reserva",
            "Metas",
            "Investimentos",
            "Dívidas",
            "Configurações",
        ]
    )
    with tabs[0]:
        _tab_dashboard(di, df)
    with tabs[1]:
        _tab_importar()
    with tabs[2]:
        _tab_extratos()
    with tabs[3]:
        _tab_movimentos(di, df)
    with tabs[4]:
        _tab_resumo(di, df)
    with tabs[5]:
        _tab_contas_fixas()
    with tabs[6]:
        _tab_manuais(di, df)
    with tabs[7]:
        _tab_orcamento()
    with tabs[8]:
        tab_planejamento(db, di, df)
    with tabs[9]:
        tab_reserva(db)
    with tabs[10]:
        tab_metas(db)
    with tabs[11]:
        tab_investimentos(db)
    with tabs[12]:
        tab_dividas(db)
    with tabs[13]:
        tab_config(db)


if __name__ == "__main__":
    main()
