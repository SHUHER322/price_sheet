"""Уведомление в Telegram после проверки: что подешевело, что снова в наличии.

Шлём одно сообщение и только когда есть новости — чтобы бот не спамил «ничего не изменилось».
Отправка — простым запросом к Telegram Bot API, отдельная библиотека для бота не нужна.
"""
import html
import logging
from decimal import Decimal

import httpx

from .table import IN_STOCK, OUT_OF_STOCK, _num, trend

log = logging.getLogger(__name__)

MAX_LINES = 20        # длинные списки обрезаем: подробности всё равно в таблице
TELEGRAM_LIMIT = 4000


def _rub(value: Decimal) -> str:
    return _num(value).replace(".", ",")


def _title(r) -> str:
    name = (r.product.name if r.product and r.product.name else r.task.name) or r.task.url
    return html.escape(name if len(name) <= 60 else name[:57] + "…")


def _change_line(r) -> str:
    old, new = r.task.old_price, r.product.price
    percent = (new - old) / old * 100
    sign = "−" if percent < 0 else "+"
    pct = f"{abs(percent):.1f}".replace(".", ",")
    return (f"• <a href=\"{html.escape(r.task.url, quote=True)}\">{_title(r)}</a> — "
            f"{_rub(old)} → {_rub(new)} ₽ ({sign}{pct}%)")


def _section(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    shown = lines[:MAX_LINES]
    more = f"\n…и ещё {len(lines) - MAX_LINES}" if len(lines) > MAX_LINES else ""
    return f"{title} ({len(lines)}):\n" + "\n".join(shown) + more


def build_message(results, price_up: bool = False) -> str | None:
    """Текст уведомления или None, если сообщать не о чем."""
    found = [r for r in results if r.product and r.product.price is not None]
    down = [r for r in found if trend(r.task, r.product) == "down"]
    up = [r for r in found if trend(r.task, r.product) == "up"] if price_up else []
    back = [r for r in found if r.task.old_stock == OUT_OF_STOCK and r.product.in_stock]
    gone = [r for r in found if r.task.old_stock == IN_STOCK and r.product.in_stock is False]
    failed = [r for r in results if r.error]

    # Сортируем по размеру изменения: самое заметное — сверху
    down.sort(key=lambda r: r.product.price / r.task.old_price)
    up.sort(key=lambda r: r.task.old_price / r.product.price)

    parts = [
        _section("📉 <b>Подешевело</b>", [_change_line(r) for r in down]),
        _section("📈 <b>Подорожало</b>", [_change_line(r) for r in up]),
        _section("📦 <b>Снова в наличии</b>", [f"• {_title(r)}" for r in back]),
        _section("🚫 <b>Закончилось</b>", [f"• {_title(r)}" for r in gone]),
    ]
    parts = [p for p in parts if p]
    if not parts:
        return None   # ошибки без новостей не шлём — их видно в таблице
    if failed:
        parts.append(f"⚠️ Не удалось проверить: {len(failed)} — причины в столбце «Ошибка»")
    text = "\n\n".join(parts)
    return text if len(text) <= TELEGRAM_LIMIT else text[:TELEGRAM_LIMIT - 1] + "…"


async def send_telegram(token: str, chat_ids, text: str, client: httpx.AsyncClient | None = None) -> int:
    """Отправить всем получателям. Ошибка одного не мешает остальным. Возвращает, скольким дошло."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    delivered = 0
    try:
        for chat_id in chat_ids:
            try:
                r = await client.post(url, json={"chat_id": chat_id, "text": text,
                                                 "parse_mode": "HTML",
                                                 "disable_web_page_preview": True})
                if r.status_code == 200:
                    delivered += 1
                else:
                    log.error("Telegram не принял сообщение для %s: %s", chat_id, r.text[:200])
            except httpx.HTTPError:
                # Токен в адресе — не пишем исключение целиком в лог
                log.error("Не удалось отправить уведомление в Telegram (%s)", chat_id)
    finally:
        if own:
            await client.aclose()
    return delivered
