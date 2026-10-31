"""Поиск товара на странице: название, цена, старая цена, валюта, наличие.

Почти все интернет-магазины размечают товар для поисковиков, поэтому парсер
сначала читает эту разметку — она одинакова на тысячах сайтов:
  1. свои CSS-селекторы для домена (лист «Настройки»), если заданы;
  2. JSON-LD (schema.org Product) — <script type="application/ld+json">;
  3. микроразметка schema.org — itemprop="price";
  4. мета-теги Open Graph / product:price:amount.
Чего не нашлось в одном источнике, ищется в следующих.
"""
import json
from dataclasses import dataclass, field
from decimal import Decimal

from bs4 import BeautifulSoup, Tag

from .prices import parse_currency, parse_price

# Типичные классы зачёркнутой «старой» цены в шаблонах магазинов
OLD_PRICE_SELECTOR = (
    '[class*="old-price"], [class*="price-old"], [class*="old_price"], [class*="price_old"], '
    '[class*="oldprice"], [class*="oldPrice"], [class*="OldPrice"], [class*="price--old"], '
    '[class*="price__old"]'
)
IN_STOCK = ("instock", "in_stock", "limitedavailability", "onlineonly", "preorder", "presale")
OUT_OF_STOCK = ("outofstock", "out_of_stock", "soldout", "discontinued")


@dataclass(frozen=True)
class Selectors:
    """Свои CSS-селекторы для сайта, где разметки нет или она неверная."""
    price: str = ""
    name: str = ""
    old_price: str = ""


@dataclass
class Product:
    name: str | None = None
    price: Decimal | None = None
    old_price: Decimal | None = None
    currency: str | None = None
    in_stock: bool | None = None          # None — сайт не сообщает
    sources: list[str] = field(default_factory=list)  # откуда что взяли — для отладки

    def merge(self, other: "Product", source: str) -> None:
        """Дополнить пустые поля найденным в следующем источнике."""
        used = False
        for name in ("name", "price", "old_price", "currency", "in_stock"):
            if getattr(self, name) is None and getattr(other, name) is not None:
                setattr(self, name, getattr(other, name))
                used = True
        if used:
            self.sources.append(source)


def _availability(value) -> bool | None:
    text = str(value or "").lower().replace(" ", "").rsplit("/", 1)[-1]
    if any(mark in text for mark in OUT_OF_STOCK):
        return False
    if any(mark in text for mark in IN_STOCK):
        return True
    return None


def _clean(text: str | None) -> str | None:
    """Лишние пробелы и «хвосты» вроде «Куртка зимняя, » (так бывает в og:title у WB)."""
    text = " ".join((text or "").split()).rstrip(" ,;|–-")
    return text or None


# --- 1. свои селекторы ---

def _from_selectors(soup: BeautifulSoup, sel: Selectors) -> Product:
    def text(css: str) -> str | None:
        if not css:
            return None
        el = soup.select_one(css)
        if el is None:
            return None
        return el.get("content") or el.get_text(" ", strip=True)

    price_text = text(sel.price)
    return Product(name=_clean(text(sel.name)), price=parse_price(price_text),
                   old_price=parse_price(text(sel.old_price)),
                   currency=parse_currency(price_text))


# --- 2. JSON-LD ---

