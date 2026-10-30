"""Загрузка страниц обычными HTTP-запросами (httpx) и распознавание заглушек защиты.

Вежливость к сайтам: всего не больше CONCURRENCY запросов одновременно, а к одному
домену — строго по очереди с паузой DOMAIN_DELAY. Так магазины не воспринимают нас
как атаку и реже блокируют.
"""
import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

HEADERS = {
    # Обычный Chrome на Windows: с «пустым» User-Agent многие сайты сразу отвечают 403
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

# Признаки страницы-заглушки: проверка браузера, капча, DDoS-защита
BLOCK_MARKERS = re.compile(
    r"captcha|проверка браузера|проверяем ваш браузер|ddos-guard|qrator|variti|"
    r"cf-chl|challenge-platform|just a moment|access denied|доступ ограничен|"
    r"подтвердите, что вы не робот|are you a robot|servicepipe",
    re.IGNORECASE,
)
BLOCK_STATUSES = {401, 403, 429, 498, 503}


@dataclass
class Page:
    url: str
    status: int | None = None
    html: str = ""
    error: str | None = None     # человекочитаемая причина, если страницу не получили
    blocked: bool = False        # сайт отдал заглушку защиты — стоит попробовать браузер

    @property
    def ok(self) -> bool:
        return self.error is None


def domain(url: str) -> str:
    """https://www.shop.ru/item/1 → shop.ru (без www — так проще в «Настройках»)."""
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.").lower()


def looks_blocked(status: int | None, html: str) -> bool:
    """Заглушка защиты вместо товара. Маркеры ищем только в коротких страницах:
    на нормальной карточке слово «captcha» может встретиться в скриптах формы отзыва."""
    if status in BLOCK_STATUSES:
        return True
    head = html[:30000]
    return len(html) < 60000 and bool(BLOCK_MARKERS.search(head))


def describe_status(status: int) -> str:
    return {404: "страница не найдена (404)", 410: "товар удалён (410)"}.get(
        status, f"сайт ответил ошибкой {status}")


class Fetcher:
    def __init__(self, concurrency: int = 5, domain_delay: float = 1.5, timeout: float = 20,
                 client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(headers=HEADERS, timeout=timeout,
                                                   follow_redirects=True, http2=False)
        self._limit = asyncio.Semaphore(concurrency)
        self._delay = domain_delay
        self._domain_locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def get(self, url: str) -> Page:
        lock = self._domain_locks.setdefault(domain(url), asyncio.Lock())
        async with lock:
            async with self._limit:
                page = await self._get(url)
            # Пауза держит «замок» домена (следующий запрос к этому сайту подождёт),
            # но не общий лимит — запросы к другим сайтам в это время идут
            await asyncio.sleep(self._delay)
            return page

    async def _get(self, url: str) -> Page:
        if not url.lower().startswith(("http://", "https://")):
            return Page(url, error="ссылка должна начинаться с http:// или https://")
        try:
            response = await self._client.get(url)
        except httpx.TimeoutException:
            return Page(url, error="сайт не ответил вовремя")
        except httpx.HTTPError as e:
            return Page(url, error=f"не удалось открыть: {type(e).__name__}")
        html = response.text
        if looks_blocked(response.status_code, html):
            return Page(url, response.status_code, html, blocked=True,
                        error="сайт закрыт защитой от ботов")
        if response.status_code >= 400:
            return Page(url, response.status_code, html, error=describe_status(response.status_code))
        return Page(url, response.status_code, html)

    async def get_all(self, urls: list[str]) -> list[Page]:
        return await asyncio.gather(*(self.get(u) for u in urls))
