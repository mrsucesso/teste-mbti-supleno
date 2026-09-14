import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFase10L(unittest.TestCase):
    def test_map_accepts_styles_object_and_legacy_string(self):
        source = (ROOT / "assets/mapa-integrado.js").read_text(encoding="utf-8")
        script = """
const fs=require('fs'),vm=require('vm'); const c={}; c.globalThis=c;
vm.runInNewContext(fs.readFileSync('assets/mapa-integrado.js','utf8'),c);
for (const value of [{code:'D'}, 'I']) {
  const out=c.SuplenoMapa.combinar({tipos:{resultado:{code:'INTJ'}}, estilos:{resultado:value}, tracos:{resultado:{}}});
  if (out.estilo !== (typeof value === 'string' ? value : value.code)) throw Error('estilo não normalizado');
}
"""
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertIn("typeof dados.estilos.code === 'string'", source)

    def test_v1_schema_requires_scores_access_token_and_strict_objects(self):
        schema = json.loads((ROOT / "docs/integracao-v1/schemas/captura.request.schema.json").read_text())
        self.assertIn("scores", schema["required"])
        self.assertIn("access_token", schema["required"])
        for field in ("person", "consent", "attribution"):
            self.assertFalse(schema["properties"][field].get("additionalProperties", True))

    def test_apps_script_v1_has_auth_strict_validation_and_attribution_fingerprint(self):
        source = (ROOT / "apps-script/Code.gs").read_text(encoding="utf-8")
        for token in ("ACCESS_TOKEN", "hasOnlyKeys", "validateAttribution", "normalizeAttribution", "data.scores", "data.attribution"):
            self.assertIn(token, source)
        self.assertIn("attribution: data.attribution", source)
        self.assertIn('"Atribuição"', source)
        self.assertIn('attribution: validated.attribution', source)

    def test_adapter_keeps_public_antiabuse_token_outside_legacy_fields(self):
        source = (ROOT / "assets/integracao-v1-adapter.js").read_text(encoding="utf-8")
        self.assertIn("access_token: legado.token || ''", source)
        self.assertIn("honeypot: legado.website || legado.honeypot || ''", source)
        self.assertNotIn("ACCESS_TOKEN", source)

    def test_v1_contract_rejects_completed_and_requires_honeypot(self):
        schema = json.loads((ROOT / "docs/integracao-v1/schemas/captura.response.schema.json").read_text())
        self.assertNotIn("completed", schema["properties"]["sequence_state"]["enum"])
        request = json.loads((ROOT / "docs/integracao-v1/schemas/captura.request.schema.json").read_text())
        self.assertIn("honeypot", request["required"])
        self.assertFalse(request["additionalProperties"])

    def test_email_limit_is_semantically_bounded_at_254_chars(self):
        for path in (ROOT / "apps-script/Code.gs", ROOT / "tipos/index.html", ROOT / "estilos/index.html", ROOT / "tracos/index.html"):
            self.assertIn("(?=.{1,254}$)", path.read_text(encoding="utf-8"))
        source = (ROOT / "apps-script/Code.gs").read_text(encoding="utf-8")
        self.assertIn("PII_RETENTION_MS", source)
        self.assertIn("purgarDadosExpirados", source)

    def test_public_privacy_policy_states_the_180_day_retention(self):
        source = (ROOT / "privacidade/index.html").read_text(encoding="utf-8")
        self.assertIn("purgados em até 180 dias", source)
        self.assertNotIn("ainda precisa definir e publicar prazo de retenção", source)


if __name__ == "__main__":
    unittest.main()
