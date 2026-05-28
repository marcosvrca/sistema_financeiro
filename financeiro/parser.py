from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from financeiro.numbers import parse_br_decimal, parse_decimal_valor

_ROW_START = re.compile(r"^(\d{2}/\d{2}/\d{4})")


@dataclass(frozen=True)
class LinhaExtrato:
    data: date
    historico: str
    docto: str
    credito: Decimal | None
    debito: Decimal | None
    saldo: Decimal | None


def _parse_data(s: str) -> date:
    d, m, y = s.strip().split("/")
    return date(int(y), int(m), int(d))


def _norm_col(name: str) -> str:
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    return n.lower().strip()


def eh_extrato_nubank(conteudo: str) -> bool:
    texto = conteudo.strip().lstrip("\ufeff")
    for line in texto.splitlines()[:8]:
        line = line.strip()
        if not line:
            continue
        low = _norm_col(line)
        if "identificador" in low and ("descricao" in low or "descri" in low):
            return True
        if low.startswith("data,valor") or low.startswith("data;valor"):
            return True
    return False


def parse_nubank_csv(conteudo: str) -> list[LinhaExtrato]:
    """
    CSV exportado pelo app/site Nubank:
    Data,Valor,Identificador,Descrição
    Valor positivo = entrada; negativo = saída (formato -25.00).
    """
    texto = conteudo.strip().lstrip("\ufeff")
    delim = ";" if texto.count(";") > texto.count(",") else ","
    reader = csv.reader(StringIO(texto), delimiter=delim)

    linhas: list[LinhaExtrato] = []
    visto: set[tuple[date, str, str, str, str, str]] = set()
    idx_data = idx_valor = idx_id = idx_desc = None

    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue

        cols = [_norm_col(c) for c in row]
        if idx_data is None:
            if "data" in cols and "valor" in cols:
                idx_data = cols.index("data")
                idx_valor = cols.index("valor")
                idx_id = cols.index("identificador") if "identificador" in cols else None
                idx_desc = next(
                    (i for i, c in enumerate(cols) if c.startswith("descric")),
                    len(row) - 1,
                )
            continue

        if len(row) <= max(idx_data, idx_valor, idx_desc):
            continue

        data_s = row[idx_data].strip()
        if not _ROW_START.match(data_s):
            continue

        valor = parse_decimal_valor(row[idx_valor])
        if valor is None:
            continue

        historico = row[idx_desc].strip() if idx_desc < len(row) else ""
        docto = row[idx_id].strip()[:64] if idx_id is not None and idx_id < len(row) else ""

        if valor >= 0:
            credito, debito = valor, None
        else:
            credito, debito = None, abs(valor)

        try:
            d = _parse_data(data_s)
        except ValueError:
            continue

        chave = (d, historico, docto, str(credito), str(debito), "")
        if chave in visto:
            continue
        visto.add(chave)

        linhas.append(
            LinhaExtrato(
                data=d,
                historico=historico,
                docto=docto,
                credito=credito,
                debito=debito,
                saldo=None,
            )
        )

    linhas.sort(key=lambda r: (r.data, r.historico, r.docto))
    return linhas


def parse_extrato_bradesco(conteudo: str) -> list[LinhaExtrato]:
    """Extrato Bradesco e similares: campos com ';' e crédito/débito separados."""
    linhas: list[LinhaExtrato] = []
    visto: set[tuple[date, str, str, str, str, str]] = set()

    for line in conteudo.splitlines():
        line = line.strip()
        if not line or line.startswith("Extrato de:") or "Filtro de resultados" in line:
            continue
        if line.startswith("Últimos Lancamentos") or line.startswith("Data;Histórico"):
            continue
        if line.startswith(";;;;") or line.startswith(";;Total"):
            continue
        if "Os dados acima" in line:
            continue

        m = _ROW_START.match(line)
        if not m:
            continue

        partes = [p.strip() for p in line.split(";")]
        if len(partes) < 5:
            continue

        data_s = partes[0]
        historico = partes[1] if len(partes) > 1 else ""
        docto = partes[2] if len(partes) > 2 else ""

        credito = parse_br_decimal(partes[3]) if len(partes) > 3 else None
        debito = parse_br_decimal(partes[4]) if len(partes) > 4 else None
        saldo = parse_br_decimal(partes[5]) if len(partes) > 5 else None

        try:
            d = _parse_data(data_s)
        except ValueError:
            continue

        chave = (d, historico, docto, str(credito), str(debito), str(saldo))
        if chave in visto:
            continue
        visto.add(chave)

        linhas.append(
            LinhaExtrato(
                data=d,
                historico=historico,
                docto=docto,
                credito=credito,
                debito=debito,
                saldo=saldo,
            )
        )

    linhas.sort(key=lambda r: (r.data, r.historico, r.docto))
    return linhas


def detectar_banco_extrato(conteudo: str) -> str:
    """Identifica o banco/instituição a partir do cabeçalho ou formato do arquivo."""
    texto = conteudo.strip().lstrip("\ufeff")
    if eh_extrato_nubank(texto):
        return "Nubank"
    amostra = texto[:4000].upper()
    marcas = (
        ("BRB", "BRB"),
        ("BANCO DE BRASILIA", "BRB"),
        ("BRADESCO", "Bradesco"),
        ("ITAÚ", "Itaú"),
        ("ITAU", "Itaú"),
        ("SANTANDER", "Santander"),
        ("CAIXA ECON", "Caixa"),
        ("BANCO DO BRASIL", "Banco do Brasil"),
        ("BANCO INTER", "Inter"),
        ("C6 BANK", "C6 Bank"),
        ("NUBANK", "Nubank"),
    )
    for chave, rotulo in marcas:
        if chave in amostra:
            return rotulo
    if ";" in texto and _ROW_START.search(texto):
        return "Bradesco"
    return "Outro"


