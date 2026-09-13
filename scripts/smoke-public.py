#!/usr/bin/env python3
"""Smoke test local do pacote público, sem rede externa."""

from __future__ import annotations

import argparse
import importlib.util
import tempfile
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_public", ROOT / "scripts" / "build-public.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("não foi possível carregar o builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build


class Fallback404Handler(SimpleHTTPRequestHandler):
    def send_error(self, code, message=None, explain=None):
        if code != 404:
            return super().send_error(code, message, explain)
        body = Path(self.directory, "404.html").read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def check(url: str, expected_status: int, content_type: str) -> None:
    try:
        response = urllib.request.urlopen(url)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read().decode("utf-8")
    assert response.status == expected_status, (url, response.status)
    assert response.headers.get_content_type() == content_type, (url, response.headers.get_content_type())
    if expected_status == 404:
        assert "Página não encontrada" in body, url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "public"
        load_builder()(output)
        handler = partial(Fallback404Handler, directory=str(output))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            for path, content_type in (("/", "text/html"), ("/tipos/", "text/html"),
                                       ("/privacidade/", "text/html"),
                                       ("/metodologia/", "text/html"),
                                       ("/assets/style.css", "text/css"),
                                       ("/assets/nav.js", "application/javascript"),
                                       ("/robots.txt", "text/plain")):
                check(base + path, 200, content_type)
            check(base + "/rota-inexistente", 404, "text/html")
        finally:
            server.shutdown()
            thread.join()
    print("Smoke local do pacote público: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
