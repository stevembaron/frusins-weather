"""Offline tests for the deal analyst's brief rendering.

Run with: python3 -m unittest discover tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import deal_analyst  # noqa: E402

SAMPLE_BRIEF = """\
# Gear brief — June 9, 2026

## Act now
- **Rossignol Rallybird 102** at $279.00 (67% off, watch-term brand) — [view](https://lonepinegearx.com/products/rallybird)

## Worth watching
- Dynastar M-Pro 90 at $349.99 — buy if it drops below $300: https://www.evo.com/skis/m-pro-90

## Notes
Evo data is cached & stale today (source returned 403).
"""


class MarkdownToHtmlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rendered = deal_analyst.markdown_to_html(SAMPLE_BRIEF)

    def test_headings(self) -> None:
        self.assertIn("<h1>Gear brief — June 9, 2026</h1>", self.rendered)
        self.assertIn("<h2>Act now</h2>", self.rendered)

    def test_bold_and_markdown_link(self) -> None:
        self.assertIn("<strong>Rossignol Rallybird 102</strong>", self.rendered)
        self.assertIn('<a href="https://lonepinegearx.com/products/rallybird">view</a>', self.rendered)

    def test_bare_url_linked_once(self) -> None:
        self.assertIn('<a href="https://www.evo.com/skis/m-pro-90">', self.rendered)
        self.assertNotIn('href="<a', self.rendered)

    def test_list_structure(self) -> None:
        self.assertEqual(self.rendered.count("<ul>"), 2)
        self.assertEqual(self.rendered.count("<li>"), 2)

    def test_plain_paragraph_and_escaping(self) -> None:
        self.assertIn("<p>Evo data is cached &amp; stale today (source returned 403).</p>", self.rendered)

    def test_full_page_renders(self) -> None:
        page = deal_analyst.render_brief_html(SAMPLE_BRIEF)
        self.assertIn("<!DOCTYPE html>", page)
        self.assertIn("<h1>Gear brief — June 9, 2026</h1>", page)
        self.assertIn(deal_analyst.MODEL, page)


if __name__ == "__main__":
    unittest.main()
