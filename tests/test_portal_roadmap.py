#!/usr/bin/env python3
"""Regressões da apresentação pública do roteiro futuro."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTAL = (ROOT / "index.html").read_text(encoding="utf-8")


class TestPortalRoadmap(unittest.TestCase):
    def _card(self, name: str) -> str:
        match = re.search(
            rf'<article class="product-card">(?:(?!</article>).)*<h2>{re.escape(name)}</h2>(?:(?!</article>).)*</article>',
            PORTAL,
            re.DOTALL,
        )
        if match is None:
            self.fail(f"card ausente: {name}")
        return match.group(0)

    def test_future_products_are_visible_but_inactive(self):
        for name in ("Supleno Estruturas", "Supleno Personas", "Supleno Posições"):
            card = self._card(name)
            self.assertIn('<span class="badge soon">Em breve</span>', card)
            self.assertIn('<button class="btn secondary" type="button" disabled>Em breve</button>', card)
            self.assertNotIn("href=", card)

    def test_current_products_remain_available(self):
        for name in ("Supleno Tipos", "Supleno Estilos", "Supleno Traços", "Mapa Integrado"):
            card = self._card(name)
            self.assertIn('<span class="badge live">Disponível</span>', card)
            self.assertIn("href=", card)
            self.assertNotIn(" disabled", card)


if __name__ == "__main__":
    unittest.main()