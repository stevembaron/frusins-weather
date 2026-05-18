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
WEB_DIR = ROOT / "ski-deals"
WEB_OUTPUT = WEB_DIR / "index.html"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0 Safari/537.36 SkiDealMonitor/1.0"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
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
    previous_price: float | None = None
    price_change: float | None = None
    price_change_percent: float | None = None
    price_trend: str | None = None
    first_seen_at: str | None = None


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
                deals.append(make_deal(title, urljoin(base_url, str(url)), source_name, current, original, found_at))
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
) -> list[Deal]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return []

    deals: list[Deal] = []
    for product in payload.get("products", []):
        title = clean_text(str(product.get("title", "")))
        handle = product.get("handle")
        if not title or not handle:
            continue

        product_url = urljoin(base_url, f"/products/{handle}")
        for variant in product.get("variants", []):
            if ignore_sold_out and not variant.get("available", True):
                continue

            current = money(variant.get("price"))
            if current is None:
                continue

            original = money(variant.get("compare_at_price"))
            variant_title = normalize_shopify_variant_title(variant.get("title"))
            deal_title = title if variant_title in ("", "Default Title") else f"{title} - {variant_title}"
            deals.append(make_deal(deal_title, product_url, source_name, current, original, found_at))

    return deals


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
        deals.append(make_deal(deal_title, product_url, source_name, current, original, found_at))
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
        prices = [money(match.group(1)) for match in PRICE_RE.finditer(link["text"])]
        prices = [price for price in prices if price is not None]
        if not prices:
            continue

        current = min(prices)
        original = max(prices) if len(prices) > 1 and max(prices) > current else None
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
        prices = extract_prices(block)
        if not prices:
            continue

        compare_at = re.search(r"Compare At\s+\$\s?([0-9,]+(?:\.[0-9]{2})?)", block, re.I)
        current, original = choose_prices(prices)
        if compare_at:
            original = money(compare_at.group(1))
        deals.append(make_deal(title, url, source_name, current, original, found_at))
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
        consolidated.append(make_deal(base_title, url, source, best_current, best_original, latest_found_at, sizes=sizes))

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
                        )
                    )
                if candidates:
                    all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                    time.sleep(float(source.get("delay_seconds", 1.2)))
                    continue
                if not source.get("reader_fallback"):
                    errors.append(SourceError(source_name, url, blocked))
                    continue
                markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                blocked = block_reason(markup)
                if blocked:
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
                    )
                )
            candidates.extend(link_candidates(markup, url, source_name, found_at))
            candidates.extend(markdown_candidates(markup, url, source_name, found_at))
            candidates.extend(geartrade_search_candidates(markup, url, source_name, found_at))
            if not candidates and source.get("reader_fallback"):
                markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                candidates = markdown_candidates(markup, url, source_name, found_at)
                candidates.extend(link_candidates(markup, url, source_name, found_at))
                candidates.extend(geartrade_search_candidates(markup, url, source_name, found_at))
            all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
            time.sleep(float(source.get("delay_seconds", 1.2)))
        except (HTTPError, URLError, TimeoutError, OSError) as error:
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
                            )
                        )
                    if candidates:
                        all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                        time.sleep(float(source.get("delay_seconds", 1.2)))
                        continue
                    markup = fetch_reader_target(source.get("reader_url") or url, timeout=45)
                    blocked = block_reason(markup)
                    if blocked:
                        errors.append(SourceError(source_name, url, blocked))
                        continue
                    candidates = markdown_candidates(markup, url, source_name, found_at)
                    candidates.extend(link_candidates(markup, url, source_name, found_at))
                    candidates.extend(geartrade_search_candidates(markup, url, source_name, found_at))
                    all_deals.extend(filter_and_sort(candidates, source_filter_config)[:per_source_limit])
                    time.sleep(float(source.get("delay_seconds", 1.2)))
                    continue
                except (HTTPError, URLError, TimeoutError, OSError) as fallback_error:
                    errors.append(SourceError(source_name, url, f"{error}; reader fallback failed: {fallback_error}"))
                    continue
            errors.append(SourceError(source_name, url, str(error)))

    return rank_deals(dedupe(all_deals)), errors


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
    return payload


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
        items[key] = {
            "title": deal.title,
            "url": deal.url,
            "source": deal.source,
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
    html_output = render_html(payload, config)
    html_output_path.write_text(html_output, encoding="utf-8")
    web_output.write_text(html_output, encoding="utf-8")


def resolve_output_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


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
    html_deals = sorted(
        payload["deals"],
        key=lambda deal: (
            stock_sort_key(deal.get("stock_status")),
            deal["current_price"],
            -(deal["discount_percent"] or 0),
        ),
    )
    source_counts: dict[str, int] = {}
    for deal in html_deals:
        source_counts[str(deal["source"])] = source_counts.get(str(deal["source"]), 0) + 1

    for deal in html_deals:
        original = f"<span class='was'>Was ${deal['original_price']:.2f}</span>" if deal["original_price"] else ""
        discount = f"<span>{deal['discount_percent']}% off</span>" if deal["discount_percent"] else "<span>Price found</span>"
        savings = f"<span>Save ${deal['savings']:.2f}</span>" if deal["savings"] else ""
        trend_label = price_trend_label(deal)
        trend_class = f" trend-{html.escape(str(deal.get('price_trend') or 'unknown'))}"
        trend_badge = f"<span class='trend{trend_class}'>{html.escape(trend_label)}</span>" if trend_label else ""
        sizes = f"<span>Sizes {html.escape(', '.join(deal['sizes']))}</span>" if deal.get("sizes") else ""
        status = stock_label(deal.get("stock_status"))
        stock_badge = f"<span class='stock stock-{html.escape(deal['stock_status'])}'>{html.escape(status)}</span>" if status else ""
        cards.append(
            f"""
            <article class="deal" data-source="{html.escape(deal['source'])}">
              <div>
                <p class="source">{html.escape(deal['source'])}</p>
                <h2><a href="{html.escape(deal['url'])}" target="_blank" rel="noreferrer">{html.escape(deal['title'])}</a></h2>
              </div>
              <div class="price">
                <strong>${deal['current_price']:.2f}</strong>
                {original}
              </div>
              <div class="badges">{discount}{savings}{trend_badge}{sizes}{stock_badge}<span>Score {deal['score']:.0f}</span></div>
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
    source_filter = (
        f"""
        <section class="filters" aria-label="Store filters">
          <div class="filter-head">
            <h2>Stores</h2>
            <div class="filter-actions">
              <button type="button" data-filter-action="all">All</button>
              <button type="button" data-filter-action="none">None</button>
            </div>
          </div>
          <div class="source-toggles">{source_controls}</div>
          <p class="meta visible-count"><span id="visibleDealCount">{len(html_deals)}</span> shown</p>
        </section>
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
      :root {{ color-scheme: light; --ink:#16201c; --muted:#52645c; --line:#d8e0dc; --accent:#0d7c66; --hot:#b42318; --bg:#f7f8f5; }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
      main {{ width: min(1060px, 100%); margin: 0 auto; padding: 32px 14px 56px; }}
      header {{ display: flex; justify-content: space-between; gap: 18px; align-items: end; border-bottom: 1px solid var(--line); padding-bottom: 18px; margin-bottom: 18px; }}
      h1 {{ margin: 0; font-size: 2rem; }}
      h2 {{ margin: 0; font-size: 1.05rem; line-height: 1.35; }}
      button {{ border: 1px solid var(--line); border-radius: 7px; background: white; color: var(--ink); padding: 7px 10px; font: inherit; cursor: pointer; }}
      button:hover {{ border-color: var(--accent); color: var(--accent); }}
      a {{ color: inherit; }}
      .meta, .source, .was {{ color: var(--muted); }}
      .filters {{ margin: 0 0 18px; padding: 14px; border: 1px solid var(--line); background: #ffffff; border-radius: 8px; }}
      .filter-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }}
      .filter-head h2 {{ font-size: 1rem; }}
      .filter-actions {{ display: flex; gap: 8px; }}
      .source-toggles {{ display: flex; flex-wrap: wrap; gap: 8px; }}
      .source-toggle {{ display: inline-flex; align-items: center; gap: 7px; min-height: 34px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 7px; background: var(--bg); font-size: .88rem; cursor: pointer; }}
      .source-toggle input {{ accent-color: var(--accent); }}
      .source-toggle b {{ color: var(--muted); font-size: .78rem; }}
      .visible-count {{ margin: 12px 0 0; }}
      .deal {{ display: grid; grid-template-columns: 1fr auto; gap: 14px; padding: 16px 0; border-bottom: 1px solid var(--line); }}
      .deal[hidden] {{ display: none; }}
      .source {{ margin: 0 0 5px; font-size: .86rem; }}
      .price {{ text-align: right; min-width: 120px; }}
      .price strong {{ display: block; font-size: 1.45rem; color: var(--hot); }}
      .was {{ display: block; text-decoration: line-through; }}
      .badges {{ grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 8px; }}
      .badges span {{ border: 1px solid var(--line); border-radius: 8px; padding: 5px 8px; background: white; }}
      .trend-down {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .trend-up {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .trend-flat {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .trend-new {{ border-color: #c9d6e8; background: #f0f6ff; color: #24558f; }}
      .stock-in_stock {{ border-color: #b7d9d0; background: #edf8f4; color: var(--accent); }}
      .stock-sold_out {{ border-color: #efc2bd; background: #fff0ee; color: var(--hot); }}
      .stock-availability_unknown {{ border-color: #d8d1b1; background: #fff8df; color: #7a6200; }}
      .empty {{ padding: 24px 0; color: var(--muted); }}
      .errors {{ margin-top: 26px; border-top: 1px solid var(--line); padding-top: 16px; }}
      @media (max-width: 620px) {{ header, .deal, .filter-head {{ display: block; }} .filter-actions {{ margin-top: 10px; }} .price {{ text-align: left; margin-top: 12px; }} }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <div>
          <h1>{title}</h1>
          <p class="meta">Generated {html.escape(payload['generated_at'])}</p>
        </div>
        <p class="meta">{payload['deal_count']} deals from {payload['sources_checked']} enabled sources</p>
      </header>
      {source_filter}
      <section class="deals-list">
        {''.join(cards) if cards else empty}
      </section>
      {"<section class='errors'><h2>Source errors</h2><ul>" + errors + "</ul></section>" if errors else ""}
    </main>
    <script>
      const checkboxes = [...document.querySelectorAll('.source-toggle input')];
      const deals = [...document.querySelectorAll('.deal')];
      const visibleDealCount = document.querySelector('#visibleDealCount');

      function applyStoreFilters() {{
        const enabled = new Set(checkboxes.filter((box) => box.checked).map((box) => box.value));
        let visible = 0;
        for (const deal of deals) {{
          const show = enabled.has(deal.dataset.source);
          deal.hidden = !show;
          if (show) visible += 1;
        }}
        if (visibleDealCount) visibleDealCount.textContent = visible;
      }}

      for (const box of checkboxes) {{
        box.addEventListener('change', applyStoreFilters);
      }}
      for (const button of document.querySelectorAll('[data-filter-action]')) {{
        button.addEventListener('click', () => {{
          const checked = button.dataset.filterAction === 'all';
          for (const box of checkboxes) box.checked = checked;
          applyStoreFilters();
        }});
      }}
      applyStoreFilters();
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
