import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "tipos": ROOT / "tipos/index.html",
    "estilos": ROOT / "estilos/index.html",
    "tracos": ROOT / "tracos/index.html",
}
SIMULATOR = ROOT / "scripts/simulador-integracao-v1.py"


class TestFase10H(unittest.TestCase):
    def valid_request(self, **overrides):
        request = {
            "contract": "supleno.integracao.v1",
            "submission_id": "synthetic",
            "product": "tipos",
            "person": {"name": "Pessoa", "email": "pessoa@example.invalid"},
            "result": {"code": "INTJ", "gender": "M"},
            "consent": {"granted": True, "captured_at": "2026-09-13T15:00:00Z", "purpose": "resultado_e_sequencia_supleno", "version": "1"},
            "attribution": {"origin": "local"},
            "opt_out": False,
        }
        request.update(overrides)
        return request

    def test_same_id_same_payload_is_duplicate_and_changed_payload_conflicts(self):
        spec = importlib.util.spec_from_file_location("simulador", SIMULATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        request = self.valid_request()
        store = {}
        self.assertEqual(module.captura(store, request)["status"], "accepted")
        reordered = {**request, "result": {"code": "INTJ", "gender": "M"}, "consent": dict(request["consent"]), "submission_id": "synthetic"}
        self.assertEqual(module.captura(store, reordered)["status"], "duplicate")
        changed = {**request, "result": {"code": "ENFP"}}
        conflict = module.captura(store, changed)
        self.assertEqual(conflict["status"], "rejected")
        self.assertEqual(conflict["error"]["code"], "duplicate_payload_conflict")

    def test_products_persist_back_and_reset_interface_explicitly(self):
        for product, page in PAGES.items():
            text = page.read_text(encoding="utf-8")
            self.assertIn("SuplenoProgresso.salvar('" + product + "'", text, product)
            self.assertIn("function goBack(){ if(current>0){ current--;", text, product)
            self.assertIn("window.addEventListener('supleno:progresso-apagado', restartQuiz);", text, product)
            self.assertIn("order = []; current = 0; answers = [];", text, product)

    def test_local_progress_rejects_invalid_answers_and_personal_fields(self):
        script = r"""
const fs = require('fs'), vm = require('vm');
const source = fs.readFileSync('assets/progresso-local.js', 'utf8');
const values = new Map();
const localStorage = {getItem: k => values.get(k) || null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k)};
const context = {localStorage, Date, JSON, console, Number, Object, Array}; context.globalThis = context;
vm.runInNewContext(source, context);
const api = context.SuplenoProgresso;
if (api.salvar('tipos', {respostas: ['nao-e-polo'], progresso: 1, ordem: [0]}) !== null) throw new Error('resposta arbitraria aceita');
if (api.salvar('tipos', {respostas: ['E'], progresso: 1, ordem: [0], resultado: {code:'INTJ', gender:'M', email:'x'}}) !== null) throw new Error('PII aceito no resultado');
if (!api.salvar('tipos', {respostas: ['E'], progresso: 1, ordem: [0], resultado: {code:'INTJ', gender:'M'}})) throw new Error('registro valido rejeitado');
"""
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_simulator_rejects_malformed_requests_and_suppresses_after_opt_out(self):
        spec = importlib.util.spec_from_file_location("simulador", SIMULATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.captura({}, {})["error"]["code"], "invalid_request")
        request = self.valid_request()
        request["attribution"]["origin"] = "https://site.example/a?email=pessoa@example.com"
        self.assertEqual(module.captura({}, request)["error"]["code"], "invalid_request")
        request = self.valid_request()
        store = {}
        self.assertEqual(module.captura(store, request)["status"], "accepted")
        store[request["submission_id"]]["opt_out"] = True
        self.assertEqual(module.captura(store, request)["status"], "suppressed")


if __name__ == "__main__":
    unittest.main()
