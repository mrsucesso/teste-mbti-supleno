import pytest
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from backend.funil_store import FunilStore

@pytest.fixture
def store(tmp_path):
    path = tmp_path / "leads.jsonl"
    return FunilStore(path, optout_secret="secret")

def test_get_optout_does_not_change_state(store):
    email = "test@example.com"
    token = store.gerar_optout_token(email)
    assert not store.esta_opt_out(email)

def test_token_resolves_without_local_lead(store):
    email = "unregistered@example.com"
    token = store.gerar_optout_token(email)
    
    # Lead is NOT registered in store._leads
    resolved_email = store.resolver_email_por_token(token)
    assert resolved_email == email

def test_outbox_lease_reconciliation_recovers_stuck_sending(store):
    # Register a lead
    payload = {
        "teste": "tipos",
        "nome": "Test User",
        "email": "stuck@example.com",
        "consentimento": True,
        "submission_id": "sub-stuck"
    }
    store.registrar_lead(payload)
    
    # Force the 'imediato' stage into 'sending' with an old timestamp (expired lease)
    with store._lock, store._lock_processo():
        lead = store._leads["sub-stuck"]
        lead["envios"]["imediato"] = "sending"
        lead["envios_timestamps"] = {"imediato": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
        store._persistir_tudo_locked()
        
    # Run reconciliation or process_fila with lease check
    # Should recover 'sending' stuck for > lease time back to 'pending' or process it
    reconciled = store.reconciliar_outbox(lease_timeout_segundos=60)
    assert reconciled > 0
    
    lead_reconciled = store.obter_lead("sub-stuck")
    assert lead_reconciled["envios"]["imediato"] == "pending"
