"""Разбор цены из текста: «1 299,90 ₽», «от 990 руб.», «$1,299.00», «12.990 р»."""
import re
from decimal import Decimal, InvalidOperation

# Пробелы, которыми магазины разделяют разряды: обычный, неразрывный, узкий
SPACES = " \u00a0\u202f\u2009\u2007"
NUMBER_RE = re.compile(r"\d[\d" + SPACES + r".,']*")

CURRENCIES = {
    "₽": "RUB", "руб": "RUB", "р.": "RUB", "rub": "RUB", "rur": "RUB",
    "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR",
    "₸": "KZT", "тг": "KZT", "kzt": "KZT", "byn": "BYN",
}


def parse_price(text: str | int | float | None) -> Decimal | None:
    """Первое число в строке как цена. None — если числа нет или оно не похоже на цену.

    Разделители разрядов и копеек угадываются: в «1.299,90» точка — разряды, запятая —
    копейки; в «1,299.90» наоборот; «12.990» — двенадцать тысяч (три цифры после точки),
    а «12.99» — двенадцать с копейками.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return Decimal(str(text)) if text > 0 else None
    match = NUMBER_RE.search(str(text))
    if not match:
        return None
    raw = match.group().strip(SPACES + ".,'")
    for ch in SPACES + "'":
        raw = raw.replace(ch, "")
    if "," in raw and "." in raw:
        # Десятичный — тот разделитель, что стоит последним
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        whole, _, tail = raw.rpartition(sep)
        if raw.count(sep) > 1 or len(tail) == 3:
            raw = raw.replace(sep, "")          # 1,299,000 или 12.990 — разряды
        else:
            raw = whole.replace(sep, "") + "." + tail  # 1299,9 / 12.99 — копейки
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def parse_currency(text: str | None) -> str | None:
    """Код валюты по символу или слову в строке цены."""
    if not text:
        return None
    low = str(text).lower()
    for mark, code in CURRENCIES.items():
        if mark in low:
            return code
    return None
