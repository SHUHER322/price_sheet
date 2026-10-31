"""Что и как пишем в таблицу. Чистые функции — без Google и сети, легко тестировать.

Лист «Товары»: заказчик заполняет только столбец «Ссылка», остальное пишет парсер.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .extract import Product, Selectors

PRODUCTS_HEADER = ["Ссылка", "Название", "Цена", "Старая цена", "Валюта", "Наличие",
                   "Изменение", "Проверено", "Ошибка"]
HISTORY_HEADER = ["Дата", "Ссылка", "Название", "Цена", "Старая цена", "Наличие"]
SETTINGS_HEADER = ["Домен", "Селектор цены", "Селектор названия", "Селектор старой цены",
                   "Режим (auto / browser)"]

COL = {name: i for i, name in enumerate(PRODUCTS_HEADER)}
IN_STOCK, OUT_OF_STOCK, UNKNOWN = "в наличии", "нет в наличии", "—"


@dataclass(frozen=True)
class SiteSettings:
    selectors: Selectors
    browser: bool = False     # всегда открывать через браузер


@dataclass
class Task:
    row: int                  # номер строки на листе (с 2, первая — заголовок)
    url: str
    old_price: Decimal | None # цена с прошлой проверки — чтобы посчитать изменение
    name: str = ""            # название с прошлой проверки — для уведомления об ошибке
    old_stock: str = ""       # «Наличие» с прошлой проверки — чтобы заметить «снова в наличии»


def to_number(value) -> Decimal | None:
    """Ячейка → число. В таблице может быть «12 990», «12990,5» или пусто."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except Exception:
        return None


def read_tasks(rows: list[list]) -> list[Task]:
    """Строки листа «Товары» (без заголовка) → что проверять. Пустые ссылки пропускаем."""
    tasks = []
    for i, row in enumerate(rows, start=2):
        url = str(row[0]).strip() if row else ""
        if not url:
            continue
        cell_at = lambda name: str(row[COL[name]]).strip() if len(row) > COL[name] else ""  # noqa: E731
        tasks.append(Task(i, url, to_number(cell_at("Цена")), cell_at("Название"),
                          cell_at("Наличие")))
    return tasks


def read_settings(rows: list[list]) -> dict[str, SiteSettings]:
    """Строки листа «Настройки» → настройки по домену."""
    result = {}
    for row in rows:
        cells = [str(c).strip() for c in row] + [""] * 5
        site = cells[0].lower().removeprefix("https://").removeprefix("http://")
        site = site.removeprefix("www.").split("/")[0]
        if not site:
            continue
        result[site] = SiteSettings(Selectors(price=cells[1], name=cells[2], old_price=cells[3]),
                                    browser=cells[4].lower() in ("browser", "браузер"))
    return result


def settings_for(domain: str, settings: dict[str, SiteSettings]) -> SiteSettings | None:
    """Настройки для домена или его родителя: m.shop.ru найдёт запись shop.ru."""
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        found = settings.get(".".join(parts[i:]))
        if found:
            return found
    return None


def change_text(old: Decimal | None, new: Decimal | None) -> str:
    """«▼ −500 (−3,7%)», «▲ +200 (+1,5%)», «без изменений» или «первая проверка»."""
    if new is None:
        return ""
    if old is None:
        return "первая проверка"
    if new == old:
        return "без изменений"
    diff = new - old
    percent = diff / old * 100 if old else Decimal(0)
    arrow = "▼" if diff < 0 else "▲"
    sign = "−" if diff < 0 else "+"
    return f"{arrow} {sign}{_num(abs(diff))} ({sign}{abs(percent):.1f}%)".replace(".", ",")


def _num(value: Decimal) -> str:
    """12990 → '12 990', 1299.90 → '1 299.9' (точку потом меняем на запятую)."""
    value = value.normalize()
    whole, _, frac = f"{value:f}".partition(".")
    whole = f"{int(whole):,}".replace(",", " ")
    return whole + ("." + frac if frac else "")


def stock_text(in_stock: bool | None) -> str:
    return {True: IN_STOCK, False: OUT_OF_STOCK}.get(in_stock, UNKNOWN)


def cell(value: Decimal | None):
    """Число для таблицы: int или float, чтобы Google считал его числом, а не текстом."""
    if value is None:
        return ""
    return int(value) if value == value.to_integral() else float(value)


def result_row(task: Task, product: Product | None, error: str | None,
               checked_at: datetime) -> tuple[str, list]:
    """Что записать в строку: (первый столбец, значения подряд).

    Успех — столбцы B…I целиком. Ошибка — только H…I («Проверено», «Ошибка»): старые
    название и цену не затираем, чтобы таблица не «пустела» из-за временного сбоя сайта.
    """
    when = checked_at.strftime("%d.%m.%Y %H:%M")
    if product is None or product.price is None:
        reason = error or "цена на странице не найдена — задайте селектор на листе «Настройки»"
        return "H", [when, reason]
    return "B", [
        product.name or "",
        cell(product.price),
        cell(product.old_price),
        product.currency or "",
        stock_text(product.in_stock),
        change_text(task.old_price, product.price),
        when,
        "",
    ]


def history_row(task: Task, product: Product, checked_at: datetime) -> list:
    return [checked_at.strftime("%d.%m.%Y %H:%M"), task.url, product.name or "",
            cell(product.price), cell(product.old_price), stock_text(product.in_stock)]


def trend(task: Task, product: Product | None) -> str | None:
    """'down' / 'up' — для подсветки ячейки цены; None — без подсветки."""
    if product is None or product.price is None or task.old_price is None:
        return None
    if product.price < task.old_price:
        return "down"
    if product.price > task.old_price:
        return "up"
    return None
