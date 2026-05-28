"""Abas Streamlit para funcionalidades estendidas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st

from financeiro.db import (
    obter_salario_mensal,
    resumo_por_categoria,
    salvar_orcamento,
)
from financeiro.features import (
    TIPOS_ATIVO_INVEST,
    analise_503020,
    calendario_vencimentos,
    comparativo_meses,
    copiar_orcamento_mes,
    definir_tags_lancamento,
    desativar_divida,
    aportar_meta,
    aportar_projeto,
    definir_valor_meta,
    definir_valor_projeto,
    desativar_projeto,
    dre_pessoal,
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
)
from financeiro.parser import CATEGORIAS_SUGERIDAS


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


def _parse_valor(s: str) -> Decimal | None:
    from financeiro.numbers import parse_br_decimal

    return parse_br_decimal(s)


def tab_planejamento(db_path, di: date, df: date) -> None:
    hoje = date.today()
    mes = st.text_input("Mês (AAAA-MM)", value=hoje.strftime("%Y-%m"), key="pl_mes")

    st.subheader("Calendário de vencimentos")
    y, m = int(mes[:4]), int(mes[5:7])
    cal = calendario_vencimentos(y, m, db_path)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total do mês", _fmt_br(cal["total_mes"]))
    c2.metric("Vence até dia 15", _fmt_br(cal["vence_ate_dia_15"]))
    c3.metric("Saldo extrato", _fmt_br(cal["saldo_extrato"]))
    for item in cal["itens"]:
        st.write(f"**Dia {item['dia']}** · {item['nome']} · {_fmt_br(item['valor'])}")

    st.divider()
    st.subheader("Orçamento com alertas")
    col_a, col_b = st.columns(2)
    with col_a:
        with st.form("orc_novo"):
            cat = st.selectbox("Categoria", CATEGORIAS_SUGERIDAS, key="orc_pl_cat")
            lim = st.text_input("Limite (R$)")
            if st.form_submit_button("Definir limite"):
                v = _parse_valor(lim)
                if v is None:
                    st.error("Valor inválido.")
                else:
                    salvar_orcamento(db_path, mes, cat, v)
                    st.success("Salvo.")
                    st.rerun()
    with col_b:
        origem = st.text_input("Copiar de (AAAA-MM)", value=mes)
        if st.button("Copiar orçamento do mês anterior"):
            y2, m2 = int(mes[:4]), int(mes[5:7])
            ant = f"{y2 - 1}-12" if m2 == 1 else f"{y2}-{m2 - 1:02d}"
            n = copiar_orcamento_mes(origem or ant, mes, db_path)
            st.success(f"{n} categorias copiadas.")
            st.rerun()

    linhas = orcamento_com_alertas(mes, db_path)
    if linhas:
        st.table(
            [
                {
                    "Categoria": o["categoria"],
                    "Limite": _fmt_br(o["limite"]),
                    "Gasto": _fmt_br(o["gasto"]),
                    "Uso %": f"{o['pct']:.0f}%",
                    "Alerta": o["alerta"],
                    "Projeção mês": _fmt_br(o["projecao_mes"]) if o["projecao_mes"] else "—",
                }
                for o in linhas
            ]
        )
    else:
        st.info("Sem limites para este mês.")

    st.divider()
    st.subheader("Regra 50/30/20")
    regra = obter_regra_503020(db_path)
    with st.form("503020"):
        n1 = st.number_input("Necessidades %", value=regra["necessidades"], min_value=0, max_value=100)
        n2 = st.number_input("Desejos %", value=regra["desejos"], min_value=0, max_value=100)
        n3 = st.number_input("Poupança %", value=regra["poupanca"], min_value=0, max_value=100)
        if st.form_submit_button("Salvar regra"):
            salvar_regra_503020(int(n1), int(n2), int(n3), db_path)
            st.success("Regra salva.")
            st.rerun()
    sal = obter_salario_mensal(db_path)
    if sal:
        a = analise_503020(mes, sal, db_path)
        st.json(a)

    st.divider()
    st.subheader("Comparativo mês a mês")
    comp = comparativo_meses(mes, db_path)
    st.write(f"**{comp['mes_atual']}** vs **{comp['mes_anterior']}**")
    st.table(
        {
            "": ["Entradas", "Saídas", "Líquido"],
            comp["mes_atual"]: [
                _fmt_br(Decimal(str(comp["atual"]["entradas"]))),
                _fmt_br(Decimal(str(comp["atual"]["saidas"]))),
                _fmt_br(Decimal(str(comp["atual"]["liquido"]))),
            ],
            "Variação": [
                _fmt_br(Decimal(str(comp["variacao"]["entradas"]))),
                _fmt_br(Decimal(str(comp["variacao"]["saidas"]))),
                _fmt_br(Decimal(str(comp["variacao"]["liquido"]))),
            ],
        }
    )

    st.subheader("DRE pessoal (período)")
    dre = dre_pessoal(di, df, db_path)
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Receitas", _fmt_br(Decimal(str(dre["receitas"]))))
    d2.metric("Essenciais", _fmt_br(Decimal(str(dre["despesas_essenciais"]))))
    d3.metric("Discricionárias", _fmt_br(Decimal(str(dre["despesas_discricionarias"]))))
    d4.metric("Resultado", _fmt_br(Decimal(str(dre["resultado"]))))


def tab_reserva(db_path) -> None:
    st.subheader("Reserva de emergência")
    st.caption(
        "Colchão financeiro para imprevistos. O progresso acompanha seu **saldo disponível** "
        "(extrato ou entradas − saídas) — não precisa registrar aportes manualmente."
    )
    st.info(
        "A meta é calculada como **N × total das contas fixas**. "
        "Cadastre suas contas fixas em **Contas fixas** para a meta fazer sentido."
    )
    mult = obter_reserva_multiplicador(db_path)
    novo_mult = st.number_input(
        "Quantos meses de despesas fixas você quer guardar?",
        value=mult,
        min_value=1,
        max_value=24,
        help="Regra comum: 6 meses.",
    )
    if st.button("Salvar meta de reserva", type="primary"):
        salvar_reserva_multiplicador(int(novo_mult), db_path)
        st.success("Meta de reserva atualizada.")
        st.rerun()

    res = resumo_reserva_emergencia(db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meta (N × fixas)", _fmt_br(res["meta_reserva"]))
    c2.metric("Saldo disponível", _fmt_br(res["saldo_atual"]))
    c3.metric("% atingido", f"{res['pct_atingido']:.1f}%")
    c4.metric("Falta juntar", _fmt_br(res["falta"]))
    if res.get("saldo_origem") == "calculado":
        st.caption("Saldo calculado a partir das movimentações (extrato sem coluna saldo).")
    elif res.get("saldo_origem") == "extrato":
        st.caption("Saldo lido da coluna saldo do extrato importado.")
    st.progress(min(res["pct_atingido"] / 100, 1.0))


def tab_metas(db_path) -> None:
    st.subheader("Metas e projetos")
    st.caption(
        "Objetivos com valor alvo (apartamento, viagem, etc.). "
        "Registre um **aporte** sempre que guardar dinheiro — o valor é somado ao acumulado."
    )

    st.subheader("Metas personalizadas")
    with st.form("nova_meta"):
        nome = st.text_input("Nome da meta", placeholder="Ex.: Entrada do apartamento")
        alvo = st.text_input("Quanto você quer juntar (R$)", placeholder="20.000,00")
        atual = st.text_input("Quanto já tem guardado hoje (R$)", value="0,00")
        if st.form_submit_button("Criar meta"):
            v_alvo = _parse_valor(alvo)
            v_atual = _parse_valor(atual) or Decimal(0)
            if nome and v_alvo:
                salvar_meta(nome, "geral", v_alvo, v_atual, db_path=db_path)
                st.success("Meta criada.")
                st.rerun()

    metas = listar_metas(db_path)
    if not metas:
        st.info("Nenhuma meta cadastrada.")
    for m in metas:
        pct = m["pct"] or 0
        st.progress(min(pct / 100, 1.0), text=f"{m['nome']} — {pct:.0f}%")
        c1, c2, c3 = st.columns([2, 2, 1])
        c1.write(f"**Acumulado:** {_fmt_br(m['valor_atual'])}")
        c2.write(f"**Meta:** {_fmt_br(m['valor_alvo'])} · **Falta:** {_fmt_br(m['falta'])}")
        with c3:
            if st.button("Excluir", key=f"del_meta_{m['id']}"):
                excluir_meta(m["id"], db_path)
                st.rerun()
        with st.form(f"aporte_meta_{m['id']}"):
            aporte = st.text_input(
                "Registrar aporte (R$)",
                placeholder="500,00",
                key=f"ap_meta_val_{m['id']}",
                help="Soma ao que você já guardou. Ex.: guardou R$ 200 este mês → digite 200.",
            )
            col_a, col_b = st.columns(2)
            somar = col_a.form_submit_button("➕ Somar aporte")
            definir = col_b.form_submit_button("Definir total")
            if somar:
                v = _parse_valor(aporte)
                if v is None or v <= 0:
                    st.error("Informe um valor válido.")
                else:
                    aportar_meta(m["id"], v, db_path)
                    st.success(f"+ {_fmt_br(v)} registrado.")
                    st.rerun()
            if definir:
                v = _parse_valor(aporte)
                if v is None or v < 0:
                    st.error("Informe o total acumulado.")
                else:
                    definir_valor_meta(m["id"], v, db_path)
                    st.success("Total atualizado.")
                    st.rerun()
        st.divider()

    st.subheader("Projetos / sonhos")
    with st.form("novo_proj"):
        pn = st.text_input("Projeto")
        pa = st.text_input("Valor alvo (R$)")
        pac = st.text_input("Já guardado (R$)", value="0")
        pm = st.text_input("Aporte mensal (R$)")
        if st.form_submit_button("Criar projeto"):
            va = _parse_valor(pa)
            vc = _parse_valor(pac) or Decimal(0)
            vm = _parse_valor(pm)
            if pn and va:
                salvar_projeto(pn, va, vc, vm, db_path=db_path)
                st.success("Projeto criado.")
                st.rerun()
    projs = listar_projetos(db_path)
    if not projs:
        st.info("Nenhum projeto cadastrado.")
    for p in projs:
        st.progress(min(p["pct"] / 100, 1.0), text=f"{p['nome']} — {p['pct']:.0f}%")
        st.write(
            f"**Acumulado:** {_fmt_br(p['valor_acumulado'])} · "
            f"**Meta:** {_fmt_br(p['valor_alvo'])} · **Falta:** {_fmt_br(p['falta'])}"
        )
        with st.form(f"aporte_proj_{p['id']}"):
            aporte = st.text_input("Registrar aporte (R$)", placeholder="300,00", key=f"ap_proj_{p['id']}")
            c1, c2, c3 = st.columns(3)
            if c1.form_submit_button("➕ Somar aporte"):
                v = _parse_valor(aporte)
                if v and v > 0:
                    aportar_projeto(p["id"], v, db_path)
                    st.rerun()
            if c2.form_submit_button("Definir total"):
                v = _parse_valor(aporte)
                if v is not None and v >= 0:
                    definir_valor_projeto(p["id"], v, db_path)
                    st.rerun()
            if c3.form_submit_button("Arquivar"):
                desativar_projeto(p["id"], db_path)
                st.rerun()
        st.divider()


def tab_investimentos(db_path) -> None:
    res = resumo_investimentos(db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Patrimônio", _fmt_br(res["patrimonio_total"]))
    c2.metric("Aportes no mês", _fmt_br(res["aportes_mes"]))
    c3.metric("Rendimentos no mês", _fmt_br(res["rendimentos_mes"]))
    c4.metric("Ativos", res["qtd_ativos"])

    st.subheader("Carteira")
    with st.form("novo_ativo"):
        nome = st.text_input("Nome")
        tipo = st.selectbox("Tipo", TIPOS_ATIVO_INVEST)
        inst = st.text_input("Instituição")
        val = st.text_input("Valor atual (R$)", value="0")
        if st.form_submit_button("Adicionar ativo"):
            v = _parse_valor(val) or Decimal(0)
            if nome:
                salvar_ativo(nome, tipo, v, inst or None, db_path=db_path)
                st.rerun()
    for a in listar_ativos(db_path):
        st.write(f"**{a['nome']}** ({a['tipo']}) · {_fmt_br(a['valor_atual'])}")

    st.subheader("Movimento")
    ativos = listar_ativos(db_path)
    if ativos:
        with st.form("mov_inv"):
            aid = st.selectbox("Ativo", ativos, format_func=lambda x: x["nome"])
            d = st.date_input("Data", value=date.today())
            tp = st.selectbox("Tipo", ["aporte", "resgate", "rendimento"])
            v = st.text_input("Valor (R$)")
            obs = st.text_input("Observação")
            if st.form_submit_button("Registrar"):
                val = _parse_valor(v)
                if val:
                    registrar_mov_investimento(aid["id"], d, tp, val, obs or None, db_path)
                    st.rerun()

    st.subheader("Meta de alocação")
    with st.form("aloc"):
        ta = st.selectbox("Tipo", TIPOS_ATIVO_INVEST, key="aloc_t")
        pct = st.number_input("% alvo", min_value=0, max_value=100, value=20)
        if st.form_submit_button("Salvar alocação"):
            salvar_meta_alocacao(ta, Decimal(pct), db_path)
            st.rerun()
    for row in listar_metas_alocacao(db_path):
        atual_pct = res["por_tipo"].get(row["tipo_ativo"], 0)
        tot = float(res["patrimonio_total"]) or 1
        st.write(f"{row['tipo_ativo']}: meta {row['percentual']:.0f}% · atual {atual_pct / tot * 100:.1f}%")


def tab_dividas(db_path) -> None:
    with st.form("nova_divida"):
        nome = st.text_input("Nome")
        total = st.text_input("Valor total (R$)")
        pago = st.text_input("Já pago (R$)", value="0")
        taxa = st.text_input("Taxa mensal % (opcional)")
        parc = st.number_input("Parcelas", min_value=0, value=0)
        if st.form_submit_button("Cadastrar"):
            vt = _parse_valor(total)
            vp = _parse_valor(pago) or Decimal(0)
            tx = _parse_valor(taxa) if taxa else None
            if nome and vt:
                salvar_divida(nome, vt, vp, tx, int(parc) or None, db_path=db_path)
                st.rerun()
    for d in listar_dividas(db_path):
        st.write(
            f"**{d['nome']}** · restante {_fmt_br(d['restante'])} "
            f"({d['pct']:.0f}% quitado)"
        )
        if st.button("Quitar registro", key=f"off_div_{d['id']}"):
            desativar_divida(d["id"], db_path)
            st.rerun()
    st.subheader("Ordem sugerida de quitação")
    for s in sugestao_quitacao_dividas(db_path):
        st.write(f"**{s['metodo']}**: " + " → ".join(s["ordem"]))


def tab_config(db_path) -> None:
    st.subheader("Regras de categorização")
    with st.form("regra_cat"):
        pad = st.text_input("Se histórico contém")
        cat = st.selectbox("Categoria", CATEGORIAS_SUGERIDAS, key="regra_cat_sel")
        pri = st.number_input("Prioridade", value=10)
        if st.form_submit_button("Adicionar regra"):
            if pad:
                salvar_regra_categoria(pad, cat, int(pri), db_path=db_path)
                st.rerun()
    for r in listar_regras_categoria(db_path):
        c1, c2 = st.columns([4, 1])
        c1.write(f"`{r['padrao']}` → **{r['categoria']}** (prio {r['prioridade']})")
        if c2.button("Excluir", key=f"del_regra_{r['id']}"):
            excluir_regra_categoria(r["id"], db_path)
            st.rerun()

    st.subheader("Contas bancárias")
    with st.form("conta_banco"):
        cn = st.text_input("Nome da conta")
        ct = st.selectbox("Tipo", ["corrente", "poupanca", "investimento", "cartao"])
        if st.form_submit_button("Adicionar conta"):
            if cn:
                salvar_conta_bancaria(cn, ct, db_path=db_path)
                st.rerun()
    for c in listar_contas_bancarias(db_path):
        st.write(f"**{c['nome']}** ({c['tipo']})")

    st.subheader("Tags")
    with st.form("tag_nova"):
        tn = st.text_input("Nova tag")
        if st.form_submit_button("Criar tag"):
            if tn:
                salvar_tag(tn, db_path)
                st.rerun()
    st.write(", ".join(t["nome"] for t in listar_tags(db_path)) or "Nenhuma tag")

    st.subheader("Notificações (e-mail)")
    with st.form("notif"):
        em = st.text_input("E-mail para alertas", value=obter_notificacoes_email(db_path))
        if st.form_submit_button("Salvar"):
            salvar_notificacoes_email(em, db_path)
            st.success("Salvo (envio real requer integração futura).")

    st.subheader("Exportar movimentos")
    de = st.date_input("De", value=date.today().replace(day=1), key="exp_de")
    ate = st.date_input("Até", value=date.today(), key="exp_ate")
    csv_data = exportar_movimentos_csv(de, ate, db_path)
    st.download_button("Baixar CSV", csv_data, file_name="movimentos.csv", mime="text/csv")

    st.subheader("Alertas do sistema")
    mes = date.today().strftime("%Y-%m")
    for a in resumo_alertas_sistema(mes, db_path):
        if a["nivel"] == "danger":
            st.error(a["texto"])
        elif a["nivel"] == "warn":
            st.warning(a["texto"])
        else:
            st.info(a["texto"])
