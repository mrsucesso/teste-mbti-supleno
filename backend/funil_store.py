#!/usr/bin/env python3
"""Adaptador local (stdlib) do funil dos três testes Supleno.

Este módulo é a referência/adaptador local e sandboxed do contrato de
persistência e da sequência de nutrição (imediato/D1/D3/D5/D7) compartilhado
pelos três produtos (Supleno Tipos, Supleno Estilos e Supleno Traços). Ele
existe para homologar o contrato com dados sintéticos e validar por TDD,
já que os backends de produção continuam sendo um Apps Script por produto
(ver README > "Rotas e estrutura" e > "Configuração necessária antes da
produção"). Nenhum e-mail real é enviado por este módulo: em modo sandbox
(padrão) os estágios da sequência apenas são registrados e logados; fora do
sandbox, é obrigatório fornecer um `adaptador_envio_real` explícito.
"""
from __future__ import annotations

import json
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Sandbox obrigatório por padrão: sem um adaptador de envio real explícito,
# não há como esta biblioteca disparar qualquer comunicação de verdade.
SANDBOX_MODE = True

# Os três produtos da família Testes Supleno (ver README > Rotas e estrutura).
TESTES_VALIDOS = frozenset({"tipos", "estilos", "tracos"})

# Estágios da sequência de nutrição, em ordem, com o deslocamento em dias
# a partir da data de criação do lead.
ESTAGIOS = ("imediato", "d1", "d3", "d5", "d7")
_OFFSET_DIAS = {"imediato": 0, "d1": 1, "d3": 3, "d5": 5, "d7": 7}
_ESTADO_APOS_ESTAGIO = {
    "imediato": "imediato_enviado",
    "d1": "d1_enviado",
    "d3": "d3_enviado",
    "d5": "d5_enviado",
    "d7": "concluido",
}
_PROXIMO_INDICE_POR_ESTADO = {
    "pendente": 0,
    "imediato_enviado": 1,
    "d1_enviado": 2,
    "d3_enviado": 3,
    "d5_enviado": 4,
}

_NOME_PRODUTO = {
    "tipos": "Supleno Tipos",
    "estilos": "Supleno Estilos",
    "tracos": "Supleno Traços",
}

EMAIL_PATTERN = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$")
WHATSAPP_PATTERN = re.compile(r"^[0-9 ()+\-]{0,20}$")

# Templates em português natural, sem plágio de metodologias fechadas e
# respeitando a governança editorial (ver README > Governança editorial):
# sem construções "(a)", sem "energia" como sinônimo de ânimo/disposição,
# sem citar 16Personalities/Big Five. Todo template oferece opt-out.
TEMPLATES = {
    "imediato": {
        "assunto": "{nome}, aqui está o resumo do seu {produto}",
        "corpo": (
            "Olá, {nome}!\n\n"
            "Obrigado por concluir o {produto}. Seu resultado resumido é: "
            "{resultado_texto}.\n\n"
            "Quer ver a página completa, com mais detalhes sobre o seu "
            "resultado?\n{cta_url}\n\n"
            "Se preferir não receber os próximos e-mails desta sequência, "
            "cancele aqui: {optout_url}"
        ),
    },
    "d1": {
        "assunto": "Um detalhe a mais sobre o seu resultado no {produto}",
        "corpo": (
            "Olá, {nome}!\n\n"
            "Faz um dia que você concluiu o {produto} e chegou a "
            "{resultado_texto}. Hoje trouxemos um ponto extra para você "
            "refletir sobre esse resultado.\n\n"
            "Veja mais em {cta_url}\n\n"
            "Não quer mais receber estes e-mails? Cancele aqui: "
            "{optout_url}"
        ),
    },
    "d3": {
        "assunto": "Como {resultado_texto} aparece no seu dia a dia",
        "corpo": (
            "Olá, {nome}!\n\n"
            "Já se passaram três dias desde o seu {produto}. Preparamos um "
            "exemplo prático de como o resultado {resultado_texto} costuma "
            "aparecer nas escolhas do dia a dia.\n\n"
            "Continue explorando em {cta_url}\n\n"
            "Se quiser sair desta sequência de e-mails, cancele aqui: "
            "{optout_url}"
        ),
    },
    "d5": {
        "assunto": "{nome}, um convite para ir além do resultado",
        "corpo": (
            "Olá, {nome}!\n\n"
            "Cinco dias após o seu {produto}, este é um convite para ir "
            "além do resultado {resultado_texto} e aprofundar o "
            "autoconhecimento com o Método Supleno.\n\n"
            "Saiba mais em {cta_url}\n\n"
            "Prefere não continuar recebendo? Cancele aqui: {optout_url}"
        ),
    },
    "d7": {
        "assunto": "Fechando o ciclo do seu {produto}",
        "corpo": (
            "Olá, {nome}!\n\n"
            "Esta é a última mensagem desta sequência sobre o seu "
            "{produto}. Esperamos que o resultado {resultado_texto} tenha "
            "sido útil para o seu autoconhecimento.\n\n"
            "O convite para conhecer o Método Supleno continua aberto em "
            "{cta_url}\n\n"
            "Se ainda receber e-mails futuros e quiser parar, cancele "
            "aqui: {optout_url}"
        ),
    },
}


