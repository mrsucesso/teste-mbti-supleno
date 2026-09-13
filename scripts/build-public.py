#!/usr/bin/env python3
"""Gera o pacote estático público do Testes Supleno de forma determinística."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("index.html", "404.html", "robots.txt", "sitemap.xml")
PUBLIC_DIRS = ("assets", "resultados", "tipos", "estilos", "tracos", "privacidade", "metodologia")
CONFIG_DIRS = ("tipos", "estilos", "tracos")


def copy_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.name == "config.example.js":
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def build(output: Path) -> dict[str, str]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for name in ROOT_FILES:
        shutil.copyfile(ROOT / name, output / name)
    for name in PUBLIC_DIRS:
        copy_tree(ROOT / name, output / name)

    # A configuração pública sempre parte do exemplo seguro e nunca de config.js.
    for product in CONFIG_DIRS:
        example = ROOT / product / "config.example.js"
        target = output / product / "config.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, target)

    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            relative = path.relative_to(output).as_posix()
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {"format": 1, "files": files}
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("public"))
    args = parser.parse_args()
    files = build(args.output)
    print(f"Pacote público criado em {args.output} ({len(files)} arquivos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
