import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "tipos": ROOT / "tipos/index.html",
    "estilos": ROOT / "estilos/index.html",
    "tracos": ROOT / "tracos/index.html",
}


class TestFase10G(unittest.TestCase):
    def test_completed_reload_restores_result_before_rendering_question(self):
        for produto, page in PAGES.items():
            text = page.read_text(encoding="utf-8")
            self.assertIn("function restoreSavedResult", text, produto)
            self.assertIn("restoreSavedResult(saved)", text, produto)
            self.assertIn("if (restoreSavedResult(saved)) return;", text, produto)
            if produto == "estilos":
                self.assertIn("saved.respostas.forEach(p => scores[p]++)", text)
            self.assertRegex(
                text,
                r"Number\.isInteger\(current\).*current.*QUESTIONS\.length",
                produto,
            )

    def test_progress_schema_requires_version_and_bounds_records(self):
        text = (ROOT / "assets/progresso-local.js").read_text(encoding="utf-8")
        for token in (
            "isValidRecord",
            "MAX_RESPONSES",
            "Number.isInteger(value.progresso)",
            "value.progresso > value.respostas.length",
            "Array.isArray(value.ordem)",
        ):
            self.assertIn(token, text)

    @unittest.skipUnless(shutil.which("node"), "Node.js não instalado")
    def test_malformed_local_records_are_ignored_by_progress_reader(self):
        script = r"""
const fs = require('fs'), vm = require('vm');
const source = fs.readFileSync('assets/progresso-local.js', 'utf8');
const values = new Map();
const localStorage = {
  getItem: key => values.get(key) || null,
  setItem: (key, value) => values.set(key, value),
  removeItem: key => values.delete(key),
};
const context = { localStorage, Date, JSON, console };
context.globalThis = context;
vm.runInNewContext(source, context);
const api = context.SuplenoProgresso;
const bad = [
  {schema: 1, produto: 'tipos', respostas: [], progresso: 1, ordem: [], expiresAt: Date.now() + 10000},
  {schema: 1, produto: 'tipos', respostas: new Array(101).fill(null), progresso: 0, ordem: null, expiresAt: Date.now() + 10000},
  {schema: 1, produto: 'tipos', respostas: [null], progresso: 0, ordem: [9], expiresAt: Date.now() + 10000},
];
for (const [i, record] of bad.entries()) {
  values.set('supleno:progresso:tipos', JSON.stringify(record));
  if (api.ler('tipos') !== null) throw new Error('registro malformado aceito #' + i);
}
const good = api.salvar('tipos', {ordem: [0], respostas: ['E'], progresso: 1, resultado: {code: 'INTJ', gender: 'M'}});
if (!good || api.ler('tipos').resultado.code !== 'INTJ') throw new Error('registro válido rejeitado');
"""
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_capture_schema_requires_consent_version(self):
        schema = json.loads(
            (ROOT / "docs/integracao-v1/schemas/captura.request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("version", schema["properties"]["consent"]["required"])

    def test_capture_schema_rejects_consent_without_version(self):
        schema = json.loads(
            (ROOT / "docs/integracao-v1/schemas/captura.request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        consent = {"granted": True, "captured_at": "2026-09-13T12:00:00Z", "purpose": "resultado_e_sequencia_supleno"}
        missing = set(schema["properties"]["consent"]["required"]) - set(consent)
        self.assertIn("version", missing)

    def test_map_render_does_not_interpolate_storage_values_into_inner_html(self):
        text = (ROOT / "mapa/index.html").read_text(encoding="utf-8")
        self.assertNotIn("node.innerHTML=", text)
        self.assertIn("textContent", text)
        self.assertIn("createElement", text)
        self.assertIn("ALLOWED", text)


if __name__ == "__main__":
    unittest.main()
