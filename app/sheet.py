"""Работа с Google Таблицей через gspread: листы «Товары», «История», «Настройки».

gspread синхронный, поэтому вызывающий код запускает эти методы в отдельном потоке
(asyncio.to_thread) — пока идёт запрос к Google, загрузка страниц не стоит.
"""
import logging

import gspread

from .table import HISTORY_HEADER, PRODUCTS_HEADER, SETTINGS_HEADER

log = logging.getLogger(__name__)

PRODUCTS, HISTORY, SETTINGS = "Товары", "История", "Настройки"
GREEN = {"red": 0.85, "green": 0.94, "blue": 0.83}   # цена снизилась
RED = {"red": 0.98, "green": 0.85, "blue": 0.84}     # цена выросла
WHITE = {"red": 1, "green": 1, "blue": 1}


class PriceSheet:
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        client = gspread.service_account(filename=credentials_path)
        self.book = client.open_by_key(spreadsheet_id)
        self.products = self._sheet(PRODUCTS, PRODUCTS_HEADER, rename_first=True)
        self.history = self._sheet(HISTORY, HISTORY_HEADER)
        self.settings = self._sheet(SETTINGS, SETTINGS_HEADER)

    def _sheet(self, title: str, header: list[str], rename_first: bool = False):
        """Лист с заголовком. Нет листа — создаём; пустой «Лист1» новой таблицы переименуем."""
        try:
            ws = self.book.worksheet(title)
        except gspread.WorksheetNotFound:
            first = self.book.sheet1
            if rename_first and not any(first.get_all_values()):
                first.update_title(title)
                ws = first
            else:
                ws = self.book.add_worksheet(title, rows=1000, cols=len(header))
            log.info("Создан лист «%s»", title)
        if ws.row_values(1) != header:
            ws.update([header], "A1")
            ws.format("1:1", {"textFormat": {"bold": True}})
            ws.freeze(rows=1)
        return ws

    def read_products(self) -> list[list]:
        return self.products.get_all_values()[1:]

    def read_settings(self) -> list[list]:
        return self.settings.get_all_values()[1:]

    def write_results(self, updates: list[tuple[int, str, list]]) -> None:
        """updates — (строка, первый столбец, значения). Одним запросом на все строки."""
        if updates:
            self.products.batch_update(
                [{"range": f"{col}{row}", "values": [values]} for row, col, values in updates],
                value_input_option="RAW")  # RAW — Google не превратит текст в дату или формулу
            try:  # ширина столбцов B–I по содержимому, чтобы дата и ошибка не обрезались
                self.products.columns_auto_resize(1, len(PRODUCTS_HEADER))
            except Exception:
                log.warning("Не удалось подогнать ширину столбцов", exc_info=True)

    def color_prices(self, trends: dict[int, str | None]) -> None:
        """Подсветка ячейки «Цена»: зелёная — подешевело, красная — подорожало."""
        if not trends:
            return
        color = {"down": GREEN, "up": RED, None: WHITE}
        self.products.batch_format([{"range": f"C{row}",
                                     "format": {"backgroundColor": color[t]}}
                                    for row, t in trends.items()])

    def append_history(self, rows: list[list]) -> None:
        if rows:
            self.history.append_rows(rows, value_input_option="RAW")
