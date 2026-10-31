"""Текст уведомления в Telegram и отправка."""
import asyncio
from decimal import Decimal

from app.extract import Product
from app.notify import build_message, send_telegram
from app.run import Checked
from app.table import Task


def checked(row, old, new, name="Товар", old_stock="", in_stock=None, url=None):
    task = Task(row, url or f"https://shop.ru/{row}", Decimal(old) if old else None, name, old_stock)
    product = Product(name=name, price=Decimal(new), in_stock=in_stock) if new else None
    return Checked(task, product, None)


def test_nothing_new_no_message():
    results = [checked(2, "100", "100"), checked(3, None, "50")]
    assert build_message(results) is None


def test_errors_alone_do_not_trigger():
    failed = Checked(Task(2, "https://x.ru", None), None, "сайт закрыт защитой от ботов")
    assert build_message([failed]) is None


def test_price_drops_sorted_by_size():
    results = [checked(2, "1000", "950", "Мелкая скидка"),
               checked(3, "60999", "52999", "iPhone 15"),
               checked(4, "100", "120", "Подорожал")]
    text = build_message(results)
    assert text.startswith("📉 <b>Подешевело</b> (2):")
    assert text.index("iPhone 15") < text.index("Мелкая скидка")      # −13% выше −5%
    assert "60 999 → 52 999 ₽ (−13,1%)" in text
    assert 'href="https://shop.ru/3"' in text                         # точки в адресе целы
    assert "Подорожал" not in text                                    # рост — только по флагу
    assert "Подорожало" in build_message(results, price_up=True)


def test_stock_changes_and_failed_count():
    results = [checked(2, "100", "100", "Книга", old_stock="нет в наличии", in_stock=True),
               checked(3, "100", "100", "Куртка", old_stock="в наличии", in_stock=False),
               Checked(Task(4, "https://x.ru", None), None, "сайт не ответил вовремя")]
    text = build_message(results)
    assert "📦 <b>Снова в наличии</b> (1):\n• Книга" in text
    assert "🚫 <b>Закончилось</b> (1):\n• Куртка" in text
    assert "Не удалось проверить: 1" in text


def test_html_escaped_and_long_list_cut():
    results = [checked(i, "100", "90", f"<b>Товар {i}</b>") for i in range(2, 30)]
    text = build_message(results)
    assert "&lt;b&gt;Товар 2&lt;/b&gt;" in text
    assert "…и ещё 8" in text


class FakeResponse:
    def __init__(self, status):
        self.status_code, self.text = status, "{}"


class FakeClient:
    def __init__(self):
        self.sent = []

    async def post(self, url, json):
        self.sent.append(json["chat_id"])
        return FakeResponse(200 if json["chat_id"] != 2 else 403)

    async def aclose(self):
        pass


def test_send_to_all_even_if_one_fails():
    client = FakeClient()
    delivered = asyncio.run(send_telegram("T", [1, 2, 3], "hi", client=client))
    assert client.sent == [1, 2, 3] and delivered == 2
