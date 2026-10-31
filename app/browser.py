"""Запасной вариант: открыть страницу в настоящем Chrome (patchright).

Нужен для сайтов с защитой от ботов (DNS, Wildberries, Ozon…) и для магазинов,
где цена появляется только после работы скриптов. Chrome один на всю проверку:
страницы открываются по очереди в одной вкладке — так быстрее и меньше похоже на бота.
Профиль браузера (cookie) хранится в data/browser_profile: однажды пройдя проверку,
сайт в следующий раз пускает сразу.
"""
import asyncio
import logging
import random
from pathlib import Path

from .extract import Selectors, extract
from .fetch import Page, looks_blocked

log = logging.getLogger(__name__)

WAIT = 25          # сколько секунд ждать, пока пройдёт проверка и появится цена
POLL = 1.5         # как часто проверять страницу


class BrowserFetcher:
    def __init__(self, profile_dir: Path, pause: tuple[float, float] = (1.5, 3.5),
                 headless: bool = False):
        self.profile_dir = profile_dir
        self.pause = pause
        # Видимое окно: «безголовый» Chrome защиты распознают гораздо чаще.
        # На сервере окно рисуется на виртуальном экране (xvfb), как в price_monitor
        self.headless = headless
        self._pw = self._context = self._page = None
        self._used = False

    async def __aenter__(self):
        from patchright.async_api import async_playwright   # нужен, только если дошло до браузера
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir), channel="chrome",
            headless=self.headless, no_viewport=True)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        return self

    async def __aexit__(self, *exc):
        try:
            if self._context:
                await self._context.close()
        finally:
            if self._pw:
                await self._pw.stop()

    async def get(self, url: str, selectors: Selectors | None = None) -> Page:
        """Открыть страницу и дождаться цены (или понять, что её не будет)."""
        if self._used:
            await asyncio.sleep(random.uniform(*self.pause))   # не частим: так меньше банов
        self._used = True
        page = self._page
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            return Page(url, error=f"браузер не открыл страницу: {type(e).__name__}")
        status = response.status if response else None

        html = ""
        for _ in range(int(WAIT / POLL)):
            await asyncio.sleep(POLL)
            try:
                html = await page.content()
            except Exception:
                continue   # страница в этот момент перезагружается (прошла проверку) — ждём
            if not looks_blocked(None, html) and extract(html, selectors).price is not None:
                return Page(url, 200, html)
        if looks_blocked(None, html) or (status in (401, 403, 429, 498) and not html):
            return Page(url, status, html, blocked=True,
                        error="сайт не пустил даже браузер (защита от ботов)")
        return Page(url, status, html)   # открылась, но цены нет — разберёт extract и скажет