def mask_email(email: str) -> str:
    """Mascara a parte local de um e-mail para uso seguro em logs."""
    email = (email or "").strip()
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = (local[:1] or "*") + "***"
    return f"{masked_local}@{domain}"


def render_template(estagio: str, contexto: dict) -> dict:
    """Renderiza o template de um estágio, substituindo os placeholders."""
    template = TEMPLATES.get(estagio)
    if template is None:
        raise ValueError(f"estágio de sequência desconhecido: {estagio!r}")
    return {
        "assunto": template["assunto"].format(**contexto),
        "corpo": template["corpo"].format(**contexto),
    }


class FunilStore:
    """Persistência local (JSON Lines) e máquina de estados do funil.

    Não é o backend de produção: é o adaptador local usado para homologar o
    contrato (campos persistidos, idempotência, sequência de nutrição,
    opt-out) com dados sintéticos, comum aos três produtos Supleno.
    """

    def __init__(
        self,
        path: Path,
        sandbox: bool = SANDBOX_MODE,
        adaptador_envio_real: Optional[Callable[[dict], None]] = None,
        cta_url: str = "https://supleno.com",
        optout_base_url: str = "https://testes.supleno.com",
        optout_secret: Optional[str] = None,
    ) -> None:
        if not sandbox and adaptador_envio_real is None:
            raise ValueError(
                "fora do modo sandbox é obrigatório informar um "
                "adaptador_envio_real explícito — não há envio real implícito"
            )
        self.path = Path(path)
        self.sandbox = sandbox
        self.adaptador_envio_real = adaptador_envio_real
        self.cta_url = cta_url
        self.optout_base_url = optout_base_url
        self.optout_secret = (optout_secret or secrets.token_urlsafe(32)).encode("utf-8")
        self._lock = threading.RLock()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._leads: dict[str, dict] = {}
        self._opt_out_emails: set[str] = set()
        self._carregar()

    def _carregar(self) -> None:
        self._leads = {}
        self._opt_out_emails = set()
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                linha = linha.strip()
                if not linha:
                    continue
                lead = json.loads(linha)
                if lead.get("record_type") == "opt_out":
                    self._opt_out_emails.add(lead["email"].strip().lower())
                    continue
                self._leads[lead["submission_id"]] = lead
                if lead.get("opt_out"):
                    self._opt_out_emails.add(lead["email"].strip().lower())

    @contextmanager
    def _lock_processo(self):
        """Exclusão mútua entre processos para ler-modificar-gravar."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.touch(exist_ok=True)
        with lock_path.open("r+", encoding="utf-8") as lock_file:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def registrar_lead(self, payload: dict, agora: Optional[datetime] = None) -> dict:
        agora = agora or datetime.now(timezone.utc)

        teste = (payload.get("teste") or "").strip()
        nome = (payload.get("nome") or "").strip()
        email = (payload.get("email") or "").strip()
        whatsapp = (payload.get("whatsapp") or "").strip()
        consentimento = payload.get("consentimento")

        if not nome:
            raise ValueError("nome é obrigatório")
        if not email or not EMAIL_PATTERN.match(email):
            raise ValueError("e-mail é obrigatório e deve ser válido")
        if whatsapp and not WHATSAPP_PATTERN.match(whatsapp):
            raise ValueError("whatsapp inválido")
        if teste not in TESTES_VALIDOS:
            raise ValueError(f"teste inválido: {teste!r}")
        if consentimento is not True:
            raise ValueError("consentimento explícito é obrigatório")

        submission_id = (payload.get("submission_id") or "").strip()
        if not submission_id:
            dia = agora.date().isoformat()
            submission_id = f"auto:{teste}:{email.lower()}:{dia}"

        with self._lock, self._lock_processo():
            self._carregar()
            if email.lower() in self._opt_out_emails:
                raise ValueError("e-mail com opt-out ativo; recadastro bloqueado")
            existente = self._leads.get(submission_id)
            if existente is not None:
                logger.info("lead duplicado ignorado: teste=%s email=%s submission_id=%s", teste, mask_email(email), submission_id)
                return {"ok": True, "duplicado": True, "submission_id": submission_id}
            lead = {
                "submission_id": submission_id, "teste": teste, "nome": nome,
                "email": email, "whatsapp": whatsapp, "consentimento": True,
                "resultado": payload.get("resultado") or {}, "pontuacoes": payload.get("pontuacoes") or {},
                "utm_source": payload.get("utm_source") or "", "utm_medium": payload.get("utm_medium") or "",
                "utm_campaign": payload.get("utm_campaign") or "", "origem": payload.get("origem") or "",
                "data_criacao": agora.isoformat(), "estado_sequencia": "pendente", "opt_out": False,
                "envios": {estagio: "pending" for estagio in ESTAGIOS},
            }
            self._leads[submission_id] = lead
            self._persistir_tudo_locked()
        logger.info(
            "lead registrado: teste=%s email=%s submission_id=%s",
            teste, mask_email(email), submission_id,
        )
        return {"ok": True, "duplicado": False, "submission_id": submission_id}

    def obter_lead(self, submission_id: str) -> Optional[dict]:
        return self._leads.get(submission_id)

    def listar_leads(self) -> list:
        return list(self._leads.values())

    def gerar_optout_token(self, email: str) -> str:
        normalizado = (email or "").strip().lower()
        normalizado_bytes = normalizado.encode("utf-8")
        mac = hmac.new(self.optout_secret, normalizado_bytes, hashlib.sha256).hexdigest()
        b64_email = base64.urlsafe_b64encode(normalizado_bytes).decode("utf-8").rstrip("=")
        return f"{b64_email}.{mac}"

    def registrar_opt_out(self, email: str, token: Optional[str] = None) -> dict:
        email_normalizado = (email or "").strip().lower()
        if not email_normalizado or not token:
            raise ValueError("token de opt-out inválido")
        # Valida token resolvendo e conferindo se bate com o email
        email_resolvido = self.resolver_email_por_token(token)
        if not email_resolvido or email_resolvido != email_normalizado:
            raise ValueError("token de opt-out inválido")
        with self._lock, self._lock_processo():
            self._carregar()
            self._opt_out_emails.add(email_normalizado)
            afetados = 0
            for lead in self._leads.values():
                if lead["email"].strip().lower() == email_normalizado and not lead["opt_out"]:
                    lead["opt_out"] = True
                    lead["estado_sequencia"] = "opt_out"
                    afetados += 1
            self._persistir_tudo_locked()
        logger.info("opt-out registrado: email=%s afetados=%d", mask_email(email), afetados)
        return {"ok": True, "afetados": afetados}

    def resolver_email_por_token(self, token: str) -> Optional[str]:
        """Resolve um e-mail a partir de um token assinado (b64.hmac)
        mesmo se ainda não houver lead local."""
        if not token or "." not in token:
            return None
        with self._lock, self._lock_processo():
            self._carregar()
            try:
                b64_email, mac = token.split(".", 1)
                missing_padding = len(b64_email) % 4
                if missing_padding:
                    b64_email += "=" * (4 - missing_padding)
                email_bytes = base64.urlsafe_b64decode(b64_email.encode("utf-8"))
                email = email_bytes.decode("utf-8").strip().lower()
                
                expected_mac = hmac.new(self.optout_secret, email_bytes, hashlib.sha256).hexdigest()
                if hmac.compare_digest(mac, expected_mac):
                    return email
            except Exception:
                return None
        return None

    def marcar_enviado_manualmente(self, submission_id: str, estagio: str) -> None:
        """Marca um estágio como enviado, útil para reconciliação manual."""
        with self._lock, self._lock_processo():
            self._carregar()
            lead = self._leads.get(submission_id)
            if not lead:
                raise ValueError(f"lead {submission_id} não encontrado")
            lead.setdefault("envios", {})[estagio] = "sent"
            lead["estado_sequencia"] = _ESTADO_APOS_ESTAGIO[estagio]
            self._persistir_tudo_locked()

    def esta_opt_out(self, email: str) -> bool:
        return (email or "").strip().lower() in self._opt_out_emails

    def processar_fila(self, agora: Optional[datetime] = None) -> list:
        """Processa a fila de nutrição: envia (simulado, em sandbox) no
        máximo um estágio por lead a cada chamada — o estágio mais antigo
        ainda pendente e já vencido."""
        agora = agora or datetime.now(timezone.utc)
        enviados = []
        with self._lock, self._lock_processo():
            self._carregar()
            for lead in self._leads.values():
                if lead["opt_out"]:
                    continue
                estagio = self._proximo_estagio_devido(lead, agora)
                if estagio is None:
                    continue

                contexto = self._construir_contexto(lead)
                mensagem = render_template(estagio, contexto)
                if not self.sandbox:
                    lead.setdefault("envios", {})[estagio] = "sending"
                    lead.setdefault("envios_timestamps", {})[estagio] = agora.isoformat()
                    self._persistir_tudo_locked()
                    self.adaptador_envio_real({
                        "destinatario": lead["email"],
                        "mensagem": mensagem,
                        "submission_id": lead["submission_id"],
                        "estagio": estagio,
                    })

                lead.setdefault("envios", {})[estagio] = "sent"
                lead.setdefault("envios_timestamps", {})[estagio] = agora.isoformat()
                lead["estado_sequencia"] = _ESTADO_APOS_ESTAGIO[estagio]
                self._persistir_tudo_locked()
                enviados.append({"submission_id": lead["submission_id"], "estagio": estagio})
                logger.info(
                    "estágio enviado (sandbox=%s): teste=%s estagio=%s email=%s",
                    self.sandbox, lead["teste"], estagio, mask_email(lead["email"]),
                )

            if enviados:
                self._persistir_tudo_locked()
        return enviados

    def reconciliar_outbox(self, lease_timeout_segundos: int = 300, agora: Optional[datetime] = None) -> int:
        """Recupera registros de envio presos no status 'sending' (ex: após queda de processo).

        Nota sobre garantia de entrega: Sem suporte a chaves de idempotência no provedor
        final (adaptador_envio_real), o limite teórico é 'at-least-once'. A reconciliação
        minimiza duplicidade ao usar um lease (timeout), mas se um processo cair exatamente
        após o envio mas antes de persistir o status 'sent', o estágio será reprocessado
        após o timeout.
        """
        agora = agora or datetime.now(timezone.utc)
        reconciliados = 0
        with self._lock, self._lock_processo():
            self._carregar()
            for lead in self._leads.values():
                envios = lead.setdefault("envios", {})
                timestamps = lead.setdefault("envios_timestamps", {})
                for estagio, status in list(envios.items()):
                    if status == "sending":
                        ts_str = timestamps.get(estagio)
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str)
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                                if (agora - ts).total_seconds() > lease_timeout_segundos:
                                    envios[estagio] = "pending"
                                    reconciliados += 1
                            except ValueError:
                                envios[estagio] = "pending"
                                reconciliados += 1
                        else:
                            # Se não houver timestamp mas está em sending, recupera por precaução
                            envios[estagio] = "pending"
                            reconciliados += 1
            if reconciliados > 0:
                self._persistir_tudo_locked()
        return reconciliados

    def _proximo_estagio_devido(self, lead: dict, agora: datetime) -> Optional[str]:
        indice = _PROXIMO_INDICE_POR_ESTADO.get(lead["estado_sequencia"])
        if indice is None:
            return None
        estagio = ESTAGIOS[indice]
        if lead.get("envios", {}).get(estagio, "pending") != "pending":
            return None
        data_criacao = datetime.fromisoformat(lead["data_criacao"])
        data_devida = data_criacao + timedelta(days=_OFFSET_DIAS[estagio])
        if agora >= data_devida:
            return estagio
        return None

    def _construir_contexto(self, lead: dict) -> dict:
        resultado = lead.get("resultado") or {}
        if "code" in resultado:
            resultado_texto = str(resultado["code"])
        elif resultado:
            resultado_texto = ", ".join(f"{chave}: {valor}" for chave, valor in resultado.items())
        else:
            resultado_texto = ""
        return {
            "nome": lead["nome"],
            "produto": _NOME_PRODUTO.get(lead["teste"], lead["teste"]),
            "resultado_texto": resultado_texto,
            "cta_url": self.cta_url,
            "optout_url": f"{self.optout_base_url}/optout?token={quote(self.gerar_optout_token(lead['email']))}",
        }

    def _persistir_tudo(self) -> None:
        with self._lock:
            with self._lock_processo():
                self._persistir_tudo_locked()

    def _persistir_tudo_locked(self) -> None:
        temporario = self.path.with_name(f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with temporario.open("w", encoding="utf-8") as arquivo:
            for email in sorted(self._opt_out_emails):
                arquivo.write(json.dumps({"record_type": "opt_out", "email": email}, ensure_ascii=False))
                arquivo.write("\n")
            for lead in self._leads.values():
                arquivo.write(json.dumps(lead, ensure_ascii=False))
                arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, self.path)
