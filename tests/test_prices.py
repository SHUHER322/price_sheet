"""Разбор цены из строки в разных форматах."""
from decimal import Decimal

import pytest

from app.prices import parse_currency, parse_price


@pytest.mark.parametrize("text, value", [
    ("1 299,90 ₽", "1299.90"),
    ("1 299 ₽", "1299"),           # неразрывный пробел
    ("12 990 руб.", "12990"),      # узкий пробел
    ("от 990 руб.", "990"),
    ("$1,299.00", "1299.00"),
    ("1.299,90 €", "1299.90"),
    ("12.990 р", "12990"),              # точка — разряды
    ("12.99", "12.99"),                 # точка — копейки
    ("1,299,000", "1299000"),
    ("2499", "2499"),
    ("Цена: 15 490 ₽ / шт", "15490"),
    (799, "799"),
    (12990.5, "12990.5"),
])
def test_parse_price(text, value):
    assert parse_price(text) == Decimal(value)


@pytest.mark.parametrize("text", [None, "", "нет в наличии", "0", 0, "Цена по запросу"])
def test_no_price(text):
    assert parse_price(text) is None


@pytest.mark.parametrize("text, code", [
    ("1 299 ₽", "RUB"), ("990 руб.", "RUB"), ("$10", "USD"), ("10 €", "EUR"),
    ("5000 ₸", "KZT"), ("100", None), (None, None),
])
def test_parse_currency(text, code):
    assert parse_currency(text) == code
