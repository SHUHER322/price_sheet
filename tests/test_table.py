"""Чтение листов и подготовка строк для записи."""
from datetime import datetime
from decimal import Decimal

from app.extract import Product
from app.table import (Task, change_text, history_row, read_settings, read_tasks, result_row,
                       settings_for, to_number, trend)

NOW = datetime(2026, 10, 30, 19, 5)


def test_read_tasks_skips_empty_and_reads_old_price():
    rows = [
        ["https://shop.ru/a", "Товар А", "12 990"],
        [""],
        [],
        ["  https://shop.ru/b  "],
        ["https://shop.ru/c", "", "1299,5"],
    ]
    tasks = read_tasks(rows)
    assert [(t.row, t.url, t.old_price) for t in tasks] == [
        (2, "https://shop.ru/a", Decimal("12990")),
        (5, "https://shop.ru/b", None),
        (6, "https://shop.ru/c", Decimal("1299.5")),
    ]


def test_to_number():
    assert to_number(12990) == Decimal("12990")
    assert to_number("12 990") == Decimal("12990")
    assert to_number("") is None and to_number("abc") is None


def test_read_settings_normalizes_domain():
    rows = [["https://www.Shop.ru/catalog", ".price", "", "", "browser"],
            ["dns-shop.ru", "", "h1"],
            ["", ".x"]]
    s = read_settings(rows)
    assert set(s) == {"shop.ru", "dns-shop.ru"}
    assert s["shop.ru"].selectors.price == ".price" and s["shop.ru"].browser
    assert s["dns-shop.ru"].selectors.name == "h1" and not s["dns-shop.ru"].browser


def test_settings_for_subdomain():
    s = read_settings([["shop.ru", ".p"]])
    assert settings_for("m.shop.ru", s) is s["shop.ru"]
    assert settings_for("shop.ru", s) is s["shop.ru"]
    assert settings_for("other.ru", s) is None


def test_change_text():
    assert change_text(None, Decimal("100")) == "первая проверка"
    assert change_text(Decimal("100"), Decimal("100")) == "без изменений"
    assert change_text(Decimal("13490"), Decimal("12990")) == "▼ −500 (−3,7%)"
    assert change_text(Decimal("1000"), Decimal("1251.5")) == "▲ +251,5 (+25,2%)"
    assert change_text(Decimal("100"), None) == ""


def test_result_row_success():
    task = Task(3, "https://shop.ru/a", Decimal("13490"))
    product = Product(name="Товар", price=Decimal("12990"), old_price=Decimal("15990.50"),
                      currency="RUB", in_stock=True)
    col, values = result_row(task, product, None, NOW)
    assert col == "B"
    assert values == ["Товар", 12990, 15990.5, "RUB", "в наличии", "▼ −500 (−3,7%)",
                      "30.10.2026 19:05", ""]


def test_result_row_error_keeps_old_values():
    task = Task(3, "https://shop.ru/a", Decimal("13490"))
    assert result_row(task, None, "сайт закрыт защитой от ботов", NOW) == (
        "H", ["30.10.2026 19:05", "сайт закрыт защитой от ботов"])
    col, values = result_row(task, Product(name="Без цены"), None, NOW)
    assert col == "H" and "селектор" in values[1]


def test_trend_and_history():
    task = Task(2, "u", Decimal("100"))
    assert trend(task, Product(price=Decimal("90"))) == "down"
    assert trend(task, Product(price=Decimal("110"))) == "up"
    assert trend(task, Product(price=Decimal("100"))) is None
    assert trend(Task(2, "u", None), Product(price=Decimal("1"))) is None
    row = history_row(task, Product(name="A", price=Decimal("90"), in_stock=False), NOW)
    assert row == ["30.10.2026 19:05", "u", "A", 90, "", "нет в наличии"]


def test_read_tasks_keeps_name_and_stock():
    tasks = read_tasks([["https://a.ru", "Книга", "579", "695", "RUB", "нет в наличии"]])
    assert (tasks[0].name, tasks[0].old_stock) == ("Книга", "нет в наличии")
