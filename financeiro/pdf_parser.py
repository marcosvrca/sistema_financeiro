"""Parsers de extrato em PDF (Nubank, BRB)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from financeiro.numbers import parse_br_decimal, parse_decimal_valor
from financeiro.parser import LinhaExtrato

_MESES = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}

_VALOR_BR = re.compile(r"^(\d{1,3}(?:\.\d{3})*,\d{2})$")
_VALOR_FIM_LINHA = re.compile(r"^(.+?)\s+(\d{1,3}(?:\.\d{3})*,\d{2})$")
_NUBANK_DATA = re.compile(r"^(\d{2})\s+([A-Z]{3})\s+(\d{4})\b")
_NUBANK_INICIO_TX = re.compile(
    r"^(Transferência|Compra no débito|Compra no debito|Pagamento de|"
    r"Rendimento|Estorno|Resgate|Aplicação|Aplicacao|Saída|Entrada)",
    re.IGNORECASE,
)
_BRB_LINHA = re.compile(
    r"^(\d{2}/\d{2})(?:\s+(.+?))?\s+R\$\s*([+\-−]\s*[\d.,]+)\s*$"
)
_BRB_MES_ANO = re.compile(r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ]+)/(\d{4})", re.IGNORECASE)


def eh_extrato_nubank_pdf(conteudo: str) -> bool:
    texto = conteudo.strip()
    if "Movimentações" not in texto and "Movimentacoes" not in texto:
        return False
    if "CPF Agência Conta" not in texto and "CPF Agencia Conta" not in texto:
        return False
    return bool(_NUBANK_DATA.search(texto))


def eh_extrato_brb_pdf(conteudo: str) -> bool:
    texto = conteudo.strip()
    if "Conta Corrente" not in texto:
        return False
    if "Dia" in texto and "Histórico" in texto and "Valor" in texto:
        return True
    if "Agência:" in texto or "Agencia:" in texto:
        return bool(_BRB_LINHA.search(texto))
    return False


def _parse_data_nubank(dia: int, mes_abrev: str, ano: int) -> date | None:
    mes = _MESES.get(mes_abrev.upper())
    if not mes:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _linha_ruido_nubank(linha: str) -> bool:
    s = linha.strip()
    if not s:
        return True
    if s.startswith("-- ") and " of " in s:
        return True
    if "Tem alguma dúvida" in s or "nubank.com.br" in s:
        return True
    if s.startswith("Marcos ") or "CPF Agência" in s or "CPF Agencia" in s:
        return True
    if "DE JUNHO" in s or "DE JULHO" in s or "VALORES EM R$" in s:
        return True
    if s in ("Movimentações", "Movimentacoes", "a"):
        return True
    if s.startswith("Saldo ") or s.startswith("Rendimento") or s.startswith("R$ "):
        return True
    if s.startswith("Total de entradas") or s.startswith("Total de saídas"):
        return True
    if s.startswith("Total de saidas"):
        return True
    if re.match(r"^[\d.,+-]+$", s) and "," not in s:
        return True
    if re.match(r"^\d{5,}-\d$", s):
        return True
    if "Agência:" in s or "Agencia:" in s:
        return True
    if s.startswith("PAGAMENTOS - IP") or s.startswith("NU PAGAMENTOS"):
        return True
    if re.match(r"^\d{6,}-\d$", s):
        return True
    return False


def parse_nubank_pdf(conteudo: str) -> list[LinhaExtrato]:
    """Extrato mensal Nubank em PDF."""
    linhas: list[LinhaExtrato] = []
    visto: set[tuple[date, str, str, str, str, str]] = set()

    data_atual: date | None = None
    buffer_desc: list[str] = []

    def finalizar(valor_s: str) -> None:
        nonlocal buffer_desc, data_atual
        if data_atual is None or not buffer_desc:
            buffer_desc = []
            return
        valor = parse_br_decimal(valor_s)
        if valor is None:
            buffer_desc = []
            return
        historico = " ".join(buffer_desc).strip()
        historico = re.sub(r"\s+", " ", historico)
        if not historico:
            buffer_desc = []
            return

        low = historico.lower()
        if "recebida" in low or "recebido" in low:
            credito, debito = valor, None
        else:
            credito, debito = None, valor

        chave = (data_atual, historico, "", str(credito), str(debito), "")
        if chave not in visto:
            visto.add(chave)
            linhas.append(
                LinhaExtrato(
                    data=data_atual,
                    historico=historico,
                    docto="",
                    credito=credito,
                    debito=debito,
                    saldo=None,
                )
            )
        buffer_desc = []

    for raw in conteudo.splitlines():
        linha = raw.strip()
        if not linha:
            continue

        if _VALOR_BR.match(linha):
            finalizar(linha)
            continue

        m_inline = _VALOR_FIM_LINHA.match(linha)
        if m_inline and _NUBANK_INICIO_TX.match(m_inline.group(1)):
            buffer_desc = [m_inline.group(1)]
            finalizar(m_inline.group(2))
            continue

        if _linha_ruido_nubank(linha):
            continue

        m_data = _NUBANK_DATA.match(linha)
        if m_data:
            dia, mes_abrev, ano = int(m_data.group(1)), m_data.group(2), int(m_data.group(3))
            data_atual = _parse_data_nubank(dia, mes_abrev, ano)
            resto = linha[m_data.end() :].strip()
            if resto.startswith("Total de"):
                continue
            if resto and _NUBANK_INICIO_TX.match(resto):
                buffer_desc = [resto]
            continue

        if _NUBANK_INICIO_TX.match(linha):
            if buffer_desc:
                buffer_desc = []
            buffer_desc.append(linha)
        elif buffer_desc:
            if not re.match(r"^Conta:\s*\d", linha):
                buffer_desc.append(linha)

    linhas.sort(key=lambda r: (r.data, r.historico))
    return linhas


def _mes_ano_brb(conteudo: str) -> tuple[int, int] | None:
    for linha in conteudo.splitlines()[:30]:
        m = _BRB_MES_ANO.search(linha.upper())
        if m:
            mes_nome = m.group(1).upper()
            ano = int(m.group(2))
            for abrev, num in _MESES.items():
                if mes_nome.startswith(abrev) or abrev in mes_nome:
                    return num, ano
            nomes = {
                "JANEIRO": 1,
                "FEVEREIRO": 2,
                "MARÇO": 3,
                "MARCO": 3,
                "ABRIL": 4,
                "MAIO": 5,
                "JUNHO": 6,
                "JULHO": 7,
                "AGOSTO": 8,
                "SETEMBRO": 9,
                "OUTUBRO": 10,
                "NOVEMBRO": 11,
                "DEZEMBRO": 12,
            }
            for nome, num in nomes.items():
                if nome in mes_nome:
                    return num, ano
    return None


def _parse_valor_brb(raw: str) -> Decimal | None:
    s = raw.replace("−", "-").replace("\u2212", "-").replace(" ", "")
    neg = s.startswith("-")
    s = s.lstrip("+-")
    val = parse_br_decimal(s) or parse_decimal_valor(s)
    if val is None:
        return None
    if neg:
        return abs(val)
    return val


def _linha_ruido_brb(linha: str) -> bool:
    s = linha.strip()
    if not s:
        return True
    if s.startswith("-- ") and " of " in s:
        return True
    if s.startswith("SALDO ATUAL") or s.startswith("Saldo Conta") or s.startswith("Saldo da Poupança"):
        return True
    if s.startswith("Saldo Atual"):
        return True
    if s == "Extrato":
        return True
    if "Agência:" in s or "Agencia:" in s:
        return True
    if re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$", s):
        return True
    if s == "Dia Histórico Valor" or (s.startswith("Dia") and "Histórico" in s):
        return True
    if re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ/]+/\d{4}$", s):
        return True
    if re.match(r"^[A-Z][A-Z\s]+$", s) and len(s) > 15 and "/" not in s:
        return True
    return False


def parse_brb_pdf(conteudo: str) -> list[LinhaExtrato]:
    """Extrato BRB em PDF (layout em colunas do pdfplumber)."""
    mes_ano = _mes_ano_brb(conteudo)
    if not mes_ano:
        return []
    mes_ref, ano_ref = mes_ano

    linhas: list[LinhaExtrato] = []
    visto: set[tuple[date, str, str, str, str, str]] = set()

    pending_tipo: str | None = None
    pending_dia_valor: tuple[int, str] | None = None
    pending_detalhe: list[str] = []

    def registrar(dia: int, historico: str, valor_raw: str) -> None:
        historico = re.sub(r"\s+", " ", historico).strip(" —-")
        if not historico:
            historico = "Lançamento BRB"
        valor = _parse_valor_brb(valor_raw)
        if valor is None:
            return
        try:
            d = date(ano_ref, mes_ref, dia)
        except ValueError:
            return

        sinal = valor_raw.replace(" ", "").replace("−", "-").replace("\u2212", "-")
        if sinal.startswith("+"):
            credito, debito = valor, None
        else:
            credito, debito = None, valor

        chave = (d, historico, "", str(credito), str(debito), "")
        if chave in visto:
            return
        visto.add(chave)
        linhas.append(
            LinhaExtrato(
                data=d,
                historico=historico,
                docto="",
                credito=credito,
                debito=debito,
                saldo=None,
            )
        )

    def flush_pendente() -> None:
        nonlocal pending_tipo, pending_dia_valor, pending_detalhe
        if pending_dia_valor is None:
            pending_detalhe = []
            return
        hist = pending_tipo or "Lançamento BRB"
        if pending_detalhe:
            hist = f"{hist} — {' '.join(pending_detalhe)}"
        registrar(pending_dia_valor[0], hist, pending_dia_valor[1])
        pending_tipo = None
        pending_dia_valor = None
        pending_detalhe = []

    _dia_valor = re.compile(r"^(\d{2}/\d{2})\s+R\$\s*([+\-−]\s*[\d.,]+)\s*$")
    _linha_completa = re.compile(
        r"^(\d{2}/\d{2})\s+(.+?)\s+R\$\s*([+\-−]\s*[\d.,]+)\s*$"
    )
    _desc_brb = re.compile(r"^(DEBITO |CRED )", re.IGNORECASE)

    for raw in conteudo.splitlines():
        linha = raw.strip()
        if _linha_ruido_brb(linha):
            continue

        m = _linha_completa.match(linha)
        if m:
            flush_pendente()
            registrar(int(m.group(1).split("/")[0]), m.group(2), m.group(3))
            continue

        m = _dia_valor.match(linha)
        if m:
            flush_pendente()
            pending_dia_valor = (int(m.group(1).split("/")[0]), m.group(2))
            continue

        if _desc_brb.match(linha):
            flush_pendente()
            pending_tipo = linha
            pending_detalhe = []
            continue

        if pending_dia_valor is not None:
            pending_detalhe.append(linha)
            flush_pendente()

    flush_pendente()
    linhas.sort(key=lambda r: (r.data, r.historico))
    return linhas


def parse_extrato_pdf(conteudo: str, banco: str | None = None) -> list[LinhaExtrato]:
    """Detecta e importa extrato em PDF (texto já extraído)."""
    texto = conteudo.strip()
    banco_norm = (banco or "").strip().lower()

    if banco_norm == "nubank" or (not banco_norm and eh_extrato_nubank_pdf(texto)):
        rows = parse_nubank_pdf(texto)
        if rows:
            return rows

    if banco_norm == "brb" or (not banco_norm and eh_extrato_brb_pdf(texto)):
        rows = parse_brb_pdf(texto)
        if rows:
            return rows

    if eh_extrato_nubank_pdf(texto):
        return parse_nubank_pdf(texto)
    if eh_extrato_brb_pdf(texto):
        return parse_brb_pdf(texto)
    return []