def parse_extrato_texto(conteudo: str) -> list[LinhaExtrato]:
    """Detecta Nubank (CSV) ou Bradesco (';') e importa as linhas."""
    texto = conteudo.strip().lstrip("\ufeff")
    if eh_extrato_nubank(texto):
        nubank = parse_nubank_csv(texto)
        if nubank:
            return nubank
    return parse_extrato_bradesco(texto)


def _eh_gasolina(h: str) -> bool:
    """Posto/combustível — deve ser testado antes de regras de PIX."""
    if any(
        k in h
        for k in (
            "POSTO ",
            " POSTO",
            "POSTOS ",
            " POSTOS",
            "COMBUSTIV",
            "COMBUSTÍV",
            "COMBUSTIVEIS",
            "COMBUSTÍVEIS",
            "PETRO POSTOS",
            "LUAR COMBUST",
        )
    ):
        return True
    if h.startswith("POSTO") or " POSTO " in h:
        return True
    return False


def _eh_utilidade(h: str) -> bool:
    # evita falso positivo em "ARAGUAIA" (contém AGUA como substring)
    if re.search(r"\b(ÁGUA|AGUA)\b", h):
        return True
    return any(
        k in h
        for k in (
            "ENERGIA",
            "LUZ",
            "GAS DE ",
            "GÁS ",
            "INTERNET",
            "TELEFONE",
            "CELULAR",
            "PRONTO FIBRA",
            "SABESP",
            "CEMIG",
            "COPEL",
        )
    )


def categoria_por_historico(historico: str) -> str:
    h = historico.upper()
    if any(k in h for k in ("ALUGUEL", "CONDOMINIO", "CONDOMÍNIO", "IPTU", "FINANCIAMENTO")):
        return "Moradia"
    if _eh_gasolina(h):
        return "Gasolina"
    if _eh_utilidade(h):
        return "Contas fixas (utilidades)"
    if any(k in h for k in ("SALARIO", "SALÁRIO", "FOLHA", "PROVENTOS", "CRÉDITO EM CONTA")):
        return "Salário / renda"
    if "TRANSFERENCIA PIX" in h or "TRANSFERÊNCIA PIX" in h:
        return "Transferência PIX"
    if "TRANSFERÊNCIA RECEBIDA" in h or "TRANSFERENCIA RECEBIDA" in h:
        return "PIX"
    if "TRANSFERÊNCIA ENVIADA" in h or "TRANSFERENCIA ENVIADA" in h:
        return "Transferência PIX"
    if "PIX" in h:
        return "PIX"
    if any(k in h for k in ("UBER", "99APP", "ESTACION")):
        return "Transporte"
    if any(k in h for k in ("FARMAC", "DROGAR", "RAIA", "HOSPITAL", "CLINICA", "CLÍNICA", "PLANO DE SAUDE")):
        return "Saúde"
    if any(k in h for k in ("ESCOLA", "FACULD", "CURSO", "MENSALIDADE")):
        return "Educação"
    if any(
        k in h
        for k in (
            "NETFLIX",
            "SPOTIFY",
            "DISNEY",
            "HBO",
            "AMAZON PRIME",
            "ASSINAT",
            "YOUTUBE",
            "APPLE.COM/BILL",
            "GOOGLE ONE",
            "CRUNCHYROLL",
            "PARAMOUNT",
            "DEEZER",
            "MICROSOFT",
        )
    ):
        return "Assinaturas"
    if any(
        k in h
        for k in (
            "MERCADO",
            "SUPERMERC",
            "CARREFOUR",
            "ATACADAO",
            "ATACADÃO",
            "PAO DE ACUCAR",
            "PÃO DE AÇÚCAR",
            "ASSAI",
            "BIG",
        )
    ):
        return "Mercado"
    if any(
        k in h
        for k in (
            "PADARIA",
            "RESTAUR",
            "IFOOD",
            "LANCH",
            "BURGUER",
            "ACAI",
            "SORVETE",
        )
    ):
        return "Alimentação"
    if "COMPRA NO DÉBITO" in h or "COMPRA NO DEBITO" in h:
        return "Cartão / compras"
    if "COMPRA ELO" in h or "COMPRA" in h or "DEBITO" in h:
        return "Cartão / compras"
    if "RENTAB" in h or "INVEST" in h:
        return "Rendimentos"
    if "COD. LANC" in h:
        return "Ajuste / lançamento"
    if any(k in h for k in ("TARIFA", "IOF", "ANUIDADE")):
        return "Taxas bancárias"
    return "Outros"


CATEGORIAS_SUGERIDAS = [
    "Salário / renda",
    "Moradia",
    "Contas fixas (utilidades)",
    "Alimentação",
    "Mercado",
    "Assinaturas",
    "Gasolina",
    "Transporte",
    "Saúde",
    "Educação",
    "Cartão / compras",
    "PIX",
    "Transferência PIX",
    "Rendimentos",
    "Investimentos",
    "Taxas bancárias",
    "Ajuste / lançamento",
    "Outros",
]
