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

    def test_each_new_question_is_focusable_and_focused_for_announcement(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            self.assertIn('id="qText" tabindex="-1"', text, page.name)
            render = _extract_function(text, "renderQuestion")
            self.assertIn("qText.focus({preventScroll:true})", render, page.name)

    def test_tracos_arrows_select_radio_and_update_aria_checked(self):
        text = (ROOT / "tracos/index.html").read_text(encoding="utf-8")
        render = _extract_function(text, "renderQuestion")
        self.assertIn("setLikertSelection(qi,", render)
        selection = _extract_function(text, "setLikertSelection")
        self.assertIn("aria-checked", selection)
        self.assertIn("answers[qi] = value", selection)

    def test_all_result_pages_have_one_main_h1(self):
        pages = sorted((ROOT / "tipos/resultados").glob("*.html"))
        self.assertEqual(len(pages), 32)
        for page in pages:
            text = page.read_text(encoding="utf-8")
            main = text[text.index('<main id="conteudo"'):text.index("</main>")]
            self.assertEqual(len(re.findall(r"<h1\b", main)), 1, page.name)

    def test_all_products_share_one_configurable_production_backend_contract(self):
        for product in ("tipos", "estilos", "tracos"):
            config = (ROOT / product / "config.example.js").read_text(encoding="utf-8")
            self.assertRegex(config, r'WEBHOOK_URL:\s*""')
            page = (ROOT / product / "index.html").read_text(encoding="utf-8")
            self.assertIn("SUPLENO_CONFIG.WEBHOOK_URL", page)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("backend de produção compartilhado", readme)


def _extract_function(text, name):
    start = text.index(f"function {name}(")
    end = text.index("\nfunction ", start + 1)
    return text[start:end]


class TestSandboxNuncaAlegaEnvio(unittest.TestCase):
    """Em sandbox (padrão), nenhuma tela ou mensagem pode alegar que a
    captura foi enviada/recebida por um servidor — nada é transmitido."""

    def test_submit_button_label_depends_on_actual_transmission(self):
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            submit_src = _extract_function(text, "submitLead")
            self.assertNotRegex(
                submit_src,
                r"textContent\s*=\s*'Enviando\.\.\.'\s*;",
                f"{page.name}: rótulo do botão não pode alegar envio incondicionalmente",
            )
            self.assertIn("WEBHOOK_URL && !SANDBOX_MODE", submit_src, page.name)

    def test_lead_sent_message_is_honest_about_sandbox(self):
        for page in (ROOT / "estilos/index.html", ROOT / "tracos/index.html"):
            text = page.read_text(encoding="utf-8")
            show_sent_src = _extract_function(text, "showLeadSent")
            self.assertRegex(show_sent_src, r"function showLeadSent\(\s*transmitted\s*\)", page.name)
            self.assertIn("não foi transmitid", show_sent_src.lower(), page.name)

    def test_tipos_shows_honest_outcome_message(self):
        text = (ROOT / "tipos/index.html").read_text(encoding="utf-8")
        self.assertIn('id="leadOutcomeMsg"', text)
        show_outcome_src = _extract_function(text, "showLeadOutcome")
        self.assertRegex(show_outcome_src, r"function showLeadOutcome\(\s*transmitted\s*\)")
        self.assertIn("não foi transmitid", show_outcome_src.lower())


if __name__ == "__main__":
    unittest.main()
