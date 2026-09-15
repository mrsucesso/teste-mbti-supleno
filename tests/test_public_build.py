import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build-public.py"


class TestPublicBuild(unittest.TestCase):
    def run_build(self, output):
        return subprocess.run(
            [sys.executable, str(BUILDER), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_build_creates_allowlisted_package_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "public"
            result = self.run_build(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "manifest.json").is_file())
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["format"], 1)
            self.assertIn("index.html", manifest["files"])
            self.assertIn("tipos/config.js", manifest["files"])
            for forbidden in ("backend", "tests", "apps-script", ".git", ".github"):
                self.assertFalse((output / forbidden).exists())

    def test_build_generates_safe_configs_from_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "public"
            result = self.run_build(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            for product in ("tipos", "estilos", "tracos"):
                config = (output / product / "config.js").read_text()
                self.assertIn('WEBHOOK_URL: ""', config)
                self.assertIn("SANDBOX_MODE: true", config)
                self.assertNotIn("config.example.js", config)

    def test_build_versions_shared_stylesheet_with_its_content_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "public"
            result = self.run_build(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = hashlib.sha256((output / "assets/style.css").read_bytes()).hexdigest()[:12]
            pages = sorted(output.rglob("*.html"))
            self.assertGreater(len(pages), 60)
            for page in pages:
                content = page.read_text(encoding="utf-8")
                if "assets/style.css" in content:
                    self.assertIn(f"assets/style.css?v={digest}", content, str(page))

    def test_build_versions_open_graph_images_with_content_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "public"
            result = self.run_build(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            pages = sorted(output.rglob("*.html"))
            for image in sorted((output / "assets/og").glob("*.jpg")):
                digest = hashlib.sha256(image.read_bytes()).hexdigest()[:12]
                reference = f"https://testes.supleno.com/assets/og/{image.name}"
                consumers = [page for page in pages if reference in page.read_text(encoding="utf-8")]
                self.assertTrue(consumers, image.name)
                for page in consumers:
                    content = page.read_text(encoding="utf-8")
                    suffixes = re.findall(rf'{re.escape(reference)}([^"<]*)', content)
                    self.assertTrue(suffixes, str(page))
                    self.assertEqual({f"?v={digest}"}, set(suffixes), str(page))

    def test_manifest_hashes_match_built_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "public"
            result = self.run_build(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "manifest.json").read_text())
            for relative, expected in manifest["files"].items():
                actual = hashlib.sha256((output / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected, relative)

    def test_second_build_is_byte_for_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "first", Path(tmp) / "second"
            self.assertEqual(self.run_build(first).returncode, 0)
            self.assertEqual(self.run_build(second).returncode, 0)
            first_files = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
            second_files = sorted(p.relative_to(second) for p in second.rglob("*") if p.is_file())
            self.assertEqual(first_files, second_files)
            for relative in first_files:
                self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes(), str(relative))

    def test_same_dedicated_directory_can_be_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dedicated"
            first = self.run_build(output)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_files = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
            (output / "stale-from-previous-build.txt").write_text("remover")
            second = self.run_build(output)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse((output / "stale-from-previous-build.txt").exists())
            second_files = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
            self.assertEqual(first_files, second_files)

    def test_dangerous_output_is_rejected_before_removal(self):
        result = self.run_build(ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((ROOT / "scripts" / "build-public.py").is_file())

    def test_existing_external_directory_is_not_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "arbitrary"
            output.mkdir()
            sentinel = output / "do-not-delete.txt"
            sentinel.write_text("preservar")
            result = self.run_build(output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(), "preservar")

    def test_broken_output_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "broken-link"
            output.symlink_to(Path(tmp) / "missing-target")
            result = self.run_build(output)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(output.is_symlink())

    def test_copy_tree_rejects_source_symlink(self):
        spec = importlib.util.spec_from_file_location("builder", BUILDER)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, destination = base / "source", base / "destination"
            source.mkdir()
            (base / "outside.txt").write_text("não publicar")
            (source / "vazamento.txt").symlink_to(base / "outside.txt")
            with self.assertRaises(ValueError):
                builder.copy_tree(source, destination)
            self.assertFalse((destination / "vazamento.txt").exists())


if __name__ == "__main__":
    unittest.main()
