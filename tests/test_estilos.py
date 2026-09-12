#!/usr/bin/env python3
"""Testes do Supleno Estilos: conteúdo original, escala e fluxo seguro."""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "estilos" / "index.html"
TEXT = INDEX.read_text(encoding="utf-8")


def extract_array(marker: str) -> list:
    start = TEXT.index(marker) + len(marker)
    end = TEXT.index("\n];", start) + 2
    return json.loads(TEXT[start:end])


class TestBancoEstilos(unittest.TestCase):
    def test_has_24_questions_and_four_dimensions(self):
        questions = extract_array("const QUESTIONS = ")
        self.assertEqual(len(questions), 24)
        self.assertEqual({q["pair"] for q in questions}, {"DI", "DS", "DC", "IS", "IC", "SC"})
        self.assertTrue(all(q["a"]["p"] in "DISC" and q["b"]["p"] in "DISC" for q in questions))
        self.assertTrue(all(q["a"]["p"] != q["b"]["p"] for q in questions))

    def test_each_dimension_has_equal_exposure(self):
        questions = extract_array("const QUESTIONS = ")
        counts = {dimension: 0 for dimension in "DISC"}
        for question in questions:
            counts[question["a"]["p"]] += 1
            counts[question["b"]["p"]] += 1
        self.assertEqual(counts, {"D": 12, "I": 12, "S": 12, "C": 12})

    def test_questions_are_original_and_not_placeholder_copy(self):
        questions = extract_array("const QUESTIONS = ")
        texts = [option["t"] for q in questions for option in (q["a"], q["b"])]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertNotIn("16Personalities", TEXT)
        self.assertNotIn("Big Five", TEXT)
        self.assertNotRegex(TEXT, r"\benerg(?:ia|izado|izada)\b")
        self.assertNotRegex(TEXT, r"\b[\wÀ-ÿ]+\(a\)")


class TestPontuacaoEFluxo(unittest.TestCase):
    def test_algorithm_has_fixed_tie_order_and_uses_all_dimensions(self):
        self.assertIn('const ORDER = ["D", "I", "S", "C"]', TEXT)
        body = TEXT[TEXT.index("function computeStyle"):TEXT.index("function renderResult")]
        self.assertIn("scores[dim] > bestScore", body)
        self.assertIn("scores[dim]", body)

    def test_algorithm_executes_deterministically_and_resolves_ties(self):
        match = re.search(r"<script>\n(.*?)\n</script>", TEXT, re.DOTALL)
        if match is None:
            self.fail("script inline não encontrado")
        runner = (
            "globalThis.window={SUPLENO_CONFIG:{}};"
            "globalThis.document={getElementById:()=>({textContent:''})};"
            + match.group(1)
            + "globalThis.pick=(v)=>{scores=v;return computeStyle()};"
            + "console.log(JSON.stringify([pick({D:6,I:6,S:1,C:1}),pick({D:1,I:2,S:8,C:2}),pick({D:1,I:2,S:2,C:8})]));"
        )
        result = subprocess.run(["node", "-e", runner], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["D", "S", "C"])

    def test_result_is_rendered_before_optional_capture(self):
        finish = TEXT[TEXT.index("function finishQuiz"):TEXT.index("function computeStyle")]
        self.assertLess(finish.index("renderResult"), finish.index("showScreen('screen-result')"))
        result_start = TEXT.index("id=\"screen-result\"")
        capture_start = TEXT.index("id=\"captureBlock\"")
        self.assertLess(result_start, capture_start)
        self.assertIn("opcional", TEXT[capture_start:capture_start + 500])

    def test_capture_is_optional_and_webhook_is_configured_outside_html(self):
        self.assertIn('const WEBHOOK_URL = SUPLENO_CONFIG.WEBHOOK_URL || "";', TEXT)
        self.assertIn("if(WEBHOOK_URL)", TEXT)
        self.assertIn('id="leadForm"', TEXT)
        self.assertIn("e.preventDefault()", TEXT)
        self.assertNotIn("script.google.com/macros/s/", TEXT)

    def test_js_syntax_is_valid(self):
        script = re.search(r"<script>\n(.*?)\n</script>", TEXT, re.DOTALL)
        if script is None:
            self.fail("script inline não encontrado")
        result = subprocess.run(["node", "--check"], input=script.group(1), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
