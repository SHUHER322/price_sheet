from app.browser import has_text
from app.extract import extract
from app.presets import BUILTIN

# Так выглядит карточка WB после отрисовки (сокращено): в h1 — рейтинг, не название
WB_READY = """<html><head><title>Интернет-магазин Wildberries: широкий ассортимент</title>
<meta property="og:title" content="Интернет-магазин Wildberries: широкий ассортимент"></head><body>
<h1 class="ratingNumberMinimized--bNTVE">4,9</h1>
<h2 class="mo-typography productTitle--ktP8Z">Куртка зимняя, пуховик детский</h2>
<ins class="mo-typography priceBlockFinalPrice--iToZR">4 114 ₽</ins>
<del class="priceBlockOldPrice--qSWAf">13 000 ₽</del></body></html>"""

WB_NO_TITLE_YET = WB_READY.replace('<h2 class="mo-typography productTitle--ktP8Z">Куртка зимняя, пуховик детский</h2>', "")


def test_wb_preset_takes_product_title_not_rating_or_site_title():
    product = extract(WB_READY, BUILTIN["wildberries.ru"].selectors)
    assert product.name == "Куртка зимняя, пуховик детский"
    assert (product.price, product.old_price) == (4114, 13000)


def test_has_text_waits_for_title():
    css = BUILTIN["wildberries.ru"].selectors.name
    assert has_text(WB_READY, css)
    assert not has_text(WB_NO_TITLE_YET, css)
    assert not has_text('<h2 class="productTitle--x">  </h2>', css)
