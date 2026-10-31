"""Настройки из файла .env."""
import os
from pathlib import Path
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    google_credentials: str
    spreadsheet_id: str
    timezone: ZoneInfo        # по нему пишется время проверки в таблицу
    concurrency: int          # сколько страниц загружать одновременно
    domain_delay: float       # пауза между запросами к одному сайту, секунды
    browser: bool             # включён ли запасной браузер (Chrome через patchright)
    browser_profile: Path     # где браузер хранит cookie между запусками
    interval_hours: float     # как часто проверять в режиме app.watch
    telegram_token: str       # пусто — уведомления выключены
    telegram_chat_ids: tuple[int, ...]
    notify_price_up: bool     # сообщать и о подорожании


def _number(name: str, default: str, kind=float):
    value = os.getenv(name, default)
    try:
        number = kind(value)
    except ValueError:
        raise RuntimeError(f"{name} должно быть числом, сейчас: {value!r}")
    if number <= 0:
        raise RuntimeError(f"{name} должно быть больше нуля, сейчас: {value!r}")
    return number


def _chat_ids(value: str) -> tuple[int, ...]:
    """'123, 456' → (123, 456). Можно несколько получателей или ID группы (с минусом)."""
    ids = []
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            raise RuntimeError(f"TELEGRAM_CHAT_ID — числа через запятую, сейчас: {value!r}")
    return tuple(dict.fromkeys(ids))


def load_config() -> Config:
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("Заполни SPREADSHEET_ID в .env — часть адреса таблицы между /d/ и /edit")
    credentials = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
    if not os.path.exists(credentials):
        raise RuntimeError(f"Не найден ключ Google {credentials!r} — положи credentials.json "
                           "в папку проекта (как в lead_bot)")
    tz_name = os.getenv("TIMEZONE", "Asia/Tomsk")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(f"Неизвестный часовой пояс TIMEZONE={tz_name!r}")
    browser = os.getenv("BROWSER", "auto").strip().lower()
    if browser not in ("auto", "off"):
        raise RuntimeError(f"BROWSER — auto или off, сейчас: {browser!r}")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = _chat_ids(os.getenv("TELEGRAM_CHAT_ID", ""))
    if token and not chat_ids:
        raise RuntimeError("Указан TELEGRAM_BOT_TOKEN, но пуст TELEGRAM_CHAT_ID — кому слать?")
    return Config(credentials, spreadsheet_id, tz,
                  concurrency=_number("CONCURRENCY", "5", int),
                  domain_delay=_number("DOMAIN_DELAY", "1.5"),
                  browser=browser == "auto",
                  browser_profile=Path(os.getenv("BROWSER_PROFILE", "data/browser_profile")),
                  interval_hours=_number("INTERVAL_HOURS", "6"),
                  telegram_token=token,
                  telegram_chat_ids=chat_ids,
                  notify_price_up=os.getenv("NOTIFY_PRICE_UP", "0").strip() in ("1", "yes", "да"))
