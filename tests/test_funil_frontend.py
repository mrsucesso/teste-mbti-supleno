import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "tipos/index.html", ROOT / "estilos/index.html", ROOT / "tracos/index.html"]


class TestFunilFrontend(unittest.TestCase):
    def test_all_products_capture_whatsapp_consent_and_attribution(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertIn('id="leadWhats"', text, page.name)
            self.assertIn('id="leadConsent"', text, page.name)
            self.assertIn("consentimento", text, page.name)
            self.assertIn("utm_source", text, page.name)
            self.assertIn("utm_medium", text, page.name)
            self.assertIn("utm_campaign", text, page.name)
            self.assertIn("submission_id", text, page.name)

    def test_consent_is_required_before_network_submission(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            submit = text[text.index("function submitLead"):]
            self.assertRegex(submit, r"leadConsent")
            self.assertLess(submit.index("leadConsent"), submit.index("fetch(WEBHOOK_URL"), page.name)

    def test_result_is_available_before_optional_capture_on_all_products(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertLess(text.index('id="screen-result"'), text.index('id="captureBlock"'), page.name)

    def test_submissions_are_sandboxed_by_default(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertIn("SANDBOX_MODE", text, page.name)
            self.assertRegex(text, r"SANDBOX_MODE\s*=\s*SUPLENO_CONFIG\.SANDBOX_MODE\s*!==\s*false", page.name)


if __name__ == "__main__":
    unittest.main()
