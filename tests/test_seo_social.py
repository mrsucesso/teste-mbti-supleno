#!/usr/bin/env python3
"""Contratos de SEO técnico e compartilhamento social."""
from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://testes.supleno.com"
PRIMARY = {
    "index.html": "portal.jpg",
    "tipos/index.html": "tipos.jpg",
    "estilos/index.html": "estilos.jpg",
    "tracos/index.html": "tracos.jpg",
    "mapa/index.html": "mapa.jpg",
    "metodologia/index.html": "portal.jpg",
    "privacidade/index.html": "portal.jpg",
}


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        raise ValueError(f"JPEG inválido: {path}")
    index = 2
    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    while index + 8 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        marker = data[index]
        index += 1
        if marker in (0xD8, 0xD9):
            continue
        length = int.from_bytes(data[index:index + 2], "big")
        if marker in sof_markers:
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return width, height
        index += length
    raise ValueError(f"Dimensões JPEG não encontradas: {path}")


class TestSeoSocial(unittest.TestCase):
    def test_open_graph_jpegs_have_expected_dimensions_and_weight(self):
        expected = {"portal.jpg", "tipos.jpg", "estilos.jpg", "tracos.jpg", "mapa.jpg"}
        images = {path.name for path in (ROOT / "assets/og").glob("*.jpg")}
        self.assertEqual(images, expected)
        for name in expected:
            path = ROOT / "assets/og" / name
            self.assertEqual(jpeg_dimensions(path), (1200, 630), name)
            self.assertGreater(path.stat().st_size, 20_000, name)
            self.assertLess(path.stat().st_size, 400_000, name)

    def test_primary_pages_have_complete_absolute_social_metadata(self):
        for relative, image in PRIMARY.items():
            page = (ROOT / relative).read_text(encoding="utf-8")
            url = f"{BASE}/assets/og/{image}"
            self.assertIn(f'<meta property="og:image" content="{url}">', page, relative)
            self.assertIn('<meta property="og:image:type" content="image/jpeg">', page, relative)
            self.assertIn('<meta property="og:image:width" content="1200">', page, relative)
            self.assertIn('<meta property="og:image:height" content="630">', page, relative)
            self.assertIn('<meta property="og:image:alt"', page, relative)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', page, relative)
            self.assertIn(f'<meta name="twitter:image" content="{url}">', page, relative)
            self.assertIn('<meta name="twitter:image:alt"', page, relative)
            self.assertNotIn("assets/og/portal.svg", page, relative)
            self.assertNotIn("assets/og/tipos.svg", page, relative)
            self.assertNotIn("assets/og/estilos.svg", page, relative)
            self.assertNotIn("assets/og/tracos.svg", page, relative)

    def test_type_results_use_absolute_raster_social_image(self):
        pages = sorted((ROOT / "tipos/resultados").glob("*.html"))
        self.assertEqual(len(pages), 32)
        url = f"{BASE}/assets/og/tipos.jpg"
        for path in pages:
            page = path.read_text(encoding="utf-8")
            canonical = f"{BASE}/tipos/resultados/{path.stem}"
            self.assertIn(f'<link rel="canonical" href="{canonical}">', page, path.name)
            self.assertIn(f'<meta property="og:url" content="{canonical}">', page, path.name)
            self.assertIn(f'<meta property="og:image" content="{url}">', page, path.name)
            self.assertIn('<meta property="og:image:type" content="image/jpeg">', page, path.name)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', page, path.name)
            self.assertIn(f'<meta name="twitter:image" content="{url}">', page, path.name)
            self.assertIn('<meta name="twitter:image:alt"', page, path.name)
            self.assertNotIn(".svg", page, path.name)

    def test_type_result_links_match_cloudflare_clean_urls(self):
        app = (ROOT / "tipos/index.html").read_text(encoding="utf-8")
        self.assertIn('`resultados/${code.toLowerCase()}-${gk}`', app)
        self.assertNotIn('`resultados/${code.toLowerCase()}-${gk}.html`', app)
        backend = (ROOT / "apps-script/Code.gs").read_text(encoding="utf-8")
        self.assertIn('`${SITE_BASE_URL}/tipos/resultados/${code.toLowerCase()}-${gk}`', backend)
        self.assertNotIn('`${SITE_BASE_URL}/tipos/resultados/${code.toLowerCase()}-${gk}.html`', backend)
        for path in sorted((ROOT / "resultados").glob("*.html")):
            page = path.read_text(encoding="utf-8")
            destination = f"/tipos/resultados/{path.stem}"
            self.assertIn(f"https://testes.supleno.com{destination}", page, path.name)
            self.assertIn(f"url=..{destination}", page, path.name)
            self.assertNotIn(f"{destination}.html", page, path.name)

    def test_sitemap_matches_indexable_canonicals(self):
        sitemap = ET.parse(ROOT / "sitemap.xml")
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = {node.text for node in sitemap.findall("sm:url/sm:loc", namespace) if node.text}
        expected = set()
        pages = [ROOT / relative for relative in PRIMARY]
        pages.extend(sorted((ROOT / "tipos/resultados").glob("*.html")))
        for path in pages:
            page = path.read_text(encoding="utf-8")
            match = re.search(r'<link rel="canonical" href="([^"]+)">', page)
            if match is None:
                self.fail(f"Canonical ausente: {path}")
            expected.add(match.group(1))
        self.assertEqual(locations, expected)
        self.assertFalse(any("/resultados/" in url and "/tipos/resultados/" not in url for url in locations))

    def test_robots_and_documentation_point_to_canonical_sitemap(self):
        robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertIn(f"Sitemap: {BASE}/sitemap.xml", robots)
        docs = ROOT / "docs/seo/README.md"
        self.assertTrue(docs.is_file())
        text = docs.read_text(encoding="utf-8")
        for term in ("Open Graph", "canonical", "sitemap.xml", "robots.txt", "generate-og-images.py"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
