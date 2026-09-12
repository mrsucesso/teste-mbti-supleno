#!/usr/bin/env python3
"""Valida conteúdo e estrutura do Supleno Tipos."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
RESULTS = ROOT / "resultados"

errors: list[str] = []

def fail(message: str) -> None:
    errors.append(message)

public_files = [INDEX, ROOT / "apps-script" / "Code.gs", ROOT / "PROMPTS-IMAGENS.md"]
public_files.extend(sorted(RESULTS.glob("*.html")))

parenthetical_gender = re.compile(r"\b[\wÀ-ÿ]+\(a\)", re.IGNORECASE)
vague_energy = re.compile(r"\benerg(?:ia|ias|izado|izada|izados|izadas)\b", re.IGNORECASE)
wrong_brand = re.compile(r"(?:https?://[^\s\"']*sucesso\.com|@sucesso\.com\.br)", re.IGNORECASE)

for path in public_files:
    text = path.read_text(encoding="utf-8")
    for label, pattern in (
        ("marcação artificial de gênero", parenthetical_gender),
        ("uso editorial proibido de energia", vague_energy),
        ("referência indevida à Sucesso", wrong_brand),
    ):
        matches = sorted(set(pattern.findall(text)))
        if matches:
            fail(f"{path.relative_to(ROOT)}: {label}: {', '.join(matches)}")

index_text = INDEX.read_text(encoding="utf-8")
questions_match = re.search(r"const QUESTIONS = (\[.*?\]);\nconst PROFILES", index_text, re.DOTALL)
profiles_match = re.search(r"const PROFILES = (\{.*?\});\nconst ORDER", index_text, re.DOTALL)

if not questions_match or not profiles_match:
    fail("index.html: não foi possível localizar QUESTIONS ou PROFILES")
else:
    questions = json.loads(questions_match.group(1))
    profiles = json.loads(profiles_match.group(1))
    if len(questions) != 28:
        fail(f"esperadas 28 perguntas; encontradas {len(questions)}")
    if len(profiles) != 16:
        fail(f"esperados 16 tipos; encontrados {len(profiles)}")

    expected_pages = {
        f"{code.lower()}-{gender}.html"
        for code in profiles
        for gender in ("m", "f")
    }
    actual_pages = {path.name for path in RESULTS.glob("*.html")}
    missing = sorted(expected_pages - actual_pages)
    extra = sorted(actual_pages - expected_pages)
    if missing:
        fail(f"páginas de resultado ausentes: {', '.join(missing)}")
    if extra:
        fail(f"páginas de resultado inesperadas: {', '.join(extra)}")

if len(list(RESULTS.glob("*.html"))) != 32:
    fail(f"esperadas 32 páginas de resultado; encontradas {len(list(RESULTS.glob('*.html')))}")

if errors:
    print("VALIDAÇÃO FALHOU")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("VALIDAÇÃO OK: 28 perguntas, 16 tipos, 32 resultados e linguagem editorial conforme as regras.")
