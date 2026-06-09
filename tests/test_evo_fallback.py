"""Offline tests for the Evo Constructor-API fallback in deal_monitor.

Run with: python3 -m unittest discover tests
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import deal_monitor  # noqa: E402


class ConstructorKeyCacheTest(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evo_constructor_key.json"
            self.assertIsNone(deal_monitor.load_cached_evo_constructor_key(path))
            deal_monitor.save_cached_evo_constructor_key("key_abc123", path)
            self.assertEqual(deal_monitor.load_cached_evo_constructor_key(path), "key_abc123")

    def test_corrupt_cache_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evo_constructor_key.json"
            path.write_text("not json", encoding="utf-8")
            self.assertIsNone(deal_monitor.load_cached_evo_constructor_key(path))

    def test_key_extracted_from_markup(self) -> None:
        markup = 'foo;window.eHS.constructor_index_key = "key_FromPage";bar'
        self.assertEqual(deal_monitor.evo_constructor_api_key(markup), "key_FromPage")


class EvoApiFallbackTest(unittest.TestCase):
    BASE_URL = "https://www.evo.com/collections/skis?sortBy=price&sortOrder=ascending"

    def test_non_evo_url_skipped(self) -> None:
        deals = deal_monitor.evo_api_fallback_candidates(
            "https://www.campsaver.com/skis", {}, "CampSaver", "2026-06-09T00:00:00+00:00", 10
        )
        self.assertEqual(deals, [])

    def test_no_key_available_returns_empty(self) -> None:
        with mock.patch.object(deal_monitor, "load_cached_evo_constructor_key", return_value=None):
            deals = deal_monitor.evo_api_fallback_candidates(
                self.BASE_URL, {}, "Evo", "2026-06-09T00:00:00+00:00", 10
            )
        self.assertEqual(deals, [])

    def test_config_key_wins_over_cache(self) -> None:
        with mock.patch.object(deal_monitor, "evo_constructor_deals", return_value=[]) as deals_call:
            with mock.patch.object(deal_monitor, "load_cached_evo_constructor_key", return_value="key_cached"):
                deal_monitor.evo_api_fallback_candidates(
                    self.BASE_URL,
                    {"constructor_key": "key_config"},
                    "Evo",
                    "2026-06-09T00:00:00+00:00",
                    10,
                )
        deals_call.assert_called_once()
        self.assertEqual(deals_call.call_args.args[0], "key_config")

    def test_cached_key_used_when_config_missing(self) -> None:
        with mock.patch.object(deal_monitor, "evo_constructor_deals", return_value=[]) as deals_call:
            with mock.patch.object(deal_monitor, "load_cached_evo_constructor_key", return_value="key_cached"):
                deal_monitor.evo_api_fallback_candidates(
                    self.BASE_URL, {}, "Evo", "2026-06-09T00:00:00+00:00", 10
                )
        self.assertEqual(deals_call.call_args.args[0], "key_cached")

    def test_hydrated_candidates_save_key(self) -> None:
        markup = 'window.eHS.constructor_index_key = "key_FromPage";'
        with mock.patch.object(deal_monitor, "evo_constructor_deals", return_value=[]):
            with mock.patch.object(deal_monitor, "save_cached_evo_constructor_key") as save_call:
                deal_monitor.evo_hydrated_collection_candidates(
                    markup, self.BASE_URL, "Evo", "2026-06-09T00:00:00+00:00", 10
                )
        save_call.assert_called_once_with("key_FromPage")


class ConstructorResultParsingTest(unittest.TestCase):
    def test_result_deal_parsed(self) -> None:
        item = {
            "value": "Dynastar M-Pro 90 Skis 2025",
            "data": {
                "url": "https://www.evo.com/skis/dynastar-m-pro-90",
                "price": "349.99",
                "compare_at_price": "599.95",
                "size": "170 cm",
                "availability": True,
                "image_url": "https://images.evo.com/m-pro-90.jpg",
            },
        }
        deal = deal_monitor.evo_constructor_result_deal(item, "Evo", "2026-06-09T00:00:00+00:00")
        self.assertIsNotNone(deal)
        assert deal is not None
        self.assertEqual(deal.title, "Dynastar M-Pro 90 Skis 2025")
        self.assertEqual(deal.current_price, 349.99)
        self.assertEqual(deal.original_price, 599.95)
        self.assertEqual(deal.sizes, ["170 cm"])
        self.assertEqual(deal.stock_status, "in_stock")
        self.assertEqual(deal.image_url, "https://images.evo.com/m-pro-90.jpg")

    def test_constructor_api_url_keeps_filters(self) -> None:
        query = {
            "sortBy": ["price"],
            "sortOrder": ["ascending"],
            "filters[size]": ["170 cm", "160 cm"],
            "filters[gender]": [" adult-male"],
        }
        url = deal_monitor.evo_constructor_api_url("key_abc", query, page=2, per_page=80)
        self.assertIn("key=key_abc", url)
        self.assertIn("sort_by=price", url)
        self.assertIn("page=2", url)
        self.assertIn("filters%5Bsize%5D=170%20cm", url)
        self.assertIn("filters%5Bgender%5D=%20adult-male", url)


if __name__ == "__main__":
    unittest.main()
