import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFase10D(unittest.TestCase):
    def test_mapa_page_is_public_functional_and_safe(self):
        text = (ROOT / "mapa/index.html").read_text(encoding="utf-8")
        for token in (
            "Mapa Integrado Supleno",
            "mapa-integrado.js",
            "data-action=\"apagar\"",
            "data-action=\"imprimir\"",
            "data-action=\"compartilhar\"",
            "aria-live=\"polite\"",
            "og:title",
            "canonical",
            "não é diagnóstico",
        ):
            self.assertIn(token, text)
        self.assertNotRegex(text, r"fetch\(|XMLHttpRequest|analytics|pixel|whatsapp|e-mail")

    def test_portal_links_to_mapa_without_future_label(self):
        text = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="mapa/"', text)
        self.assertNotIn("Em breve</span>\n        <h2>Mapa Integrado", text)

    def test_mapa_aggregator_has_explicit_deterministic_rule(self):
        text = (ROOT / "assets/mapa-integrado.js").read_text(encoding="utf-8")
        for token in ("SuplenoProgresso", "ler", "tipos", "estilos", "tracos", "regra", "determin", "não é diagnóstico"):
            self.assertIn(token, text)
        script = """
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync('assets/mapa-integrado.js', 'utf8');
const records = {
  tipos: { resultado: { code: 'ENTJ', gender: 'M' } },
  estilos: { resultado: 'D' },
  tracos: { resultado: { abertura: { percent: 80, faixa: 'alto' } } }
};
const context = { console, window: {}, SuplenoProgresso: { ler: key => records[key] } };
context.window = context;
vm.runInNewContext(src, context);
const out = context.SuplenoMapa.combinar();
if (!out.completo || out.tipo !== 'ENTJ' || out.estilo !== 'D' || out.tracos.abertura.percent !== 80) process.exit(1);
const missing = context.SuplenoMapa.combinar({ estilos: null });
if (missing.completo || missing.faltam.indexOf('estilos') < 0) process.exit(2);
"""
        result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mapa_has_no_personal_data_and_documents_local_rule(self):
        page = (ROOT / "mapa/index.html").read_text(encoding="utf-8")
        for token in ("somente no seu navegador", "resultados locais", "sem nome", "sem contato", "sem diagnóstico", "regra transparente"):
            self.assertIn(token, page.lower())


if __name__ == "__main__":
    unittest.main()
