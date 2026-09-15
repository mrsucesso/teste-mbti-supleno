#!/usr/bin/env python3
"""Regressões da identidade visual oficial do Supleno."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ("#153126", "#1F4033", "#3C6E52", "#5C9A78", "#EAF3EC", "#FBFAF7", "#24302A")
LEGACY = ("#C15A38", "#A3492C", "#D9A441", "#FAF6F1", "#FFF3EC", "#1F4B4C", "#163736")


class TestBrandPalette(unittest.TestCase):
    def test_shared_css_declares_official_supleno_palette(self):
        css = (ROOT / "assets/style.css").read_text(encoding="utf-8")
        for color in OFFICIAL:
            self.assertIn(color, css)
        for color in LEGACY:
            self.assertNotIn(color, css)

    def test_test_intros_use_shared_editorial_header(self):
        for product in ("tipos", "estilos", "tracos"):
            page = (ROOT / product / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="test-intro-meta"', page)
            self.assertIn('class="product-icon"', page)

    def test_type_result_emblems_no_longer_use_legacy_palette(self):
        pages = sorted((ROOT / "tipos/resultados").glob("*.html"))
        self.assertEqual(len(pages), 32)
        for page in pages:
            text = page.read_text(encoding="utf-8")
            for color in LEGACY:
                self.assertNotIn(color, text, page.name)
            self.assertNotIn("tons quentes", text, page.name)
            self.assertNotIn("tons frios", text, page.name)

    def test_portal_hero_uses_local_green_artwork(self):
        portal = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("assets/illustrations/portal-atlas.webp", portal)
        artwork = ROOT / "assets/illustrations/portal-atlas.webp"
        self.assertTrue(artwork.is_file())
        self.assertGreater(artwork.stat().st_size, 20_000)

    def test_desktop_navigation_never_wraps(self):
        styles = (ROOT / "assets/style.css").read_text(encoding="utf-8")
        self.assertRegex(styles, r"\.site-nav \.nav-brand\{[^}]*flex:0 0 auto")
        self.assertRegex(styles, r"\.nav-links\{[^}]*flex:0 0 auto[^}]*flex-wrap:nowrap")


if __name__ == "__main__":
    unittest.main()
