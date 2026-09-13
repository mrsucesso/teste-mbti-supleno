import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "integracao-v1"
SCHEMAS = CONTRACT / "schemas"
SIMULATOR = ROOT / "scripts" / "simulador-integracao-v1.py"


class TestContratoIntegracaoV1(unittest.TestCase):
    def test_schemas_de_request_e_resposta_existem_e_sao_json_schema(self):
        for filename in ("captura.request.schema.json", "captura.response.schema.json"):
            data = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data["version"], "1.0")
            self.assertIn("type", data)

    def test_contrato_documenta_estados_idempotencia_consentimento_optout_utm_erros_exportacao(self):
        text = (CONTRACT / "README.md").read_text(encoding="utf-8").lower()
        for token in ("idempot", "consentimento", "opt-out", "utm", "erro", "export", "pending", "uncertain"):
            self.assertIn(token, text)

    def test_matriz_documenta_planilha_banco_e_adaptadores_existentes(self):
        text = (CONTRACT / "matriz-adaptadores.md").read_text(encoding="utf-8").lower()
        for token in ("frontend", "apps script", "funilstore", "planilha", "banco", "adaptador"):
            self.assertIn(token, text)

    def test_contrato_nao_cria_endpoint_ou_credencial_real(self):
        for path in CONTRACT.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"https?://(?!json-schema\.org)[^\s\"']+/(webhook|api|exec)")
                self.assertNotRegex(text, r"(api[_-]?key|client[_-]?secret|password)\s*[:=]\s*[^<\s]+", msg=str(path))


class TestSimuladorE2E(unittest.TestCase):
    def test_simulador_e2e_sintetico_executa_sem_rede_e_exporta_resumo(self):
        resultado = subprocess.run(
            [sys.executable, str(SIMULATOR)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        saida = json.loads(resultado.stdout)
        self.assertEqual(saida["contrato"], "supleno.integracao.v1")
        self.assertEqual(saida["rede_real"], False)
        self.assertEqual(saida["captura"]["status"], "accepted")
        self.assertEqual(saida["duplicata"]["status"], "duplicate")
        self.assertEqual(saida["opt_out"]["status"], "suppressed")
        self.assertEqual(saida["sequencia"], ["imediato", "d1", "d3", "d5", "d7"])
        self.assertEqual(saida["exportacao"]["registros"], 1)

    def test_simulador_nao_conhece_url_de_transporte(self):
        texto = SIMULATOR.read_text(encoding="utf-8")
        self.assertNotIn("requests", texto)
        self.assertNotIn("urllib.request", texto)
        self.assertNotIn("http://", texto)
        self.assertNotIn("https://", texto)


if __name__ == "__main__":
    unittest.main()
