#!/usr/bin/env python3
"""Rota WSGI mínima para opt-out por token assinado e opaco."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from backend.funil_store import FunilStore


class OptOutApplication:
    """Resolve somente o token; o e-mail nunca trafega na URL."""

    def __init__(self, store: FunilStore) -> None:
        self.store = store

    def __call__(self, environ: dict, start_response):
        if environ.get("PATH_INFO") != "/optout":
            return self._respond(start_response, "404 Not Found", "Rota não encontrada.")

        if environ.get("REQUEST_METHOD") == "GET":
            params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
            token = params.get("token", [""])[0]
            email = self.store.resolver_email_por_token(token)
            if not email:
                return self._respond(start_response, "400 Bad Request", "Link de cancelamento inválido.")
            return self._respond_confirm(start_response, token)

        if environ.get("REQUEST_METHOD") == "POST":
            # A confirmação lê exclusivamente o corpo; query strings são ignoradas.
            try:
                request_body_size = int(environ.get("CONTENT_LENGTH") or 0)
            except (TypeError, ValueError):
                request_body_size = 0
            stream = environ.get("wsgi.input")
            request_body = stream.read(request_body_size) if stream is not None else b""
            try:
                post_params = parse_qs(request_body.decode("utf-8"), keep_blank_values=True)
            except UnicodeDecodeError:
                return self._respond(start_response, "400 Bad Request", "Token de confirmação inválido.")
            token_post = post_params.get("token", [""])[0]
            action = post_params.get("action", [""])[0]
            if action != "optout_confirm" or not token_post:
                return self._respond(start_response, "400 Bad Request", "Token de confirmação inválido.")
            email = self.store.resolver_email_por_token(token_post)
            if not email:
                return self._respond(start_response, "400 Bad Request", "Link de cancelamento inválido.")
            self.store.registrar_opt_out(email, token_post)
            return self._respond(start_response, "200 OK", "Recebimento de e-mails cancelado.")

        return self._respond(start_response, "405 Method Not Allowed", "Método não permitido.")

    def _respond_confirm(self, start_response, token: str):
        body = (
            "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\">"
            "<title>Supleno</title><h1>Confirmar cancelamento</h1>"
            "<p>Deseja realmente parar de receber nossos e-mails?</p>"
            "<form method=\"POST\" action=\"/optout\">"
            "<input type=\"hidden\" name=\"action\" value=\"optout_confirm\">"
            f"<input type=\"hidden\" name=\"token\" value=\"{token}\">"
            "<button type=\"submit\">Sim, confirmar cancelamento</button></form></html>"
        ).format(token=token).encode("utf-8")
        start_response("200 OK", [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ])
        return [body]

    @staticmethod
    def _respond(start_response, status: str, message: str):
        body = ("<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\">"
                f"<title>Supleno</title><h1>{message}</h1></html>").encode("utf-8")
        start_response(status, [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ])
        return [body]


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local de opt-out Supleno")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    secret = os.environ.get("SUPLENO_OPTOUT_SECRET")
    if not secret:
        parser.error("SUPLENO_OPTOUT_SECRET é obrigatório")
    app = OptOutApplication(FunilStore(args.data, optout_secret=secret))
    with make_server(args.host, args.port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
