#!/usr/bin/env python3
"""
Ski gear deal monitor.

This intentionally uses only the Python standard library so it can run from a
plain local checkout or a scheduled Codex automation without dependency setup.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "deal_sources.json"
DATA_DIR = ROOT / "data"
JSON_OUTPUT = DATA_DIR / "deals.json"
HTML_OUTPUT = DATA_DIR / "deals.html"
MD_OUTPUT = DATA_DIR / "deal_report.md"
PRICE_HISTORY_OUTPUT = DATA_DIR / "price_history.json"
EVO_CONSTRUCTOR_KEY_CACHE = DATA_DIR / "evo_constructor_key.json"
CLOTHING_JSON_OUTPUT = DATA_DIR / "clothing_deals.json"
PREFERENCES_CONFIG = ROOT / "config" / "deal_preferences.json"
WEB_DIR = ROOT / "ski-deals"
WEB_OUTPUT = WEB_DIR / "index.html"

# Keep this looking like a real, current browser. WAFs flag stale Chrome
# versions and custom UA suffixes (the old "... SkiDealMonitor/1.0" tail was a
# likely trigger for evo's 403s).
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

PRICE_RE = re.compile(r"\$\s?([0-9]{1,4}(?:,[0-9]{3})?(?:\.[0-9]{2})?)")
SPACE_RE = re.compile(r"\s+")
MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>https?://[^)]+)\)")
MARKDOWN_IMAGE_LINK_RE = re.compile(
    r"\[(?P<prefix>[^\]]*?)!\[(?P<alt>[^\]]*)\]\((?P<img>[^)]+)\)(?P<tail>[^\]]*?)\]\((?P<url>https?://[^)]+)\)",
    re.DOTALL,
)
EMBEDDED_PROMO_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(https?://static\.evo\.com/[^)]+\)",
    re.IGNORECASE,
)
JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
REMIX_CONTEXT_RE = re.compile(r"window\.__remixContext\s*=\s*(\{.*?\});__remixContext\.p", re.DOTALL)
GEARTRADE_CARD_RE = re.compile(r"<product-card\b.*?</product-card>", re.IGNORECASE | re.DOTALL)
GEARTRADE_TITLE_RE = re.compile(
    r'<a(?=[^>]*\bcard-link\b)(?=[^>]*href="(?P<href>[^"]+)")[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
GEARTRADE_PRICE_RE = re.compile(
    r'<strong[^>]+class="[^"]*\bprice__current\b[^"]*"[^>]*>\$(?P<dollars>[0-9,]+)<sup>(?P<cents>[0-9]{2})',
    re.IGNORECASE | re.DOTALL,
)
GEARTRADE_DISCOUNT_RE = re.compile(r"(?P<discount>[0-9]{1,3})%\s*Off", re.IGNORECASE)
GEARTRADE_SIZE_RE = re.compile(r'<span[^>]+class="[^"]*\bplp_size\b[^"]*"[^>]*>.*?<b>\s*Size:\s*</b>\s*&nbsp;\s*(?P<size>[^<]+)', re.IGNORECASE | re.DOTALL)
GEARTRADE_IMAGE_RE = re.compile(r'<img[^>]+(?:src|data-src)="(?P<src>[^"]+)"', re.IGNORECASE | re.DOTALL)
CAMPSAVER_GRID_RE = re.compile(
    r'<div\b(?P<attrs>[^>]*\bgtmProduct\b[^>]*)>(?P<body>.*?)(?=<div\b[^>]*\bgtmProduct\b|<script\b|</main>|</body>)',
    re.IGNORECASE | re.DOTALL,
)
HTML_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
EVO_COLLECTION_ITEM_RE = re.compile(
    r'\{id:"[^"]+",name:"(?P<name>(?:[^"\\]|\\.)+)",.*?variant:"(?P<variant>(?:[^"\\]|\\.)*)",'
    r'\s*price:\s*"(?P<price>[^"]+)",.*?variantId:\s*"(?P<variant_id>\d+)",.*?handle:"(?P<handle>[^"]+)",\s*compareAtPrice:\s*"(?P<compare>[^"]+)"',
    re.DOTALL,
)
EVO_META_RE = re.compile(r"var meta = (?P<payload>\{\"products\":.*?\"page\":\{.*?\}\});", re.DOTALL)
EVO_CONSTRUCTOR_KEY_RE = re.compile(r'window\.eHS\.constructor_index_key\s*=\s*"(?P<key>[^"]+)"')
BLOCK_PATTERNS = [
    "before we continue",
    "human challenge",
    "captcha",
    "access denied",
    "forbidden",
    "verify you are human",
    "unusual traffic",
    "attention required",
    "sorry, you have been blocked",
    "something went wrong",
    "looking to shop",
    "awswaf",
    "challenge.js",
    "max challenge attempts exceeded",
    "javascript is disabled",
    "request blocked",
    "cloudfront",
]


@dataclass
class Deal:
    title: str
    url: str
    source: str
    current_price: float
    original_price: float | None
    discount_percent: float | None
    savings: float | None
    score: float
    found_at: str
    sizes: list[str] | None = None
    stock_status: str | None = None
    image_url: str | None = None
    is_cached: bool = False
    previous_price: float | None = None
    price_change: float | None = None
    price_change_percent: float | None = None
    price_trend: str | None = None
    first_seen_at: str | None = None
    lowest_price: float | None = None
    highest_price: float | None = None


@dataclass
class SourceError:
    source: str
    url: str
    error: str


class LinkTextParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._active_href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value for key, value in attrs if value}
        href = attr_map.get("href")
        if href:
            self._active_href = urljoin(self.base_url, href)
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_href:
            return
        text = clean_text(" ".join(self._text_parts))
        if text:
            self.links.append({"url": self._active_href, "text": text})
        self._active_href = None
        self._text_parts = []


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(value)).strip()


def money(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"[0-9][0-9,]*(?:\.[0-9]+)?", str(value))
    if not match:
        return None
    try:
        return round(float(match.group(0).replace(",", "")), 2)
    except ValueError:
        return None


def image_url(value: Any, base_url: str = "") -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = clean_text(value)
        if not candidate:
            return None
        if candidate.startswith("//"):
            return f"https:{candidate}"
        if candidate.startswith(("http://", "https://")):
            return candidate
        if base_url and candidate.startswith("/"):
            return urljoin(base_url, candidate)
        return None
    if isinstance(value, list):
        for item in value:
            candidate = image_url(item, base_url)
            if candidate:
                return candidate
    if isinstance(value, dict):
        for key in ("src", "url", "image", "imageUrl", "thumbnail", "thumbnailUrl"):
            candidate = image_url(value.get(key), base_url)
            if candidate:
                return candidate
        for key in ("nodes", "edges"):
            candidate = image_url(value.get(key), base_url)
            if candidate:
                return candidate
    return None


def first_image_from_fields(item: dict[str, Any], base_url: str, fields: tuple[str, ...]) -> str | None:
    for field in fields:
        candidate = image_url(item.get(field), base_url)
        if candidate:
            return candidate
    return None


def fetch(url: str, timeout: int = 25) -> str:
    request = Request(url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def reader_url(url: str) -> str:
    return f"https://r.jina.ai/http://r.jina.ai/http://{quote(url, safe='')}"


def reader_url_variants(url: str) -> list[str]:
    variants = [url]
    parsed = urlparse(url)
    if parsed.scheme == "https":
        variants.append(urlunparse(parsed._replace(scheme="http")))
    return [reader_url(variant) for variant in variants]


def fetch_reader_target(url: str, timeout: int = 45) -> str:
    last_error: Exception | None = None
    last_block: str | None = None
    for candidate in reader_url_variants(url):
        try:
            markup = fetch(candidate, timeout=timeout)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last_error = error
            continue
        blocked = block_reason(markup)
        if not blocked:
            return markup
        last_block = blocked

    if last_block:
        raise OSError(last_block)
    if last_error:
        raise last_error
    raise OSError("Reader fallback failed")


def block_reason(markup: str) -> str | None:
    if "collectionView:{" in markup and "handle:" in markup and "compareAtPrice:" in markup:
        return None

    sample = clean_text(markup[:15000]).lower()
    for pattern in BLOCK_PATTERNS:
        if pattern in sample:
            return f"Blocked by retailer anti-bot page: {pattern}"
    return None


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def keyword_allowed(title: str, keywords: list[str], excludes: list[str]) -> bool:
    lowered = title.lower()
    if any(exclude_keyword_matches(lowered, excluded) for excluded in excludes):
        return False
    return not keywords or any(keyword.lower() in lowered for keyword in keywords)


def exclude_keyword_matches(value: str, keyword: str) -> bool:
    normalized = keyword.lower().strip()
    if not normalized:
        return False
    if normalized in {"kid", "kids", "kid's", "kids'"}:
        return bool(re.search(r"(?<![a-z0-9])kids?'?s?(?![a-z0-9])", value))
    pattern = re.escape(normalized).replace(r"\ ", r"[-\s]+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", value))


def flatten_json_ld(item: Any) -> list[dict[str, Any]]:
    if isinstance(item, list):
        flattened: list[dict[str, Any]] = []
        for child in item:
            flattened.extend(flatten_json_ld(child))
        return flattened
    if not isinstance(item, dict):
        return []

    nodes: list[dict[str, Any]] = []
    item_type = item.get("@type")
    types = item_type if isinstance(item_type, list) else [item_type]
    if any(str(kind).lower() == "product" for kind in types):
        nodes.append(item)

    graph = item.get("@graph")
    if graph:
        nodes.extend(flatten_json_ld(graph))

    for key in ("itemListElement", "offers", "mainEntity", "hasVariant"):
        if key in item:
            nodes.extend(flatten_json_ld(item[key]))

    if "item" in item:
        nodes.extend(flatten_json_ld(item["item"]))

    return nodes


def json_ld_candidates(markup: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    deals: list[Deal] = []
    for match in JSON_LD_RE.finditer(markup):
        raw = clean_text(match.group(1))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for product in flatten_json_ld(payload):
            title = clean_text(str(product.get("name", "")))
            if not title:
                continue

            offers = product.get("offers", {})
            offer = offers[0] if isinstance(offers, list) and offers else offers
            offer = offer if isinstance(offer, dict) else {}

            current = money(offer.get("price") or product.get("price"))
            price_spec = offer.get("priceSpecification")
            price_spec_price = price_spec.get("price") if isinstance(price_spec, dict) else None
            original = money(offer.get("highPrice") or price_spec_price)
            url = offer.get("url") or product.get("url") or base_url
            if current:
                deals.append(
                    make_deal(
                        title,
                        urljoin(base_url, str(url)),
                        source_name,
                        current,
                        original,
                        found_at,
                        image_url=image_url(product.get("image"), base_url),
                    )
                )
    return deals


def remix_candidates(markup: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    match = REMIX_CONTEXT_RE.search(markup)
    if not match:
        return []

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    loader_data = payload.get("state", {}).get("loaderData", {})
    deals: list[Deal] = []
    for route_data in loader_data.values():
        collection = route_data.get("collection") if isinstance(route_data, dict) else None
        products = collection.get("products", {}).get("nodes", []) if isinstance(collection, dict) else []
        for product in products:
            deals.extend(product_variant_deals(product, base_url, source_name, found_at))
    return deals


def shopify_products_json_candidates(
    payload_text: str,
    base_url: str,
    source_name: str,
    found_at: str,
    ignore_sold_out: bool = True,
    required_tags: list[str] | None = None,
    required_variant_terms: list[str] | None = None,
    size_min_cm: int | None = None,
    size_max_cm: int | None = None,
) -> list[Deal]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return []

    deals: list[Deal] = []
    required_tag_set = {tag.lower() for tag in required_tags or []}
    required_terms = [term.lower() for term in required_variant_terms or []]
    for product in payload.get("products", []):
        title = clean_text(str(product.get("title", "")))
        handle = product.get("handle")
        if not title or not handle:
            continue
        product_tags = {str(tag).lower() for tag in product.get("tags", [])}
        if required_tag_set and not required_tag_set.issubset(product_tags):
            continue

        product_url = urljoin(base_url, f"/products/{handle}")
        product_image = image_url(product.get("image"), base_url) or image_url(product.get("images"), base_url)
        for variant in product.get("variants", []):
            if ignore_sold_out and not variant.get("available", True):
                continue

            current = money(variant.get("price"))
            if current is None:
                continue

            original = money(variant.get("compare_at_price"))
            variant_title = normalize_shopify_variant_title(variant.get("title"))
            variant_text = variant_title.lower()
            if required_terms and not all(term in variant_text for term in required_terms):
                continue
            if not shopify_variant_size_allowed(variant_title, size_min_cm, size_max_cm):
                continue
            variant_size = shopify_variant_size_label(variant_title)
            deal_title = title if variant_title in ("", "Default Title") else f"{title} - {variant_title}"
            deals.append(
                make_deal(
                    deal_title,
                    product_url,
                    source_name,
                    current,
                    original,
                    found_at,
                    sizes=[variant_size] if variant_size else None,
                    image_url=image_url(variant.get("featured_image"), base_url) or product_image,
                )
            )

    return deals


def shopify_variant_size_label(variant_title: str) -> str | None:
    match = re.search(r"\b(\d{2,3})\s*cm\b", variant_title, re.IGNORECASE)
    return f"{int(match.group(1))}cm" if match else None


def shopify_variant_size_allowed(variant_title: str, size_min_cm: int | None, size_max_cm: int | None) -> bool:
    if size_min_cm is None and size_max_cm is None:
        return True
    label = shopify_variant_size_label(variant_title)
    if not label:
        return False
    size = int(label.removesuffix("cm"))
    if size_min_cm is not None and size < size_min_cm:
        return False
    if size_max_cm is not None and size > size_max_cm:
        return False
    return True


def searchspring_candidates(
    payload_text: str,
    base_url: str,
    source_name: str,
    found_at: str,
) -> list[Deal]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return []

    deals: list[Deal] = []
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue

        title = clean_text(str(item.get("name") or item.get("title") or ""))
        current = money(item.get("price") or item.get("ss_price"))
        original = money(item.get("msrp") or item.get("compare_at_price"))
        if not title or current is None:
            continue

        handle = clean_text(str(item.get("handle") or ""))
        item_url = clean_text(str(item.get("url") or ""))
        if handle:
            item_url = urljoin(base_url, f"/products/{handle}")
        elif item_url:
            item_url = item_url.replace("https://utahskis.myshopify.com", "https://utahskis.com")
        else:
            item_url = base_url

        deals.append(
            make_deal(
                title,
                item_url,
                source_name,
                current,
                original,
                found_at,
                sizes=searchspring_sizes(item),
                stock_status="in_stock" if str(item.get("ss_sold_out", "0")) != "1" else "sold_out",
                image_url=first_image_from_fields(
                    item,
                    base_url,
                    (
                        "thumbnailImageUrl",
                        "imageUrl",
                        "image",
                        "thumbnail",
                        "ss_image",
                        "ss_image_url",
                        "primary_image",
                    ),
                ),
            )
        )

    return deals


def searchspring_sizes(item: dict[str, Any]) -> list[str] | None:
    sizes: set[str] = set()
    for value in item.get("ss_variants_in_stock") or []:
        text = clean_text(str(value))
        for pattern in (
            r"\boption1=([^,}]+)",
            r"\bdisplay_name=[^-]+-\s*([^,}]+)",
            r"\btitle=([^,}]+)",
        ):
            match = re.search(pattern, text)
            if not match:
                continue
            size = normalize_shopify_variant_title(match.group(1))
            if size and re.search(r"\d", size):
                sizes.add(size)
                break
    return sorted(sizes) or None


def product_variant_deals(product: dict[str, Any], base_url: str, source_name: str, found_at: str) -> list[Deal]:
    title = clean_text(str(product.get("title", "")))
    handle = product.get("handle")
    if not title or not handle:
        return []

    product_url = urljoin(base_url, f"/products/{handle}")
    product_image = image_url(product.get("featuredImage"), base_url) or image_url(product.get("images"), base_url)
    variants = product.get("variants", {}).get("nodes", [])
    deals: list[Deal] = []
    for variant in variants:
        if not variant.get("availableForSale", True):
            continue

        current = money(variant.get("price", {}).get("amount"))
        if current is None:
            continue

        original = money((variant.get("compareAtPrice") or {}).get("amount"))
        variant_title = normalize_shopify_variant_title(variant.get("title"))
        deal_title = title if variant_title in ("", "Default Title") else f"{title} - {variant_title}"
        deals.append(make_deal(deal_title, product_url, source_name, current, original, found_at, image_url=product_image))
    return deals


def normalize_shopify_variant_title(value: Any) -> str:
    title = clean_text(str(value or ""))
    if not title:
        return ""
    return clean_text(re.sub(r"(?i)\s*/\s*n/?a\s*$", "", title))


def link_candidates(markup: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    parser = LinkTextParser(base_url)
    parser.feed(markup)
    deals: list[Deal] = []

    for link in parser.links:
        prices = extract_offer_prices(link["text"], source_name)
        if not prices:
            continue

        current, original = choose_prices(prices)
        title = PRICE_RE.sub("", link["text"])
        title = clean_text(re.sub(r"\b(now|sale|was|reg|regular|from|save)\b", " ", title, flags=re.I))
        if len(title) < 8:
            continue
        deals.append(make_deal(title, link["url"], source_name, current, original, found_at))

    return deals


def markdown_candidates(markdown: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    if "Markdown Content:" in markdown:
        markdown = markdown.split("Markdown Content:", 1)[1]

    # Evo's reader view sometimes injects a second promo image inside a
    # product card. Remove those embedded badges so the outer product link
    # still parses as a single markdown image link.
    markdown = EMBEDDED_PROMO_IMAGE_RE.sub(" ", markdown)

    deals = markdown_image_candidates(markdown, source_name, found_at)
    deals.extend(markdown_sierra_sequence_candidates(markdown, source_name, found_at))
    return deals


def campsaver_grid_candidates(markup: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    if "campsaver" not in source_name.lower():
        return []

    deals: list[Deal] = []
    for match in CAMPSAVER_GRID_RE.finditer(markup):
        attrs = {name.lower(): html.unescape(value) for name, value in HTML_ATTR_RE.findall(match.group("attrs"))}
        title = clean_text(attrs.get("data-name") or "")
        current = money(attrs.get("data-price"))
        slug = attrs.get("data-url") or ""
        if not title or current is None or not slug:
            continue

        body = match.group("body")
        save_match = re.search(r"Save\s+(?:Up\s+to\s+)?\$\s?([0-9,]+(?:\.[0-9]{2})?)", body, re.I)
        savings = money(save_match.group(1)) if save_match else None
        original = round(current + savings, 2) if savings else None
        image_match = re.search(r'<img[^>]+src="(?P<src>[^"]+)"', body, re.I | re.DOTALL)
        model_match = re.search(r'title="(?P<count>[0-9]+\s+models?)\s+available"', body, re.I)
        flag_match = re.search(r'class="[^"]*\bgrid__item-flag\b[^"]*".*?<span\s+title="(?P<flag>[^"]+)"', body, re.I | re.DOTALL)
        prefix = f"{model_match.group('count')} " if model_match else ""
        suffix = f" {clean_text(flag_match.group('flag'))}" if flag_match else ""
        product_url = urljoin(base_url, slug if slug.endswith(".html") else f"{slug}.html")
        deals.append(
            make_deal(
                f"{prefix}{title}{suffix}",
                product_url,
                source_name,
                current,
                original,
                found_at,
                image_url=image_url(image_match.group("src"), base_url) if image_match else None,
            )
        )

    return deals


def geartrade_search_candidates(markup: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    deals: list[Deal] = []
    for card in GEARTRADE_CARD_RE.findall(markup):
        title_match = GEARTRADE_TITLE_RE.search(card)
        price_match = GEARTRADE_PRICE_RE.search(card)
        if not title_match or not price_match:
            continue

        title = clean_text(re.sub(r"<[^>]+>", " ", title_match.group("title")))
        if len(title) < 4:
            continue

        current = money(f"{price_match.group('dollars')}.{price_match.group('cents')}")
        if current is None:
            continue

        discount_match = GEARTRADE_DISCOUNT_RE.search(card)
        discount = float(discount_match.group("discount")) if discount_match else None
        original = None
        if discount and 0 < discount < 100:
            original = round(current / (1 - (discount / 100)), 2)

        size_match = GEARTRADE_SIZE_RE.search(card)
        image_match = GEARTRADE_IMAGE_RE.search(card)
        sizes = [clean_text(size_match.group("size"))] if size_match else None
        deals.append(
            make_deal(
                title,
                urljoin(base_url, html.unescape(title_match.group("href"))),
                source_name,
                current,
                original,
                found_at,
                sizes=sizes,
                image_url=image_url(image_match.group("src"), base_url) if image_match else None,
            )
        )
    return deals


def evo_collection_candidates(markup: str, base_url: str, source_name: str, found_at: str) -> list[Deal]:
    if "evo.com" not in base_url:
        return []

    size_prefixes = evo_size_prefixes(base_url)
    if not size_prefixes:
        return []

    meta_products = evo_meta_products(markup)
    availability_cache: dict[str, dict[str, Any] | None] = {}
    deals: list[Deal] = []
    for match in EVO_COLLECTION_ITEM_RE.finditer(markup):
        handle = clean_text(match.group("handle").replace("\\/", "/"))
        title = clean_text(match.group("name").replace("\\/", "/"))
        current = money(match.group("price"))
        original = money(match.group("compare"))
        if not title or not handle or current is None:
            continue

        sizes, stock_status = evo_collection_stock_details(
            meta_products.get(handle),
            evo_product_availability(availability_cache, base_url, handle),
            current,
            size_prefixes,
        )
        if not sizes:
            continue

        deals.append(
            make_deal(
                title,
                urljoin(base_url, f"/products/{handle}"),
                source_name,
                current,
                original,
                found_at,
                sizes=sizes,
                stock_status=stock_status,
                image_url=evo_meta_product_image(meta_products.get(handle), base_url),
            )
        )

    return deals


def evo_hydrated_collection_candidates(
    markup: str,
    base_url: str,
    source_name: str,
    found_at: str,
    max_results: int,
) -> list[Deal]:
    if "evo.com" not in base_url:
        return []

    api_key = evo_constructor_api_key(markup)
    if not api_key:
        return []

    save_cached_evo_constructor_key(api_key)
    return evo_constructor_deals(api_key, base_url, source_name, found_at, max_results)


def evo_api_fallback_candidates(
    base_url: str,
    source: dict[str, Any],
    source_name: str,
    found_at: str,
    max_results: int,
) -> list[Deal]:
    """Query evo's Constructor search API directly when the page fetch is blocked.

    The API key is a public client-side key embedded in evo's pages. It rarely
    changes, so the last key seen on a successful page fetch is cached and
    reused here; a `constructor_key` field on the source config wins if set.
    """
    if "evo.com" not in base_url:
        return []

    api_key = clean_text(str(source.get("constructor_key") or "")) or load_cached_evo_constructor_key()
    if not api_key:
        return []
    return evo_constructor_deals(api_key, base_url, source_name, found_at, max_results)


def evo_constructor_deals(
    api_key: str,
    base_url: str,
    source_name: str,
    found_at: str,
    max_results: int,
) -> list[Deal]:
    parsed = urlparse(base_url)
    base_query = parse_qs(parsed.query, keep_blank_values=True)
    page = 1
    per_page = min(max_results, 100)
    deals: list[Deal] = []

    while len(deals) < max_results:
        url = evo_constructor_api_url(api_key, base_query, page, per_page)
        try:
            with urlopen(Request(url, headers=REQUEST_HEADERS), timeout=30) as response:
                payload = json.load(response)
        except (json.JSONDecodeError, HTTPError, URLError, TimeoutError, OSError):
            break

        page_results = payload.get("response", {}).get("results", [])
        if not isinstance(page_results, list) or not page_results:
            break

        for item in page_results:
            deal = evo_constructor_result_deal(item, source_name, found_at)
            if deal:
                deals.append(deal)
            if len(deals) >= max_results:
                break

        total = payload.get("response", {}).get("total_num_results")
        if not isinstance(total, int) or page * per_page >= total:
            break
        page += 1

    return deals[:max_results]


def evo_constructor_api_key(markup: str) -> str | None:
    match = EVO_CONSTRUCTOR_KEY_RE.search(markup)
    return match.group("key") if match else None


def load_cached_evo_constructor_key(path: Path | None = None) -> str | None:
    path = path or EVO_CONSTRUCTOR_KEY_CACHE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    key = clean_text(str(payload.get("key") or "")) if isinstance(payload, dict) else ""
    return key or None


def save_cached_evo_constructor_key(api_key: str, path: Path | None = None) -> None:
    path = path or EVO_CONSTRUCTOR_KEY_CACHE
    if load_cached_evo_constructor_key(path) == api_key:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"key": api_key, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def evo_constructor_api_url(api_key: str, query: dict[str, list[str]], page: int, per_page: int) -> str:
    params: list[tuple[str, str]] = [
        ("key", api_key),
        ("sort_by", (query.get("sortBy") or ["relevance"])[0]),
        ("sort_order", (query.get("sortOrder") or ["descending"])[0]),
        ("num_results_per_page", str(per_page)),
        ("page", str(page)),
    ]
    for key, values in query.items():
        if key in {"sortBy", "sortOrder", "page"}:
            continue
        if key.startswith("filters["):
            for value in values:
                params.append((key, value))
    return "https://ac.cnstrc.com/browse/group_id/skis?" + "&".join(
        f"{quote(key, safe='')}={quote(value, safe='')}" for key, value in params
    )


def evo_constructor_result_deal(item: Any, source_name: str, found_at: str) -> Deal | None:
    if not isinstance(item, dict):
        return None
    data = item.get("data")
    title = clean_text(str(item.get("value", "")))
    if not isinstance(data, dict) or not title:
        return None

    url = clean_text(str(data.get("url") or ""))
    current = money(data.get("price"))
    original = money(data.get("compare_at_price"))
    size = clean_text(str(data.get("size") or ""))
    if not url or current is None:
        return None

    stock_status = "in_stock" if data.get("availability", False) else "sold_out"
    sizes = [size] if evo_size_text(size) else None
    return make_deal(
        title,
        url,
        source_name,
        current,
        original,
        found_at,
        sizes=sizes,
        stock_status=stock_status,
        image_url=first_image_from_fields(
            data,
            url,
            (
                "image_url",
                "image",
                "thumbnail_url",
                "thumbnail",
                "primary_image",
                "groups_image_url",
            ),
        ),
    )


def evo_stock_status_from_payload(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return "availability_unknown"
    if payload.get("available", False):
        return "in_stock"
    return "sold_out"


def evo_size_text(value: str) -> bool:
    return bool(re.search(r"\b\d{2,3}\s*cm\b", value, re.I))


def evo_meta_products(markup: str) -> dict[str, dict[str, Any]]:
    match = EVO_META_RE.search(markup)
    if not match:
        return {}

    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return {}

    products = payload.get("products", [])
    return {
        clean_text(str(product.get("handle", ""))): product
        for product in products
        if isinstance(product, dict) and product.get("handle")
    }


def evo_meta_product_image(product: dict[str, Any] | None, base_url: str) -> str | None:
    if not isinstance(product, dict):
        return None
    return first_image_from_fields(
        product,
        base_url,
        (
            "featured_image",
            "featuredImage",
            "image",
            "imageUrl",
            "images",
        ),
    )


def evo_product_availability(
    cache: dict[str, dict[str, Any] | None],
    base_url: str,
    handle: str,
) -> dict[str, Any] | None:
    if handle in cache:
        return cache[handle]

    product_url = urljoin(base_url, f"/products/{handle}.js")
    try:
        payload = json.loads(fetch(product_url, timeout=30))
    except (json.JSONDecodeError, HTTPError, URLError, TimeoutError, OSError):
        payload = None

    cache[handle] = payload if isinstance(payload, dict) else None
    return cache[handle]


def evo_collection_stock_details(
    product: dict[str, Any] | None,
    availability_payload: dict[str, Any] | None,
    current_price: float,
    size_prefixes: set[str],
) -> tuple[list[str], str | None]:
    if not isinstance(product, dict):
        return [], None

    available_variant_ids = evo_available_variant_ids(availability_payload)
    matching_sizes: list[str] = []
    available_sizes: list[str] = []
    for variant in product.get("variants", []):
        if not isinstance(variant, dict):
            continue
        variant_id = str(variant.get("id") or "")
        variant_price = evo_meta_variant_price(variant.get("price"))
        variant_title = clean_text(str(variant.get("public_title") or ""))
        if (
            not variant_id
            or variant_price != current_price
            or not evo_variant_matches_size_filter(variant_title, size_prefixes)
        ):
            continue
        matching_sizes.append(variant_title)
        if variant_id in available_variant_ids:
            available_sizes.append(variant_title)

    if available_sizes:
        return sorted(set(available_sizes)), "in_stock"
    if matching_sizes:
        if availability_payload is None:
            return sorted(set(matching_sizes)), "availability_unknown"
        return sorted(set(matching_sizes)), "sold_out"
    return [], None


def evo_available_variant_ids(payload: dict[str, Any] | None) -> set[str]:
    if not isinstance(payload, dict) or not payload.get("available", False):
        return set()

    return {
        str(variant.get("id"))
        for variant in payload.get("variants", [])
        if isinstance(variant, dict) and variant.get("available", False) and variant.get("id") is not None
    }


def evo_meta_variant_price(value: Any) -> float | None:
    if isinstance(value, int):
        return round(value / 100, 2)
    if isinstance(value, str) and value.isdigit():
        return round(int(value) / 100, 2)
    return money(value)


def evo_size_prefixes(base_url: str) -> set[str]:
    query = parse_qs(urlparse(base_url).query)
    prefixes: set[str] = set()
    for value in query.get("filters[size]", []):
        match = re.search(r"\b([0-9]{2})[0-9]\s*cm\b", value, re.I)
        if match:
            prefixes.add(match.group(1))
    return prefixes


def evo_variant_matches_size_filter(variant_title: str, size_prefixes: set[str]) -> bool:
    match = re.search(r"\b([0-9]{2})[0-9]\s*cm\b", variant_title, re.I)
    return bool(match and match.group(1) in size_prefixes)


def markdown_image_candidates(markdown: str, source_name: str, found_at: str) -> list[Deal]:
    deals: list[Deal] = []
    matches = list(MARKDOWN_IMAGE_LINK_RE.finditer(markdown))
    for index, match in enumerate(matches):
        url = match.group("url")
        if not is_product_url(url):
            continue

        title = clean_markdown_image_title(match.group("alt"))
        if len(title) < 8:
            title = clean_markdown_title(
                f"{match.group('prefix')} {match.group('alt')} {match.group('tail')}"
            )
        if not title:
            title = title_from_sierra_image(match.group("img"))
        if not title or len(title) < 8:
            continue

        next_start = matches[index + 1].start() if index + 1 < len(matches) else min(len(markdown), match.end() + 800)
        block = markdown[match.start() : next_start]
        prices = extract_offer_prices(block, source_name)
        if not prices:
            continue

        compare_at = re.search(r"Compare At\s+\$\s?([0-9,]+(?:\.[0-9]{2})?)", block, re.I)
        list_at = re.search(r"\bList:?\s+\$\s?([0-9,]+(?:\.[0-9]{2})?)", block, re.I)
        current, original = choose_prices(prices)
        if compare_at:
            original = money(compare_at.group(1))
        elif list_at:
            original = money(list_at.group(1))
        deals.append(make_deal(title, url, source_name, current, original, found_at, image_url=image_url(match.group("img"))))
    return deals


def clean_markdown_image_title(value: str) -> str:
    value = clean_markdown_title(value)
    value = re.sub(r"^(?:image\s+)?\d+\s*:?\s*", "", value, flags=re.I)
    return value


def markdown_sierra_sequence_candidates(markdown: str, source_name: str, found_at: str) -> list[Deal]:
    deals: list[Deal] = []
    matches = list(MARKDOWN_LINK_RE.finditer(markdown))

    for index, match in enumerate(matches):
        label = match.group("label")
        url = match.group("url")
        if "sierra.com" not in url or "~p~" not in url:
            continue

        next_start = matches[index + 1].start() if index + 1 < len(matches) else min(len(markdown), match.end() + 500)
        block = markdown[match.end() : next_start]
        title = clean_markdown_title(label)
        if title.lower().startswith("image"):
            img_match = re.search(r"https://[^)]+/([^/~]+(?:-[^/~]+)*)~p~", match.group(0))
            title = img_match.group(1).replace("-", " ").title() if img_match else ""

        prices = extract_prices(block)
        if not title or not prices:
            continue

        current = prices[0]
        original_match = re.search(r"Compare At\s+\$\s?([0-9,]+(?:\.[0-9]{2})?)", block, re.I)
        original = money(original_match.group(1)) if original_match else (prices[1] if len(prices) > 1 else None)
        deals.append(make_deal(title, url, source_name, current, original, found_at))

    return deals


def extract_prices(value: str) -> list[float]:
    prices = [money(match.group(1)) for match in PRICE_RE.finditer(value)]
    return [price for price in prices if price is not None]


def extract_offer_prices(value: str, source_name: str) -> list[float]:
    if "campsaver" in source_name.lower():
        # CampSaver variant rows include "Save $X" next to List/current prices.
        # Treating that savings amount as a price creates impossible $69 ski deals.
        value = re.sub(r"\bSave\s+(?:Up\s+to\s+)?\$\s?[0-9,]+(?:\.[0-9]{2})?", " ", value, flags=re.I)
    return extract_prices(value)


def choose_prices(prices: list[float]) -> tuple[float, float | None]:
    if len(prices) == 1:
        return prices[0], None
    current = min(prices)
    original = max(prices)
    return current, original if original > current else None


def clean_markdown_title(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"\b(Image|Sale|Compare|View Selections)\b", " ", value, flags=re.I)
    value = PRICE_RE.sub(" ", value)
    value = re.sub(r"\b(Sale\s*-\s*)\b", " ", value, flags=re.I)
    return collapse_repeated_title(clean_text(value))


def collapse_repeated_title(value: str) -> str:
    parts = value.split()
    if len(parts) % 2:
        return collapse_repeated_prefix(parts, value)
    midpoint = len(parts) // 2
    if parts[:midpoint] == parts[midpoint:]:
        return " ".join(parts[:midpoint])
    return collapse_repeated_prefix(parts, value)


def collapse_repeated_prefix(parts: list[str], fallback: str) -> str:
    max_prefix = len(parts) // 2
    for size in range(max_prefix, 2, -1):
        if parts[:size] == parts[size : size * 2]:
            return " ".join(parts[:size] + parts[size * 2 :])
    return fallback


def title_from_sierra_image(image_url: str) -> str:
    filename = image_url.rsplit("/", 1)[-1]
    slug = filename.split("~p~", 1)[0]
    slug = re.sub(r"-in-[a-z0-9-]+$", "", slug, flags=re.I)
    return clean_text(slug.replace("-", " ")).title()


def is_product_url(url: str) -> bool:
    if "sierra.com" in url:
        return "~p~" in url
    if "evo.com" in url:
        return "static.evo.com" not in url and "/shop/" not in url
    if "campsaver.com" in url:
        return True
    return url.startswith("http")


def make_deal(
    title: str,
    url: str,
    source: str,
    current: float,
    original: float | None,
    found_at: str,
    sizes: list[str] | None = None,
    stock_status: str | None = None,
    image_url: str | None = None,
    is_cached: bool = False,
) -> Deal:
    discount = None
    savings = None
    if original and original > current:
        savings = round(original - current, 2)
        discount = round((savings / original) * 100, 1)

    score = current_score(current, discount, savings)
    return Deal(
        title=title[:180],
        url=url,
        source=source,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        savings=savings,
        score=score,
        found_at=found_at,
        sizes=sizes,
        stock_status=stock_status,
        image_url=image_url,
        is_cached=is_cached,
    )


def current_score(current: float, discount: float | None, savings: float | None) -> float:
    discount_score = discount or 0
    savings_score = min((savings or 0) / 4, 35)
    price_score = max(0, 20 - min(current / 50, 20))
    return round(discount_score + savings_score + price_score, 2)


SIZE_SUFFIX_RE = re.compile(r"(?i)^(?:(?:[^/]+?)\s*/\s*)?(?:\d{3}|\d{2,3}\.\d)(?:\s*cm)?$")


def split_size_variant(title: str) -> tuple[str, str | None]:
    if " - " not in title:
        return title, None
    base, suffix = title.rsplit(" - ", 1)
    suffix = clean_text(suffix)
    if not SIZE_SUFFIX_RE.match(suffix):
        return title, None
    return clean_text(base), suffix


def consolidate_size_variants(deals: list[Deal]) -> list[Deal]:
    grouped: dict[tuple[str, str, str], list[tuple[Deal, str]]] = {}
    passthrough: list[Deal] = []

    for deal in deals:
        base_title, size = split_size_variant(deal.title)
        if not size:
            passthrough.append(deal)
            continue
        grouped.setdefault((deal.source, deal.url, base_title), []).append((deal, size))

    consolidated = list(passthrough)
    for (source, url, base_title), variants in grouped.items():
        if len(variants) == 1:
            consolidated.append(variants[0][0])
            continue

        best_current = min(deal.current_price for deal, _ in variants)
        originals = [deal.original_price for deal, _ in variants if deal.original_price is not None]
        best_original = max(originals) if originals else None
        latest_found_at = max(deal.found_at for deal, _ in variants)
        sizes = sorted({size for _, size in variants})
        image = next((deal.image_url for deal, _ in variants if deal.image_url), None)
        stock_status = next((deal.stock_status for deal, _ in variants if deal.stock_status), None)
        consolidated.append(
            make_deal(
                base_title,
                url,
                source,
                best_current,
                best_original,
                latest_found_at,
                sizes=sizes,
                stock_status=stock_status,
                image_url=image,
            )
        )

    return consolidated


def dedupe(deals: list[Deal]) -> list[Deal]:
    best: dict[str, Deal] = {}
    for deal in deals:
        key = re.sub(r"[^a-z0-9]+", "", f"{deal.title.lower()}-{deal.current_price}")
        existing = best.get(key)
        if not existing or deal.score > existing.score:
            best[key] = deal
    return list(best.values())


def filter_and_sort(deals: list[Deal], config: dict[str, Any]) -> list[Deal]:
    keywords = config.get("keywords", [])
    excludes = config.get("exclude_keywords", [])
    min_discount = float(config.get("min_discount_percent", 0) or 0)

    filtered = []
    for deal in consolidate_size_variants(dedupe(deals)):
        if not keyword_allowed(deal.title, keywords, excludes):
            continue
        if deal.discount_percent is not None and deal.discount_percent < min_discount:
            continue
        filtered.append(deal)

    if config.get("sort_results_by") == "price_asc":
        return sorted(
            filtered,
            key=lambda item: (
                stock_sort_key(item.stock_status),
                item.current_price,
                -(item.discount_percent or 0),
                -(item.savings or 0),
            ),
        )

    return sorted(
        filtered,
        key=lambda item: (
            stock_sort_key(item.stock_status),
            -(item.score),
            -(item.discount_percent or 0),
            -(item.savings or 0),
        ),
    )


def scan(config: dict[str, Any]) -> tuple[list[Deal], list[SourceError]]:
    found_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    all_deals: list[Deal] = []
    errors: list[SourceError] = []
    history = load_price_history(resolve_output_path(config.get("price_history_output"), PRICE_HISTORY_OUTPUT))
    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue

        source_name = source.get("name") or source.get("url")
        url = source.get("url")
        if not url:
            continue

        markup = ""
        source_filter_config = merged_filter_config(config, source)
        per_source_limit = int(source_filter_config.get("max_results_per_source", 30) or 30)

        try:
            if source.get("searchspring_json"):
                candidates = searchspring_candidates(
                    fetch(source["searchspring_json"], timeout=30),
                    url,
                    source_name,
                    found_at,
                )
                all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                time.sleep(float(source.get("delay_seconds", 1.2)))
                continue

            if source.get("prefer_reader_fallback") and source.get("reader_fallback"):
                markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                blocked = block_reason(markup)
                if blocked:
                    all_deals.extend(cached_source_deals(history, source_name, found_at, per_source_limit))
                    errors.append(SourceError(source_name, url, blocked))
                    continue
            else:
                markup = fetch(url)
                blocked = block_reason(markup)
            if blocked:
                candidates = []
                if source.get("shopify_products_json"):
                    candidates.extend(
                        shopify_products_json_candidates(
                            fetch(source["shopify_products_json"], timeout=30),
                            url,
                            source_name,
                            found_at,
                            bool(source.get("ignore_sold_out", True)),
                            list(source.get("shopify_required_tags", [])),
                            list(source.get("shopify_required_variant_terms", [])),
                            source.get("size_min_cm"),
                            source.get("size_max_cm"),
                        )
                    )
                if candidates:
                    all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                    time.sleep(float(source.get("delay_seconds", 1.2)))
                    continue
                evo_deals = evo_api_fallback_candidates(url, source, source_name, found_at, per_source_limit)
                if evo_deals:
                    all_deals.extend(filter_and_sort(evo_deals, source_filter_config)[:per_source_limit])
                    time.sleep(float(source.get("delay_seconds", 1.2)))
                    continue
                if not source.get("reader_fallback"):
                    all_deals.extend(cached_source_deals(history, source_name, found_at, per_source_limit))
                    errors.append(SourceError(source_name, url, blocked))
                    continue
                markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                blocked = block_reason(markup)
                if blocked:
                    all_deals.extend(cached_source_deals(history, source_name, found_at, per_source_limit))
                    errors.append(SourceError(source_name, url, blocked))
                    continue
            candidates = json_ld_candidates(markup, url, source_name, found_at)
            candidates.extend(remix_candidates(markup, url, source_name, found_at))
            evo_hydrated_candidates: list[Deal] = []
            if "evo.com" in url:
                evo_hydrated_candidates = evo_hydrated_collection_candidates(
                    markup,
                    url,
                    source_name,
                    found_at,
                    per_source_limit,
                )
            if evo_hydrated_candidates:
                candidates.extend(evo_hydrated_candidates)
            else:
                candidates.extend(evo_collection_candidates(markup, url, source_name, found_at))
            if source.get("shopify_products_json"):
                candidates.extend(
                    shopify_products_json_candidates(
                        fetch(source["shopify_products_json"], timeout=30),
                        url,
                        source_name,
                        found_at,
                        bool(source.get("ignore_sold_out", True)),
                        list(source.get("shopify_required_tags", [])),
                        list(source.get("shopify_required_variant_terms", [])),
                        source.get("size_min_cm"),
                        source.get("size_max_cm"),
                    )
                )
            campsaver_candidates = campsaver_grid_candidates(markup, url, source_name, found_at)
            if campsaver_candidates:
                candidates.extend(campsaver_candidates)
            else:
                candidates.extend(link_candidates(markup, url, source_name, found_at))
                candidates.extend(markdown_candidates(markup, url, source_name, found_at))
            candidates.extend(geartrade_search_candidates(markup, url, source_name, found_at))
            if not candidates and source.get("reader_fallback"):
                markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                candidates = campsaver_grid_candidates(markup, url, source_name, found_at)
                if not candidates:
                    candidates = markdown_candidates(markup, url, source_name, found_at)
                    candidates.extend(link_candidates(markup, url, source_name, found_at))
                candidates.extend(geartrade_search_candidates(markup, url, source_name, found_at))
            all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
            time.sleep(float(source.get("delay_seconds", 1.2)))
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            try:
                evo_deals = evo_api_fallback_candidates(url, source, source_name, found_at, per_source_limit)
            except (HTTPError, URLError, TimeoutError, OSError):
                evo_deals = []
            if evo_deals:
                all_deals.extend(filter_and_sort(evo_deals, source_filter_config)[:per_source_limit])
                time.sleep(float(source.get("delay_seconds", 1.2)))
                continue
            if source.get("reader_fallback"):
                try:
                    candidates = []
                    if source.get("shopify_products_json"):
                        candidates.extend(
                            shopify_products_json_candidates(
                                fetch(source["shopify_products_json"], timeout=30),
                                url,
                                source_name,
                                found_at,
                                bool(source.get("ignore_sold_out", True)),
                                list(source.get("shopify_required_tags", [])),
                                list(source.get("shopify_required_variant_terms", [])),
                                source.get("size_min_cm"),
                                source.get("size_max_cm"),
                            )
                        )
                    if candidates:
                        all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                        time.sleep(float(source.get("delay_seconds", 1.2)))
                        continue
                    markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                    blocked = block_reason(markup)
                    if blocked:
                        all_deals.extend(cached_source_deals(history, source_name, found_at, per_source_limit))
                        errors.append(SourceError(source_name, url, blocked))
                        continue
                    candidates = campsaver_grid_candidates(markup, url, source_name, found_at)
                    if not candidates:
                        candidates = markdown_candidates(markup, url, source_name, found_at)
                        candidates.extend(link_candidates(markup, url, source_name, found_at))
                    candidates.extend(geartrade_search_candidates(markup, url, source_name, found_at))
                    all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                    time.sleep(float(source.get("delay_seconds", 1.2)))
                    continue
                except (HTTPError, URLError, TimeoutError, OSError) as fallback_error:
                    all_deals.extend(cached_source_deals(history, source_name, found_at, per_source_limit))
                    errors.append(SourceError(source_name, url, f"{error}; reader fallback failed: {fallback_error}"))
                    continue
            all_deals.extend(cached_source_deals(history, source_name, found_at, per_source_limit))
            errors.append(SourceError(source_name, url, str(error)))

    return rank_deals(dedupe(all_deals)), errors


def cached_source_deals(history: dict[str, Any], source_name: str, found_at: str, limit: int) -> list[Deal]:
    items = history.get("items", {})
    if not isinstance(items, dict):
        return []

    cached: list[Deal] = []
    for item in items.values():
        if not isinstance(item, dict) or item.get("source") != source_name:
            continue
        title = clean_text(str(item.get("title") or ""))
        url = clean_text(str(item.get("url") or ""))
        current = money(item.get("current_price"))
        if not title or not url or current is None:
            continue
        cached.append(
            make_deal(
                title,
                url,
                source_name,
                current,
                money(item.get("highest_price")),
                found_at,
                image_url=image_url(item.get("image_url")),
                is_cached=True,
            )
        )

    return rank_deals(cached)[:limit]


def merged_filter_config(config: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config)
    for key in ("keywords", "exclude_keywords", "min_discount_percent", "max_results_per_source"):
        if key in source:
            if key == "exclude_keywords":
                merged[key] = list(config.get(key, [])) + list(source.get(key, []))
            else:
                merged[key] = source[key]
    return merged


def rank_deals(deals: list[Deal]) -> list[Deal]:
    return sorted(
        deals,
        key=lambda item: (
            stock_sort_key(item.stock_status),
            -(item.score),
            -(item.discount_percent or 0),
            -(item.savings or 0),
        ),
    )


def stock_sort_key(status: str | None) -> int:
    if status == "sold_out":
        return 2
    if status == "availability_unknown":
        return 1
    return 0


def stock_label(status: str | None) -> str | None:
    if status == "in_stock":
        return "In stock"
    if status == "sold_out":
        return "Sold out"
    if status == "availability_unknown":
        return "Availability unknown"
    return None


def price_history_key(deal: Deal | dict[str, Any]) -> str:
    source = str(deal["source"] if isinstance(deal, dict) else deal.source)
    title = str(deal["title"] if isinstance(deal, dict) else deal.title)
    url = str(deal["url"] if isinstance(deal, dict) else deal.url)
    parsed = urlparse(url)
    normalized_url = urlunparse(parsed._replace(query="", fragment="")).rstrip("/")
    if normalized_url:
        return f"{source}|{normalized_url}".lower()
    normalized_title = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{source}|{normalized_title}".lower()


def load_price_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"items": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
        return {"items": {}}
    sanitize_price_history(payload)
    return payload


def sanitize_price_history(history: dict[str, Any]) -> None:
    items = history.get("items")
    if not isinstance(items, dict):
        return

    for item in items.values():
        if not isinstance(item, dict) or item.get("source") != "CampSaver backcountry skis":
            continue
        if not campsaver_has_suspicious_cached_price(item):
            continue

        observations = item.get("observations")
        if not isinstance(observations, list):
            continue
        sane_observations = [
            observation
            for observation in observations
            if isinstance(observation, dict) and (money(observation.get("price")) or 0) >= 100
        ]
        if not sane_observations:
            continue

        item["observations"] = sane_observations
        latest = max(sane_observations, key=lambda observation: str(observation.get("date", "")))
        prices = [price for price in [money(observation.get("price")) for observation in sane_observations] if price is not None]
        latest_price = money(latest.get("price"))
        if latest_price is not None:
            item["current_price"] = latest_price
        if prices:
            item["lowest_price"] = min(prices)
            item["highest_price"] = max(prices)


def campsaver_has_suspicious_cached_price(item: dict[str, Any]) -> bool:
    current = money(item.get("current_price"))
    highest = money(item.get("highest_price"))
    title = str(item.get("title") or "").lower()
    if current is None:
        return False
    return current < 100 and (highest or 0) > 300 and ("as low as" in title or "black diamond impulse" in title)


def latest_prior_observation(item: dict[str, Any], today: str) -> dict[str, Any] | None:
    observations = item.get("observations")
    if not isinstance(observations, list):
        return None
    prior = [
        observation
        for observation in observations
        if isinstance(observation, dict) and str(observation.get("date", "")) < today
    ]
    return max(prior, key=lambda observation: str(observation.get("date", ""))) if prior else None


def annotate_and_update_price_history(deals: list[Deal], history_path: Path, generated_at: str) -> dict[str, Any]:
    history = load_price_history(history_path)
    items = history.setdefault("items", {})
    today = generated_at[:10]

    for deal in deals:
        key = price_history_key(deal)
        existing = items.get(key) if isinstance(items.get(key), dict) else {}
        if not deal.image_url and existing.get("image_url"):
            deal.image_url = str(existing["image_url"])
        previous = latest_prior_observation(existing, today)
        if previous:
            previous_price = money(previous.get("price"))
            if previous_price is not None:
                deal.previous_price = previous_price
                deal.price_change = round(deal.current_price - previous_price, 2)
                if previous_price:
                    deal.price_change_percent = round((deal.price_change / previous_price) * 100, 1)
                if deal.price_change < 0:
                    deal.price_trend = "down"
                elif deal.price_change > 0:
                    deal.price_trend = "up"
                else:
                    deal.price_trend = "flat"
        else:
            deal.price_trend = "new"

        observations = existing.get("observations")
        if not isinstance(observations, list):
            observations = []
        observations = [
            observation
            for observation in observations
            if isinstance(observation, dict) and str(observation.get("date", "")) != today
        ]
        observations.append({"date": today, "price": deal.current_price, "seen_at": generated_at})
        observations = sorted(observations, key=lambda observation: str(observation.get("date", "")))[-90:]

        first_seen_at = str(existing.get("first_seen_at") or generated_at)
        deal.first_seen_at = first_seen_at
        lowest = min([deal.current_price] + [price for price in [money(obs.get("price")) for obs in observations] if price is not None])
        highest = max([deal.current_price] + [price for price in [money(obs.get("price")) for obs in observations] if price is not None])
        deal.lowest_price = round(lowest, 2)
        deal.highest_price = round(highest, 2)
        items[key] = {
            "title": deal.title,
            "url": deal.url,
            "source": deal.source,
            "image_url": deal.image_url,
            "first_seen_at": first_seen_at,
            "last_seen_at": generated_at,
            "current_price": deal.current_price,
            "lowest_price": round(lowest, 2),
            "highest_price": round(highest, 2),
            "observations": observations,
        }

    history["generated_at"] = generated_at
    history["tracked_count"] = len(items)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return history


def price_trend_label(deal: dict[str, Any]) -> str | None:
    trend = deal.get("price_trend")
    change = deal.get("price_change")
    percent = deal.get("price_change_percent")
    previous = deal.get("previous_price")
    percent_label = f" ({abs(percent):.1f}%)" if isinstance(percent, (int, float)) else ""
    if trend == "down" and change is not None:
        return f"Down ${abs(change):.2f}{percent_label} since prior day"
    if trend == "up" and change is not None:
        return f"Up ${abs(change):.2f}{percent_label} since prior day"
    if trend == "flat" and previous is not None:
        return "Same as prior day"
    if trend == "new":
        return "Newly tracked"
    return None


def write_outputs(deals: list[Deal], errors: list[SourceError], config: dict[str, Any]) -> None:
    json_output = resolve_output_path(config.get("json_output"), JSON_OUTPUT)
    markdown_output = resolve_output_path(config.get("markdown_output"), MD_OUTPUT)
    html_output_path = resolve_output_path(config.get("html_output"), HTML_OUTPUT)
    web_output = resolve_output_path(config.get("web_output"), WEB_OUTPUT)
    history_output = resolve_output_path(config.get("price_history_output"), PRICE_HISTORY_OUTPUT)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    html_output_path.parent.mkdir(parents=True, exist_ok=True)
    web_output.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    history = annotate_and_update_price_history(deals, history_output, generated_at)
    changed_deals = [
        deal
        for deal in deals
        if deal.price_trend in {"up", "down"} and deal.price_change is not None
    ]
    payload = {
        "generated_at": generated_at,
        "deal_count": len(deals),
        "sources_checked": len([source for source in config.get("sources", []) if source.get("enabled", True)]),
        "price_history_count": int(history.get("tracked_count") or 0),
        "price_change_count": len(changed_deals),
        "deals": [asdict(deal) for deal in deals],
        "errors": [asdict(error) for error in errors],
    }

    json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_output.write_text(render_markdown(payload, config), encoding="utf-8")
    html_payload, html_config = combined_tracker_payload(payload, config)
    html_output = trim_trailing_whitespace(render_html(html_payload, html_config))
    html_output_path.write_text(html_output, encoding="utf-8")
    web_output.write_text(html_output, encoding="utf-8")


def resolve_output_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def trim_trailing_whitespace(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()) + "\n"


def combined_tracker_payload(payload: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if resolve_output_path(config.get("json_output"), JSON_OUTPUT) != JSON_OUTPUT:
        return payload, config

    clothing_payload = load_json_payload(resolve_output_path(config.get("combined_clothing_json"), CLOTHING_JSON_OUTPUT))
    if not clothing_payload:
        tagged = dict(payload)
        tagged["deals"] = [tag_deal_for_category(deal, "ski") for deal in payload.get("deals", [])]
        tagged["category_counts"] = {"ski": len(tagged["deals"]), "clothing": 0}
        return tagged, config

    ski_deals = [tag_deal_for_category(deal, "ski") for deal in payload.get("deals", [])]
    clothing_deals = [tag_deal_for_category(deal, "clothing") for deal in clothing_payload.get("deals", [])]
    combined = dict(payload)
    combined["deals"] = ski_deals + clothing_deals
    combined["deal_count"] = len(combined["deals"])
    combined["category_counts"] = {"ski": len(ski_deals), "clothing": len(clothing_deals)}
    combined["errors"] = list(payload.get("errors", [])) + [
        dict(error, source=f"Clothing: {error.get('source', 'unknown')}")
        for error in clothing_payload.get("errors", [])
        if isinstance(error, dict)
    ]
    current_keys = {price_history_key(deal) for deal in combined["deals"]}
    error_sources = {str(error.get("source", "")) for error in combined["errors"] if isinstance(error, dict)}
    history = load_price_history(resolve_output_path(config.get("price_history_output"), PRICE_HISTORY_OUTPUT))
    combined["disappeared_deals"] = recent_disappeared_deals(history, current_keys, error_sources, limit=10)
    preferences = load_preferences(resolve_output_path(config.get("preferences"), PREFERENCES_CONFIG))
    annotate_preferences(combined["deals"], preferences)
    combined["preferences"] = preference_summary(preferences, combined["deals"])

    html_config = dict(config)
    html_config["report_title"] = "Gear Deals"
    return combined, html_config


def load_json_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def tag_deal_for_category(deal: dict[str, Any], category: str) -> dict[str, Any]:
    tagged = dict(deal)
    tagged["category"] = category
    tagged.setdefault("stock_status", None)
    tagged.setdefault("image_url", None)
    tagged.setdefault("is_cached", False)
    tagged.setdefault("previous_price", None)
    tagged.setdefault("price_change", None)
    tagged.setdefault("price_change_percent", None)
    tagged.setdefault("price_trend", None)
    tagged.setdefault("first_seen_at", None)
    tagged.setdefault("lowest_price", None)
    tagged.setdefault("highest_price", None)
    return tagged


def recent_disappeared_deals(
    history: dict[str, Any],
    current_keys: set[str],
    error_sources: set[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    items = history.get("items", {})
    if not isinstance(items, dict):
        return []

    disappeared = []
    for key, item in items.items():
        if key in current_keys or not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        if source in error_sources:
            continue
        title = clean_text(str(item.get("title") or ""))
        url = clean_text(str(item.get("url") or ""))
        current = money(item.get("current_price"))
        last_seen_at = str(item.get("last_seen_at") or "")
        if not title or not url or current is None or not last_seen_at:
            continue
        disappeared.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "current_price": current,
                "last_seen_at": last_seen_at,
            }
        )

    return sorted(disappeared, key=lambda item: item["last_seen_at"], reverse=True)[:limit]


def buy_zone(deal: dict[str, Any]) -> tuple[str, str]:
    price = money(deal.get("current_price")) or 0
    discount = float(deal.get("discount_percent") or 0)
    trend = str(deal.get("price_trend") or "")
    category = str(deal.get("category") or "ski")
    lowest = money(deal.get("lowest_price"))

    if trend == "down" and lowest is not None and price <= lowest:
        return "New low", "zone-new-low"
    if discount >= 70 or (category == "ski" and price <= 250 and discount >= 45):
        return "Buy zone", "zone-buy"
    if discount >= 55 or (category == "clothing" and price <= 50 and discount >= 45):
        return "Strong deal", "zone-strong"
    if trend == "up":
        return "Going up", "zone-watch"
    return "Fair deal", "zone-fair"


def is_lowest_seen(deal: dict[str, Any]) -> bool:
    price = money(deal.get("current_price"))
    lowest = money(deal.get("lowest_price"))
    highest = money(deal.get("highest_price"))
    return price is not None and lowest is not None and highest is not None and highest > lowest and price <= lowest


def is_sweet_spot(deal: dict[str, Any]) -> bool:
    price = money(deal.get("current_price")) or 0
    discount = float(deal.get("discount_percent") or 0)
    category = str(deal.get("category") or "ski")
    stock_status = str(deal.get("stock_status") or "in_stock")
    size_match = bool(deal.get("matches_my_size") or deal.get("matches_family_size") or category == "clothing")
    max_price = 500 if category == "ski" else 100
    return bool(
        size_match
        and price <= max_price
        and discount >= 40
        and stock_status != "sold_out"
        and not deal.get("is_muted")
    )


def deal_verdict(deal: dict[str, Any]) -> tuple[str, str]:
    price = money(deal.get("current_price")) or 0
    discount = float(deal.get("discount_percent") or 0)
    trend = str(deal.get("price_trend") or "")
    category = str(deal.get("category") or "ski")

    if deal.get("is_muted"):
        return "Muted", "verdict-muted"
    if is_sweet_spot(deal) and (is_lowest_seen(deal) or trend == "down" or discount >= 55):
        return "Buy now", "verdict-buy"
    if deal.get("matches_my_size") or deal.get("matches_family_size"):
        if category == "ski" and price <= 500 and discount >= 35:
            return "Only if size is right", "verdict-size"
        if category == "clothing" and price <= 100 and discount >= 25:
            return "Only if size is right", "verdict-size"
    if trend == "up":
        return "Wait", "verdict-wait"
    if discount < 30:
        return "Wait", "verdict-wait"
    return "Worth a look", "verdict-look"


def duplicate_key(deal: dict[str, Any]) -> str:
    title = str(deal.get("title") or "").lower()
    title = re.sub(r"\b(?:19|20)\d{2}\b", " ", title)
    title = re.sub(r"\b\d{2,3}(?:\.\d)?\s*cm\b", " ", title)
    title = re.sub(r"\b\d{2,3}(?:\.\d)?\b", " ", title)
    title = re.sub(r"\b(?:new|used|demo|open|skis?|womens?|mens?|unisex|flat|with|bindings?|cm)\b", " ", title)
    title = re.sub(r"[^a-z0-9]+", " ", title)
    words = [word for word in title.split() if len(word) > 1]
    return " ".join(words[:6])


def short_seen_label(value: str) -> str:
    if not value:
        return "last run"
    try:
        seen = datetime.fromisoformat(value)
    except ValueError:
        return value[:10]
    return seen.strftime("%b %-d")


def source_health_card(source: str, deals: list[dict[str, Any]], count: int, error: str | None) -> str:
    source_deals = [deal for deal in deals if str(deal.get("source")) == source]
    cached = sum(1 for deal in source_deals if deal.get("is_cached"))
    photos = sum(1 for deal in source_deals if deal.get("image_url"))
    drops = sum(1 for deal in source_deals if deal.get("price_trend") == "down")
    if error:
        status = "Issue"
        status_class = "health-issue"
        detail = error
    elif cached:
        status = "Cached"
        status_class = "health-cached"
        detail = f"{cached} cached listing{'s' if cached != 1 else ''}"
    elif count:
        status = "Live"
        status_class = "health-live"
        detail = f"{count} deals - {photos} photos - {drops} drops"
    else:
        status = "Quiet"
        status_class = "health-quiet"
        detail = "No matching deals this run"

    return f"""
    <div class="health-card {status_class}">
      <strong>{html.escape(source)}</strong>
      <span>{html.escape(status)}</span>
      <p>{html.escape(detail)}</p>
    </div>
    """


def load_preferences(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def preference_terms(preferences: dict[str, Any], key: str) -> list[str]:
    values = preferences.get(key)
    if not isinstance(values, list):
        return []
    return [str(value).strip().lower() for value in values if str(value).strip()]


def preference_numbers(preferences: dict[str, Any], key: str) -> list[int]:
    values = preferences.get(key)
    if not isinstance(values, list):
        return []
    numbers = []
    for value in values:
        try:
            numbers.append(int(value))
        except (TypeError, ValueError):
            continue
    return numbers


def annotate_preferences(deals: list[dict[str, Any]], preferences: dict[str, Any]) -> None:
    watch_terms = preference_terms(preferences, "watch_terms")
    muted_terms = preference_terms(preferences, "muted_terms")
    muted_urls = set(preference_terms(preferences, "muted_urls"))
    my_ski_sizes = preference_numbers(preferences, "my_ski_sizes")
    family_ski_sizes = preference_numbers(preferences, "family_ski_sizes")
    if not my_ski_sizes and not family_ski_sizes:
        my_ski_sizes = preference_numbers(preferences, "ski_sizes")
    clothing_sizes = set(preference_terms(preferences, "clothing_sizes"))
    max_prices = preferences.get("max_prices") if isinstance(preferences.get("max_prices"), dict) else {}

    for deal in deals:
        haystack = " ".join(
            [
                str(deal.get("title") or ""),
                str(deal.get("source") or ""),
                str(deal.get("url") or ""),
            ]
        ).lower()
        category = str(deal.get("category") or "ski")
        sizes = [str(size).lower() for size in deal.get("sizes") or []]
        current_price = money(deal.get("current_price")) or 0
        max_price = money(max_prices.get(category)) if isinstance(max_prices, dict) else None

        deal["is_watchlist"] = any(term in haystack for term in watch_terms)
        deal["is_muted"] = any(term in haystack for term in muted_terms) or str(deal.get("url") or "").lower() in muted_urls
        deal["matches_my_size"] = matches_preferred_size(category, sizes, my_ski_sizes, clothing_sizes)
        deal["matches_family_size"] = category != "clothing" and matches_preferred_size(category, sizes, family_ski_sizes, set())
        deal["matches_size"] = bool(deal["matches_my_size"] or deal["matches_family_size"])
        deal["matches_price"] = max_price is None or current_price <= max_price
        deal["matches_preferences"] = bool(deal["is_watchlist"] or (deal["matches_size"] and deal["matches_price"]))


def matches_preferred_size(category: str, sizes: list[str], ski_sizes: list[int], clothing_sizes: set[str]) -> bool:
    if not sizes:
        return False
    if category == "clothing":
        return any(size in clothing_sizes for size in sizes)
    if not ski_sizes:
        return False
    for size in sizes:
        for number in re.findall(r"\d{2,3}", size):
            try:
                if int(number) in ski_sizes:
                    return True
            except ValueError:
                continue
    return False


def preference_summary(preferences: dict[str, Any], deals: list[dict[str, Any]]) -> dict[str, Any]:
    watch_terms = preference_terms(preferences, "watch_terms")
    muted_terms = preference_terms(preferences, "muted_terms")
    my_ski_sizes = preference_numbers(preferences, "my_ski_sizes")
    family_ski_sizes = preference_numbers(preferences, "family_ski_sizes")
    if not my_ski_sizes and not family_ski_sizes:
        my_ski_sizes = preference_numbers(preferences, "ski_sizes")
    clothing_sizes = preference_terms(preferences, "clothing_sizes")
    return {
        "watch_terms": watch_terms,
        "muted_terms": muted_terms,
        "my_ski_sizes": my_ski_sizes,
        "family_ski_sizes": family_ski_sizes,
        "ski_sizes": sorted(set(my_ski_sizes + family_ski_sizes)),
        "clothing_sizes": clothing_sizes,
        "watchlist_count": sum(1 for deal in deals if deal.get("is_watchlist")),
        "muted_count": sum(1 for deal in deals if deal.get("is_muted")),
        "my_size_match_count": sum(1 for deal in deals if deal.get("matches_my_size")),
        "family_size_match_count": sum(1 for deal in deals if deal.get("matches_family_size")),
        "size_match_count": sum(1 for deal in deals if deal.get("matches_size")),
        "preference_match_count": sum(1 for deal in deals if deal.get("matches_preferences")),
    }


def report_title(config: dict[str, Any]) -> str:
    return str(config.get("report_title") or "Ski Gear Deals")


def empty_message(config: dict[str, Any]) -> str:
    fallback = "No matching deals found. Add or enable more sources in the config."
    return str(config.get("empty_message") or fallback)


def render_markdown(payload: dict[str, Any], config: dict[str, Any]) -> str:
    lines = [
        f"# {report_title(config)}",
        "",
        f"Generated: {payload['generated_at']}",
        f"Deals found: {payload['deal_count']}",
        "",
    ]

    if not payload["deals"]:
        lines.append(empty_message(config))
    else:
        for index, deal in enumerate(payload["deals"][:25], start=1):
            discount = f" ({deal['discount_percent']}% off)" if deal["discount_percent"] else ""
            original = f" was ${deal['original_price']:.2f}" if deal["original_price"] else ""
            trend = price_trend_label(deal)
            status = stock_label(deal.get("stock_status"))
            lines.extend(
                [
                    f"{index}. [{deal['title']}]({deal['url']})",
                    f"   ${deal['current_price']:.2f}{original}{discount} - {deal['source']}",
                    f"   Price trend: {trend}" if trend else "",
                    f"   Sizes: {', '.join(deal['sizes'])}" if deal.get("sizes") else "",
                    f"   Stock: {status}" if status else "",
                    "",
                ]
            )

    if payload["errors"]:
        lines.extend(["", "## Source Errors", ""])
        for error in payload["errors"]:
            lines.append(f"- {error['source']}: {error['error']}")

    return "\n".join(lines).strip() + "\n"


def render_html(payload: dict[str, Any], config: dict[str, Any]) -> str:
    cards = []
    show_category_filter = "category_counts" in payload or any("category" in deal for deal in payload.get("deals", []))
    html_deals = sorted(
        payload["deals"],
        key=lambda deal: (
            stock_sort_key(deal.get("stock_status")),
            deal["current_price"],
            1 if deal.get("is_muted") else 0,
            0 if deal.get("is_watchlist") else 1,
            -(deal["discount_percent"] or 0),
        ),
    )
    source_counts: dict[str, int] = {}
    for deal in html_deals:
        source_counts[str(deal["source"])] = source_counts.get(str(deal["source"]), 0) + 1
    category_counts = payload.get("category_counts") or {
        "ski": sum(1 for deal in html_deals if deal.get("category", "ski") == "ski"),
        "clothing": sum(1 for deal in html_deals if deal.get("category") == "clothing"),
    }
    image_count = sum(1 for deal in html_deals if deal.get("image_url"))
    price_drop_count = sum(1 for deal in html_deals if deal.get("price_trend") == "down")
    newly_tracked_deals = sorted(
        [deal for deal in html_deals if deal.get("price_trend") == "new"],
        key=lambda deal: (deal["current_price"], -(deal.get("discount_percent") or 0)),
    )[:8]
    disappeared_deals = payload.get("disappeared_deals") if isinstance(payload.get("disappeared_deals"), list) else []
    preferences = payload.get("preferences") if isinstance(payload.get("preferences"), dict) else {}
    best_discount = max((deal.get("discount_percent") or 0 for deal in html_deals), default=0)
    lowest_price = min((deal["current_price"] for deal in html_deals), default=0)
    duplicate_groups: dict[str, list[dict[str, Any]]] = {}
    for deal in html_deals:
        key = duplicate_key(deal)
        if len(key) >= 6:
            duplicate_groups.setdefault(key, []).append(deal)
    duplicate_winners: set[int] = set()
    duplicate_counts: dict[int, int] = {}
    for group in duplicate_groups.values():
        if len(group) < 2:
            continue
        ranked = sorted(group, key=lambda item: (item["current_price"], -(item.get("score") or 0)))
        duplicate_winners.add(id(ranked[0]))
        for item in group:
            duplicate_counts[id(item)] = len(group)
    for_you_deals = sorted(
        [
            deal
            for deal in html_deals
            if not deal.get("is_muted")
            and (
                deal.get("is_watchlist")
                or deal.get("matches_my_size")
                or (deal.get("matches_family_size") and (deal.get("current_price") or 0) <= 500)
            )
        ],
        key=lambda deal: (-(deal.get("score") or 0), deal["current_price"]),
    )[:8]
    best_my_deal = next((deal for deal in for_you_deals if deal.get("matches_my_size")), None)
    best_family_deal = next((deal for deal in for_you_deals if deal.get("matches_family_size")), None)
    biggest_drop_deal = next(
        iter(
            sorted(
                [deal for deal in html_deals if deal.get("price_trend") == "down" and not deal.get("is_muted")],
                key=lambda deal: (-(abs(float(deal.get("price_change") or 0))), deal["current_price"]),
            )
        ),
        None,
    )
    sweet_spot_count = sum(1 for deal in html_deals if is_sweet_spot(deal))
    lowest_seen_count = sum(1 for deal in html_deals if is_lowest_seen(deal))
    category_panel = (
        f"""
        <div class="category-panel" aria-label="Category filters">
          <label class="category-toggle category-ski">
            <input type="checkbox" value="ski" checked />
            <span>Ski deals</span>
            <b>{category_counts["ski"]}</b>
          </label>
          <label class="category-toggle category-clothing">
            <input type="checkbox" value="clothing" checked />
            <span>Clothing deals</span>
            <b>{category_counts["clothing"]}</b>
          </label>
        </div>
        """
        if show_category_filter
        else ""
    )

    for deal in html_deals:
        original = f"<span class='was'>Was ${deal['original_price']:.2f}</span>" if deal["original_price"] else ""
        discount = f"<span>{deal['discount_percent']}% off</span>" if deal["discount_percent"] else "<span>Price found</span>"
        savings = f"<span>Save ${deal['savings']:.2f}</span>" if deal["savings"] else ""
        trend_label = price_trend_label(deal)
        trend_class = f" trend-{html.escape(str(deal.get('price_trend') or 'unknown'))}"
        trend_badge = f"<span class='trend{trend_class}'>{html.escape(trend_label)}</span>" if trend_label else ""
        zone_label, zone_class = buy_zone(deal)
        zone_badge = f"<span class='buy-zone {html.escape(zone_class)}'>{html.escape(zone_label)}</span>"
        verdict_label, verdict_class = deal_verdict(deal)
        verdict_badge = f"<span class='verdict {html.escape(verdict_class)}'>{html.escape(verdict_label)}</span>"
        sweet_spot = is_sweet_spot(deal)
        sweet_badge = "<span class='sweet-badge'>Sweet spot</span>" if sweet_spot else ""
        lowest_seen = is_lowest_seen(deal)
        lowest_badge = "<span class='floor-badge'>Lowest seen</span>" if lowest_seen else ""
        duplicate_count = duplicate_counts.get(id(deal), 1)
        duplicate_badge = (
            f"<span class='dupe-badge'>{duplicate_count - 1} alternate{'s' if duplicate_count != 2 else ''}</span>"
            if duplicate_count > 1
            else ""
        )
        dupe_primary = duplicate_count <= 1 or id(deal) in duplicate_winners
        category = str(deal.get("category") or "ski")
        category_label = "Clothing" if category == "clothing" else "Ski"
        category_badge = (
            f"<span class='category category-{html.escape(category)}'>{html.escape(category_label)}</span>"
            if show_category_filter
            else ""
        )
        sizes = f"<span>Sizes {html.escape(', '.join(deal['sizes']))}</span>" if deal.get("sizes") else ""
        status = stock_label(deal.get("stock_status"))
        stock_badge = f"<span class='stock stock-{html.escape(deal['stock_status'])}'>{html.escape(status)}</span>" if status else ""
        cached_badge = "<span class='cached'>Cached last seen price</span>" if deal.get("is_cached") else ""
        watch_badge = "<span class='watch-badge'>Watchlist</span>" if deal.get("is_watchlist") else ""
        muted_badge = "<span class='muted-badge'>Muted</span>" if deal.get("is_muted") else ""
        my_size_badge = "<span class='size-badge'>My size</span>" if deal.get("matches_my_size") else ""
        family_size_badge = "<span class='family-size-badge'>Family size</span>" if deal.get("matches_family_size") else ""
        thumbnail = (
            f"""<a class="thumb" href="{html.escape(deal['url'])}" target="_blank" rel="noreferrer" aria-label="{html.escape(deal['title'])}">
                <img src="{html.escape(deal['image_url'])}" alt="" loading="lazy" decoding="async" />
              </a>"""
            if deal.get("image_url")
            else "<div class='thumb thumb-empty' aria-hidden='true'></div>"
        )
        cards.append(
            f"""
            <article
              class="deal"
              data-url="{html.escape(str(deal['url']))}"
              data-source="{html.escape(deal['source'])}"
              data-title="{html.escape(str(deal['title']).lower())}"
              data-price="{deal['current_price']:.2f}"
              data-discount="{deal['discount_percent'] or 0:.1f}"
              data-savings="{deal['savings'] or 0:.2f}"
              data-score="{deal['score']:.2f}"
              data-trend="{html.escape(str(deal.get('price_trend') or ''))}"
              data-has-image="{'true' if deal.get('image_url') else 'false'}"
              data-category="{html.escape(category)}"
              data-watchlist="{'true' if deal.get('is_watchlist') else 'false'}"
              data-muted="{'true' if deal.get('is_muted') else 'false'}"
              data-server-muted="{'true' if deal.get('is_muted') else 'false'}"
              data-local-muted="false"
              data-size-match="{'true' if deal.get('matches_size') else 'false'}"
              data-my-size-match="{'true' if deal.get('matches_my_size') else 'false'}"
              data-family-size-match="{'true' if deal.get('matches_family_size') else 'false'}"
              data-sweet-spot="{'true' if sweet_spot else 'false'}"
              data-lowest-seen="{'true' if lowest_seen else 'false'}"
              data-verdict="{html.escape(verdict_label.lower())}"
              data-dupe-primary="{'true' if dupe_primary else 'false'}"
            >
              {thumbnail}
              <div class="deal-main">
                <p class="source">{html.escape(deal['source'])}</p>
                <h2><a href="{html.escape(deal['url'])}" target="_blank" rel="noreferrer">{html.escape(deal['title'])}</a></h2>
              </div>
              <div class="price">
                <strong>${deal['current_price']:.2f}</strong>
                {original}
              </div>
              <div class="badges">{watch_badge}{muted_badge}{verdict_badge}{sweet_badge}{lowest_badge}{zone_badge}{category_badge}{discount}{savings}{trend_badge}{cached_badge}{my_size_badge}{family_size_badge}{duplicate_badge}{sizes}{stock_badge}<span>Score {deal['score']:.0f}</span><button class="note-button" type="button" data-ignore-value="{html.escape(str(deal['url']))}">Not interested</button></div>
            </article>
            """
        )

    errors = "".join(
        f"<li>{html.escape(error['source'])}: {html.escape(error['error'])}</li>" for error in payload["errors"]
    )
    empty = f"<p class='empty'>{html.escape(empty_message(config))}</p>"
    title = html.escape(report_title(config))
    source_controls = "".join(
        f"""
        <label class="source-toggle">
          <input type="checkbox" value="{html.escape(source)}" checked />
          <span>{html.escape(source)}</span>
          <b>{count}</b>
        </label>
        """
        for source, count in sorted(source_counts.items())
    )
    new_items = "".join(
        f"""
        <a class="mini-card" href="{html.escape(deal['url'])}" target="_blank" rel="noreferrer">
          <strong>{html.escape(deal['title'])}</strong>
          <span>${deal['current_price']:.2f} &middot; {html.escape(deal['source'])}</span>
        </a>
        """
        for deal in newly_tracked_deals
    )
    for_you_items = "".join(
        f"""
        <a class="mini-card" href="{html.escape(deal['url'])}" target="_blank" rel="noreferrer">
          <strong>{html.escape(deal['title'])}</strong>
          <span>${deal['current_price']:.2f} &middot; {html.escape(deal['source'])} &middot; Score {float(deal.get('score') or 0):.0f}</span>
        </a>
        """
        for deal in for_you_deals
    )
    digest_cards = "".join(
        f"""
        <a class="digest-card" href="{html.escape(deal['url'])}" target="_blank" rel="noreferrer">
          <span>{html.escape(label)}</span>
          <strong>{html.escape(deal['title'])}</strong>
          <em>${deal['current_price']:.2f} &middot; {html.escape(deal['source'])}</em>
        </a>
        """
        for label, deal in (
            ("Best for me", best_my_deal),
            ("Best for family", best_family_deal),
            ("Biggest drop", biggest_drop_deal),
        )
        if isinstance(deal, dict)
    )
    disappeared_items = "".join(
        f"""
        <a class="mini-card ghost-card" href="{html.escape(str(deal['url']))}" target="_blank" rel="noreferrer">
          <strong>{html.escape(str(deal['title']))}</strong>
          <span>Last seen ${float(deal['current_price']):.2f} &middot; {html.escape(short_seen_label(str(deal.get('last_seen_at') or '')))}</span>
        </a>
        """
        for deal in disappeared_deals[:8]
        if isinstance(deal, dict) and money(deal.get("current_price")) is not None
    )
    activity_panel = (
        f"""
        <section class="digest-panel" aria-label="Daily digest">
          <div class="section-head">
            <h2>Today at a glance</h2>
            <span>best quick reads</span>
          </div>
          <div class="digest-grid">{digest_cards if digest_cards else "<p class='empty-mini'>No digest picks yet.</p>"}</div>
        </section>
        <details class="secondary-panel">
          <summary>
            <span>More context</span>
            <b>{len(for_you_deals)} for you &middot; {len(newly_tracked_deals)} new &middot; {len(disappeared_deals[:8])} gone</b>
          </summary>
          <section class="for-you-panel" aria-label="For you">
            <div class="section-head">
              <h2>For you</h2>
              <span>{len(for_you_deals)} watchlist or size hits</span>
            </div>
            <div class="mini-list">{for_you_items if for_you_items else "<p class='empty-mini'>No preference matches yet.</p>"}</div>
          </section>
          <section class="activity-grid" aria-label="Deal activity">
            <div class="activity-card">
              <div class="section-head">
                <h2>New since last run</h2>
                <span>{len(newly_tracked_deals)} shown</span>
              </div>
              <div class="mini-list">{new_items if new_items else "<p class='empty-mini'>Nothing new this run.</p>"}</div>
            </div>
            <div class="activity-card">
              <div class="section-head">
                <h2>Recently disappeared</h2>
                <span>{len(disappeared_deals[:8])} shown</span>
              </div>
              <div class="mini-list">{disappeared_items if disappeared_items else "<p class='empty-mini'>No recent vanishers.</p>"}</div>
            </div>
          </section>
        </details>
        """
        if show_category_filter
        else ""
    )
    error_by_source = {
        str(error.get("source", "")): str(error.get("error", "Source error"))
        for error in payload.get("errors", [])
        if isinstance(error, dict)
    }
    health_sources = sorted(set(source_counts) | set(error_by_source))
    health_cards = "".join(
        source_health_card(source, html_deals, source_counts.get(source, 0), error_by_source.get(source))
        for source in health_sources
    )
    health_panel = (
        f"""
        <details class="health-panel secondary-panel" aria-label="Store health">
          <summary>
            <span>Store health</span>
            <b>{len(health_sources)} sources</b>
          </summary>
          <div class="health-grid">{health_cards}</div>
        </details>
        """
        if health_cards
        else ""
    )
    preference_panel = (
        f"""
        <section class="preference-panel start-panel" aria-label="Deal preferences">
          <div>
            <span class="eyebrow">Start here</span>
            <h2>Pick a lane, then browse.</h2>
            <p>The buttons below change the list instantly. Use the sidebar only when you need to get fussy.</p>
          </div>
          <div class="preference-grid">
            <button type="button" data-radar-filter="dealsOfDay" aria-pressed="false"><strong>5</strong><span>best today</span></button>
            <button type="button" data-radar-filter="mySizeOnly" aria-pressed="false"><strong>{int(preferences.get("my_size_match_count") or 0)}</strong><span>for me</span></button>
            <button type="button" data-radar-filter="familySizeOnly" aria-pressed="false"><strong>{int(preferences.get("family_size_match_count") or 0)}</strong><span>family sizes</span></button>
            <button type="button" data-radar-filter="dropOnly" aria-pressed="false"><strong>{price_drop_count}</strong><span>price drops</span></button>
            <button type="button" data-radar-filter="sweetOnly" aria-pressed="false"><strong>{sweet_spot_count}</strong><span>sweet spot</span></button>
            <button type="button" data-radar-filter="lowestSeenOnly" aria-pressed="false"><strong>{lowest_seen_count}</strong><span>lowest seen</span></button>
          </div>
        </section>
        """
        if preferences
        else ""
    )
    source_filter = (
        f"""
        <details class="controls" aria-label="Deal controls" open>
          <summary class="controls-summary">
            <span>Filters</span>
            <a class="brief-link" href="../deal-brief/index.html" onclick="event.stopPropagation()">Morning brief</a>
            <span class="summary-count"><strong id="visibleDealCount">{len(html_deals)}</strong> shown</span>
          </summary>
          <div class="controls-body">
            {category_panel}
            <div class="tool-grid">
              <label class="field search-field">
                <span>Search</span>
                <input id="dealSearch" type="search" placeholder="brand, model, store..." autocomplete="off" />
              </label>
              <label class="field">
                <span>Sort</span>
                <select id="dealSort">
                  <option value="price-asc">Lowest price</option>
                  <option value="discount-desc">Biggest discount</option>
                  <option value="savings-desc">Most saved</option>
                  <option value="score-desc">Best score</option>
                </select>
              </label>
              <label class="field">
                <span>Max price</span>
                <input id="maxPrice" type="number" min="0" step="25" placeholder="Any" />
              </label>
              <div class="quick-filters primary-filters" aria-label="Quick filters">
                <button id="dealsOfDay" class="quick-button" type="button" aria-pressed="false">Best 5 today</button>
                <label><input id="mySizeOnly" type="checkbox" /> For me</label>
                <label><input id="familySizeOnly" type="checkbox" /> Family</label>
                <label><input id="dropOnly" type="checkbox" /> Drops</label>
              </div>
              <details class="filter-section">
                <summary>More filters</summary>
                <div class="quick-filters" aria-label="Advanced filters">
                  <label><input id="sweetOnly" type="checkbox" /> Sweet spot</label>
                  <label><input id="lowestSeenOnly" type="checkbox" /> Lowest seen</label>
                  <label><input id="hideAlternates" type="checkbox" /> Hide alternates</label>
                  <label><input id="photoOnly" type="checkbox" /> Photos only</label>
                  <label><input id="newOnly" type="checkbox" /> Newly tracked</label>
                  <label><input id="watchOnly" type="checkbox" /> Watchlist</label>
                  <label><input id="hideMuted" type="checkbox" checked /> Hide muted</label>
                  <button type="button" id="resetFilters">Reset everything</button>
                </div>
              </details>
            </div>
            <details class="store-panel">
              <summary>
                <strong>Stores</strong>
                <span class="meta">{len(source_counts)} active</span>
              </summary>
              <div class="filter-actions">
                <button type="button" data-filter-action="all">All stores</button>
                <button type="button" data-filter-action="none">No stores</button>
              </div>
              <div class="source-toggles">{source_controls}</div>
            </details>
          </div>
        </details>
        """
        if source_controls
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      :root {{ color-scheme: light; --ink:#17211d; --muted:#586a62; --line:#d9e1dc; --accent:#0d7c66; --accent-soft:#e7f3ef; --hot:#b42318; --gold:#8a5b00; --bg:#f4f2ea; --card:#fffef9; }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; font-family: Avenir Next, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at 7% 0%, #ffffff 0, #f4f2ea 28%, #e8f0eb 100%); color: var(--ink); }}
      main {{ width: min(1480px, 100%); margin: 0 auto; padding: 18px 16px 52px; }}
      header {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, .75fr); gap: 18px; align-items: end; padding: 18px 20px; margin-bottom: 14px; border: 1px solid rgba(13,124,102,.16); border-radius: 24px; background: linear-gradient(135deg, rgba(255,255,255,.88), rgba(232,244,239,.78)); box-shadow: 0 16px 34px rgba(39,61,51,.07); }}
      h1 {{ margin: 0; font-size: clamp(1.85rem, 3vw, 2.8rem); letter-spacing: -0.055em; line-height: .94; }}
      h2 {{ margin: 0; font-size: 1.05rem; line-height: 1.35; }}
      button, input, select {{ font: inherit; }}
      button {{ border: 1px solid var(--line); border-radius: 999px; background: white; color: var(--ink); padding: 8px 12px; cursor: pointer; }}
      button:hover {{ border-color: var(--accent); color: var(--accent); }}
      input, select {{ width: 100%; border: 1px solid var(--line); border-radius: 12px; background: white; color: var(--ink); padding: 11px 12px; }}
      input:focus, select:focus {{ outline: 3px solid rgba(13,124,102,.18); border-color: var(--accent); }}
      a {{ color: inherit; }}
      .meta, .source, .was {{ color: var(--muted); }}
      .stats {{ display: grid; grid-template-columns: repeat(4, minmax(74px, 1fr)); gap: 8px; min-width: 0; }}
      .stat {{ padding: 10px; border: 1px solid rgba(13,124,102,.16); border-radius: 16px; background: rgba(255,255,255,.72); }}
      .stat strong {{ display: block; font-size: 1.35rem; letter-spacing: -0.04em; }}
      .stat span {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
      .app-shell {{ display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 16px; align-items: start; }}
      .sidebar {{ position: sticky; top: 14px; max-height: calc(100vh - 28px); overflow: auto; scrollbar-width: thin; }}
      .content {{ min-width: 0; }}
      .controls {{ margin: 0; padding: 14px; border: 1px solid var(--line); background: rgba(255,254,249,.94); border-radius: 22px; box-shadow: 0 16px 36px rgba(39,61,51,.10); backdrop-filter: blur(12px); }}
      .controls-summary {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; font-weight: 800; list-style: none; }}
      .controls-summary::-webkit-details-marker {{ display: none; }}
      .controls-summary::before {{ content: "Hide"; border: 1px solid var(--line); border-radius: 999px; background: white; color: var(--muted); padding: 5px 9px; font-size: .78rem; font-weight: 700; order: 3; }}
      .controls:not([open]) .controls-summary::before {{ content: "Show"; }}
      .summary-count {{ color: var(--muted); font-weight: 500; margin-left: auto; }}
      .summary-count strong {{ color: var(--ink); }}
      .brief-link {{ border: 1px solid var(--line); border-radius: 999px; background: white; color: var(--ink); padding: 5px 11px; font-size: .78rem; font-weight: 700; text-decoration: none; }}
      .brief-link:hover {{ border-color: var(--ink); }}
      .controls-body {{ margin-top: 12px; }}
      .category-panel {{ display: grid; gap: 8px; margin-bottom: 12px; }}
      .category-toggle {{ display: inline-flex; align-items: center; gap: 8px; min-height: 42px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 999px; background: white; cursor: pointer; font-weight: 700; }}
      .category-toggle input {{ width: auto; accent-color: var(--accent); }}
      .category-toggle b {{ color: var(--muted); font-size: .82rem; }}
      .category-toggle:has(input:checked) {{ border-color: rgba(13,124,102,.38); background: var(--accent-soft); }}
      .category-clothing:has(input:checked) {{ border-color: #d6b86c; background: #fff7dc; }}
      .tool-grid {{ display: grid; grid-template-columns: 1fr; gap: 10px; align-items: stretch; }}
      .field span {{ display: block; margin: 0 0 5px; color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
      .quick-filters {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: stretch; padding-bottom: 1px; }}
      .quick-filters label, .quick-button {{ display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 38px; padding: 8px 9px; border: 1px solid var(--line); border-radius: 12px; background: var(--accent-soft); white-space: nowrap; font-size: .88rem; }}
      .quick-filters #resetFilters {{ grid-column: 1 / -1; }}
      .primary-filters {{ grid-template-columns: 1fr; }}
      .primary-filters label, .primary-filters .quick-button {{ justify-content: flex-start; min-height: 42px; padding-inline: 12px; font-weight: 800; }}
      .quick-filters input {{ width: auto; accent-color: var(--accent); }}
      .quick-button {{ cursor: pointer; color: var(--ink); font: inherit; }}
      .quick-button[aria-pressed="true"] {{ border-color: rgba(13,124,102,.45); background: #edf8f4; color: var(--accent); box-shadow: inset 0 0 0 1px rgba(13,124,102,.18); }}
      .filter-section, .store-panel {{ margin-top: 10px; border-top: 1px solid var(--line); padding-top: 10px; }}
      .filter-section summary, .store-panel summary, .secondary-panel summary {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; cursor: pointer; list-style: none; font-weight: 800; }}
      .filter-section summary::-webkit-details-marker, .store-panel summary::-webkit-details-marker, .secondary-panel summary::-webkit-details-marker {{ display: none; }}
      .filter-section summary::after, .store-panel summary::after, .secondary-panel summary::after {{ content: "Show"; border: 1px solid var(--line); border-radius: 999px; background: white; color: var(--muted); padding: 4px 8px; font-size: .74rem; font-weight: 800; }}
      .filter-section[open] summary::after, .store-panel[open] summary::after, .secondary-panel[open] summary::after {{ content: "Hide"; }}
      .filter-section .quick-filters {{ margin-top: 10px; }}
      .filter-actions {{ display: flex; gap: 8px; }}
      .store-panel .filter-actions {{ margin: 10px 0; }}
      .source-toggles {{ display: grid; gap: 7px; }}
      .source-toggle {{ display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 7px; min-height: 34px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 10px; background: var(--bg); font-size: .88rem; cursor: pointer; }}
      .source-toggle input {{ accent-color: var(--accent); }}
      .source-toggle b {{ color: var(--muted); font-size: .78rem; }}
      .visible-count {{ margin: 12px 0 0; }}
      .activity-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 0 0 18px; }}
      .activity-card, .health-panel, .preference-panel, .for-you-panel, .digest-panel, .secondary-panel {{ border: 1px solid var(--line); border-radius: 18px; background: rgba(255,254,249,.9); box-shadow: 0 10px 26px rgba(39,61,51,.05); padding: 14px; }}
      .section-head {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; }}
      .section-head h2 {{ margin: 0; font-size: 1rem; }}
      .section-head span {{ color: var(--muted); font-size: .84rem; }}
      .mini-list {{ display: grid; gap: 8px; }}
      .mini-card {{ display: block; padding: 10px; border: 1px solid var(--line); border-radius: 12px; background: white; text-decoration: none; }}
      .mini-card:hover {{ border-color: rgba(13,124,102,.45); }}
      .mini-card strong {{ display: block; font-size: .92rem; line-height: 1.25; }}
      .mini-card span, .empty-mini {{ display: block; margin: 4px 0 0; color: var(--muted); font-size: .84rem; }}
      .ghost-card {{ background: #fbfaf4; }}
      .digest-panel {{ margin: 0 0 18px; background: linear-gradient(135deg, rgba(20,54,47,.96), rgba(13,124,102,.82)); color: white; }}
      .digest-panel .section-head span {{ color: rgba(255,255,255,.72); }}
      .digest-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
      .digest-card {{ display: block; padding: 12px; border: 1px solid rgba(255,255,255,.22); border-radius: 14px; background: rgba(255,255,255,.10); color: white; text-decoration: none; }}
      .digest-card span {{ display: block; color: rgba(255,255,255,.72); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
      .digest-card strong {{ display: block; margin-top: 5px; line-height: 1.2; }}
      .digest-card em {{ display: block; margin-top: 5px; color: rgba(255,255,255,.78); font-style: normal; font-size: .86rem; }}
      .for-you-panel {{ margin: 12px 0 0; background: linear-gradient(135deg, rgba(237,248,244,.96), rgba(255,248,223,.72)); }}
      .health-panel {{ margin: 0 0 18px; }}
      .secondary-panel {{ margin: 0 0 18px; }}
      .secondary-panel summary b {{ color: var(--muted); font-size: .84rem; font-weight: 700; }}
      .secondary-panel[open] > summary {{ margin-bottom: 12px; }}
      .preference-panel {{ margin: 0 0 14px; }}
      .start-panel {{ display: grid; grid-template-columns: minmax(220px, .7fr) minmax(0, 1.3fr); gap: 14px; align-items: center; padding: 16px; background: linear-gradient(135deg, rgba(255,254,249,.96), rgba(237,248,244,.88)); }}
      .start-panel h2 {{ font-size: clamp(1.35rem, 2.2vw, 2rem); letter-spacing: -0.045em; line-height: 1; }}
      .start-panel p {{ margin: 8px 0 0; color: var(--muted); max-width: 42ch; }}
      .eyebrow {{ display: inline-block; margin-bottom: 6px; color: var(--accent); font-size: .75rem; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }}
      .preference-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
      .preference-grid button {{ width: 100%; padding: 12px; border: 1px solid var(--line); border-radius: 14px; background: white; text-align: left; cursor: pointer; color: var(--ink); }}
      .preference-grid button:hover {{ border-color: rgba(13,124,102,.45); transform: translateY(-1px); }}
      .preference-grid button[aria-pressed="true"] {{ border-color: rgba(13,124,102,.55); background: var(--accent-soft); box-shadow: inset 0 0 0 1px rgba(13,124,102,.16); }}
      .preference-grid strong {{ display: block; font-size: 1.45rem; letter-spacing: -0.04em; }}
      .preference-grid span, .preference-panel p {{ color: var(--muted); font-size: .84rem; }}
      .health-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }}
      .health-card {{ border: 1px solid var(--line); border-radius: 14px; background: white; padding: 10px; }}
      .health-card strong {{ display: block; font-size: .9rem; line-height: 1.25; }}
      .health-card span {{ display: inline-block; margin-top: 7px; border-radius: 999px; padding: 3px 7px; font-size: .75rem; font-weight: 800; }}
      .health-card p {{ margin: 7px 0 0; color: var(--muted); font-size: .82rem; }}
      .health-live span {{ background: #edf8f4; color: var(--accent); }}
      .health-cached span {{ background: #fff8df; color: var(--gold); }}
      .health-issue span {{ background: #fff0ee; color: var(--hot); }}
      .health-quiet span {{ background: #f0f2ef; color: var(--muted); }}
      .deals-list {{ display: grid; gap: 12px; }}
      .deal {{ display: grid; grid-template-columns: 104px 1fr auto; gap: 16px; padding: 14px; border: 1px solid var(--line); border-radius: 18px; background: var(--card); box-shadow: 0 10px 26px rgba(39,61,51,.06); align-items: start; }}
      .deal:hover {{ border-color: rgba(13,124,102,.45); transform: translateY(-1px); transition: transform .16s ease, border-color .16s ease; }}
      .deal[hidden] {{ display: none; }}
      .thumb {{ display: block; width: 104px; height: 104px; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: white; }}
      .thumb img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
      .thumb-empty {{ background: linear-gradient(135deg, #ffffff, #eef2ed); }}
      .source {{ margin: 0 0 5px; font-size: .86rem; }}
      .deal-main {{ min-width: 0; }}
      .deal-main h2 a {{ text-decoration-thickness: 1px; text-underline-offset: 3px; }}
      .price {{ text-align: right; min-width: 120px; }}
      .price strong {{ display: block; font-size: 1.6rem; color: var(--hot); letter-spacing: -0.04em; }}
      .was {{ display: block; text-decoration: line-through; }}
      .badges {{ grid-column: 2 / -1; display: flex; flex-wrap: wrap; gap: 8px; }}
      .badges span {{ border: 1px solid var(--line); border-radius: 999px; padding: 5px 8px; background: white; font-size: .86rem; }}
      .trend-down {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .trend-up {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .trend-flat {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .trend-new {{ border-color: #c9d6e8; background: #f0f6ff; color: #24558f; }}
      .buy-zone {{ font-weight: 800; }}
      .verdict {{ font-weight: 900; }}
      .verdict-buy, .sweet-badge, .floor-badge {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .verdict-size, .dupe-badge {{ border-color: #c9d6e8; background: #f0f6ff; color: #24558f; }}
      .verdict-wait, .verdict-muted {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .verdict-look {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .watch-badge {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); font-weight: 800; }}
      .muted-badge {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .size-badge {{ border-color: #c9d6e8; background: #f0f6ff; color: #24558f; font-weight: 800; }}
      .family-size-badge {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; font-weight: 800; }}
      .zone-new-low, .zone-buy {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .zone-strong {{ border-color: #c9d6e8; background: #f0f6ff; color: #24558f; }}
      .zone-watch {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .zone-fair {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .category-ski {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .category-clothing {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .cached {{ border-color: #d8d1b1; background: #fff8df; color: var(--gold); }}
      .stock-in_stock {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .stock-sold_out {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .stock-availability_unknown {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .note-button {{ border: 1px solid var(--line); border-radius: 999px; padding: 5px 8px; background: #fff; color: var(--muted); cursor: pointer; font: inherit; font-size: .86rem; }}
      .note-button:hover {{ border-color: rgba(13,124,102,.45); color: var(--accent); }}
      .deal[data-local-muted="true"] .note-button {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .empty {{ padding: 24px 0; color: var(--muted); }}
      .errors {{ margin-top: 26px; border-top: 1px solid var(--line); padding-top: 16px; }}
      @media (max-width: 1080px) {{ header {{ grid-template-columns: 1fr; }} .app-shell {{ grid-template-columns: 280px minmax(0, 1fr); }} .digest-grid, .activity-grid, .start-panel {{ grid-template-columns: 1fr; }} }}
      @media (max-width: 820px) {{ main {{ padding-inline: 10px; }} .app-shell {{ grid-template-columns: 1fr; }} .sidebar {{ position: static; max-height: none; overflow: visible; }} .controls {{ margin-bottom: 14px; }} .controls:not([open]) {{ padding-bottom: 14px; }} .quick-filters, .preference-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
      @media (max-width: 620px) {{ header {{ padding: 16px; }} .stats {{ grid-template-columns: repeat(2, 1fr); }} .deal {{ grid-template-columns: 82px 1fr; gap: 12px; }} .thumb {{ width: 82px; height: 82px; }} .price {{ grid-column: 2; text-align: left; margin-top: 2px; }} .badges {{ grid-column: 1 / -1; }} }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <div>
          <h1>{title}</h1>
          <p class="meta">Generated {html.escape(payload['generated_at'])}</p>
        </div>
        <div class="stats" aria-label="Report summary">
          <div class="stat"><strong>{payload['deal_count']}</strong><span>Deals</span></div>
          <div class="stat"><strong>${lowest_price:.0f}</strong><span>Lowest</span></div>
          <div class="stat"><strong>{best_discount:.0f}%</strong><span>Best off</span></div>
          <div class="stat"><strong>{image_count}</strong><span>Photos</span></div>
        </div>
      </header>
      <div class="app-shell">
        <aside class="sidebar">
          {source_filter}
        </aside>
        <div class="content">
          {preference_panel}
          {activity_panel}
          {health_panel}
          <section class="deals-list">
            {''.join(cards) if cards else empty}
          </section>
          {"<section class='errors'><h2>Source errors</h2><ul>" + errors + "</ul></section>" if errors else ""}
        </div>
      </div>
    </main>
    <script>
      const checkboxes = [...document.querySelectorAll('.source-toggle input')];
      const categoryBoxes = [...document.querySelectorAll('.category-toggle input')];
      const deals = [...document.querySelectorAll('.deal')];
      const dealsList = document.querySelector('.deals-list');
      const visibleDealCount = document.querySelector('#visibleDealCount');
      const searchInput = document.querySelector('#dealSearch');
      const sortSelect = document.querySelector('#dealSort');
      const maxPriceInput = document.querySelector('#maxPrice');
      const photoOnly = document.querySelector('#photoOnly');
      const dropOnly = document.querySelector('#dropOnly');
      const newOnly = document.querySelector('#newOnly');
      const watchOnly = document.querySelector('#watchOnly');
      const mySizeOnly = document.querySelector('#mySizeOnly');
      const familySizeOnly = document.querySelector('#familySizeOnly');
      const sweetOnly = document.querySelector('#sweetOnly');
      const lowestSeenOnly = document.querySelector('#lowestSeenOnly');
      const hideAlternates = document.querySelector('#hideAlternates');
      const hideMuted = document.querySelector('#hideMuted');
      const dealsOfDay = document.querySelector('#dealsOfDay');
      const resetFilters = document.querySelector('#resetFilters');
      const radarButtons = [...document.querySelectorAll('[data-radar-filter]')];
      const localMuteKey = 'skiDeals.localMutedUrls.v1';
      let localMutedUrls = readLocalMutes();

      function numericValue(deal, key) {{
        return Number.parseFloat(deal.dataset[key] || '0') || 0;
      }}

      function readLocalMutes() {{
        try {{
          const storage = window.localStorage;
          if (!storage) return new Set();
          const parsed = JSON.parse(storage.getItem(localMuteKey) || '[]');
          return new Set(Array.isArray(parsed) ? parsed.filter(Boolean) : []);
        }} catch (error) {{
          return new Set();
        }}
      }}

      function writeLocalMutes() {{
        try {{
          const storage = window.localStorage;
          if (storage) storage.setItem(localMuteKey, JSON.stringify([...localMutedUrls].sort()));
        }} catch (error) {{
          // Storage can be unavailable in restricted browser contexts; current-page hiding still works.
        }}
      }}

      function applyLocalMutes() {{
        for (const deal of deals) {{
          const url = deal.dataset.url || '';
          const isLocalIgnored = Boolean(url && localMutedUrls.has(url));
          deal.dataset.localMuted = String(isLocalIgnored);
          deal.dataset.muted = String(deal.dataset.serverMuted === 'true' || isLocalIgnored);
          const button = deal.querySelector('.note-button');
          if (button) button.textContent = isLocalIgnored ? 'Undo' : 'Not interested';
        }}
      }}

      function sortDeals() {{
        const sorted = [...deals].sort((a, b) => {{
          const mode = sortSelect?.value || 'price-asc';
          const topDealsMode = dealsOfDay?.getAttribute('aria-pressed') === 'true';
          if (topDealsMode) {{
            return numericValue(b, 'score') - numericValue(a, 'score') || numericValue(a, 'price') - numericValue(b, 'price');
          }}
          if (mode === 'price-asc') {{
            const priceDelta = numericValue(a, 'price') - numericValue(b, 'price');
            if (priceDelta !== 0) return priceDelta;
            if (a.dataset.muted !== b.dataset.muted) return a.dataset.muted === 'true' ? 1 : -1;
            if (a.dataset.watchlist !== b.dataset.watchlist) return a.dataset.watchlist === 'true' ? -1 : 1;
            return numericValue(b, 'discount') - numericValue(a, 'discount');
          }}
          if (a.dataset.muted !== b.dataset.muted) return a.dataset.muted === 'true' ? 1 : -1;
          if (a.dataset.watchlist !== b.dataset.watchlist) return a.dataset.watchlist === 'true' ? -1 : 1;
          if (mode === 'discount-desc') return numericValue(b, 'discount') - numericValue(a, 'discount');
          if (mode === 'savings-desc') return numericValue(b, 'savings') - numericValue(a, 'savings');
          if (mode === 'score-desc') return numericValue(b, 'score') - numericValue(a, 'score');
          return numericValue(a, 'price') - numericValue(b, 'price');
        }});
        for (const deal of sorted) dealsList?.appendChild(deal);
      }}

      function applyFilters() {{
        const enabled = new Set(checkboxes.filter((box) => box.checked).map((box) => box.value));
        const enabledCategories = new Set(categoryBoxes.filter((box) => box.checked).map((box) => box.value));
        const query = (searchInput?.value || '').trim().toLowerCase();
        const maxPrice = Number.parseFloat(maxPriceInput?.value || '');
        const requirePhoto = Boolean(photoOnly?.checked);
        const requireDrop = Boolean(dropOnly?.checked);
        const requireNew = Boolean(newOnly?.checked);
        const requireWatch = Boolean(watchOnly?.checked);
        const requireMySize = Boolean(mySizeOnly?.checked);
        const requireFamilySize = Boolean(familySizeOnly?.checked);
        const requireSweet = Boolean(sweetOnly?.checked);
        const requireLowestSeen = Boolean(lowestSeenOnly?.checked);
        const shouldHideAlternates = Boolean(hideAlternates?.checked);
        const shouldHideMuted = Boolean(hideMuted?.checked);
        const topDealsMode = dealsOfDay?.getAttribute('aria-pressed') === 'true';
        const eligibleTopDeals = topDealsMode
          ? [...deals]
              .filter((deal) => {{
                const matchesStore = enabled.has(deal.dataset.source);
                const matchesCategory = !categoryBoxes.length || enabledCategories.has(deal.dataset.category || 'ski');
                const matchesSearch = !query || deal.dataset.title.includes(query) || deal.dataset.source.toLowerCase().includes(query);
                const matchesPrice = Number.isNaN(maxPrice) || numericValue(deal, 'price') <= maxPrice;
                const matchesPhoto = !requirePhoto || deal.dataset.hasImage === 'true';
                const matchesDrop = !requireDrop || deal.dataset.trend === 'down';
                const matchesNew = !requireNew || deal.dataset.trend === 'new';
                const matchesWatch = !requireWatch || deal.dataset.watchlist === 'true';
                const matchesSizeGroup = (!requireMySize && !requireFamilySize) || (requireMySize && deal.dataset.mySizeMatch === 'true') || (requireFamilySize && deal.dataset.familySizeMatch === 'true');
                const matchesSweet = !requireSweet || deal.dataset.sweetSpot === 'true';
                const matchesLowestSeen = !requireLowestSeen || deal.dataset.lowestSeen === 'true';
                const matchesAlternate = !shouldHideAlternates || deal.dataset.dupePrimary === 'true';
                const matchesMuted = !shouldHideMuted || deal.dataset.muted !== 'true';
                return matchesStore && matchesCategory && matchesSearch && matchesPrice && matchesPhoto && matchesDrop && matchesNew && matchesWatch && matchesSizeGroup && matchesSweet && matchesLowestSeen && matchesAlternate && matchesMuted;
              }})
              .sort((a, b) => numericValue(b, 'score') - numericValue(a, 'score') || numericValue(a, 'price') - numericValue(b, 'price'))
              .slice(0, 5)
          : [];
        const topDealSet = new Set(eligibleTopDeals);
        let visible = 0;
        for (const deal of deals) {{
          const matchesStore = enabled.has(deal.dataset.source);
          const matchesCategory = !categoryBoxes.length || enabledCategories.has(deal.dataset.category || 'ski');
          const matchesSearch = !query || deal.dataset.title.includes(query) || deal.dataset.source.toLowerCase().includes(query);
          const matchesPrice = Number.isNaN(maxPrice) || numericValue(deal, 'price') <= maxPrice;
          const matchesPhoto = !requirePhoto || deal.dataset.hasImage === 'true';
          const matchesDrop = !requireDrop || deal.dataset.trend === 'down';
          const matchesNew = !requireNew || deal.dataset.trend === 'new';
          const matchesWatch = !requireWatch || deal.dataset.watchlist === 'true';
          const matchesSizeGroup = (!requireMySize && !requireFamilySize) || (requireMySize && deal.dataset.mySizeMatch === 'true') || (requireFamilySize && deal.dataset.familySizeMatch === 'true');
          const matchesSweet = !requireSweet || deal.dataset.sweetSpot === 'true';
          const matchesLowestSeen = !requireLowestSeen || deal.dataset.lowestSeen === 'true';
          const matchesAlternate = !shouldHideAlternates || deal.dataset.dupePrimary === 'true';
          const matchesMuted = !shouldHideMuted || deal.dataset.muted !== 'true';
          const matchesTopDeals = !topDealsMode || topDealSet.has(deal);
          const show = matchesStore && matchesCategory && matchesSearch && matchesPrice && matchesPhoto && matchesDrop && matchesNew && matchesWatch && matchesSizeGroup && matchesSweet && matchesLowestSeen && matchesAlternate && matchesMuted && matchesTopDeals;
          deal.hidden = !show;
          if (show) visible += 1;
        }}
        if (visibleDealCount) visibleDealCount.textContent = visible;
      }}

      function updateView() {{
        sortDeals();
        applyFilters();
        syncRadarButtons();
      }}

      function radarTarget(name) {{
        if (name === 'dropOnly') return dropOnly;
        if (name === 'watchOnly') return watchOnly;
        if (name === 'mySizeOnly') return mySizeOnly;
        if (name === 'familySizeOnly') return familySizeOnly;
        if (name === 'sweetOnly') return sweetOnly;
        if (name === 'lowestSeenOnly') return lowestSeenOnly;
        if (name === 'showMuted') return hideMuted;
        return null;
      }}

      function syncRadarButtons() {{
        for (const button of radarButtons) {{
          const name = button.dataset.radarFilter;
          if (name === 'dealsOfDay') {{
            button.setAttribute('aria-pressed', String(dealsOfDay?.getAttribute('aria-pressed') === 'true'));
            continue;
          }}
          if (name === 'showMuted') {{
            button.setAttribute('aria-pressed', String(Boolean(hideMuted && !hideMuted.checked)));
            continue;
          }}
          const target = radarTarget(name);
          button.setAttribute('aria-pressed', String(Boolean(target?.checked)));
        }}
      }}

      for (const box of checkboxes) {{
        box.addEventListener('change', updateView);
      }}
      for (const box of categoryBoxes) {{
        box.addEventListener('change', updateView);
      }}
      for (const button of document.querySelectorAll('[data-filter-action]')) {{
        button.addEventListener('click', () => {{
          const checked = button.dataset.filterAction === 'all';
          for (const box of checkboxes) box.checked = checked;
          updateView();
        }});
      }}
      for (const button of radarButtons) {{
        button.addEventListener('click', () => {{
          const name = button.dataset.radarFilter;
          if (name === 'dealsOfDay') {{
            const enabled = dealsOfDay?.getAttribute('aria-pressed') !== 'true';
            if (dealsOfDay) {{
              dealsOfDay.setAttribute('aria-pressed', String(enabled));
              dealsOfDay.textContent = enabled ? 'Showing best 5' : 'Best 5 today';
            }}
            if (enabled && sortSelect) sortSelect.value = 'score-desc';
            updateView();
            return;
          }}
          if (name === 'showMuted') {{
            if (hideMuted) hideMuted.checked = !hideMuted.checked;
            updateView();
            return;
          }}
          const target = radarTarget(name);
          if (target) target.checked = !target.checked;
          updateView();
        }});
      }}
      for (const control of [searchInput, sortSelect, maxPriceInput, photoOnly, dropOnly, newOnly, watchOnly, mySizeOnly, familySizeOnly, sweetOnly, lowestSeenOnly, hideAlternates, hideMuted]) {{
        control?.addEventListener('input', updateView);
        control?.addEventListener('change', updateView);
      }}
      for (const button of document.querySelectorAll('.note-button')) {{
        button.addEventListener('click', async () => {{
          const value = button.dataset.ignoreValue || '';
          if (!value) return;
          if (localMutedUrls.has(value)) {{
            localMutedUrls.delete(value);
          }} else {{
            localMutedUrls.add(value);
          }}
          writeLocalMutes();
          applyLocalMutes();
          updateView();
        }});
      }}
      dealsOfDay?.addEventListener('click', () => {{
        const enabled = dealsOfDay.getAttribute('aria-pressed') !== 'true';
        dealsOfDay.setAttribute('aria-pressed', String(enabled));
        dealsOfDay.textContent = enabled ? 'Showing best 5' : 'Best 5 today';
        if (enabled && sortSelect) sortSelect.value = 'score-desc';
        updateView();
      }});
      resetFilters?.addEventListener('click', () => {{
        if (searchInput) searchInput.value = '';
        if (sortSelect) sortSelect.value = 'price-asc';
        if (maxPriceInput) maxPriceInput.value = '';
        if (photoOnly) photoOnly.checked = false;
        if (dropOnly) dropOnly.checked = false;
        if (newOnly) newOnly.checked = false;
        if (watchOnly) watchOnly.checked = false;
        if (mySizeOnly) mySizeOnly.checked = false;
        if (familySizeOnly) familySizeOnly.checked = false;
        if (sweetOnly) sweetOnly.checked = false;
        if (lowestSeenOnly) lowestSeenOnly.checked = false;
        if (hideAlternates) hideAlternates.checked = false;
        if (hideMuted) hideMuted.checked = true;
        if (dealsOfDay) {{
          dealsOfDay.setAttribute('aria-pressed', 'false');
          dealsOfDay.textContent = 'Best 5 today';
        }}
        for (const box of checkboxes) box.checked = true;
        for (const box of categoryBoxes) box.checked = true;
        updateView();
      }});
      applyLocalMutes();
      updateView();
    </script>
  </body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor configured URLs for ski gear deals.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    config = load_config(args.config)
    deals, errors = scan(config)
    write_outputs(deals, errors, config)

    json_output = resolve_output_path(config.get("json_output"), JSON_OUTPUT)
    html_output = resolve_output_path(config.get("html_output"), HTML_OUTPUT)
    web_output = resolve_output_path(config.get("web_output"), WEB_OUTPUT)
    markdown_output = resolve_output_path(config.get("markdown_output"), MD_OUTPUT)
    history_output = resolve_output_path(config.get("price_history_output"), PRICE_HISTORY_OUTPUT)

    print(f"Checked {len([s for s in config.get('sources', []) if s.get('enabled', True)])} sources.")
    print(f"Found {len(deals)} matching deals.")
    print(f"Wrote {json_output}")
    print(f"Wrote {html_output}")
    print(f"Wrote {web_output}")
    print(f"Wrote {markdown_output}")
    print(f"Wrote {history_output}")
    if errors:
        print(f"{len(errors)} source(s) had errors.", file=sys.stderr)
    return 0 if deals or not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
