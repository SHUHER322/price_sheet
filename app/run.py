"""Одна проверка всех ссылок из таблицы: python -m app.run"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from .extract import Product, Selectors, extract
from .fetch import Fetcher, Page, domain
from .table import (SiteSettings, Task, history_row, read_settings, read_tasks, result_row,
                    settings_for, trend)

log = logging.getLogger(__name__)


@dataclass
class Checked:
    task: Task
    product: Product | None
    error: str | None
    via: str = "http"       # чем открывали: http / browser


def parse_page(task: Task, page: Page, site: SiteSettings | None) -> Checked:
    if not page.ok:
        return Checked(task, None, page.error)
    product = extract(page.html, site.selectors if site else Selectors())
    return Checked(task, product, None)


async def check_all(tasks: list[Task], settings: dict[str, SiteSettings],
                    fetcher: Fetcher) -> list[Checked]:
    """Загрузить и разобрать все страницы (параллельно, с паузами по доменам)."""
    async def one(task: Task) -> Checked:
        site = settings_for(domain(task.url), settings)
        page = await fetcher.get(task.url)
        return parse_page(task, page, site)
    return await asyncio.gather(*(one(t) for t in tasks))


def plan_writes(results: list[Checked], checked_at: datetime):
    """Из результатов — что записать на «Товары», чем подсветить и что добавить в «Историю»."""
    updates, trends, history = [], {}, []
    for r in results:
        col, values = result_row(r.task, r.product, r.error, checked_at)
        updates.append((r.task.row, col, values))
        if r.product and r.product.price is not None:
            trends[r.task.row] = trend(r.task, r.product)
            history.append(history_row(r.task, r.product, checked_at))
    return updates, trends, history


def summary(results: list[Checked]) -> str:
    found = [r for r in results if r.product and r.product.price is not None]
    down = sum(1 for r in found if trend(r.task, r.product) == "down")
    up = sum(1 for r in found if trend(r.task, r.product) == "up")
    return (f"Проверено ссылок: {len(results)}. Цена найдена: {len(found)}, "
            f"ошибок: {len(results) - len(found)}. Подешевело: {down}, подорожало: {up}.")


async def main() -> None:
    from .config import load_config
    from .sheet import PriceSheet

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    sheet = await asyncio.to_thread(PriceSheet, config.google_credentials, config.spreadsheet_id)
    tasks = read_tasks(await asyncio.to_thread(sheet.read_products))
    if not tasks:
        log.info("На листе «Товары» нет ссылок — вставьте их в столбец A и запустите снова")
        return
    settings = read_settings(await asyncio.to_thread(sheet.read_settings))
    log.info("Ссылок: %d, сайтов с настройками: %d", len(tasks), len(settings))

    async with Fetcher(config.concurrency, config.domain_delay) as fetcher:
        results = await check_all(tasks, settings, fetcher)

    checked_at = datetime.now(config.timezone)
    updates, trends, history = plan_writes(results, checked_at)
    await asyncio.to_thread(sheet.write_results, updates)
    await asyncio.to_thread(sheet.color_prices, trends)
    await asyncio.to_thread(sheet.append_history, history)
    for r in results:
        if r.error:
            log.warning("Строка %d: %s — %s", r.task.row, r.task.url, r.error)
    log.info(summary(results))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as error:
        logging.error("%s", error)
        raise SystemExit(1)
