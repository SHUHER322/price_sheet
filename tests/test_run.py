"""Проверка целиком: таблица → загрузка → разбор → что записать."""
import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.fetch import Page
from app.run import Checked, check_all, plan_writes, summary
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
    assert summary(results) == ("Проверено ссылок: 3. Цена найдена: 2 (через браузер: 0), "
                                "ошибок: 1. Подешевело: 1, подорожало: 0.")


WB_PAGE = ('<html><head><meta property="og:title" content="Куртка зимняя, "></head><body>'
           '<span class="priceBlockPrice--BO6Px"><ins class="priceBlockFinalPrice--yEKcc">'
           '5\u00a0694\u00a0₽</ins></span><span class="priceBlockOldPrice--WPpN1">13\u00a0000\u00a0₽</span>'
           '</body></html>')


class FakeBrowser:
    """Вместо Chrome: отдаёт заготовленные страницы и запоминает, что открывал."""
    def __init__(self, pages, fail=False):
        self.pages, self.fail, self.opened = pages, fail, []

    def __call__(self):
        return self

    async def __aenter__(self):
        if self.fail:
            raise FileNotFoundError("Chrome не найден")
        return self

    async def __aexit__(self, *exc):
        pass

    async def get(self, url, selectors=None):
        self.opened.append(url)
        return self.pages[url]


def test_browser_for_protected_and_marked_sites():
    wb, dns, plain = ("https://www.wildberries.ru/catalog/1/detail.aspx",
                      "https://www.dns-shop.ru/product/1/", "https://shop.ru/phone")
    secure = "https://secure.ru/x"
    tasks = [Task(2, wb, None), Task(3, dns, None), Task(4, plain, None), Task(5, secure, None)]
    http = FakeFetcher({
        plain: Page(plain, 200, html("jsonld_graph.html")),
        secure: Page(secure, 403, "", blocked=True, error="сайт закрыт защитой от ботов"),
    })
    browser = FakeBrowser({
        wb: Page(wb, 200, WB_PAGE),
        dns: Page(dns, 200, html("jsonld_graph.html")),
        secure: Page(secure, 403, "", blocked=True,
                     error="сайт не пустил даже браузер (защита от ботов)"),
    })
    results = asyncio.run(check_all(tasks, {}, http, browser))
    # WB и DNS помечены «браузер» во встроенных настройках — обычный запрос к ним не делаем
    assert browser.opened == [wb, dns, secure]
    assert (results[0].product.price, results[0].product.old_price) == (Decimal("5694"),
                                                                        Decimal("13000"))
    assert results[0].product.name == "Куртка зимняя" and results[0].via == "browser"
    assert results[1].product.price == Decimal("12990.00")
    assert results[2].via == "http"                     # обычный сайт браузер не трогал
    assert "даже браузер" in results[3].error
    assert "через браузер: 2" in summary(results)


def test_browser_failed_to_start_keeps_http_results():
    wb, plain = "https://www.wildberries.ru/catalog/1/detail.aspx", "https://shop.ru/phone"
    tasks = [Task(2, wb, None), Task(3, plain, None)]
    http = FakeFetcher({plain: Page(plain, 200, html("jsonld_graph.html"))})
    results = asyncio.run(check_all(tasks, {}, http, FakeBrowser({}, fail=True)))
    assert "не запустился" in results[0].error
    assert results[1].product.price == Decimal("12990.00")


def test_without_browser_marked_sites_go_over_http():
    wb = "https://www.wildberries.ru/catalog/1/detail.aspx"
    http = FakeFetcher({wb: Page(wb, 498, "", blocked=True, error="сайт закрыт защитой от ботов")})
    results = asyncio.run(check_all([Task(2, wb, None)], {}, http, None))
    assert results[0].error == "сайт закрыт защитой от ботов"


def test_table_settings_override_builtin():
    """Своя строка для wildberries.ru на листе «Настройки» важнее встроенной."""
    wb = "https://www.wildberries.ru/catalog/1/detail.aspx"
    browser = FakeBrowser({wb: Page(wb, 200, '<b class="my-price">777 ₽</b>')})
    settings = read_settings([["wildberries.ru", ".my-price", "", "", "browser"]])
    results = asyncio.run(check_all([Task(2, wb, None)], settings, FakeFetcher({}), browser))
    assert results[0].product.price == Decimal("777")


def test_check_line_formats_result():
    from app.check import line
    from app.extract import Product
    from decimal import Decimal
    ok = Checked(Task(2, "https://shop.ru/1", None),
                 Product(name="Куртка", price=Decimal("4114"), old_price=Decimal("13000"), currency="RUB"),
                 None, "browser")
    assert "✓" in line(ok) and "Куртка | 4114 RUB, старая 13000 | через браузер" in line(ok)
    bad = Checked(Task(3, "https://shop.ru/2", None), None, "сайт не пустил")
    assert line(bad).startswith("✗") and "сайт не пустил" in line(bad)
