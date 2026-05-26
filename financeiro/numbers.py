from decimal import Decimal, InvalidOperation


def parse_br_decimal(raw: str | None) -> Decimal | None:
    """Converte string no formato brasileiro (1.234,56) em Decimal."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_decimal_valor(raw: str | None) -> Decimal | None:
    """
    Aceita valor BR (1.234,56), US/Nubank (-25.00, 1500.00) ou inteiro.
    Retorna None se inválido.
    """
    if raw is None:
        return None
    s = raw.strip().replace("\u00a0", "")
    if not s:
        return None

    neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-").strip()

    if "," in s and "." in s:
        # 1.234,56 ou 1,234.56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    return -val if neg else val
