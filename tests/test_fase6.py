#!/usr/bin/env python3
"""Regressões da instrumentação e dos assets da Fase 6."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFase6(unittest.TestCase):
    def test_frontends_load_shared_metrics_and_events(self):
        for product in ("tipos", "estilos", "tracos"):
            text = (ROOT / product / "index.html").read_text(encoding="utf-8")
            self.assertIn("funil-analytics.js", text)
            for event in ("trackInicio", "trackProgresso", "trackConclusao", "trackResultado", "trackCaptura"):
                self.assertIn(event, text)

    def test_metrics_library_has_six_events_and_no_personal_fields(self):
        text = (ROOT / "assets" / "funil-analytics.js").read_text(encoding="utf-8")
        for event in ("funil_inicio", "funil_progresso", "funil_conclusao", "funil_resultado", "funil_captura", "funil_cta"):
            self.assertIn(event, text)
        self.assertIn("ANALYTICS.ENABLED", text)
        self.assertIn("requireConsent", text)
        self.assertNotRegex(text, r"\b(nome|email|whatsapp)\b.*payload")

    def test_config_examples_are_safe_by_default(self):
        for path in ROOT.glob("*/config.example.js"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ANALYTICS", text)
            self.assertIn('ENABLED: false', text)
            self.assertIn('GA4_ID: ""', text)
            self.assertIn('META_PIXEL_ID: ""', text)

    def test_og_assets_and_metadata(self):
        for name in ("portal", "tipos", "estilos", "tracos"):
            asset = ROOT / "assets" / "og" / f"{name}.svg"
            self.assertTrue(asset.exists())
            self.assertIn("1200", asset.read_text(encoding="utf-8"))
        for path in (ROOT / "index.html", ROOT / "tipos/index.html", ROOT / "estilos/index.html", ROOT / "tracos/index.html"):
            self.assertIn('property="og:image"', path.read_text(encoding="utf-8"))

    def test_result_pages_have_share_asset_and_metrics(self):
        pages = list((ROOT / "tipos/resultados").glob("*.html"))
        self.assertEqual(len(pages), 32)
        for path in pages:
            text = path.read_text(encoding="utf-8")
            self.assertIn("../../assets/funil-analytics.js", text)
            self.assertIn("../../assets/og/tipos.svg", text)


if __name__ == "__main__":
    unittest.main()
