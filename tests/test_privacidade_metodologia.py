import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PAGES = [ROOT / "index.html", ROOT / "tipos/index.html", ROOT / "estilos/index.html", ROOT / "tracos/index.html"]
RESULT_PAGES = sorted((ROOT / "tipos/resultados").glob("*.html"))


class TestPrivacidadeMetodologia(unittest.TestCase):
    def test_shared_information_pages_have_seo_and_one_h1(self):
        for slug, title in (("privacidade", "Privacidade"), ("metodologia", "Metodologia")):
            path = ROOT / slug / "index.html"
            self.assertTrue(path.exists(), slug)
            text = path.read_text(encoding="utf-8")
            self.assertIn(f'<link rel="canonical" href="https://testes.supleno.com/{slug}/">', text)
            self.assertIn(f"<title>{title}", text)
            self.assertEqual(len(re.findall(r"<h1(?:\s|>)", text)), 1)
            self.assertIn('lang="pt-BR"', text)
            self.assertIn("Testes Supleno", text)

    def test_privacy_page_explains_safe_mode_and_policy_boundaries(self):
        text = (ROOT / "privacidade/index.html").read_text(encoding="utf-8").lower()
        for phrase in ("modo seguro", "não transmite", "consentimento", "cancelar", "opt-out", "retenção"):
            self.assertIn(phrase, text)
        self.assertNotIn("webhook_url", text)
        self.assertIn("analytics", text)
        self.assertIn("pixel", text)

    def test_methodology_page_covers_three_tests_without_clinical_claims(self):
        text = (ROOT / "metodologia/index.html").read_text(encoding="utf-8").lower()
        for product in ("supleno tipos", "supleno estilos", "supleno traços"):
            self.assertIn(product, text)
        for phrase in ("limitações", "não é diagnóstico", "não foi validado cientificamente"):
            self.assertIn(phrase, text)

    def test_public_pages_link_to_both_information_pages(self):
        for path in PUBLIC_PAGES + RESULT_PAGES:
            text = path.read_text(encoding="utf-8")
            prefix = "../../" if path in RESULT_PAGES else "../" if path.parent.name in {"tipos", "estilos", "tracos"} else ""
            self.assertIn(f'href="{prefix}privacidade/"', text, path.name)
            self.assertIn(f'href="{prefix}metodologia/"', text, path.name)

    def test_information_pages_do_not_load_tracking_or_submission_scripts(self):
        for slug in ("privacidade", "metodologia"):
            text = (ROOT / slug / "index.html").read_text(encoding="utf-8").lower()
            self.assertNotIn("fetch(", text)
            self.assertNotIn("funil-analytics", text)
            self.assertNotIn("google-analytics", text)
            self.assertNotIn("facebook", text)


if __name__ == "__main__":
    unittest.main()
