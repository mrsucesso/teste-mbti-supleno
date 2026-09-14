import importlib.util
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "smoke-public.py"

spec = importlib.util.spec_from_file_location("smoke_public", SMOKE)
if spec is None or spec.loader is None:
    raise RuntimeError("não foi possível carregar o smoke público")
smoke_public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke_public)


class MimeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        content_type = self.path[1:]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


class TestSmokePublicMimeContract(unittest.TestCase):
    def test_javascript_mime_allowlist_accepts_only_valid_types(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MimeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:{}".format(server.server_port)
        try:
            allowed = ("text/javascript", "application/javascript")
            for content_type in allowed:
                with self.subTest(accepted=content_type):
                    smoke_public.check(base + "/" + content_type, 200, allowed)
            for content_type in ("text/plain", "application/octet-stream", "text/css"):
                with self.subTest(rejected=content_type):
                    with self.assertRaises(AssertionError):
                        smoke_public.check(base + "/" + content_type, 200, allowed)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
