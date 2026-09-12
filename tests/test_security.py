#!/usr/bin/env python3
"""Testes automatizados de segurança e conformidade do Supleno Tipos.

Roda com: python3 -m unittest tests/test_security.py -v
(ou `python3 -m pytest tests/test_security.py` se pytest estiver instalado)

Cobre:
- Contagem 28 perguntas / 16 tipos / 32 páginas de resultado
- Escape de HTML no e-mail (apps-script/Code.gs)
- Proteção contra injeção de fórmula na planilha (apps-script/Code.gs)
- Padrões de validação (nome, e-mail, whatsapp) e consistência front/back-end
- Mecanismos antiabuso: honeypot, token de configuração, rate limit, payload máximo
- Configuração: config.example.js / .gitignore, sem config.js versionado
- Ausência de segredos reais no conteúdo versionado
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "tipos" / "index.html"
CODE_GS = ROOT / "apps-script" / "Code.gs"
RESULTS = ROOT / "tipos" / "resultados"
GITIGNORE = ROOT / ".gitignore"
CONFIG_EXAMPLE = ROOT / "tipos" / "config.example.js"

INDEX_TEXT = INDEX.read_text(encoding="utf-8")
CODE_GS_TEXT = CODE_GS.read_text(encoding="utf-8")


def extract_balanced(text: str, marker: str) -> str:
    """Retorna o literal `{...}` que segue `marker`, usando contagem de
    chaves (ignora chaves dentro de strings) em vez de regex genérica —
    necessário porque PROFILES tem objetos aninhados."""
    start = text.index(marker) + len(marker)
    assert text[start] == "{"
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"chave não fechada para marcador {marker!r}")


def json_array_after(text: str, marker: str) -> list:
    start = text.index(marker) + len(marker)
    assert text[start] == "["
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise AssertionError(f"colchete não fechado para marcador {marker!r}")


class TestContentCounts(unittest.TestCase):
    """Critério 28/16/32: perguntas, tipos e páginas de resultado."""

    def test_28_questions_in_index(self):
        questions = json_array_after(INDEX_TEXT, "const QUESTIONS = ")
        self.assertEqual(len(questions), 28)

    def test_16_profiles_in_index(self):
        profiles_text = extract_balanced(INDEX_TEXT, "const PROFILES = ")
        profiles = json.loads(profiles_text)
        self.assertEqual(len(profiles), 16)

    def test_16_profiles_in_backend_match_frontend(self):
        profiles_text = extract_balanced(INDEX_TEXT, "const PROFILES = ")
        frontend_profiles = json.loads(profiles_text)

        backend_text = extract_balanced(CODE_GS_TEXT, "const PROFILES = ")
        backend_profiles = json.loads(backend_text)

        self.assertEqual(len(backend_profiles), 16)
        self.assertEqual(set(frontend_profiles.keys()), set(backend_profiles.keys()))

    def test_32_result_pages_exist(self):
        pages = list(RESULTS.glob("*.html"))
        self.assertEqual(len(pages), 32)

    def test_result_pages_match_profiles_x_genders(self):
        profiles_text = extract_balanced(INDEX_TEXT, "const PROFILES = ")
        profiles = json.loads(profiles_text)
        expected = {
            f"{code.lower()}-{gender}.html" for code in profiles for gender in ("m", "f")
        }
        actual = {p.name for p in RESULTS.glob("*.html")}
        self.assertEqual(expected, actual)


class TestEscaping(unittest.TestCase):
    """Escape de HTML no corpo do e-mail para impedir injeção de marcação."""

    def test_escape_html_function_exists(self):
        self.assertIn("function escapeHtml(value)", CODE_GS_TEXT)

    def test_escape_html_escapes_dangerous_characters(self):
        start = CODE_GS_TEXT.index("function escapeHtml(value)")
        body = CODE_GS_TEXT[start:CODE_GS_TEXT.index("\n}\n\nfunction sendResultEmail", start)]
        # Verifica diretamente os pares regex -> entidade esperados.
        self.assertRegex(body, r"replace\(/&/g")
        self.assertRegex(body, r"replace\(/<\/g")
        self.assertRegex(body, r"replace\(/>/g")
        self.assertRegex(body, r"replace\(/\"/g")
        self.assertRegex(body, r"replace\(/'/g")

    def test_email_html_fields_are_escaped(self):
        send_body = extract_function_body(CODE_GS_TEXT, "sendResultEmail")
        # Campos vindos de dados do usuário ou de perfil devem passar por escapeHtml
        # antes de entrar no HTML do e-mail.
        self.assertIn("escapeHtml(name)", send_body)
        self.assertIn("escapeHtml(typeName)", send_body)
        self.assertIn("escapeHtml(desc)", send_body)
        self.assertIn("escapeHtml(s)", send_body)  # usado nos .map() de strengths/growth


class TestFormulaInjectionProtection(unittest.TestCase):
    """Proteção contra injeção de fórmula (CSV/Sheets formula injection)."""

    def test_sanitize_for_sheet_function_exists(self):
        self.assertIn("function sanitizeForSheet(value)", CODE_GS_TEXT)

    def test_sanitize_for_sheet_blocks_formula_prefixes(self):
        body = extract_function_body(CODE_GS_TEXT, "sanitizeForSheet")
        self.assertRegex(body, r"\^\[=\+\\?-@\\t\\r\]|\^\[=\+\-@\\t\\r\]")

    def test_all_appended_fields_are_sanitized(self):
        body = extract_function_body(CODE_GS_TEXT, "appendLead")
        for field in ("name", "email", "sigla", "whatsapp"):
            self.assertIn(f"sanitizeForSheet({field})", body)


class TestValidationPatterns(unittest.TestCase):
    """Padrões de validação de nome/e-mail/whatsapp, consistentes entre
    front-end (feedback imediato) e back-end (validação que efetivamente vale)."""

    def test_patterns_present_in_backend(self):
        self.assertIn("const NAME_PATTERN =", CODE_GS_TEXT)
        self.assertIn("const EMAIL_PATTERN =", CODE_GS_TEXT)
        self.assertIn("const WHATSAPP_PATTERN =", CODE_GS_TEXT)

    def test_patterns_present_in_frontend(self):
        self.assertIn("const NAME_PATTERN =", INDEX_TEXT)
        self.assertIn("const EMAIL_PATTERN =", INDEX_TEXT)
        self.assertIn("const WHATSAPP_PATTERN =", INDEX_TEXT)

    def test_patterns_identical_between_frontend_and_backend(self):
        for name in ("NAME_PATTERN", "EMAIL_PATTERN", "WHATSAPP_PATTERN"):
            front = extract_regex_literal(INDEX_TEXT, name)
            back = extract_regex_literal(CODE_GS_TEXT, name)
            self.assertEqual(front, back, f"{name} diverge entre index.html e Code.gs")

    def test_backend_rejects_missing_or_unknown_fields(self):
        body = extract_function_body(CODE_GS_TEXT, "validateInput")
        self.assertIn("NAME_PATTERN.test(name)", body)
        self.assertIn("EMAIL_PATTERN.test(email)", body)
        self.assertIn("WHATSAPP_PATTERN.test(whatsapp)", body)
        self.assertIn("PROFILES[code]", body)
        self.assertIn("VALID_GENDERS.indexOf(gender)", body)

    def test_sigla_is_always_recomputed_server_side(self):
        body = extract_function_body(CODE_GS_TEXT, "validateInput")
        # A sigla nunca deve vir direto do cliente sem ser recalculada.
        self.assertRegex(body, r'sigla\s*=\s*code\s*\+\s*"-"\s*\+\s*gender')


class TestAntiAbuse(unittest.TestCase):
    """Honeypot, token de configuração (filtro casual) e limites de taxa."""

    def test_honeypot_field_in_form(self):
        self.assertIn('id="leadWebsite"', INDEX_TEXT)
        self.assertIn('tabindex="-1"', INDEX_TEXT)
        self.assertIn('name="website"', INDEX_TEXT)

    def test_honeypot_checked_before_network_call(self):
        submit_body = extract_function_body(INDEX_TEXT, "submitLead")
        honeypot_pos = submit_body.find("leadWebsite")
        fetch_pos = submit_body.find("fetch(WEBHOOK_URL")
        self.assertNotEqual(honeypot_pos, -1)
        self.assertNotEqual(fetch_pos, -1)
        self.assertLess(honeypot_pos, fetch_pos, "honeypot deve ser checado antes do fetch")

    def test_backend_honeypot_short_circuits_without_processing(self):
        do_post_body = extract_function_body(CODE_GS_TEXT, "doPost")
        honeypot_pos = do_post_body.find("data.website")
        append_pos = do_post_body.find("appendLead(")
        self.assertNotEqual(honeypot_pos, -1)
        self.assertLess(honeypot_pos, append_pos, "honeypot deve curto-circuitar antes de gravar o lead")

    def test_config_token_is_not_a_real_secret_by_default(self):
        # O token por padrão é vazio (modo aberto) nos dois lados.
        self.assertRegex(CODE_GS_TEXT, r'const ACCESS_TOKEN = "";')
        self.assertRegex(CONFIG_EXAMPLE.read_text(encoding="utf-8"), r'CONFIG_TOKEN:\s*""')

    def test_backend_validates_token_only_when_configured(self):
        do_post_body = extract_function_body(CODE_GS_TEXT, "doPost")
        self.assertIn("if (ACCESS_TOKEN) {", do_post_body)
        self.assertIn("token !== ACCESS_TOKEN", do_post_body)

    def test_rate_limit_constants_and_function_exist(self):
        self.assertIn("RATE_LIMIT_PER_EMAIL_PER_DAY", CODE_GS_TEXT)
        self.assertIn("RATE_LIMIT_GLOBAL_PER_MINUTE", CODE_GS_TEXT)
        self.assertIn("function checkRateLimit(email)", CODE_GS_TEXT)

    def test_rate_limit_uses_lock_to_avoid_race_conditions(self):
        body = extract_function_body(CODE_GS_TEXT, "checkRateLimit")
        self.assertIn("LockService.getScriptLock()", body)
        self.assertIn("PropertiesService.getScriptProperties()", body)

    def test_rate_limit_is_enforced_in_doPost(self):
        do_post_body = extract_function_body(CODE_GS_TEXT, "doPost")
        self.assertIn("checkRateLimit(validated.email)", do_post_body)

    def test_max_payload_size_is_enforced(self):
        do_post_body = extract_function_body(CODE_GS_TEXT, "doPost")
        self.assertIn("MAX_PAYLOAD_BYTES", do_post_body)

    def test_errors_never_leak_internal_details_to_client(self):
        do_post_body = extract_function_body(CODE_GS_TEXT, "doPost")
        # Erros internos vão só para o log do servidor, nunca na resposta ao cliente.
        self.assertIn("Logger.log(", do_post_body)
        self.assertNotIn("error: String(err)", do_post_body)


class TestWebhookResponseValidation(unittest.TestCase):
    """O front-end deve validar a resposta do webhook, sem bloquear a UX
    nem alterar o algoritmo de cálculo do tipo (computeType)."""

    def test_response_ok_is_checked(self):
        submit_body = extract_function_body(INDEX_TEXT, "submitLead")
        self.assertIn("response.ok", submit_body)

    def test_response_json_is_parsed_and_validated(self):
        submit_body = extract_function_body(INDEX_TEXT, "submitLead")
        self.assertIn("response.json()", submit_body)
        self.assertIn("data.ok !== true", submit_body)

    def test_result_is_always_shown_regardless_of_webhook_outcome(self):
        submit_body = extract_function_body(INDEX_TEXT, "submitLead")
        self.assertIn(".finally(()=> showResult(code, gender))", submit_body)

    def test_scoring_algorithm_untouched(self):
        # Regressão: o algoritmo de decisão por maioria simples deve
        # continuar exatamente este, para qualquer mudança de infraestrutura
        # em volta não alterar como o tipo é calculado.
        compute_type_body = extract_function_body(INDEX_TEXT, "computeType")
        self.assertIn("scores.E >= scores.I ? 'E' : 'I'", compute_type_body)
        self.assertIn("scores.S >= scores.N ? 'S' : 'N'", compute_type_body)
        self.assertIn("scores.T >= scores.F ? 'T' : 'F'", compute_type_body)
        self.assertIn("scores.J >= scores.P ? 'J' : 'P'", compute_type_body)


class TestConfiguration(unittest.TestCase):
    """config.example.js / .gitignore e não versionamento de config.js."""

    def test_config_example_exists_and_has_no_real_values(self):
        self.assertTrue(CONFIG_EXAMPLE.exists())
        text = CONFIG_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("window.SUPLENO_CONFIG", text)
        self.assertIn("WEBHOOK_URL:", text)
        self.assertIn("CONFIG_TOKEN:", text)
        self.assertRegex(text, r'WEBHOOK_URL:\s*""')
        self.assertNotIn("script.google.com/macros/s/", text)

    def test_gitignore_excludes_config_js(self):
        self.assertTrue(GITIGNORE.exists())
        lines = [l.strip() for l in GITIGNORE.read_text(encoding="utf-8").splitlines()]
        self.assertIn("config.js", lines)

    def test_config_js_is_not_tracked_by_git(self):
        tracked = git_ls_files()
        self.assertNotIn("config.js", tracked)

    def test_index_loads_config_js_with_graceful_fallback(self):
        self.assertIn('<script src="config.js"', INDEX_TEXT)
        self.assertIn("onerror=", INDEX_TEXT.split('<script src="config.js"')[1][:400])
        self.assertIn("window.SUPLENO_CONFIG || {}", INDEX_TEXT)

    def test_index_has_no_hardcoded_webhook_url(self):
        # O único WEBHOOK_URL literal em index.html deve ser a string vazia
        # de fallback; a URL real vive em config.js (fora do git).
        self.assertRegex(INDEX_TEXT, r'const WEBHOOK_URL = SUPLENO_CONFIG\.WEBHOOK_URL \|\| "";')


class TestNoSecrets(unittest.TestCase):
    """Varredura de segredos em todo o conteúdo versionado."""

    SECRET_PATTERNS = [
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
        (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "chave privada"),
        (re.compile(r"script\.google\.com/macros/s/[A-Za-z0-9_-]{20,}"), "URL de deploy real do Apps Script"),
        (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "Google API key"),
        (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "Slack token"),
        (re.compile(r"ghp_[0-9A-Za-z]{36}"), "GitHub token"),
    ]

    def test_no_known_secret_patterns_in_tracked_files(self):
        offenders = []
        for relpath in git_ls_files():
            path = ROOT / relpath
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            for pattern, label in self.SECRET_PATTERNS:
                if pattern.search(text):
                    offenders.append(f"{relpath}: {label}")
        self.assertEqual(offenders, [], f"possíveis segredos encontrados: {offenders}")

    def test_access_token_defaults_empty_in_tracked_code_gs(self):
        self.assertIn('const ACCESS_TOKEN = "";', CODE_GS_TEXT)

    def test_no_committed_config_js_with_secrets(self):
        self.assertNotIn("config.js", git_ls_files())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def extract_function_body(text: str, function_name: str) -> str:
    """Extrai o corpo de `function <function_name>(...) { ... }` por
    contagem de chaves (robusto a chaves aninhadas e strings)."""
    marker_pattern = re.compile(r"function\s+" + re.escape(function_name) + r"\s*\([^)]*\)\s*\{")
    match = marker_pattern.search(text)
    if not match:
        raise AssertionError(f"função {function_name} não encontrada")
    start = match.end() - 1  # posição do '{' de abertura
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in "\"'`":
            in_string = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"corpo da função {function_name} não fechado corretamente")


def extract_regex_literal(text: str, const_name: str) -> str:
    match = re.search(r"const\s+" + re.escape(const_name) + r"\s*=\s*(/(?:\\.|[^/\n])+/[a-z]*);", text)
    if not match:
        raise AssertionError(f"constante {const_name} não encontrada")
    return match.group(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