def _walk_json(node):
    """Все словари внутри JSON-LD: в @graph, списках и вложенных объектах."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


OFFER_TYPES = {"offer", "aggregateoffer"}


def _is_product(node: dict) -> bool:
    """Товар — любой объект с «offers»: Product, но и Book (Читай-город), Car, Event…
    Сами Offer пропускаем — их разбираем внутри товара."""
    kind = node.get("@type")
    kinds = {str(k).lower() for k in (kind if isinstance(kind, list) else [kind])}
    return bool(node.get("offers")) and not kinds & OFFER_TYPES


def _from_json_ld(soup: BeautifulSoup) -> Product:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue  # битый JSON на сайте — просто пропускаем этот блок
        for node in _walk_json(data):
            if not _is_product(node):
                continue
            offers = node.get("offers") or {}
            offer_list = offers if isinstance(offers, list) else [offers]
            # Вариант товара с ценой: первый, где она указана
            for offer in offer_list:
                if not isinstance(offer, dict):
                    continue
                price = parse_price(offer.get("price") or offer.get("lowPrice"))
                if price is None and isinstance(offer.get("priceSpecification"), dict):
                    price = parse_price(offer["priceSpecification"].get("price"))
                if price is None:
                    continue
                name = node.get("name")
                return Product(name=_clean(name if isinstance(name, str) else None),
                               price=price,
                               currency=_clean(offer.get("priceCurrency")),
                               in_stock=_availability(offer.get("availability")))
    return Product()


# --- 3. микроразметка ---

def _itemprop(scope: Tag, prop: str) -> Tag | None:
    return scope.find(attrs={"itemprop": prop})


def _prop_value(el: Tag | None) -> str | None:
    """Значение itemprop: у <meta> — content, у <link> — href, у остальных — текст.
    Важно не брать href у ссылки: <a itemprop="name" href="/good/1">Гайковерт</a>
    (так у Стройпарка) — название здесь текст, а не адрес."""
    if el is None:
        return None
    if el.name == "link":
        return el.get("href")
    return el.get("content") or el.get_text(" ", strip=True)


def _from_microdata(soup: BeautifulSoup) -> Product:
    scope = soup.find(attrs={"itemtype": lambda v: v and "schema.org/Product" in v}) or soup
    price_el = _itemprop(scope, "price")
    if price_el is None:
        return Product()
    name_el = _itemprop(scope, "name")
    return Product(name=_clean(_prop_value(name_el)),
                   price=parse_price(_prop_value(price_el)),
                   currency=_clean(_prop_value(_itemprop(scope, "priceCurrency"))),
                   in_stock=_availability(_prop_value(_itemprop(scope, "availability"))))


# --- 4. мета-теги ---

def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if el and el.get("content"):
            return el["content"]
    return None


def _from_meta(soup: BeautifulSoup) -> Product:
    return Product(
        name=_clean(_meta(soup, "og:title")),
        price=parse_price(_meta(soup, "product:price:amount", "og:price:amount")),
        currency=_clean(_meta(soup, "product:price:currency", "og:price:currency")),
        in_stock=_availability(_meta(soup, "product:availability", "og:availability")),
    )


def _old_price_guess(soup: BeautifulSoup, price: Decimal | None) -> Decimal | None:
    """Зачёркнутая цена по типичным классам. Берём, только если она больше текущей."""
    if price is None:
        return None
    for el in soup.select(OLD_PRICE_SELECTOR)[:5]:
        value = parse_price(el.get("content") or el.get_text(" ", strip=True))
        if value and value > price:
            return value
    return None


def extract(html: str, selectors: Selectors | None = None) -> Product:
    """Главная функция: HTML страницы → что удалось узнать о товаре."""
    soup = BeautifulSoup(html, "html.parser")
    product = Product()
    if selectors and (selectors.price or selectors.name or selectors.old_price):
        product.merge(_from_selectors(soup, selectors), "selectors")
    product.merge(_from_json_ld(soup), "json-ld")
    product.merge(_from_microdata(soup), "microdata")
    product.merge(_from_meta(soup), "meta")
    if product.old_price is None:
        guess = _old_price_guess(soup, product.price)
        if guess:
            product.old_price = guess
            product.sources.append("old-price-class")
    if product.name is None:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else (soup.title.string if soup.title else None)
        product.name = _clean(title)
    if product.currency is None and product.price is not None:
        # Валюту не указали в разметке — угадываем по знакам на странице (₽, руб, $…)
        product.currency = parse_currency(soup.get_text(" ")[:200000])
    if product.currency:
        product.currency = product.currency.upper()
        if product.currency in ("RUR", "РУБ"):
            product.currency = "RUB"
    return product
