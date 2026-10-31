"""Проверка по расписанию: python -m app.watch

Первая проверка — сразу, дальше раз в INTERVAL_HOURS часов. Ошибка одной проверки
(Google недоступен, нет интернета) не останавливает расписание — следующая пройдёт по плану.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from .config import load_config
from .run import run_and_notify, setup_logging

log = logging.getLogger(__name__)


async def sleep_until(moment: datetime) -> None:
    """Спим короткими отрезками и сверяемся с часами: если компьютер уходил в сон,
    проверка не «уплывёт» на часы вперёд."""
    while (left := (moment - datetime.now(moment.tzinfo)).total_seconds()) > 0:
        await asyncio.sleep(min(left, 60))


async def main() -> None:
    setup_logging()
    config = load_config()
    every = timedelta(hours=config.interval_hours)
    log.info("Проверка цен каждые %g ч. Остановить: Ctrl + C", config.interval_hours)
    while True:
        started = datetime.now(config.timezone)
        try:
            await run_and_notify(config)
        except Exception:
            log.exception("Проверка не удалась — попробую в следующий раз")
        next_run = started + every
        log.info("Следующая проверка: %s", next_run.strftime("%d.%m.%Y %H:%M"))
        await sleep_until(next_run)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Остановлено")
    except RuntimeError as error:
        logging.error("%s", error)
        raise SystemExit(1)
