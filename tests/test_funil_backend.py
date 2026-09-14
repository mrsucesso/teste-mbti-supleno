#!/usr/bin/env python3
"""Testes do adaptador local (stdlib) do funil dos três testes Supleno.

Este módulo (backend/funil_store.py) é a referência/adaptador local e
sandboxed do contrato de persistência e da sequência de nutrição
(imediato/D1/D3/D5/D7). Não é o backend de produção (esse continua sendo
Apps Script, por produto, conforme README) — serve para homologação local
com dados sintéticos e para validar o contrato por TDD, já que Apps Script
não roda nativamente sob `python3 -m unittest`.

Regras cobertas:
- nome e e-mail obrigatórios; WhatsApp opcional
- consentimento explícito obrigatório para persistir/entrar na sequência
- resultado, pontuações, teste, UTM/origem/campanha, data e estado da
  sequência são persistidos
- idempotência (mesmo submission_id) e prevenção de duplicidade por
  janela curta (mesmo e-mail+teste+dia, sem submission_id)
- máquina de estados da sequência (imediato -> d1 -> d3 -> d5 -> d7)
- opt-out interrompe a sequência
- sandbox obrigatório por padrão; sem adaptador real, não há como enviar
  mensagem de verdade
- templates existem para os 5 estágios, em português natural, sem
  plágio de metodologias fechadas e respeitando a governança editorial
- logs não vazam e-mail/nome brutos
"""
from __future__ import annotations

import json
import logging
import multiprocessing
import re
import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from io import BytesIO

from backend.funil_store import (
    ESTAGIOS,
    SANDBOX_MODE,
    TESTES_VALIDOS,
    TEMPLATES,
    FunilStore,
    mask_email,
    render_template,
)
from backend.optout_server import OptOutApplication


def payload_base(**overrides):
    base = {
        "teste": "tipos",
        "nome": "Maria Teste",
        "email": "maria@example.com",
        "whatsapp": "",
        "consentimento": True,
        "resultado": {"code": "INTJ", "gender": "F"},
        "pontuacoes": {"E": 2, "I": 5, "S": 3, "N": 4, "T": 4, "F": 3, "J": 5, "P": 2},
        "utm_source": "instagram",
        "utm_medium": "social",
        "utm_campaign": "lancamento-tracos",
        "origem": "https://instagram.com",
        "submission_id": "sub-teste-0001",
    }
    base.update(overrides)
    return base


def _registrar_em_processo(path, submission_id, inicio):
    store = FunilStore(Path(path))
    store.registrar_lead(payload_base(submission_id=submission_id), agora=inicio)


def _processar_fila_em_processo(path, inicio, contador):
    def adapter(_message):
        with contador.get_lock():
            contador.value += 1
    FunilStore(Path(path), sandbox=False, adaptador_envio_real=adapter).processar_fila(agora=inicio)


class TestSandboxObrigatorio(unittest.TestCase):
    def test_sandbox_mode_default_is_true(self):
        self.assertTrue(SANDBOX_MODE)

    def test_store_default_is_sandboxed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FunilStore(Path(tmp) / "leads.jsonl")
            self.assertTrue(store.sandbox)

    def test_disabling_sandbox_without_real_adapter_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                FunilStore(Path(tmp) / "leads.jsonl", sandbox=False)

    def test_disabling_sandbox_with_explicit_adapter_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            def adaptador_falso(mensagem):
                return None
            store = FunilStore(Path(tmp) / "leads.jsonl", sandbox=False, adaptador_envio_real=adaptador_falso)
            self.assertFalse(store.sandbox)

    def test_real_adapter_receives_recipient_and_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = Mock()
            store = FunilStore(Path(tmp) / "leads.jsonl", sandbox=False, adaptador_envio_real=adapter)
            agora = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
            store.registrar_lead(payload_base(), agora=agora)
            store.processar_fila(agora=agora)
            adapter.assert_called_once()
            self.assertEqual(adapter.call_args.args[0]["destinatario"], "maria@example.com")


