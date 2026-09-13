#!/usr/bin/env python3
"""Gera o pacote estático público do Testes Supleno de forma determinística."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_OWNER = "testes-supleno-public-builder-v1"
ROOT_FILES = ("index.html", "404.html", "robots.txt", "sitemap.xml")
PUBLIC_DIRS = ("assets", "resultados", "tipos", "estilos", "tracos", "mapa", "privacidade", "metodologia")
CONFIG_DIRS = ("tipos", "estilos", "tracos")


def _validate_output(output: Path) -> Path:
    """Validate the destination before it can be removed."""
    if output.is_symlink():
        raise ValueError(f"saída symlink não permitida: {output}")
    resolved = output.expanduser().resolve(strict=False)
    root = ROOT.resolve()
    home = Path.home().resolve()
    forbidden = (root, *root.parents, home)
    if resolved in forbidden:
        raise ValueError(f"saída insegura: {output}")
    try:
        resolved.relative_to(root)
        inside_root = True
    except ValueError:
        inside_root = False
    if inside_root and resolved != root / "public":
        raise ValueError(f"saída deve ser o diretório público dedicado: {output}")
    if resolved.exists() and resolved != root / "public":
        if not resolved.is_dir():
            raise ValueError(f"saída não é diretório: {output}")
        manifest_path = resolved / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            manifest = None
        if not isinstance(manifest, dict) or manifest.get("builder") != BUILD_OWNER:
            raise ValueError(f"saída externa existente não é um diretório de build dedicado: {output}")
    return resolved


def copy_tree(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"fonte pública symlink não permitida: {source}")
    source = source.resolve(strict=True)
    try:
        source.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"fonte fora da raiz pública: {source}") from error
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.name == "config.example.js":
            continue
        if path.is_symlink():
            raise ValueError(f"symlink não permitido na fonte pública: {path}")
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def build(output: Path) -> dict[str, str]:
    output = _validate_output(output)
    if output.exists():
        if not output.is_dir():
            raise ValueError(f"saída não é diretório: {output}")
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

    manifest = {"builder": BUILD_OWNER, "format": 1, "files": files}
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
