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


def _number(name: str, default: str, kind=float):
    value = os.getenv(name, default)
    try:
        number = kind(value)
    except ValueError:
        raise RuntimeError(f"{name} должно быть числом, сейчас: {value!r}")
    if number <= 0:
        raise RuntimeError(f"{name} должно быть больше нуля, сейчас: {value!r}")
    return number


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
    return Config(credentials, spreadsheet_id, tz,
                  concurrency=_number("CONCURRENCY", "5", int),
                  domain_delay=_number("DOMAIN_DELAY", "1.5"),
                  browser=browser == "auto",
                  browser_profile=Path(os.getenv("BROWSER_PROFILE", "data/browser_profile")))
