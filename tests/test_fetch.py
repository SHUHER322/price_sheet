"""Загрузка страниц: заглушки защиты, ошибки, очередь по доменам."""
import asyncio
import time

import httpx
import pytest

from app.fetch import Fetcher, domain, looks_blocked


class FakeResponse:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


class FakeClient:
    """Вместо настоящего httpx: отвечает по заранее заданным правилам и ведёт журнал."""
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    async def get(self, url):
        self.calls.append((url, time.monotonic()))
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(*answer)

    async def aclose(self):
        pass


def run(fetcher, urls):
    return asyncio.run(fetcher.get_all(urls))


def test_domain():
    assert domain("https://www.Shop.ru/item/1?x=2") == "shop.ru"
    assert domain("http://m.shop.ru") == "m.shop.ru"


@pytest.mark.parametrize("status, html, blocked", [
    (200, "<html>Обычная страница товара</html>", False),
    (403, "<html>Forbidden</html>", True),
    (429, "", True),
    (200, "<title>Just a moment...</title>", True),
    (200, "<h1>Проверка браузера</h1> DDoS-Guard", True),
    (200, "x" * 70000 + "captcha", False),     # большая нормальная страница со словом captcha
])
def test_looks_blocked(status, html, blocked):
    assert looks_blocked(status, html) is blocked


def test_fetch_ok_errors_and_block():
    client = FakeClient({
        "https://a.ru/1": (200, "<html>ok</html>"),
        "https://b.ru/1": (404, "not found"),
        "https://c.ru/1": (403, "denied"),
        "https://d.ru/1": httpx.TimeoutException("slow"),
        "ftp://e.ru/1": (200, ""),
    })
    pages = run(Fetcher(domain_delay=0, client=client), list(client.answers))
    ok, missing, blocked, slow, bad = pages
    assert ok.ok and ok.html == "<html>ok</html>"
    assert missing.error == "страница не найдена (404)" and not missing.blocked
    assert blocked.blocked and blocked.error == "сайт закрыт защитой от ботов"
    assert slow.error == "сайт не ответил вовремя"
    assert "http://" in bad.error


def test_same_domain_requests_are_spaced():
    urls = ["https://a.ru/1", "https://a.ru/2", "https://b.ru/1"]
    client = FakeClient({u: (200, "ok") for u in urls})
    run(Fetcher(domain_delay=0.2, client=client), urls)
    times = {u: t for u, t in client.calls}
    assert times["https://a.ru/2"] - times["https://a.ru/1"] >= 0.19   # один сайт — по очереди
    assert abs(times["https://b.ru/1"] - times["https://a.ru/1"]) < 0.1  # разные — параллельно