class TestCamposObrigatorios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(Path(self.tmp.name) / "leads.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_name_raises(self):
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload_base(nome=""))

    def test_missing_email_raises(self):
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload_base(email=""))

    def test_invalid_email_raises(self):
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload_base(email="não-é-email"))

    def test_whatsapp_is_optional(self):
        resultado = self.store.registrar_lead(payload_base(whatsapp=""))
        self.assertTrue(resultado["ok"])

    def test_whatsapp_when_provided_is_persisted(self):
        resultado = self.store.registrar_lead(payload_base(whatsapp="(27) 99999-0000", submission_id="sub-whats"))
        lead = self.store.obter_lead(resultado["submission_id"])
        self.assertEqual(lead["whatsapp"], "(27) 99999-0000")

    def test_invalid_test_name_raises(self):
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload_base(teste="outro-produto"))

    def test_missing_consent_raises(self):
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload_base(consentimento=False))

    def test_absent_consent_key_raises(self):
        payload = payload_base()
        del payload["consentimento"]
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload)


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(Path(self.tmp.name) / "leads.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_persists_all_required_fields(self):
        agora = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        resultado = self.store.registrar_lead(payload_base(), agora=agora)
        lead = self.store.obter_lead(resultado["submission_id"])
        self.assertEqual(lead["teste"], "tipos")
        self.assertEqual(lead["nome"], "Maria Teste")
        self.assertEqual(lead["email"], "maria@example.com")
        self.assertEqual(lead["resultado"], {"code": "INTJ", "gender": "F"})
        self.assertEqual(lead["pontuacoes"]["J"], 5)
        self.assertEqual(lead["utm_source"], "instagram")
        self.assertEqual(lead["utm_medium"], "social")
        self.assertEqual(lead["utm_campaign"], "lancamento-tracos")
        self.assertEqual(lead["origem"], "https://instagram.com")
        self.assertEqual(lead["data_criacao"], agora.isoformat())
        self.assertTrue(lead["consentimento"])
        self.assertEqual(lead["estado_sequencia"], "pendente")
        self.assertFalse(lead["opt_out"])

    def test_utm_defaults_to_empty_when_absent(self):
        payload = payload_base(submission_id="sub-sem-utm")
        for key in ("utm_source", "utm_medium", "utm_campaign", "origem"):
            payload.pop(key, None)
        resultado = self.store.registrar_lead(payload)
        lead = self.store.obter_lead(resultado["submission_id"])
        self.assertEqual(lead["utm_source"], "")
        self.assertEqual(lead["utm_medium"], "")
        self.assertEqual(lead["utm_campaign"], "")
        self.assertEqual(lead["origem"], "")

    def test_each_product_type_is_accepted(self):
        for i, teste in enumerate(sorted(TESTES_VALIDOS)):
            resultado = self.store.registrar_lead(payload_base(teste=teste, submission_id=f"sub-{teste}-{i}"))
            self.assertTrue(resultado["ok"])


class TestIdempotencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(Path(self.tmp.name) / "leads.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_submission_id_does_not_duplicate(self):
        payload = payload_base(submission_id="sub-repetido")
        primeiro = self.store.registrar_lead(payload)
        segundo = self.store.registrar_lead(payload)
        self.assertFalse(primeiro["duplicado"])
        self.assertTrue(segundo["duplicado"])
        self.assertEqual(len(self.store.listar_leads()), 1)

    def test_same_submission_id_returns_same_submission_id(self):
        payload = payload_base(submission_id="sub-repetido-2")
        primeiro = self.store.registrar_lead(payload)
        segundo = self.store.registrar_lead(payload)
        self.assertEqual(primeiro["submission_id"], segundo["submission_id"])

    def test_same_submission_id_is_idempotent_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            inicio = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
            processos = [multiprocessing.Process(
                target=_registrar_em_processo,
                args=(str(path), "sub-concorrente", inicio),
            ) for _ in range(8)]
            for processo in processos:
                processo.start()
            for processo in processos:
                processo.join(10)
                self.assertEqual(processo.exitcode, 0)
            linhas = [linha for linha in path.read_text(encoding="utf-8").splitlines() if linha]
            self.assertEqual(len(linhas), 1)
            self.assertEqual(json.loads(linhas[0])["submission_id"], "sub-concorrente")

    def test_retry_without_submission_id_within_window_deduplicates(self):
        agora = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
        payload1 = payload_base(submission_id="")
        payload2 = payload_base(submission_id="")
        self.store.registrar_lead(payload1, agora=agora)
        self.store.registrar_lead(payload2, agora=agora + timedelta(seconds=30))
        self.assertEqual(len(self.store.listar_leads()), 1)

    def test_retake_next_day_is_not_treated_as_duplicate(self):
        agora = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
        payload1 = payload_base(submission_id="")
        payload2 = payload_base(submission_id="")
        self.store.registrar_lead(payload1, agora=agora)
        self.store.registrar_lead(payload2, agora=agora + timedelta(days=1))
        self.assertEqual(len(self.store.listar_leads()), 2)

    def test_different_submission_ids_for_different_people_are_not_merged(self):
        self.store.registrar_lead(payload_base(submission_id="sub-a", email="a@example.com"))
        self.store.registrar_lead(payload_base(submission_id="sub-b", email="b@example.com"))
        self.assertEqual(len(self.store.listar_leads()), 2)


class TestOptOut(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(Path(self.tmp.name) / "leads.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_opt_out_marks_existing_leads(self):
        self.store.registrar_lead(payload_base(submission_id="sub-optout", email="sai@example.com"))
        resultado = self.store.registrar_opt_out("sai@example.com", self.store.gerar_optout_token("sai@example.com"))
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["afetados"], 1)
        lead = self.store.obter_lead("sub-optout")
        self.assertTrue(lead["opt_out"])
        self.assertEqual(lead["estado_sequencia"], "opt_out")

    def test_esta_opt_out_reflects_state(self):
        self.assertFalse(self.store.esta_opt_out("nunca@example.com"))
        self.store.registrar_lead(payload_base(submission_id="sub-optout-2", email="nunca@example.com"))
        self.store.registrar_opt_out("nunca@example.com", self.store.gerar_optout_token("nunca@example.com"))
        self.assertTrue(self.store.esta_opt_out("nunca@example.com"))

    def test_opted_out_lead_does_not_advance_in_queue(self):
        agora = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        self.store.registrar_lead(payload_base(submission_id="sub-optout-3", email="parou@example.com"), agora=agora)
        self.store.registrar_opt_out("parou@example.com", self.store.gerar_optout_token("parou@example.com"))
        enviados = self.store.processar_fila(agora=agora + timedelta(days=10))
        self.assertEqual([e for e in enviados if e["submission_id"] == "sub-optout-3"], [])

    def test_opt_out_on_unknown_email_is_persisted_after_restart(self):
        resultado = self.store.registrar_opt_out("desconhecido@example.com", self.store.gerar_optout_token("desconhecido@example.com"))
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["afetados"], 0)
        reiniciado = FunilStore(
            Path(self.tmp.name) / "leads.jsonl",
            optout_secret=self.store.optout_secret.decode("utf-8"),
        )
        self.assertTrue(reiniciado.esta_opt_out("desconhecido@example.com"))

    def test_opt_out_blocks_later_registration_for_same_email(self):
        email = "bloqueado@example.com"
        self.store.registrar_opt_out(email, self.store.gerar_optout_token(email))
        with self.assertRaisesRegex(ValueError, "opt-out"):
            self.store.registrar_lead(payload_base(email=email, submission_id="sub-bloqueada"))

    def test_opt_out_by_token_rejects_get_without_confirm(self):
        email = "sai@example.com"
        self.store.registrar_lead(payload_base(submission_id="sub-optout-token", email=email))
        token = self.store.gerar_optout_token(email)
        app = OptOutApplication(self.store)

        # GET não deve alterar estado
        statuses = []
        body = b"".join(app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/optout", "QUERY_STRING": f"token={token}"},
            lambda status, _headers: statuses.append(status),
        ))
        self.assertEqual(statuses, ["200 OK"])
        self.assertIn(b"Confirmar", body)
        self.assertFalse(self.store.esta_opt_out(email))

        # POST deve persistir
        statuses = []
        body_post = f"action=optout_confirm&token={token}".encode("utf-8")
        body = b"".join(app(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/optout", "QUERY_STRING": "", "CONTENT_LENGTH": str(len(body_post)), "wsgi.input": BytesIO(body_post)},
            lambda status, _headers: statuses.append(status),
        ))
        self.assertEqual(statuses, ["200 OK"])
        self.assertIn(b"cancelado", body)
        self.assertTrue(self.store.esta_opt_out(email))

    def test_uncertain_sending_is_recoverable_after_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            attempts = []
            def crashing_adapter(message):
                attempts.append(message["submission_id"])
                raise RuntimeError("queda")

            store = FunilStore(path, sandbox=False, adaptador_envio_real=crashing_adapter)
            agora = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
            store.registrar_lead(payload_base(submission_id="sub-recon"), agora=agora)
            with self.assertRaises(RuntimeError):
                store.processar_fila(agora=agora)

            # A lease expirada vira uncertain; só então a decisão humana
            # pode confirmar o envio sem reenviar às cegas.
            store.reconciliar_outbox(
                lease_timeout_segundos=60,
                agora=agora + timedelta(minutes=2),
            )
            store.marcar_enviado_manualmente("sub-recon", "imediato")

            # Não deve tentar enviar novamente
            self.assertEqual(store.processar_fila(agora=agora), [])
            self.assertEqual(len(attempts), 1)

    def test_opt_out_rejects_missing_or_invalid_signed_token(self):
        self.store.registrar_lead(payload_base(submission_id="sub-token"))
        with self.assertRaises(ValueError):
            self.store.registrar_opt_out("maria@example.com")
        with self.assertRaises(ValueError):
            self.store.registrar_opt_out("maria@example.com", "token-invalido")

    def test_opt_out_url_contains_token_but_not_email(self):
        self.store.registrar_lead(payload_base(submission_id="sub-url"))
        contexto = self.store._construir_contexto(self.store.obter_lead("sub-url"))
        self.assertNotIn("maria@example.com", contexto["optout_url"])
        self.assertEqual(urlsplit(contexto["optout_url"]).path, "/optout")
        self.assertIn("token=", contexto["optout_url"])


class TestFilaDeSequencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(Path(self.tmp.name) / "leads.jsonl")
        self.agora = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
        self.store.registrar_lead(payload_base(submission_id="sub-seq"), agora=self.agora)

    def tearDown(self):
        self.tmp.cleanup()

    def _estagios_enviados(self, dias):
        enviados = self.store.processar_fila(agora=self.agora + timedelta(days=dias))
        return [e["estagio"] for e in enviados if e["submission_id"] == "sub-seq"]

    def test_day_zero_sends_imediato(self):
        self.assertEqual(self._estagios_enviados(0), ["imediato"])
        self.assertEqual(self.store.obter_lead("sub-seq")["estado_sequencia"], "imediato_enviado")

    def test_processing_twice_same_day_does_not_resend(self):
        self.store.processar_fila(agora=self.agora)
        segundo = self.store.processar_fila(agora=self.agora)
        self.assertEqual([e for e in segundo if e["submission_id"] == "sub-seq"], [])

    def test_sequence_advances_in_order_d1_d3_d5_d7(self):
        self.assertEqual(self._estagios_enviados(0), ["imediato"])
        self.assertEqual(self._estagios_enviados(1), ["d1"])
        self.assertEqual(self._estagios_enviados(3), ["d3"])
        self.assertEqual(self._estagios_enviados(5), ["d5"])
        self.assertEqual(self._estagios_enviados(7), ["d7"])
        self.assertEqual(self.store.obter_lead("sub-seq")["estado_sequencia"], "concluido")

    def test_jumping_straight_to_day_seven_only_sends_due_stage_once(self):
        enviados = self.store.processar_fila(agora=self.agora + timedelta(days=7))
        estagios = [e["estagio"] for e in enviados if e["submission_id"] == "sub-seq"]
        self.assertEqual(estagios, ["imediato"])

    def test_completed_sequence_is_never_resent(self):
        for dias in (0, 1, 3, 5, 7, 30):
            self.store.processar_fila(agora=self.agora + timedelta(days=dias))
        enviados = self.store.processar_fila(agora=self.agora + timedelta(days=60))
        self.assertEqual([e for e in enviados if e["submission_id"] == "sub-seq"], [])

    def test_lead_without_consent_never_enters_queue(self):
        self.store.registrar_opt_out("maria@example.com", self.store.gerar_optout_token("maria@example.com"))  # limpa estado anterior
        with self.assertRaises(ValueError):
            self.store.registrar_lead(payload_base(submission_id="sub-sem-consentimento", consentimento=False))

    def test_real_send_is_marked_sending_before_adapter_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            observed = []

            def adapter(_message):
                persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                lead = next(item for item in persisted if item.get("submission_id") == "sub-outbox")
                observed.append(lead["envios"]["imediato"])

            store = FunilStore(path, sandbox=False, adaptador_envio_real=adapter)
            store.registrar_lead(payload_base(submission_id="sub-outbox"), agora=self.agora)
            store.processar_fila(agora=self.agora)
            self.assertEqual(observed, ["sending"])

    def test_uncertain_sending_is_not_resent_after_adapter_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            attempts = []

            def crashing_adapter(message):
                attempts.append(message["estagio"])
                raise RuntimeError("queda sintética após entrega incerta")

            store = FunilStore(path, sandbox=False, adaptador_envio_real=crashing_adapter)
            store.registrar_lead(payload_base(submission_id="sub-crash"), agora=self.agora)
            with self.assertRaises(RuntimeError):
                store.processar_fila(agora=self.agora)

            restarted = FunilStore(path, sandbox=False, adaptador_envio_real=crashing_adapter)
            self.assertEqual(restarted.processar_fila(agora=self.agora), [])
            self.assertEqual(attempts, ["imediato"])
            self.assertEqual(restarted.obter_lead("sub-crash")["envios"]["imediato"], "sending")

    def test_concurrent_workers_send_each_stage_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            FunilStore(path).registrar_lead(payload_base(submission_id="sub-workers"), agora=self.agora)
            contador = multiprocessing.Value("i", 0)
            workers = [multiprocessing.Process(
                target=_processar_fila_em_processo,
                args=(str(path), self.agora, contador),
            ) for _ in range(6)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual(contador.value, 1)

    def test_successful_earlier_lead_stays_sent_when_later_adapter_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            attempts = []

            def adapter(message):
                attempts.append(message["submission_id"])
                if message["submission_id"] == "sub-second":
                    raise RuntimeError("falha sintética no segundo lead")

            store = FunilStore(path, sandbox=False, adaptador_envio_real=adapter)
            store.registrar_lead(payload_base(submission_id="sub-first", email="first@example.com"), agora=self.agora)
            store.registrar_lead(payload_base(submission_id="sub-second", email="second@example.com"), agora=self.agora)
            with self.assertRaises(RuntimeError):
                store.processar_fila(agora=self.agora)

            restarted = FunilStore(path, sandbox=False, adaptador_envio_real=adapter)
            self.assertEqual(restarted.processar_fila(agora=self.agora), [])
            self.assertEqual(attempts, ["sub-first", "sub-second"])
            self.assertEqual(restarted.obter_lead("sub-first")["envios"]["imediato"], "sent")


class TestTemplates(unittest.TestCase):
    def test_all_five_stages_have_templates(self):
        self.assertEqual(set(ESTAGIOS), {"imediato", "d1", "d3", "d5", "d7"})
        self.assertEqual(set(TEMPLATES.keys()), set(ESTAGIOS))

    def test_templates_have_subject_and_body(self):
        for estagio, template in TEMPLATES.items():
            self.assertIn("assunto", template)
            self.assertIn("corpo", template)
            self.assertTrue(template["assunto"].strip())
            self.assertTrue(template["corpo"].strip())

    def test_render_template_substitutes_placeholders(self):
        rendered = render_template("d1", {
            "nome": "Ana",
            "produto": "Supleno Tipos",
            "resultado_texto": "INTJ-F, A Planejadora Estratégica",
            "cta_url": "https://supleno.com",
            "optout_url": "https://testes.supleno.com/optout?token=token-sintetico",
        })
        self.assertIn("Ana", rendered["assunto"] + rendered["corpo"])
        self.assertIn("Supleno Tipos", rendered["corpo"])
        self.assertNotIn("{", rendered["corpo"])
        self.assertNotIn("}", rendered["corpo"])

    def test_every_template_offers_opt_out(self):
        for estagio, template in TEMPLATES.items():
            self.assertIn("{optout_url}", template["corpo"])

    def test_templates_respect_editorial_governance(self):
        texto_completo = "\n".join(t["assunto"] + " " + t["corpo"] for t in TEMPLATES.values())
        self.assertNotIn("16Personalities", texto_completo)
        self.assertNotIn("Big Five", texto_completo)
        self.assertNotRegex(texto_completo, r"\benerg(?:ia|izado|izada)\b")
        self.assertNotRegex(texto_completo, r"\b[\wÀ-ÿ]+\(a\)")

    def test_render_unknown_stage_raises(self):
        with self.assertRaises(ValueError):
            render_template("d99", {})


class TestMascaramentoDeLogs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FunilStore(Path(self.tmp.name) / "leads.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_mask_email_hides_local_part(self):
        masked = mask_email("mauricio.teste@example.com")
        self.assertNotEqual(masked, "mauricio.teste@example.com")
        self.assertTrue(masked.endswith("@example.com"))
        self.assertNotIn("mauricio.teste", masked)

    def test_mask_email_handles_short_local_part(self):
        masked = mask_email("a@example.com")
        self.assertNotIn("a@example.com", masked)
        self.assertTrue(masked.endswith("@example.com"))

    def test_registrar_lead_logs_do_not_contain_raw_email_or_name(self):
        with self.assertLogs("backend.funil_store", level="INFO") as captura:
            self.store.registrar_lead(payload_base(submission_id="sub-log", email="segredo@example.com", nome="Nome Sigiloso"))
        saida = "\n".join(captura.output)
        self.assertNotIn("segredo@example.com", saida)
        self.assertNotIn("Nome Sigiloso", saida)

    def test_processar_fila_logs_do_not_contain_raw_email(self):
        agora = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
        self.store.registrar_lead(payload_base(submission_id="sub-log-2", email="privado@example.com"), agora=agora)
        with self.assertLogs("backend.funil_store", level="INFO") as captura:
            self.store.processar_fila(agora=agora)
        saida = "\n".join(captura.output)
        self.assertNotIn("privado@example.com", saida)


class TestRetencaoLocal(unittest.TestCase):
    def test_token_ttl_is_capped_at_180_days_and_not_sliding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            store = FunilStore(path, optout_secret="secret", optout_token_ttl_dias=365)
            inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)
            token = store.gerar_optout_token("token@example.com", agora=inicio)
            primeiro = json.loads(path.read_text(encoding="utf-8").splitlines()[0])["expires_at"]
            store.gerar_optout_token("token@example.com", agora=inicio + timedelta(days=30))
            segundo = json.loads(path.read_text(encoding="utf-8").splitlines()[0])["expires_at"]
            self.assertEqual(token, store.gerar_optout_token("token@example.com", agora=inicio))
            self.assertEqual(primeiro, segundo)
            self.assertEqual(datetime.fromisoformat(primeiro), inicio + timedelta(days=180))

    def test_loading_store_purges_old_leads_tokens_and_optouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.jsonl"
            old = datetime(2025, 1, 1, tzinfo=timezone.utc)
            payload = payload_base(submission_id="old", email="old@example.com")
            payload["data_criacao"] = old.isoformat()
            path.write_text("\n".join([
                json.dumps(payload),
                json.dumps({"record_type": "opt_out", "email": "gone@example.com", "created_at": old.isoformat()}),
                json.dumps({"record_type": "optout_token", "token": "a" * 32, "email": "gone@example.com", "expires_at": old.isoformat()}),
            ]) + "\n", encoding="utf-8")
            store = FunilStore(path, optout_secret="secret")
            store.purgar_dados_expirados(agora=datetime(2026, 1, 1, tzinfo=timezone.utc))
            self.assertEqual(store.listar_leads(), [])
            self.assertFalse(store.esta_opt_out("gone@example.com"))
            self.assertIsNone(store.resolver_email_por_token("a" * 32, agora=datetime(2026, 1, 1, tzinfo=timezone.utc)))
            self.assertNotIn("old@example.com", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
