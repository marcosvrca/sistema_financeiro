from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Indicadores:
    total_creditos: Decimal
    total_debitos: Decimal
    saldo_liquido: Decimal
    qtd_movimentos: int
    qtd_debitos: int
    maior_debito: Decimal | None
    ticket_medio_debito: Decimal | None
    media_diaria_gastos: Decimal | None
    pct_fixas: Decimal | None
    pct_variaveis: Decimal | None
    total_fixas: Decimal
    total_variaveis: Decimal
    total_manuais_entrada: Decimal
    total_manuais_saida: Decimal


@dataclass(frozen=True)
class ResumoMensal:
    mes: str  # YYYY-MM
    creditos: Decimal
    debitos: Decimal
    liquido: Decimal
