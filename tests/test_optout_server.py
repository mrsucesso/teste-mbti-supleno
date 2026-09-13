import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from backend.funil_store import FunilStore
from backend.optout_server import OptOutApplication


class TestOptOutServer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(
            Path(self._tmp.name) / "leads.jsonl",
            optout_secret="secret",
        )
        self.app = OptOutApplication(self.store)

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _start_response(status, headers):
        return None

    def test_get_optout_renders_form_without_changing_state(self):
        email = "test@example.com"
        token = self.store.gerar_optout_token(email)
        environ = {
            "PATH_INFO": "/optout",
            "QUERY_STRING": f"token={token}",
            "REQUEST_METHOD": "GET",
        }
        response = self.app(environ, self._start_response)

        self.assertIn(b"Confirmar cancelamento", response[0])
        self.assertIn(b'method="POST"', response[0])
        self.assertFalse(self.store.esta_opt_out(email))

    def test_post_optout_registers(self):
        email = "test@example.com"
        token = self.store.gerar_optout_token(email)
        body = f"action=optout_confirm&token={token}".encode("utf-8")
        environ = {
            "PATH_INFO": "/optout",
            "QUERY_STRING": "",
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": BytesIO(body),
        }
        self.app(environ, self._start_response)

        self.assertTrue(self.store.esta_opt_out(email))

    def test_post_without_wsgi_input_fails_controlled_and_ignores_query(self):
        status = []

        def start_response(value, _headers):
            status.append(value)

        response = self.app(
            {
                "PATH_INFO": "/optout",
                "REQUEST_METHOD": "POST",
                "QUERY_STRING": "action=optout_confirm&token=qualquer",
                "CONTENT_LENGTH": "0",
            },
            start_response,
        )
        self.assertEqual(status[0], "400 Bad Request")
        self.assertTrue(b"inv\xc3\xa1lido" in b"".join(response))


if __name__ == "__main__":
    unittest.main()
