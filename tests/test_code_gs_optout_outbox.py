#!/usr/bin/env python3
"""Testes de regressão determinísticos para os achados da auditoria final de
segurança do backend de produção (apps-script/Code.gs):

1. Opt-out de produção: doGet só confirma (nunca altera estado); a supressão
   só ocorre via POST explícito; token HMAC assinado e opaco (sem e-mail na
   URL); identidade resolvida mesmo sem lead local; opt-out persistido
   bloqueia recadastro e qualquer envio posterior.
2. Outbox persistente (pending/sending/sent/uncertain) com lease e
   reconciliação honesta: sem chave de idempotência aceita pelo provedor
   (MailApp), uma falha ou lease expirada nunca reabre para "pending"
   automaticamente — vira "uncertain" e exige reconciliação manual.
3. Idempotência "processing" sem lease/expiração ficava órfã para sempre;
   agora tem lease e retoma exatamente de onde parou (sem duplicar
   appendLead/outbox nem perder o lead silenciosamente).
4. LockService continua cobrindo as transições atômicas.

Roda com: python3 -m unittest tests/test_code_gs_optout_outbox.py -v
Não usa pytest nem dependências externas — só stdlib + um subprocesso Node
para executar o próprio Code.gs (sem modificá-lo) com stubs determinísticos
das APIs do Apps Script (PropertiesService, LockService, MailApp, etc.).
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_GS = ROOT / "apps-script" / "Code.gs"
CODE_GS_TEXT = CODE_GS.read_text(encoding="utf-8")

DEFAULT_ACCESS_TOKEN = "test-access-token"
DEFAULT_OPTOUT_SECRET = "test-optout-secret"

# Única fonte de verdade (do lado do teste) para as colunas da aba "Outbox" —
# tem que ficar em sincronia com OUTBOX_HEADERS em apps-script/Code.gs. Um
# teste dedicado (test_outbox_headers_match_expected_contract) trava isso.
OUTBOX_HEADERS = [
    "submission_id", "fingerprint", "state", "lease_until", "attempts",
    "email", "name", "code", "gender", "teste", "resultado", "pontuacoes", "attribution",
    "enqueued_at", "sent_at", "reconciled_at",
]

# Estas são as únicas famílias de chave que devem sobrar em Script Properties
# depois de qualquer fluxo de submissão/outbox. Nenhuma delas carrega o
# payload da fila (nome, e-mail, código, resultado, pontuações) — ver
# test_outbox_payload_never_touches_script_properties.
ALLOWED_STORE_KEY_PREFIXES = (
    "ACCESS_TOKEN", "OPTOUT_SECRET", "OUTBOX_CURSOR_ROW",
    "submission_", "optout_", "rl_",
)

# Stubs determinísticos das APIs do Google Apps Script usadas por Code.gs.
# Criptografia (HMAC/SHA-256/base64url) é real (via módulo `crypto` do Node),
# não simulada — para que os testes de token realmente validem a assinatura.
# O modelo de planilha (SpreadsheetApp/Sheet/Range/TextFinder) é fiel ao
# comportamento real do Apps Script o suficiente para exercitar getRange,
# setValues e busca por TextFinder tal como Code.gs realmente os usa —
# nenhum desses testes reimplementa a lógica de outbox em paralelo.
_PRELUDE = r"""
const crypto = require('crypto');
function toBuffer(x) {
  if (typeof x === 'string') return Buffer.from(x, 'utf-8');
  if (Buffer.isBuffer(x)) return x;
  return Buffer.from(Array.from(x).map(function (b) { return b < 0 ? b + 256 : b; }));
}
function toSignedBytes(buf) {
  return Array.from(buf).map(function (b) { return b > 127 ? b - 256 : b; });
}
global.Utilities = {
  DigestAlgorithm: { SHA_256: 'SHA_256' },
  computeDigest: function (algo, value) {
    return toSignedBytes(crypto.createHash('sha256').update(toBuffer(value)).digest());
  },
  computeHmacSha256Signature: function (data, key) {
    return toSignedBytes(crypto.createHmac('sha256', toBuffer(key)).update(toBuffer(data)).digest());
  },
  base64EncodeWebSafe: function (value) {
    return toBuffer(value).toString('base64').replace(/\+/g, '-').replace(/\//g, '_');
  },
  base64DecodeWebSafe: function (str) {
    var s = String(str).replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    return toSignedBytes(Buffer.from(s, 'base64'));
  },
  newBlob: function (input) {
    var buf = toBuffer(input);
    return {
      getBytes: function () { return toSignedBytes(buf); },
      getDataAsString: function () { return buf.toString('utf-8'); },
    };
  },
};
__STORE_DECL__
global.PropertiesService = {
  getScriptProperties: function () {
    return {
      getProperty: function (k) { return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
      setProperty: function (k, v) { __store[k] = v; },
      getProperties: function () { return Object.assign({}, __store); },
      deleteProperty: function (k) { delete __store[k]; },
    };
  },
};
global.__lockCalls = 0;
global.resetLockCalls = function () { global.__lockCalls = 0; };
global.LockService = {
  getScriptLock: function () {
    return {
      tryLock: function () { global.__lockCalls++; return true; },
      releaseLock: function () {},
    };
  },
};

// --- Modelo de planilha (Sheet/Range/TextFinder) ---------------------------
// Várias abas nomeadas (Leads MBTI, Outbox), cada uma com sua matriz de
// linhas. getRange é 1-indexado como no Sheets real (linha 1 = cabeçalho).
var __sheets = {};

function __cellToText(value) {
  return value === undefined || value === null ? "" : String(value);
}

function __textFinderScan(rows, bounds, text, opts) {
  var matches = [];
  var needle = opts.matchCase ? String(text) : String(text).toLowerCase();
  for (var r = 0; r < bounds.numRows; r++) {
    var sourceRow = rows[bounds.startRow + r] || [];
    for (var c = 0; c < bounds.numCols; c++) {
      var raw = sourceRow[bounds.startCol + c];
      if (raw === undefined) continue;
      var cell = __cellToText(raw);
      if (!opts.matchCase) cell = cell.toLowerCase();
      var isMatch = opts.matchEntireCell ? cell === needle : cell.indexOf(needle) !== -1;
      if (!isMatch) continue;
      (function (absoluteRow, absoluteCol) {
        matches.push({ getRow: function () { return absoluteRow; }, getColumn: function () { return absoluteCol; } });
      })(bounds.startRow + r + 1, bounds.startCol + c + 1);
    }
  }
  return matches;
}

function __makeTextFinder(rows, bounds, text) {
  var opts = { matchEntireCell: false, matchCase: true };
  var api = {
    matchEntireCell: function (v) { opts.matchEntireCell = v; return api; },
    matchCase: function (v) { opts.matchCase = v; return api; },
    findAll: function () { return __textFinderScan(rows, bounds, text, opts); },
    findNext: function () {
      var all = __textFinderScan(rows, bounds, text, opts);
      return all.length ? all[0] : null;
    },
  };
  return api;
}

function __makeSheet() {
  var rows = [];
  function ensureRow(idx) { while (rows.length <= idx) rows.push([]); }
  var sheet = {
    rows: rows,
    getLastRow: function () { return rows.length; },
    getLastColumn: function () {
      return rows.reduce(function (max, row) { return Math.max(max, row.length); }, 0);
    },
    appendRow: function (row) { rows.push(row.slice()); },
    getRange: function (row, col, numRows, numCols) {
      numRows = numRows || 1;
      numCols = numCols || 1;
      var startRow = row - 1;
      var startCol = col - 1;
      return {
        getRow: function () { return row; },
        getColumn: function () { return col; },
        getValues: function () {
          var out = [];
          for (var r = 0; r < numRows; r++) {
            var sourceRow = rows[startRow + r] || [];
            var line = [];
            for (var c = 0; c < numCols; c++) {
              line.push(sourceRow[startCol + c] !== undefined ? sourceRow[startCol + c] : "");
            }
            out.push(line);
          }
          return out;
        },
        setValues: function (values) {
          for (var r = 0; r < numRows; r++) {
            ensureRow(startRow + r);
            var targetRow = rows[startRow + r];
            for (var c = 0; c < numCols; c++) {
              targetRow[startCol + c] = values[r][c];
            }
          }
        },
        getValue: function () { return this.getValues()[0][0]; },
        setValue: function (value) { this.setValues([[value]]); },
        createTextFinder: function (text) {
          return __makeTextFinder(rows, { startRow: startRow, startCol: startCol, numRows: numRows, numCols: numCols }, text);
        },
      };
    },
    createTextFinder: function (text) {
      var numRows = rows.length;
      var numCols = sheet.getLastColumn();
      return __makeTextFinder(rows, { startRow: 0, startCol: 0, numRows: numRows, numCols: numCols }, text);
    },
  };
  return sheet;
}

global.SpreadsheetApp = {
  getActiveSpreadsheet: function () {
    return {
      getSheetByName: function (name) { return Object.prototype.hasOwnProperty.call(__sheets, name) ? __sheets[name] : null; },
      insertSheet: function (name) { var s = __makeSheet(); __sheets[name] = s; return s; },
    };
  },
  openById: function () { return global.SpreadsheetApp.getActiveSpreadsheet(); },
  flush: function () {},
};
var __sentEmails = [];
__MAIL_THROW_DECL__
global.MailApp = {
  sendEmail: function (opts) {
    if (global.__mailShouldThrow) { throw new Error('MailApp falha simulada'); }
    __sentEmails.push(opts);
  },
};
global.Logger = { log: function () {} };
global.ContentService = {
  MimeType: { JSON: 'JSON' },
  createTextOutput: function (text) {
    return { setMimeType: function () { return { getContent: function () { return text; } }; } };
  },
};
global.HtmlService = {
  createHtmlOutput: function (html) {
    return {
      setTitle: function () { return { getContent: function () { return html; } }; },
      getContent: function () { return html; },
    };
  },
};
global.ScriptApp = {
  getService: function () {
    return { getUrl: function () { return 'https://script.google.com/macros/s/FAKE_DEPLOY/exec'; } };
  },
};
global.Session = { getActiveUser: function () { return { getEmail: function () { return 'operador@example.com'; } }; } };
function dumpState(extra) {
  var out = {
    store: __store,
    sentEmails: __sentEmails,
    sheetRows: (__sheets['Leads MBTI'] ? __sheets['Leads MBTI'].rows : []),
    leadRows: (__sheets['Leads MBTI'] ? __sheets['Leads MBTI'].rows : []),
    outboxRows: (__sheets['Outbox'] ? __sheets['Outbox'].rows : []),
    lockCalls: global.__lockCalls,
  };
  if (extra) { for (var k in extra) { out[k] = extra[k]; } }
  console.log(JSON.stringify(out));
}
"""


def run_node(probe_js: str, store: dict | None = None, mail_should_throw: bool = False) -> list:
    """Executa Code.gs (sem modificá-lo) num processo Node com stubs
    determinísticos das APIs do Apps Script, seguido do `probe_js`. Cada
    chamada a `dumpState(...)` no probe vira um dict na lista retornada."""
    store = dict(store or {})
    store.setdefault("ACCESS_TOKEN", DEFAULT_ACCESS_TOKEN)
    store.setdefault("OPTOUT_SECRET", DEFAULT_OPTOUT_SECRET)
    prelude = _PRELUDE.replace("__STORE_DECL__", "const __store = " + json.dumps(store) + ";")
    prelude = prelude.replace(
        "__MAIL_THROW_DECL__", "global.__mailShouldThrow = " + ("true" if mail_should_throw else "false") + ";"
    )
    script = prelude + "\n" + CODE_GS_TEXT + "\n" + probe_js
    completed = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        raise AssertionError(f"node falhou:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"nenhuma saída JSON do node; stderr:\n{completed.stderr}")
    return [json.loads(line) for line in lines]


def lead_payload(submission_id: str = "sub-1", email: str = "lead@example.com", name: str = "Pessoa Teste") -> dict:
    return {
        "name": name,
        "email": email,
        "whatsapp": "",
        "code": "INTJ",
        "gender": "F",
        "teste": "tipos",
        "resultado": {"code": "INTJ", "gender": "F"},
        "pontuacoes": {"E": 2, "I": 5, "S": 3, "N": 4, "T": 4, "F": 3, "J": 5, "P": 2},
        "attribution": {"utm_source": "teste", "origin": "local"},
        "consentimento": True,
        "submission_id": submission_id,
        "website": "",
        "token": DEFAULT_ACCESS_TOKEN,
    }


def outbox_entries(result: dict) -> list[dict]:
    """Converte `result["outboxRows"]` (cabeçalho + linhas de dados, tal como
    lido diretamente da aba "Outbox" pelo stub de Sheets) em uma lista de
    dicts por linha — nunca lê de Script Properties. Falha alto se o
    cabeçalho divergir de OUTBOX_HEADERS, para nunca mascarar uma mudança
    silenciosa no contrato de colunas."""
    rows = result["outboxRows"]
    if not rows:
        return []
    header, data_rows = rows[0], rows[1:]
    assert header == OUTBOX_HEADERS, f"cabeçalho da aba Outbox inesperado: {header}"
    entries = []
    for row in data_rows:
        entry = dict(zip(header, row))
        entry["attempts"] = int(entry["attempts"]) if entry["attempts"] not in ("", None) else 0
        for key in ("resultado", "pontuacoes", "attribution"):
            entry[key] = json.loads(entry[key]) if entry[key] else None
        for key in ("lease_until", "sent_at", "reconciled_at"):
            entry[key] = entry[key] if entry[key] else None
        entries.append(entry)
    return entries


def optout_confirm_post_js(token_js_expr: str) -> str:
    """Monta a chamada JS de doPost simulando o POST real que o formulário
    HTML de optoutConfirmPage envia: form-urlencoded no corpo bruto — nunca
    e.parameter/query (achado 7). `token_js_expr` é uma expressão JS que
    resolve para o token (para poder referenciar variáveis do probe)."""
    return (
        "doPost({ postData: { type: 'application/x-www-form-urlencoded', "
        "contents: 'action=optout_confirm&token=' + encodeURIComponent(" + token_js_expr + ") } })"
    )


def extract_function_body(text: str, function_name: str) -> str:
    marker_pattern = re.compile(r"function\s+" + re.escape(function_name) + r"\s*\([^)]*\)\s*\{")
    match = marker_pattern.search(text)
    if not match:
        raise AssertionError(f"função {function_name} não encontrada")
    start = match.end() - 1
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


class TestOptOutTokenCryptography(unittest.TestCase):
    """Token HMAC assinado e opaco — achado 1."""

    def test_token_round_trips_and_is_opaque(self):
        [result] = run_node(
            """
            const token = gerarOptoutToken('User@Example.com');
            dumpState({ token: token, resolved: resolverEmailPorToken(token) });
            """
        )
        self.assertEqual(result["resolved"], "user@example.com")
        # Opaco: um identificador de 128 bits (HMAC truncado), sem estrutura
        # decodificável — não é base64 nem qualquer outra codificação do
        # e-mail, então não faz sentido exigir um separador específico.
        self.assertRegex(result["token"], r"^[0-9a-f]{32}$")
        self.assertNotIn("@", result["token"], "o e-mail em claro nunca deve aparecer no token")
        self.assertNotIn("example.com", result["token"])
        self.assertNotIn("User", result["token"])

    def test_tampering_the_nonce_is_rejected(self):
        [result] = run_node(
            """
            const token = gerarOptoutToken('victim@example.com');
            const flippedChar = token[0] === '0' ? '1' : '0';
            const tampered = flippedChar + token.slice(1);
            dumpState({ resolved: resolverEmailPorToken(tampered), original: token, tampered: tampered });
            """
        )
        self.assertIsNone(result["resolved"])
        self.assertNotEqual(result["tampered"], result["original"])

    def test_tampering_the_stored_mapping_email_breaks_integrity_check(self):
        # Defesa em profundidade: mesmo que o registro nonce->e-mail guardado
        # em PropertiesService seja adulterado por qualquer outra via (bug,
        # outro script no mesmo projeto), resolverEmailPorToken recalcula o
        # nonce esperado a partir do e-mail guardado e rejeita se divergir.
        [result] = run_node(
            """
            const token = gerarOptoutToken('original@example.com');
            const key = 'optout_token_' + token;
            const record = JSON.parse(__store[key]);
            record.email = 'attacker@example.com';
            __store[key] = JSON.stringify(record);
            dumpState({ resolved: resolverEmailPorToken(token) });
            """
        )
        self.assertIsNone(result["resolved"])

    def test_same_email_always_derives_the_same_nonce(self):
        # Determinístico por e-mail: evita acumular uma entrada nova em
        # PropertiesService a cada envio para o mesmo destinatário.
        [result] = run_node(
            """
            const first = gerarOptoutToken('repeat@example.com');
            const second = gerarOptoutToken('REPEAT@Example.com');
            dumpState({
              first: first,
              second: second,
              storeKeyCount: Object.keys(__store).filter(function (k) { return k.indexOf('optout_token_') === 0; }).length,
            });
            """
        )
        self.assertEqual(result["first"], result["second"])
        self.assertEqual(result["storeKeyCount"], 1)

    def test_different_emails_derive_different_nonces(self):
        [result] = run_node(
            """
            dumpState({
              a: gerarOptoutToken('one@example.com'),
              b: gerarOptoutToken('two@example.com'),
            });
            """
        )
        self.assertNotEqual(result["a"], result["b"])

    def test_expired_token_is_rejected(self):
        [result] = run_node(
            """
            const token = gerarOptoutToken('expiring@example.com');
            const key = 'optout_token_' + token;
            const record = JSON.parse(__store[key]);
            record.expires_at = new Date(Date.now() - 1000).toISOString();
            __store[key] = JSON.stringify(record);
            dumpState({ resolved: resolverEmailPorToken(token) });
            """
        )
        self.assertIsNone(result["resolved"])

    def test_malformed_token_returns_null_without_throwing(self):
        [result] = run_node(
            """
            dumpState({
              a: resolverEmailPorToken(''),
              b: resolverEmailPorToken(null),
              c: resolverEmailPorToken('sem-ponto'),
              d: resolverEmailPorToken('....'),
              e: resolverEmailPorToken('not-base64!!.deadbeef'),
            });
            """
        )
        for key in ("a", "b", "c", "d", "e"):
            self.assertIsNone(result[key], key)

    def test_fails_closed_without_optout_secret_configured(self):
        [result] = run_node(
            """
            let threw = false;
            try { gerarOptoutToken('a@example.com'); } catch (err) { threw = true; }
            dumpState({ resolved: resolverEmailPorToken('0'.repeat(32)), threwOnGenerate: threw });
            """,
            store={"OPTOUT_SECRET": ""},
        )
        self.assertIsNone(result["resolved"])
        self.assertTrue(result["threwOnGenerate"])

    def test_resolver_identity_works_without_any_local_lead(self):
        # "resolver identidade mesmo antes de lead local": a store começa
        # totalmente vazia (nenhum lead, nenhum outbox, nenhum opt-out) e o
        # token ainda assim resolve, pois a identidade vem só do próprio token.
        [result] = run_node(
            """
            const token = gerarOptoutToken('nunca-cadastrado@example.com');
            dumpState({ resolved: resolverEmailPorToken(token), storeKeysBefore: Object.keys(__store).length });
            """,
            store={},
        )
        self.assertEqual(result["resolved"], "nunca-cadastrado@example.com")

    def test_resolver_does_not_touch_spreadsheet_or_sheet(self):
        body = extract_function_body(CODE_GS_TEXT, "resolverEmailPorToken")
        self.assertNotIn("SpreadsheetApp", body)
        self.assertNotIn("getSheet(", body)


class TestOptOutGetNeverMutates(unittest.TestCase):
    """doGet só mostra confirmação — nunca altera estado (achado 1)."""

    def test_valid_token_shows_confirmation_without_registering_optout(self):
        [result] = run_node(
            """
            const token = gerarOptoutToken('lead@example.com');
            const response = doGet({ parameter: { action: 'optout', token: token } });
            dumpState({
              content: response.getContent(),
              isOptOut: estaOptOut('lead@example.com'),
            });
            """
        )
        self.assertIn("Confirmar cancelamento", result["content"])
        self.assertIn('method="POST"', result["content"])
        self.assertFalse(result["isOptOut"])
        self.assertEqual(result["sentEmails"], [])

    def test_invalid_token_returns_generic_page_without_mutating(self):
        [result] = run_node(
            """
            const response = doGet({ parameter: { action: 'optout', token: 'lixo.invalido' } });
            dumpState({ content: response.getContent() });
            """
        )
        self.assertIn("inválido", result["content"])
        self.assertEqual(result["store"], {"ACCESS_TOKEN": DEFAULT_ACCESS_TOKEN, "OPTOUT_SECRET": DEFAULT_OPTOUT_SECRET})

    def test_unknown_action_returns_not_found(self):
        [result] = run_node(
            """
            const response = doGet({ parameter: {} });
            dumpState({ content: response.getContent() });
            """
        )
        self.assertIn("não encontrada", result["content"])

    def test_doGet_and_show_handler_never_call_registrarOptOut(self):
        combined = extract_function_body(CODE_GS_TEXT, "doGet") + extract_function_body(CODE_GS_TEXT, "handleOptOutShow")
        self.assertNotIn("registrarOptOut(", combined)
        self.assertNotIn("setProperty(", combined)


class TestOptOutPostConfirmation(unittest.TestCase):
    """A supressão só ocorre via POST/ação explícita (achado 1)."""

    def test_post_confirm_with_valid_token_registers_optout(self):
        [result] = run_node(
            f"""
            const token = gerarOptoutToken('lead2@example.com');
            const response = {optout_confirm_post_js("token")};
            dumpState({{ content: response.getContent(), isOptOut: estaOptOut('lead2@example.com') }});
            """
        )
        self.assertTrue(result["isOptOut"])
        self.assertIn("cancelado", result["content"])

    def test_post_confirm_with_tampered_token_does_not_register(self):
        [result] = run_node(
            f"""
            const token = gerarOptoutToken('lead3@example.com');
            const tampered = (token[0] === '0' ? '1' : '0') + token.slice(1);
            const response = {optout_confirm_post_js("tampered")};
            dumpState({{ content: response.getContent(), isOptOut: estaOptOut('lead3@example.com') }});
            """
        )
        self.assertFalse(result["isOptOut"])
        self.assertIn("inválido", result["content"])

    def test_post_confirm_ignores_query_string_and_requires_real_body(self):
        # Achado 7: action/token vêm exclusivamente do corpo bruto. Uma
        # requisição sem corpo (mesmo com query string tentando simular
        # optout_confirm) precisa falhar, nunca mutar estado.
        [result] = run_node(
            """
            const token = gerarOptoutToken('querystring-attack@example.com');
            const response = doPost({ parameter: { action: 'optout_confirm', token: token } });
            dumpState({ content: response.getContent(), isOptOut: estaOptOut('querystring-attack@example.com') });
            """
        )
        self.assertFalse(result["isOptOut"])
        self.assertEqual(
            json.loads(result["content"]),
            {"ok": False, "error": "Não foi possível processar sua solicitação."},
        )

    def test_plain_json_lead_submission_is_not_confused_with_optout_confirm(self):
        [result] = run_node(
            "dumpState({ response: doPost({ postData: { contents: JSON.stringify(%s) } }).getContent(), outboxRows: __sheets['Outbox'] ? __sheets['Outbox'].rows : [] });"
            % json.dumps(lead_payload())
        )
        self.assertEqual(json.loads(result["response"]), {"ok": True})
        self.assertEqual(len(result["sheetRows"]), 2)  # cabeçalho + 1 lead
        self.assertEqual(json.loads(result["sheetRows"][1][8]), {"origin": "local", "utm_source": "teste"})
        entries = outbox_entries(result)
        self.assertEqual(entries[0]["attribution"], {"origin": "local", "utm_source": "teste"})

    def test_optout_url_never_carries_email_as_a_query_parameter(self):
        for fn_name in ("optoutConfirmPage", "optoutLinkHtml"):
            body = extract_function_body(CODE_GS_TEXT, fn_name)
            self.assertNotIn("email=", body)


class TestOptOutBlocksResignupAndSends(unittest.TestCase):
    """Opt-out persistido bloqueia recadastro e qualquer envio posterior (achado 1)."""

    def test_optout_cancels_pending_outbox_and_blocks_resignup_and_future_sends(self):
        results = run_node(
            """
            const email = 'blocked@example.com';
            const firstResponse = doPost({ postData: { contents: JSON.stringify(%(first)s) } });
            dumpState({ step: 'after-first-submit', firstResponse: firstResponse.getContent() });

            const token = gerarOptoutToken(email);
            const confirmResponse = %(confirm_post_js)s;
            dumpState({ step: 'after-optout', confirmResponse: confirmResponse.getContent(), isOptOut: estaOptOut(email) });

            const secondResponse = doPost({ postData: { contents: JSON.stringify(%(second)s) } });
            dumpState({ step: 'after-second-submit', secondResponse: secondResponse.getContent() });

            const outboxResult = processarOutbox();
            dumpState({ step: 'after-processarOutbox', outboxResult: outboxResult });
            """
            % {
                "first": json.dumps(lead_payload(submission_id="sub-blocked-1", email="blocked@example.com")),
                "second": json.dumps(lead_payload(submission_id="sub-blocked-2", email="blocked@example.com")),
                "confirm_post_js": optout_confirm_post_js("token"),
            }
        )
        after_first, after_optout, after_second, after_outbox = results

        self.assertEqual(json.loads(after_first["firstResponse"]), {"ok": True})
        self.assertEqual(len(after_first["sheetRows"]), 2)

        self.assertTrue(after_optout["isOptOut"])
        outbox_states_after_optout = [entry["state"] for entry in outbox_entries(after_optout)]
        self.assertEqual(outbox_states_after_optout, ["cancelled"])
        self.assertIsNotNone(outbox_entries(after_optout)[0]["reconciled_at"], "cancelamento deve marcar reconciled_at")

        # Recadastro do mesmo e-mail (novo submission_id) deve ser recusado,
        # sem novo lead na planilha e sem nova entrada na outbox.
        self.assertEqual(json.loads(after_second["secondResponse"]), {"ok": False, "error": "Não foi possível processar sua solicitação."})
        self.assertEqual(len(after_second["sheetRows"]), 2, "não deve ter sido adicionado um segundo lead")
        self.assertEqual(len(outbox_entries(after_second)), 1, "não deve ter sido criada uma nova entrada de outbox")

        # A outbox nunca deveria efetivamente enviar para o e-mail suprimido.
        self.assertEqual(after_outbox["sentEmails"], [])

    def test_cancelarOutboxPendentePorEmail_is_case_insensitive_and_ignores_other_states(self):
        # Além do fluxo completo de opt-out acima: confere diretamente que a
        # busca por e-mail na aba ignora maiúsculas/minúsculas e nunca toca
        # linhas que já não estão "pending" (sent/cancelled ficam como estão).
        results = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%(pending)s) } });
            doPost({ postData: { contents: JSON.stringify(%(already_sent)s) } });
            const sheet = getOutboxSheet();
            const alreadySent = findOutboxRowBySubmissionId(sheet, 'sub-mixed-sent');
            alreadySent.state = 'sent';
            alreadySent.sent_at = new Date().toISOString();
            writeOutboxRow(sheet, alreadySent);
            SpreadsheetApp.flush();
            dumpState({ step: 'before-cancel' });

            cancelarOutboxPendentePorEmail('MixedCase@Example.com');
            dumpState({ step: 'after-cancel' });
            """
            % {
                "pending": json.dumps(lead_payload(submission_id="sub-mixed-pending", email="MixedCase@Example.com")),
                "already_sent": json.dumps(lead_payload(submission_id="sub-mixed-sent", email="mixedcase@example.com")),
            }
        )
        before, after = results
        before_states = {e["submission_id"]: e["state"] for e in outbox_entries(before)}
        self.assertEqual(before_states["sub-mixed-pending"], "pending")
        self.assertEqual(before_states["sub-mixed-sent"], "sent")

        after_states = {e["submission_id"]: e["state"] for e in outbox_entries(after)}
        self.assertEqual(after_states["sub-mixed-pending"], "cancelled", "case-insensitive: deveria ter cancelado")
        self.assertEqual(after_states["sub-mixed-sent"], "sent", "linha já 'sent' não deve ser tocada")

    def test_cancelarOutboxPendentePorEmail_never_calls_getProperties(self):
        body = extract_function_body(CODE_GS_TEXT, "cancelarOutboxPendentePorEmail")
        self.assertNotIn("getProperties(", body)
        self.assertNotIn("PropertiesService", body)


class TestOutboxStateMachine(unittest.TestCase):
    """Estados pending/sending/sent/uncertain com lease e reconciliação honesta (achado 2)."""

    def test_submission_only_enqueues_pending_never_sends_synchronously(self):
        [result] = run_node(
            "dumpState({ response: doPost({ postData: { contents: JSON.stringify(%s) } }).getContent() });"
            % json.dumps(lead_payload(submission_id="sub-enqueue"))
        )
        self.assertEqual(result["sentEmails"], [])
        entries = outbox_entries(result)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["state"], "pending")
        self.assertEqual(entries[0]["submission_id"], "sub-enqueue")

    def test_processarOutbox_sends_pending_and_marks_sent(self):
        results = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            dumpState({ step: 'enqueued' });
            const outcome = processarOutbox();
            dumpState({ step: 'processed', outcome: outcome });
            """
            % json.dumps(lead_payload(submission_id="sub-send-ok", email="sendok@example.com"))
        )
        _, after = results
        self.assertEqual(after["outcome"]["processados"], 1)
        self.assertEqual(len(after["sentEmails"]), 1)
        self.assertEqual(after["sentEmails"][0]["to"], "sendok@example.com")
        entries = outbox_entries(after)
        self.assertEqual(entries[0]["state"], "sent")
        self.assertEqual(entries[0]["attempts"], 1)
        self.assertIsNotNone(entries[0]["sent_at"])

    def test_send_failure_marks_uncertain_and_never_retries_blindly(self):
        results = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            const first = processarOutbox();
            dumpState({ step: 'after-first-attempt', outcome: first });
            const second = processarOutbox();
            dumpState({ step: 'after-second-attempt', outcome: second });
            """
            % json.dumps(lead_payload(submission_id="sub-send-fail", email="sendfail@example.com")),
            mail_should_throw=True,
        )
        after_first, after_second = results
        self.assertEqual(after_first["sentEmails"], [])
        entries_after_first = outbox_entries(after_first)
        self.assertEqual(entries_after_first[0]["state"], "uncertain")
        self.assertEqual(entries_after_first[0]["attempts"], 1)

        # Uma segunda chamada a processarOutbox NÃO deve tentar reenviar um
        # item "uncertain" às cegas: continua incerto, sem nova tentativa.
        entries_after_second = outbox_entries(after_second)
        self.assertEqual(entries_after_second[0]["state"], "uncertain")
        self.assertEqual(entries_after_second[0]["attempts"], 1)
        self.assertEqual(after_second["outcome"]["processados"], 0)

    def test_stuck_sending_lease_expires_to_uncertain_not_pending(self):
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            const sheet = getOutboxSheet();
            const entry = findOutboxRowBySubmissionId(sheet, 'sub-stuck');
            entry.state = 'sending';
            entry.lease_until = new Date(Date.now() - 60 * 60 * 1000).toISOString();
            writeOutboxRow(sheet, entry);
            processarOutbox();
            const finalEntry = findOutboxRowBySubmissionId(sheet, 'sub-stuck');
            dumpState({ finalState: finalEntry.state });
            """
            % json.dumps(lead_payload(submission_id="sub-stuck", email="stuck@example.com"))
        )
        self.assertEqual(result["finalState"], "uncertain")
        self.assertEqual(result["sentEmails"], [], "uma lease expirada não deve disparar novo envio")

    def test_manual_reconciliation_confirm_marks_sent_without_resending(self):
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            processarOutbox();
            outboxMarcarComoEnviadoManualmente('sub-manual-confirm');
            const sheet = getOutboxSheet();
            const finalEntry = findOutboxRowBySubmissionId(sheet, 'sub-manual-confirm');
            dumpState({ finalState: finalEntry.state, reconciledAt: finalEntry.reconciled_at });
            """
            % json.dumps(lead_payload(submission_id="sub-manual-confirm", email="manualconfirm@example.com")),
            mail_should_throw=True,
        )
        self.assertEqual(result["finalState"], "sent")
        self.assertIsNotNone(result["reconciledAt"])
        self.assertEqual(result["sentEmails"], [])

    def test_manual_reopen_only_allowed_from_uncertain(self):
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            let threwOnPending = false;
            try { outboxMarcarComoPendenteManualmente('sub-manual-reopen'); } catch (err) { threwOnPending = true; }

            processarOutbox();
            outboxMarcarComoPendenteManualmente('sub-manual-reopen');
            const sheet = getOutboxSheet();
            const finalEntry = findOutboxRowBySubmissionId(sheet, 'sub-manual-reopen');
            dumpState({ threwOnPending: threwOnPending, finalState: finalEntry.state });
            """
            % json.dumps(lead_payload(submission_id="sub-manual-reopen", email="manualreopen@example.com")),
            mail_should_throw=True,
        )
        self.assertTrue(result["threwOnPending"], "reabrir a partir de 'pending' deve falhar")
        self.assertEqual(result["finalState"], "pending")

    def test_manual_confirm_rejects_transition_from_pending_or_sent(self):
        # Achado da fatia 2: outboxMarcarComoEnviadoManualmente(...) só pode
        # sair de "uncertain" — nunca confirma um item ainda "pending", nem
        # reaplica sobre um item já "sent".
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            let threwFromPending = false;
            try { outboxMarcarComoEnviadoManualmente('sub-confirm-guard'); } catch (err) { threwFromPending = true; }

            processarOutbox(); // envia com sucesso -> state 'sent'
            let threwFromSent = false;
            try { outboxMarcarComoEnviadoManualmente('sub-confirm-guard'); } catch (err) { threwFromSent = true; }

            const sheet = getOutboxSheet();
            const finalEntry = findOutboxRowBySubmissionId(sheet, 'sub-confirm-guard');
            dumpState({ threwFromPending: threwFromPending, threwFromSent: threwFromSent, finalState: finalEntry.state });
            """
            % json.dumps(lead_payload(submission_id="sub-confirm-guard", email="confirmguard@example.com"))
        )
        self.assertTrue(result["threwFromPending"], "confirmar a partir de 'pending' deve falhar")
        self.assertTrue(result["threwFromSent"], "confirmar de novo a partir de 'sent' deve falhar")
        self.assertEqual(result["finalState"], "sent")

    def test_manual_reconciliation_functions_acquire_script_lock(self):
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            processarOutbox();
            resetLockCalls();
            outboxMarcarComoEnviadoManualmente('sub-lock-confirm');
            const afterConfirm = global.__lockCalls;

            resetLockCalls();
            let threw = false;
            try { outboxMarcarComoPendenteManualmente('sub-does-not-exist'); } catch (err) { threw = true; }
            const afterReopenAttempt = global.__lockCalls;

            dumpState({ afterConfirm: afterConfirm, afterReopenAttempt: afterReopenAttempt, threw: threw });
            """
            % json.dumps(lead_payload(submission_id="sub-lock-confirm", email="lockconfirm@example.com")),
            mail_should_throw=True,
        )
        self.assertGreater(result["afterConfirm"], 0, "outboxMarcarComoEnviadoManualmente deve chamar tryLock")
        self.assertGreater(result["afterReopenAttempt"], 0, "outboxMarcarComoPendenteManualmente deve chamar tryLock mesmo ao falhar")
        self.assertTrue(result["threw"])

    def test_processarOutbox_blocked_without_optout_secret(self):
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            const outcome = processarOutbox();
            dumpState({ outcome: outcome });
            """
            % json.dumps(lead_payload(submission_id="sub-no-secret")),
            store={"OPTOUT_SECRET": ""},
        )
        self.assertTrue(result["outcome"]["bloqueado"])
        self.assertEqual(result["sentEmails"], [])
        entries = outbox_entries(result)
        self.assertEqual(entries[0]["state"], "pending", "não deve tentar enviar sem OPTOUT_SECRET configurado")

    def test_outbox_uses_lock_service(self):
        body = extract_function_body(CODE_GS_TEXT, "processarOutbox")
        self.assertIn("LockService.getScriptLock()", body)
        self.assertIn("lock.releaseLock()", body)

    def test_processarOutbox_processes_at_most_batch_size_rows_and_advances_cursor(self):
        # Prova o cursor/lote: 30 itens enfileirados, processarOutbox() só
        # processa OUTBOX_BATCH_SIZE (25) por chamada; uma segunda chamada
        # cobre o restante, provando que o cursor avança entre execuções.
        enqueue_calls = "\n".join(
            "enqueueOutbox('sub-batch-%d', { email: 'batch%d@example.com', name: 'P%d', code: 'INTJ', "
            "gender: 'F', teste: 'tipos', resultado: {code:'INTJ',gender:'F'}, "
            "pontuacoes: {E:2,I:5,S:3,N:4,T:4,F:3,J:5,P:2} }, 'fp-%d');" % (i, i, i, i)
            for i in range(30)
        )
        results = run_node(
            f"""
            {enqueue_calls}
            const first = processarOutbox();
            dumpState({{ step: 'first-batch', processados: first.processados, sentCount: __sentEmails.length }});
            const second = processarOutbox();
            dumpState({{ step: 'second-batch', processados: second.processados, sentCount: __sentEmails.length }});
            const third = processarOutbox();
            dumpState({{ step: 'third-batch', processados: third.processados, sentCount: __sentEmails.length }});
            """
        )
        first, second, third = results
        self.assertEqual(first["processados"], 25, "não deve processar mais que OUTBOX_BATCH_SIZE por chamada")
        self.assertEqual(first["sentCount"], 25)
        self.assertEqual(second["processados"], 5, "a segunda chamada deve cobrir o restante via cursor")
        self.assertEqual(second["sentCount"], 30)
        self.assertEqual(third["processados"], 0, "todos já enviados: nada resta para processar")

    def test_outbox_functions_never_call_getProperties(self):
        for fn_name in (
            "enqueueOutbox", "processarOutbox", "cancelarOutboxPendentePorEmail",
            "outboxMarcarComoEnviadoManualmente", "outboxMarcarComoPendenteManualmente",
            "getOutboxSheet", "findOutboxRowBySubmissionId",
        ):
            body = extract_function_body(CODE_GS_TEXT, fn_name)
            self.assertNotIn("getProperties(", body, f"{fn_name} não deveria usar getProperties()")

    def test_outbox_payload_never_touches_script_properties(self):
        # A intenção de envio inteira (nome/e-mail/código/resultado/pontuações)
        # deve morar só na aba — nunca em Script Properties, nem mesmo como
        # efeito colateral do cursor de processarOutbox.
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            processarOutbox();
            dumpState({});
            """
            % json.dumps(lead_payload(
                submission_id="sub-no-properties-leak",
                email="naovazapropriedades@example.com",
                name="Nome Sigiloso Do Lead",
            ))
        )
        store_json = json.dumps(result["store"])
        self.assertNotIn("Nome Sigiloso Do Lead", store_json)
        self.assertNotIn('"resultado"', store_json)
        self.assertNotIn('"pontuacoes"', store_json)
        self.assertFalse(
            any(key.startswith("outbox_") for key in result["store"]),
            "nenhum item ou payload da outbox pode morar em Script Properties",
        )
        for key in result["store"]:
            self.assertTrue(
                any(key.startswith(prefix) for prefix in ALLOWED_STORE_KEY_PREFIXES),
                f"chave inesperada em Script Properties: {key}",
            )

    def test_getOutboxSheet_creates_sheet_with_explicit_headers(self):
        [result] = run_node(
            """
            const sheet = getOutboxSheet();
            dumpState({ headerRow: sheet.rows[0], lastRow: sheet.getLastRow() });
            """
        )
        self.assertEqual(result["headerRow"], OUTBOX_HEADERS)
        self.assertEqual(result["lastRow"], 1)

    def test_getOutboxSheet_rejects_unexpected_header(self):
        [result] = run_node(
            """
            let threw = false;
            const ss = SpreadsheetApp.getActiveSpreadsheet();
            const sheet = ss.insertSheet('Outbox');
            sheet.appendRow(['coluna_errada']);
            try { getOutboxSheet(); } catch (err) { threw = true; }
            dumpState({ threw: threw });
            """
        )
        self.assertTrue(result["threw"], "cabeçalho inesperado na aba Outbox deveria falhar alto, não ser ignorado")

    def test_getOutboxSheet_rejects_extra_columns(self):
        [result] = run_node(
            """
            let threw = false;
            const ss = SpreadsheetApp.getActiveSpreadsheet();
            const sheet = ss.insertSheet('Outbox');
            sheet.appendRow(OUTBOX_HEADERS.concat(['EXTRA']));
            try { getOutboxSheet(); } catch (err) { threw = true; }
            dumpState({ threw: threw });
            """
        )
        self.assertTrue(result["threw"])

    def test_full_submission_with_invalid_outbox_never_appends_lead(self):
        payload = lead_payload(submission_id="sub-invalid-outbox")
        [result] = run_node(
            """
            const outbox = SpreadsheetApp.getActiveSpreadsheet().insertSheet('Outbox');
            outbox.appendRow(OUTBOX_HEADERS.concat(['EXTRA']));
            const response = doPost({
              postData: { type: 'application/json', contents: JSON.stringify(%s) }
            });
            dumpState({ response: JSON.parse(response.getContent()) });
            """ % json.dumps(payload)
        )
        self.assertFalse(result["response"]["ok"])
        self.assertEqual(result["leadRows"], [], "Outbox inválida não pode deixar lead parcial")

    def test_getSheet_rejects_legacy_header_instead_of_corrupting_rows(self):
        [result] = run_node(
            """
            let threw = false;
            const ss = SpreadsheetApp.getActiveSpreadsheet();
            const sheet = ss.insertSheet('Leads MBTI');
            sheet.appendRow(['Nome', 'E-mail', 'Sigla', 'WhatsApp', 'Data']);
            try { getSheet(); } catch (err) { threw = true; }
            dumpState({ threw: threw, rows: sheet.rows });
            """
        )
        self.assertTrue(result["threw"])
        self.assertEqual(len(result["rows"]), 1, "não pode gravar linha sob cabeçalho legado")

    def test_existing_lead_row_with_same_id_and_different_fingerprint_is_rejected(self):
        payload = lead_payload(submission_id="sub-row-fingerprint", email="original@example.com")
        [result] = run_node(
            """
            const payload = %s;
            const validated = validateInput(payload);
            const fingerprint = computeSubmissionFingerprint(validated);
            appendLeadIdempotente(validated.name, validated.email, validated.whatsapp, validated.sigla,
              validated.teste, validated.resultado, validated.pontuacoes,
              'sub-row-fingerprint', fingerprint);
            let threw = false;
            try {
              appendLeadIdempotente(validated.name, 'different@example.com', validated.whatsapp, validated.sigla,
                validated.teste, validated.resultado, validated.pontuacoes,
                'sub-row-fingerprint', 'fingerprint-divergente');
            } catch (err) { threw = true; }
            dumpState({ threw: threw });
            """ % json.dumps(payload)
        )
        self.assertTrue(result["threw"])
        self.assertEqual(len(result["sheetRows"]), 2)

    def test_sent_email_uses_data_read_back_from_the_outbox_sheet(self):
        # "Envio usa aba": prova que o conteúdo realmente enviado por MailApp
        # veio da leitura da linha da aba (não de alguma cópia em memória
        # paralela), fazendo uma leitura+escrita manual na aba entre o
        # enqueue e o processamento.
        [result] = run_node(
            """
            doPost({ postData: { contents: JSON.stringify(%s) } });
            const sheet = getOutboxSheet();
            const entry = findOutboxRowBySubmissionId(sheet, 'sub-reads-from-sheet');
            entry.name = 'Nome Trocado Na Aba';
            writeOutboxRow(sheet, entry);
            processarOutbox();
            dumpState({});
            """
            % json.dumps(lead_payload(submission_id="sub-reads-from-sheet", email="readsfromsheet@example.com", name="Nome Original"))
        )
        self.assertEqual(len(result["sentEmails"]), 1)
        self.assertIn("Nome Trocado Na Aba", result["sentEmails"][0]["htmlBody"])
        self.assertNotIn("Nome Original", result["sentEmails"][0]["htmlBody"])


class TestIdempotencyLeaseReconciliation(unittest.TestCase):
    """Idempotência 'processing' com lease/expiração e reconciliação (achado 3)."""

    @staticmethod
    def _idempotency_key_expr(submission_id_js: str) -> str:
        return (
            '"submission_" + Utilities.base64EncodeWebSafe('
            f"Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, {submission_id_js}))"
        )

    def test_duplicate_submission_id_does_not_duplicate_lead_or_outbox(self):
        payload = lead_payload(submission_id="sub-dup")
        [result] = run_node(
            """
            const r1 = doPost({ postData: { contents: JSON.stringify(%(payload)s) } });
            const r2 = doPost({ postData: { contents: JSON.stringify(%(payload)s) } });
            dumpState({ r1: r1.getContent(), r2: r2.getContent() });
            """
            % {"payload": json.dumps(payload)}
        )
        self.assertEqual(json.loads(result["r1"]), {"ok": True})
        self.assertEqual(json.loads(result["r2"]), {"ok": True, "duplicate": True})
        self.assertEqual(len(result["sheetRows"]), 2)
        self.assertEqual(len(outbox_entries(result)), 1)

    def test_valid_lease_rejects_concurrent_retry_without_touching_lead_or_outbox(self):
        payload = lead_payload(submission_id="sub-concurrent")
        key_expr = self._idempotency_key_expr("'sub-concurrent'")
        [result] = run_node(
            f"""
            const key = {key_expr};
            const state = {{
              status: 'processing',
              started_at: new Date().toISOString(),
              lease_until: new Date(Date.now() + 60 * 1000).toISOString(),
              lead_appended: false,
              outbox_enqueued: false,
            }};
            __store[key] = JSON.stringify(state);
            const response = doPost({{ postData: {{ contents: JSON.stringify(%s) }} }});
            dumpState({{ response: response.getContent() }});
            """
            % json.dumps(payload)
        )
        self.assertEqual(json.loads(result["response"]), {"ok": True, "duplicate": True, "processing": True})
        self.assertEqual(result["sheetRows"], [])
        self.assertEqual(outbox_entries(result), [])

    def test_expired_lease_with_no_progress_completes_exactly_once(self):
        payload = lead_payload(submission_id="sub-expired-fresh")
        key_expr = self._idempotency_key_expr("'sub-expired-fresh'")
        [result] = run_node(
            f"""
            const key = {key_expr};
            const state = {{
              status: 'processing',
              started_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
              lease_until: new Date(Date.now() - 60 * 1000).toISOString(),
              lead_appended: false,
              outbox_enqueued: false,
            }};
            __store[key] = JSON.stringify(state);
            const response = doPost({{ postData: {{ contents: JSON.stringify(%s) }} }});
            dumpState({{ response: response.getContent(), finalState: JSON.parse(__store[key]) }});
            """
            % json.dumps(payload)
        )
        self.assertEqual(json.loads(result["response"]), {"ok": True})
        self.assertEqual(len(result["sheetRows"]), 2, "o lead não pode se perder silenciosamente")
        self.assertEqual(len(outbox_entries(result)), 1, "a intenção de envio deve ser enfileirada exatamente uma vez")
        self.assertEqual(result["finalState"]["status"], "done")

    def test_expired_lease_resumes_without_duplicating_already_appended_lead(self):
        # Simula uma queda exatamente após appendLead, mas antes de enfileirar
        # a outbox: a retomada não deve chamar appendLead de novo (a planilha
        # nunca chega a ser tocada por este teste), só concluir o que faltou.
        payload = lead_payload(submission_id="sub-expired-partial")
        key_expr = self._idempotency_key_expr("'sub-expired-partial'")
        [result] = run_node(
            f"""
            const key = {key_expr};
            const state = {{
              status: 'processing',
              started_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
              lease_until: new Date(Date.now() - 60 * 1000).toISOString(),
              lead_appended: true,
              outbox_enqueued: false,
            }};
            __store[key] = JSON.stringify(state);
            const response = doPost({{ postData: {{ contents: JSON.stringify(%s) }} }});
            dumpState({{ response: response.getContent(), finalState: JSON.parse(__store[key]) }});
            """
            % json.dumps(payload)
        )
        self.assertEqual(json.loads(result["response"]), {"ok": True})
        self.assertEqual(len(result["sheetRows"]), 1, "o pré-voo pode criar somente o cabeçalho")
        self.assertEqual(result["sheetRows"][0], [
            "Data", "Nome", "E-mail", "Sigla", "WhatsApp", "Produto",
            "Resultado", "Pontuações", "Atribuição", "Submission ID", "Fingerprint",
        ])
        self.assertEqual(len(outbox_entries(result)), 1, "a etapa pendente (outbox) deve ser concluída")
        self.assertEqual(result["finalState"]["status"], "done")

    def test_optout_during_expired_lease_aborts_without_appending_or_enqueueing(self):
        payload = lead_payload(submission_id="sub-expired-optout", email="lateoptout@example.com")
        key_expr = self._idempotency_key_expr("'sub-expired-optout'")
        [result] = run_node(
            f"""
            const key = {key_expr};
            const state = {{
              status: 'processing',
              started_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
              lease_until: new Date(Date.now() - 60 * 1000).toISOString(),
              lead_appended: false,
              outbox_enqueued: false,
            }};
            __store[key] = JSON.stringify(state);
            registrarOptOut('lateoptout@example.com');
            const response = doPost({{ postData: {{ contents: JSON.stringify(%s) }} }});
            dumpState({{ response: response.getContent(), finalState: JSON.parse(__store[key]) }});
            """
            % json.dumps(payload)
        )
        self.assertEqual(json.loads(result["response"]), {"ok": False, "error": "Não foi possível processar sua solicitação."})
        self.assertEqual(result["sheetRows"], [])
        self.assertEqual(outbox_entries(result), [])
        self.assertEqual(result["finalState"]["status"], "done")
        self.assertTrue(result["finalState"]["aborted_opt_out"])

    def test_crash_after_physical_append_but_before_checkpoint_does_not_duplicate_row(self):
        # Simula a pior janela possível: appendLeadIdempotente já gravou a
        # linha física na planilha, mas o processo caiu antes de persistir
        # lead_appended=true (e antes de marcar status "done"). A lease
        # expira e uma nova requisição com o MESMO submission_id chega.
        # appendLeadIdempotente deve reconhecer a linha já gravada (pelo
        # Submission ID) e não duplicar; só a etapa pendente (outbox) deve
        # ser concluída.
        payload = lead_payload(submission_id="sub-crash-after-append", email="crashafterappend@example.com")
        key_expr = self._idempotency_key_expr("'sub-crash-after-append'")
        [before, after] = run_node(
            f"""
            const payload = %s;
            const validated = validateInput(payload);
            const fingerprint = computeSubmissionFingerprint(validated);
            const key = {key_expr};

            // Efeito físico já ocorrido antes da queda simulada.
            appendLeadIdempotente(validated.name, validated.email, validated.whatsapp, validated.sigla,
              validated.teste, validated.resultado, validated.pontuacoes, 'sub-crash-after-append', fingerprint);

            // Checkpoint NUNCA foi salvo: lead_appended ainda false, lease já expirada.
            const state = {{
              status: 'processing',
              started_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
              lease_until: new Date(Date.now() - 60 * 1000).toISOString(),
              lead_appended: false,
              outbox_enqueued: false,
              fingerprint: fingerprint,
            }};
            __store[key] = JSON.stringify(state);
            dumpState({{ step: 'after-simulated-crash' }});

            const response = doPost({{ postData: {{ contents: JSON.stringify(payload) }} }});
            dumpState({{ step: 'after-retry', response: response.getContent(), finalState: JSON.parse(__store[key]) }});
            """
            % json.dumps(payload)
        )
        self.assertEqual(len(before["sheetRows"]), 2, "o crash simulado grava exatamente uma linha física")

        self.assertEqual(json.loads(after["response"]), {"ok": True})
        self.assertEqual(len(after["sheetRows"]), 2, "a retomada não pode duplicar a linha já gravada")
        self.assertEqual(after["finalState"]["status"], "done")
        self.assertTrue(after["finalState"]["lead_appended"])
        self.assertEqual(len(outbox_entries(after)), 1, "a etapa pendente (outbox) ainda deve ser concluída na retomada")

    def test_reused_submission_id_with_different_payload_is_rejected_not_duplicate(self):
        # O mesmo submission_id reaproveitado para um e-mail/payload diferente
        # nunca é uma duplicata legítima. Deve ser recusado (ok=false), nunca
        # retornar duplicate=true, e nunca gravar um segundo lead/outbox.
        submission_id = "sub-fingerprint-mismatch"
        first_payload = lead_payload(submission_id=submission_id, email="original@example.com", name="Pessoa Original")
        second_payload = lead_payload(submission_id=submission_id, email="different@example.com", name="Pessoa Diferente")
        [after_first, after_second] = run_node(
            """
            const firstResponse = doPost({ postData: { contents: JSON.stringify(%(first)s) } });
            dumpState({ step: 'after-first', firstResponse: firstResponse.getContent() });

            const secondResponse = doPost({ postData: { contents: JSON.stringify(%(second)s) } });
            dumpState({ step: 'after-second', secondResponse: secondResponse.getContent() });
            """
            % {"first": json.dumps(first_payload), "second": json.dumps(second_payload)}
        )
        self.assertEqual(json.loads(after_first["firstResponse"]), {"ok": True})
        self.assertEqual(len(after_first["sheetRows"]), 2)

        self.assertEqual(
            json.loads(after_second["secondResponse"]),
            {"ok": False, "error": "Não foi possível processar sua solicitação."},
        )
        self.assertEqual(len(after_second["sheetRows"]), 2, "o payload divergente não pode gerar um segundo lead")
        self.assertEqual(len(outbox_entries(after_second)), 1, "o payload divergente não pode gerar uma segunda entrada de outbox")

    def test_same_submission_id_and_identical_payload_still_dedupes_as_duplicate(self):
        # Controle: o mesmo submission_id com o MESMO payload (mesmo
        # fingerprint) continua sendo tratado como duplicata normal, não como
        # reuso indevido — o fingerprint não deve ficar mais restritivo do
        # que a idempotência já testada em test_duplicate_submission_id_does_not_duplicate_lead_or_outbox.
        payload = lead_payload(submission_id="sub-fingerprint-match")
        [result] = run_node(
            """
            const r1 = doPost({ postData: { contents: JSON.stringify(%(payload)s) } });
            const r2 = doPost({ postData: { contents: JSON.stringify(%(payload)s) } });
            dumpState({ r1: r1.getContent(), r2: r2.getContent() });
            """
            % {"payload": json.dumps(payload)}
        )
        self.assertEqual(json.loads(result["r1"]), {"ok": True})
        self.assertEqual(json.loads(result["r2"]), {"ok": True, "duplicate": True})
        self.assertEqual(len(result["sheetRows"]), 2)


class TestValidationAndLockStillEnforced(unittest.TestCase):
    """Preservação das proteções existentes: validação dos três produtos e LockService."""

    def test_all_three_products_still_processed_under_lock(self):
        body = extract_function_body(CODE_GS_TEXT, "processSubmissionAtomically")
        self.assertIn("LockService.getScriptLock()", body)
        for product_payload in (
            lead_payload(submission_id="sub-tipos", email="tipos@example.com"),
            {
                "name": "Pessoa Teste", "email": "estilos@example.com", "whatsapp": "",
                "teste": "estilos", "resultado": "D",
                "pontuacoes": {"D": 10, "I": 5, "S": 5, "C": 4},
                "consentimento": True, "submission_id": "sub-estilos",
                "website": "", "token": DEFAULT_ACCESS_TOKEN,
            },
            {
                "name": "Pessoa Teste", "email": "tracos@example.com", "whatsapp": "",
                "teste": "tracos",
                "resultado": {k: {"sum": 15, "percent": 50, "faixa": "medio"} for k in ("SO", "AN", "OM", "TE", "CO")},
                "pontuacoes": {k: {"sum": 15, "percent": 50, "faixa": "medio"} for k in ("SO", "AN", "OM", "TE", "CO")},
                "consentimento": True, "submission_id": "sub-tracos",
                "website": "", "token": DEFAULT_ACCESS_TOKEN,
            },
        ):
            with self.subTest(teste=product_payload["teste"]):
                [result] = run_node(
                    "dumpState({ response: doPost({ postData: { contents: JSON.stringify(%s) } }).getContent() });"
                    % json.dumps(product_payload)
                )
                self.assertEqual(json.loads(result["response"]), {"ok": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
