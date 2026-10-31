"""Проверить ссылки без Google Таблицы: python -m app.check ССЫЛКА [ССЫЛКА ...]

Нужно, чтобы быстро понять, берутся ли цены с сайтов заказчика, и чтобы проверить
запасной браузер на сервере (в Docker: xvfb-run -a python -m app.check ...).
Ничего не записывает — только печатает, что нашлось.
"""
import asyncio
import logging
import sys
from pathlib import Path

from .fetch import Fetcher
from .run import check_all
from .table import Task


def line(r) -> str:
    p = r.product
    if r.error or not p or p.price is None:
        return f"✗ {r.task.url}\n    {r.error or 'цена не найдена'}"
    old = f", старая {p.old_price}" if p.old_price is not None else ""
    return (f"✓ {r.task.url}\n    {p.name or '—'} | {p.price} {p.currency or ''}{old} | "
            f"через {'браузер' if r.via == 'browser' else 'обычный запрос'}")


async def main(urls: list[str], browser: bool = True) -> int:
    from .browser import BrowserFetcher

    tasks = [Task(i + 2, url, None) for i, url in enumerate(urls)]
    factory = (lambda: BrowserFetcher(Path("data/browser_profile"))) if browser else None
    async with Fetcher(concurrency=5, domain_delay=1.5) as fetcher:
        results = await check_all(tasks, {}, fetcher, factory)
    for r in results:
        print(line(r), flush=True)
    return sum(1 for r in results if r.product and r.product.price is not None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = [a for a in sys.argv[1:] if a != "--no-browser"]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    found = asyncio.run(main(args, browser="--no-browser" not in sys.argv))
    raise SystemExit(0 if found == len(args) else 1)
