"""Встроенные настройки для популярных площадок — чтобы заказчику не вписывать их самому.

Свои строки на листе «Настройки» важнее встроенных: если площадка поменяет вёрстку,
селектор можно поправить в таблице, не дожидаясь обновления программы.
"""
from .extract import Selectors
from .table import SiteSettings

BUILTIN: dict[str, SiteSettings] = {
    # Цена рисуется скриптом, классы с «хвостом» (priceBlockFinalPrice--yEKcc),
    # поэтому ищем по началу имени класса. Название — из og:title.
    "wildberries.ru": SiteSettings(
        Selectors(price='[class*="priceBlockFinalPrice"]',
                  old_price='[class*="priceBlockOldPrice"]',
                  name='meta[property="og:title"]'),
        browser=True),
    "wb.ru": SiteSettings(
        Selectors(price='[class*="priceBlockFinalPrice"]',
                  old_price='[class*="priceBlockOldPrice"]',
                  name='meta[property="og:title"]'),
        browser=True),
    # Защита Qrator: обычный запрос получает 401, браузер проходит, дальше — JSON-LD
    "dns-shop.ru": SiteSettings(Selectors(), browser=True),
    "ozon.ru": SiteSettings(Selectors(), browser=True),
}


def with_builtin(settings: dict[str, SiteSettings]) -> dict[str, SiteSettings]:
    """Встроенные + из таблицы; при совпадении домена побеждает таблица."""
    return {**BUILTIN, **settings}
