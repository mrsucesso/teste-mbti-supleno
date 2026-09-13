import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.funil_store import FunilStore


class TestFase8D(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(
            Path(self._tmp.name) / "leads.jsonl",
            optout_secret="secret",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_get_optout_does_not_change_state(self):
        email = "test@example.com"
        self.store.gerar_optout_token(email)
        self.assertFalse(self.store.esta_opt_out(email))

    def test_token_resolves_without_local_lead(self):
        email = "unregistered@example.com"
        token = self.store.gerar_optout_token(email)
        self.assertEqual(self.store.resolver_email_por_token(token), email)

    def test_outbox_lease_reconciliation_recovers_stuck_sending(self):
        payload = {
            "teste": "tipos",
            "nome": "Pessoa de Teste",
            "email": "stuck@example.com",
            "consentimento": True,
            "submission_id": "sub-stuck",
        }
        self.store.registrar_lead(payload)

        with self.store._lock, self.store._lock_processo():
            lead = self.store._leads["sub-stuck"]
            lead["envios"]["imediato"] = "sending"
            lead["envios_timestamps"] = {
                "imediato": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat()
            }
            self.store._persistir_tudo_locked()

        reconciled = self.store.reconciliar_outbox(lease_timeout_segundos=60)
        self.assertGreater(reconciled, 0)
        lead_reconciled = self.store.obter_lead("sub-stuck")
        self.assertIsNotNone(lead_reconciled)
        assert lead_reconciled is not None
        self.assertEqual(lead_reconciled["envios"]["imediato"], "pending")


if __name__ == "__main__":
    unittest.main()
