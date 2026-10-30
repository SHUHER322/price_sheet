"""Поиск товара на сохранённых страницах с разной разметкой."""
from decimal import Decimal
from pathlib import Path

from app.extract import Selectors, extract

FIXTURES = Path(__file__).parent / "fixtures"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_json_ld_in_graph():
    p = extract(page("jsonld_graph.html"))
    assert p.name == "Смартфон X 128 ГБ, чёрный"
    assert p.price == Decimal("12990.00")
    assert p.currency == "RUB"
    assert p.in_stock is True
    assert p.old_price == Decimal("15490")      # по классу product-price__old
    assert p.sources[0] == "json-ld"


def test_microdata():
    p = extract(page("microdata.html"))
    assert (p.name, p.price, p.currency) == ("Чайник электрический Z-200", Decimal("2499"), "RUB")
    assert p.in_stock is False
    assert p.sources == ["microdata"]


def test_meta_tags_only():
    p = extract(page("meta_only.html"))
    assert (p.name, p.price, p.currency, p.in_stock) == ("Кружка «Утро»", Decimal("799"), "RUB", True)


def test_custom_selectors():
    sel = Selectors(price=".card .cost", old_price=".card .was", name="h1.title")
    p = extract(page("no_markup.html"), sel)
    assert p.name == "Рюкзак городской 20 л"
    assert p.price == Decimal("1299.90")
    assert p.old_price == Decimal("1599")
    assert p.currency == "RUB"
    assert p.sources[0] == "selectors"


def test_without_selectors_price_not_found():
    p = extract(page("no_markup.html"))
    assert p.price is None
    assert p.name == "Рюкзак городской 20 л"    # название всё равно берём из <h1>


def test_broken_json_ld_falls_back_to_microdata():
    p = extract(page("broken_jsonld.html"))
    assert p.price == Decimal("350")
    assert p.name == "Носки"


def test_selectors_win_over_markup():
    """Если разметка сайта врёт (например, старая цена в JSON-LD) — свои селекторы главнее."""
    sel = Selectors(price=".product-price__old")
    p = extract(page("jsonld_graph.html"), sel)
    assert p.price == Decimal("15490")
    assert p.name == "Смартфон X 128 ГБ, чёрный"   # остальное — из JSON-LD


def test_no_price_page():
    p = extract(page("no_price.html"))
    assert p.price is None and p.old_price is None


def test_old_price_ignored_if_not_bigger():
    html = ('<span itemprop="price" content="1000"></span>'
            '<span class="old-price">900 ₽</span>')
    assert extract(html).old_price is None


def test_offers_list_takes_first_with_price():
    html = ('<script type="application/ld+json">{"@type":"Product","name":"Футболка",'
            '"offers":[{"@type":"Offer"},{"@type":"Offer","price":"599","priceCurrency":"rub"}]}'
            '</script>')
    p = extract(html)
    assert (p.price, p.currency) == (Decimal("599"), "RUB")


def test_aggregate_offer_low_price():
    html = ('<script type="application/ld+json">{"@type":["Product"],"name":"Диван",'
            '"offers":{"@type":"AggregateOffer","lowPrice":24990,"highPrice":31990}}</script>')
    assert extract(html).price == Decimal("24990")


def test_book_type_with_offers():
    """Читай-город размечает книги как Book, а не Product — цену всё равно находим."""
    html = ('<script type="application/ld+json">{"@context":"https://schema.org","@graph":['
            '{"@type":"WebSite","name":"Читай-город"},'
            '{"@type":"Book","name":"Кошки, кофе, криминал","offers":{"@type":"Offer",'
            '"availability":"https://schema.org/InStock","price":"579.00","priceCurrency":"RUB"}}'
            ']}</script>'
            '<div class="product-offer-price__old"><span>695 </span></div>')
    p = extract(html)
    assert (p.name, p.price, p.currency, p.in_stock) == (
        "Кошки, кофе, криминал", Decimal("579.00"), "RUB", True)
    assert p.old_price == Decimal("695")


def test_microdata_price_with_space():
    """Стройпарк: itemprop=price content="3 649.00" — пробел в разрядах."""
    p = extract('<meta itemprop="price" content="3 649.00"><h1>Гайковерт</h1>')
    assert p.price == Decimal("3649.00")


def test_microdata_name_link_text_not_href():
    """Стройпарк: <a itemprop="name" href="/good/…">Гайковерт</a> — берём текст, а не адрес."""
    html = ('<div itemscope itemtype="https://schema.org/Product">'
            '<a href="/good/27724301" itemprop="name">Гайковерт QUATTRO ELEMENTI</a>'
            '<meta itemprop="price" content="3 649.00"></div>'
            '<del class="carrot-product-price-old">4 290.00 ₽</del>')
    p = extract(html)
    assert p.name == "Гайковерт QUATTRO ELEMENTI"
    assert p.old_price == Decimal("4290.00")
    assert p.currency == "RUB"          # не размечена — угадали по «₽» на странице
