#!/usr/bin/env python3
"""Testes do Supleno Traços: cinco dimensões, cálculo e fluxo."""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "tracos" / "index.html"
TEXT = INDEX.read_text(encoding="utf-8")
PORTAL_TEXT = (ROOT / "index.html").read_text(encoding="utf-8")


def extract_questions() -> list[dict]:
    start = TEXT.index("const QUESTIONS = ") + len("const QUESTIONS = ")
    end = TEXT.index("\n];", start) + 2
    return json.loads(TEXT[start:end])


class TestBancoTracos(unittest.TestCase):
    def test_portal_presents_tracos_as_available(self):
        card = PORTAL_TEXT[PORTAL_TEXT.index("<h2>Supleno Traços</h2>") - 100:]
        card = card[:card.index("</article>")]
        self.assertIn('<span class="badge live">Disponível</span>', card)
        self.assertIn("Um teste de 25 perguntas", card)
        self.assertIn('href="tracos/">Fazer o teste</a>', card)
        self.assertNotIn("Em construção", card)
        self.assertNotIn("Ver prévia", card)

    def test_has_25_original_questions_and_five_dimensions(self):
        questions = extract_questions()
        self.assertEqual(len(questions), 25)
        self.assertEqual({q["dim"] for q in questions}, {"SO", "AN", "OM", "TE", "CO"})
        counts = {dimension: sum(question["dim"] == dimension for question in questions) for dimension in {question["dim"] for question in questions}}
        self.assertEqual(counts, {"SO": 5, "AN": 5, "OM": 5, "TE": 5, "CO": 5})
        self.assertEqual(sum(q["reverse"] for q in questions), 10)
        self.assertEqual(len({q["t"] for q in questions}), 25)

    def test_editorial_constraints_are_respected(self):
        self.assertNotIn("16Personalities", TEXT)
        self.assertNotIn("DISC", TEXT)
        self.assertNotRegex(TEXT, r"\benerg(?:ia|izado|izada)\b")
        self.assertNotRegex(TEXT, r"\b[\wÀ-ÿ]+\(a\)")
        self.assertIn("não é um teste clínico", TEXT)
        self.assertIn("Limitações", TEXT)


class TestPontuacaoEFluxoTracos(unittest.TestCase):
    def _script(self) -> str:
        match = re.search(r"<script>\n(.*?)\n</script>", TEXT, re.DOTALL)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_js_syntax_is_valid(self):
        result = subprocess.run(["node", "--check"], input=self._script(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scores_are_deterministic_and_reverse_items_are_inverted(self):
        script = self._script()
        runner = (
            "globalThis.window={SUPLENO_CONFIG:{}};"
            "globalThis.document={querySelectorAll:()=>[],getElementById:()=>({}),querySelector:()=>({setAttribute:()=>{}})};"
            + script
            + "console.log(JSON.stringify(computeScores(Array(25).fill(5))));"
        )
        result = subprocess.run(["node", "-e", runner], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        scores = json.loads(result.stdout)
        self.assertEqual({d: scores[d]["percent"] for d in ["SO", "AN", "OM", "TE", "CO"]}, {d: 60 for d in ["SO", "AN", "OM", "TE", "CO"]})

        low_runner = runner.replace("Array(25).fill(5)", "Array(25).fill(1)")
        low_result = subprocess.run(["node", "-e", low_runner], capture_output=True, text=True)
        self.assertEqual(low_result.returncode, 0, low_result.stderr)
        low_scores = json.loads(low_result.stdout)
        self.assertEqual({d: low_scores[d]["percent"] for d in ["SO", "AN", "OM", "TE", "CO"]}, {d: 40 for d in ["SO", "AN", "OM", "TE", "CO"]})

    def test_result_precedes_optional_capture(self):
        self.assertLess(TEXT.index('id="screen-result"'), TEXT.index('id="captureBlock"'))
        finish = TEXT[TEXT.index("function finishQuiz"):TEXT.index("const FAIXA_LABELS")]
        self.assertLess(finish.index("renderResult"), finish.index("showScreen('screen-result')"))
        self.assertIn("opcional", TEXT[TEXT.index('id="captureBlock"'):TEXT.index('id="captureBlock"') + 500])


if __name__ == "__main__":
    unittest.main()
