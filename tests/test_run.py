"""Проверка целиком: таблица → загрузка → разбор → что записать."""
import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.fetch import Page
from app.run import check_all, plan_writes, summary
from app.table import Task, read_settings

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 30, 19, 5)


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages

    async def get(self, url):
        return self.pages[url]


def html(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_check_and_plan():
    tasks = [Task(2, "https://shop.ru/phone", Decimal("13490")),
             Task(3, "https://bag.ru/backpack", None),
             Task(4, "https://secure.ru/x", Decimal("500"))]
    fetcher = FakeFetcher({
        "https://shop.ru/phone": Page("https://shop.ru/phone", 200, html("jsonld_graph.html")),
        "https://bag.ru/backpack": Page("https://bag.ru/backpack", 200, html("no_markup.html")),
        "https://secure.ru/x": Page("https://secure.ru/x", 403, "", blocked=True,
                                    error="сайт закрыт защитой от ботов"),
    })
    settings = read_settings([["bag.ru", ".card .cost"]])
    results = asyncio.run(check_all(tasks, settings, fetcher))
    assert results[0].product.price == Decimal("12990.00")
    assert results[1].product.price == Decimal("1299.90")   # по селектору из «Настроек»
    assert results[2].error == "сайт закрыт защитой от ботов"

    updates, trends, history = plan_writes(results, NOW)
    assert [u[:2] for u in updates] == [(2, "B"), (3, "B"), (4, "H")]
    assert trends == {2: "down", 3: None}
    assert [h[1] for h in history] == ["https://shop.ru/phone", "https://bag.ru/backpack"]
    assert summary(results) == ("Проверено ссылок: 3. Цена найдена: 2, ошибок: 1. "
                                "Подешевело: 1, подорожало: 0.")
