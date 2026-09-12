import pytest
from io import BytesIO
from backend.optout_server import OptOutApplication
from backend.funil_store import FunilStore
from pathlib import Path

@pytest.fixture
def store(tmp_path):
    path = tmp_path / "leads.jsonl"
    return FunilStore(path, optout_secret="secret")

@pytest.fixture
def app(store):
    return OptOutApplication(store)

def test_get_optout_renders_form(app, store):
    token = store.gerar_optout_token("test@example.com")
    environ = {
        "PATH_INFO": "/optout",
        "QUERY_STRING": f"token={token}",
        "REQUEST_METHOD": "GET"
    }
    start_response = lambda status, headers: None
    response = app(environ, start_response)
    
    assert b"Confirmar cancelamento" in response[0]
    assert b"method=\"POST\"" in response[0]

def test_post_optout_registers(app, store):
    email = "test@example.com"
    token = store.gerar_optout_token(email)
    
    # Simula o POST com o token no corpo e no QUERY_STRING (action do form)
    body = f"token={token}".encode("utf-8")
    environ = {
        "PATH_INFO": "/optout",
        "QUERY_STRING": f"token={token}",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body)
    }
    start_response = lambda status, headers: None
    response = app(environ, start_response)
    
    assert store.esta_opt_out(email)
