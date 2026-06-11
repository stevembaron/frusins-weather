"""Offline tests for cross-store annotations, sparklines, and brief continuity.

Run with: python3 -m unittest discover tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import deal_analyst  # noqa: E402
import deal_monitor  # noqa: E402


def make_deal(title: str, source: str, price: float, category: str = "ski") -> dict:
    return {"title": title, "source": source, "current_price": price, "category": category}


class CrossStoreAnnotationsTest(unittest.TestCase):
    def test_same_product_two_stores(self) -> None:
        cheap = make_deal("2024 Rossignol Rallybird 102 Skis", "Lone Pine", 279.0)
        pricey = make_deal("Rossignol Rallybird 102 Skis 2024", "Evo", 319.99)
        only = make_deal("Atomic Bent 100 Skis", "Evo", 399.0)
        notes = deal_monitor.cross_store_annotations([cheap, pricey, only])

        self.assertEqual(notes[id(cheap)], {"best": True, "stores": 2})
        self.assertEqual(notes[id(pricey)]["best"], False)
        self.assertIn("Also at Lone Pine for $279.00", notes[id(pricey)]["note"])
        self.assertNotIn(id(only), notes)

    def test_same_store_duplicates_not_flagged(self) -> None:
        a = make_deal("Elan Ripstick 96 Skis", "Evo", 399.0)
        b = make_deal("Elan Ripstick 96 Skis 2025", "Evo", 449.0)
        self.assertEqual(deal_monitor.cross_store_annotations([a, b]), {})

    def test_categories_not_mixed(self) -> None:
        ski = make_deal("Stio Azura Jacket", "Evo", 100.0, category="ski")
        clothing = make_deal("Stio Azura Jacket", "Geartrade", 70.0, category="clothing")
        self.assertEqual(deal_monitor.cross_store_annotations([ski, clothing]), {})

    def test_short_keys_skipped(self) -> None:
        a = make_deal("Poles", "Evo", 20.0)
        b = make_deal("Poles", "Sierra", 25.0)
        self.assertEqual(deal_monitor.cross_store_annotations([a, b]), {})


class SparklineTest(unittest.TestCase):
    def test_renders_polyline_and_range(self) -> None:
        svg = deal_monitor.sparkline_svg([400.0, 380.0, 350.0, 349.99])
        self.assertIn("<polyline", svg)
        self.assertIn("$350-$400", svg)
        self.assertIn("#1f6f43", svg)  # downtrend = green

    def test_uptrend_is_red_and_flat_is_gray(self) -> None:
        self.assertIn("#b3422f", deal_monitor.sparkline_svg([300.0, 320.0]))
        self.assertIn("#9aa6a0", deal_monitor.sparkline_svg([300.0, 300.0]))

    def test_too_few_points_renders_nothing(self) -> None:
        self.assertEqual(deal_monitor.sparkline_svg([300.0]), "")
        self.assertEqual(deal_monitor.sparkline_svg([]), "")

    def test_series_lookup(self) -> None:
        deal = {"title": "X", "source": "Evo", "url": "https://www.evo.com/products/x"}
        key = deal_monitor.price_history_key(deal)
        history = {key: {"observations": [{"date": "2026-06-01", "price": 400}, {"date": "2026-06-02", "price": 380}]}}
        self.assertEqual(deal_monitor.deal_price_series(history, deal), [400.0, 380.0])
        self.assertEqual(deal_monitor.deal_price_series({}, deal), [])


class RecentBriefsTest(unittest.TestCase):
    def test_includes_latest_briefs_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            for day in ("2026-06-06", "2026-06-07", "2026-06-08", "2026-06-09"):
                (archive / f"{day}.md").write_text(f"# Gear brief — {day}\nbody", encoding="utf-8")
            section = deal_analyst.recent_briefs_section(archive, limit=3)

        self.assertIn("for continuity", section)
        self.assertIn("2026-06-09", section)
        self.assertIn("2026-06-07", section)
        self.assertNotIn("2026-06-06", section)
        self.assertLess(section.index("2026-06-09"), section.index("2026-06-07"))

    def test_empty_archive_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(deal_analyst.recent_briefs_section(Path(tmp)), "")

    def test_deal_line_carries_cross_note(self) -> None:
        deal = make_deal("Rallybird 102", "Evo", 319.99)
        line = deal_analyst.deal_line(deal, "ski", "Also at Lone Pine for $279.00")
        self.assertIn("Also at Lone Pine for $279.00", line)


if __name__ == "__main__":
    unittest.main()
