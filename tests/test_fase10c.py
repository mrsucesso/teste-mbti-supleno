import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "tipos/index.html", ROOT / "estilos/index.html", ROOT / "tracos/index.html"]


class TestFase10C(unittest.TestCase):
    def test_all_products_load_local_resume_and_share_assets(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertIn("progresso-local.js", text, page)
            self.assertIn("compartilhamento.js", text, page)
            self.assertIn('data-local-progress', text, page)
            self.assertIn('data-share-result', text, page)
            self.assertIn('data-reset-progress', text, page)

    def test_local_progress_contract_has_schema_expiry_and_no_pii(self):
        text = (ROOT / "assets/progresso-local.js").read_text(encoding="utf-8")
        for token in ("schema", "expiresAt", "localStorage", "migrat", "removeItem", "respostas"):
            self.assertIn(token, text)
        self.assertRegex(text, r"NOME|EMAIL|WHATSAPP|PII|nome|email|whatsapp")
        self.assertIn("Não armazena nome, e-mail ou WhatsApp", text)

    def test_share_has_web_share_clipboard_and_accessible_fallback(self):
        text = (ROOT / "assets/compartilhamento.js").read_text(encoding="utf-8")
        for token in ("navigator.share", "navigator.clipboard", "window.print", "aria-live", "fallback"):
            self.assertIn(token, text)
        self.assertNotRegex(text, r"lead(Name|Email|Whats)")

    def test_retention_is_short_and_documented(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(text.lower(), r"expira|retenção")
        for page in PAGES:
            self.assertIn("7 dias", page.read_text(encoding="utf-8"))

    def test_result_before_capture_and_consent_order_remains(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertLess(text.index('id="screen-result"'), text.index('id="captureBlock"'))
            submit = text[text.index("function submitLead"):]
            self.assertLess(submit.index("leadConsent"), submit.index("fetch(WEBHOOK_URL"))

    def test_controls_are_keyboard_and_live_region_ready(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertRegex(text, r'data-share-result[^>]*type="button"')
            self.assertRegex(text, r'data-reset-progress[^>]*type="button"')
            self.assertIn('aria-live="polite"', text)


if __name__ == "__main__":
    unittest.main()
