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

# Validade do vínculo nonce -> e-mail do token de opt-out. Generoso porque o
# link vive dentro de e-mails já enviados (não é renovável pelo destinatário).
OPTOUT_TOKEN_TTL_DIAS_PADRAO = 180
PII_RETENTION_DIAS = 180

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

EMAIL_PATTERN = re.compile(r"^(?=.{1,254}$)[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$")
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


def _fingerprint_canonico(campos: dict) -> str:
    """Hash determinístico do payload canônico de um lead — usado para
    detectar reaproveitamento indevido de submission_id com dados
    diferentes (ver registrar_lead)."""
    canonical = json.dumps(campos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _nonce_para_email(secret: bytes, email_normalizado: str) -> str:
    """Nonce opaco e determinístico (HMAC do e-mail): função de mão única,
    não há forma de recuperar o e-mail a partir do nonce."""
    mac = hmac.new(secret, email_normalizado.encode("utf-8"), hashlib.sha256).hexdigest()
    return mac[:32]


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
        optout_token_ttl_dias: int = OPTOUT_TOKEN_TTL_DIAS_PADRAO,
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
        self.optout_token_ttl_dias = min(max(int(optout_token_ttl_dias), 1), PII_RETENTION_DIAS)
        self._lock = threading.RLock()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._leads: dict[str, dict] = {}
        self._opt_out_emails: set[str] = set()
        self._opt_out_registered_at: dict[str, str] = {}
        self._optout_tokens: dict[str, dict] = {}
        self._carregar()
        self.purgar_dados_expirados()

    def _carregar(self) -> None:
        self._leads = {}
        self._opt_out_emails = set()
        self._opt_out_registered_at = {}
        self._optout_tokens = {}
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                linha = linha.strip()
                if not linha:
                    continue
                registro = json.loads(linha)
                tipo_registro = registro.get("record_type")
                if tipo_registro == "opt_out":
                    email = registro["email"].strip().lower()
                    self._opt_out_emails.add(email)
                    if registro.get("registered_at") or registro.get("created_at"):
                        self._opt_out_registered_at[email] = registro.get("registered_at") or registro.get("created_at")
                    continue
                if tipo_registro == "optout_token":
                    self._optout_tokens[registro["token"]] = {
                        "email": registro["email"],
                        "expires_at": registro["expires_at"],
                    }
                    continue
                lead = registro
                self._leads[lead["submission_id"]] = lead
                if lead.get("opt_out"):
                    email = lead["email"].strip().lower()
                    self._opt_out_emails.add(email)
                    if email not in self._opt_out_registered_at and lead.get("data_criacao"):
                        self._opt_out_registered_at[email] = lead["data_criacao"]

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

        resultado = payload.get("resultado") or {}
        pontuacoes = payload.get("pontuacoes") or {}
        utm_source = payload.get("utm_source") or ""
        utm_medium = payload.get("utm_medium") or ""
        utm_campaign = payload.get("utm_campaign") or ""
        origem = payload.get("origem") or ""
        fingerprint = _fingerprint_canonico({
            "teste": teste, "nome": nome, "email": email.lower(), "whatsapp": whatsapp,
            "resultado": resultado, "pontuacoes": pontuacoes,
            "utm_source": utm_source, "utm_medium": utm_medium,
            "utm_campaign": utm_campaign, "origem": origem,
        })

        with self._lock, self._lock_processo():
            self._carregar()
            if email.lower() in self._opt_out_emails:
                raise ValueError("e-mail com opt-out ativo; recadastro bloqueado")
            existente = self._leads.get(submission_id)
            if existente is not None:
                if existente.get("fingerprint") != fingerprint:
                    raise ValueError(
                        f"submission_id {submission_id!r} já usado com um payload diferente"
                    )
                logger.info("lead duplicado ignorado: teste=%s email=%s submission_id=%s", teste, mask_email(email), submission_id)
                return {"ok": True, "duplicado": True, "submission_id": submission_id}
            lead = {
                "submission_id": submission_id, "teste": teste, "nome": nome,
                "email": email, "whatsapp": whatsapp, "consentimento": True,
                "resultado": resultado, "pontuacoes": pontuacoes,
                "utm_source": utm_source, "utm_medium": utm_medium,
                "utm_campaign": utm_campaign, "origem": origem,
                "data_criacao": agora.isoformat(), "estado_sequencia": "pendente", "opt_out": False,
                "envios": {estagio: "pending" for estagio in ESTAGIOS},
                "fingerprint": fingerprint,
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

    def gerar_optout_token(self, email: str, agora: Optional[datetime] = None) -> str:
        """Gera um nonce opaco e determinístico (HMAC do e-mail) sem
        NENHUM dado do e-mail codificado de forma reversível dentro dele.
        A ligação nonce -> e-mail fica persistida (com expiração
        renovável) e é o único lugar de onde o e-mail pode ser recuperado.
        """
        agora = agora or datetime.now(timezone.utc)
        with self._lock, self._lock_processo():
            self._carregar()
            nonce = self._gerar_optout_token_locked(email, agora)
            self._persistir_tudo_locked()
        return nonce

    def _gerar_optout_token_locked(self, email: str, agora: datetime) -> str:
        """Cria/renova o vínculo quando o chamador já mantém os locks."""
        normalizado = (email or "").strip().lower()
        nonce = _nonce_para_email(self.optout_secret, normalizado)
        existente = self._optout_tokens.get(nonce)
        if existente:
            try:
                expira_existente = datetime.fromisoformat(existente["expires_at"])
                if expira_existente.tzinfo is None:
                    expira_existente = expira_existente.replace(tzinfo=timezone.utc)
                if agora < expira_existente:
                    return nonce
            except (KeyError, TypeError, ValueError):
                pass
        expira_em = agora + timedelta(days=self.optout_token_ttl_dias)
        self._optout_tokens[nonce] = {
            "email": normalizado,
            "expires_at": expira_em.isoformat(),
        }
        return nonce

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
            self._opt_out_registered_at[email_normalizado] = datetime.now(timezone.utc).isoformat()
            afetados = 0
            for lead in self._leads.values():
                if lead["email"].strip().lower() == email_normalizado and not lead["opt_out"]:
                    lead["opt_out"] = True
                    lead["estado_sequencia"] = "opt_out"
                    afetados += 1
            self._persistir_tudo_locked()
        logger.info("opt-out registrado: email=%s afetados=%d", mask_email(email), afetados)
        return {"ok": True, "afetados": afetados}

    def resolver_email_por_token(self, token: Optional[str], agora: Optional[datetime] = None) -> Optional[str]:
        """Resolve um e-mail a partir do nonce opaco de opt-out, mesmo sem
        lead local: só depende do vínculo persistido nonce -> e-mail criado
        em gerar_optout_token. Confere expiração e recomputa o nonce
        esperado a partir do e-mail guardado, como verificação de
        integridade — se o registro persistido foi adulterado por qualquer
        via, a resolução falha (fail-closed)."""
        agora = agora or datetime.now(timezone.utc)
        if not token:
            return None
        nonce = token.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            return None
        with self._lock, self._lock_processo():
            self._carregar()
            registro = self._optout_tokens.get(nonce)
            if not registro:
                return None
            try:
                expira_em = datetime.fromisoformat(registro["expires_at"])
            except (KeyError, ValueError):
                return None
            if expira_em.tzinfo is None:
                expira_em = expira_em.replace(tzinfo=timezone.utc)
            if agora >= expira_em:
                return None
            email_guardado = registro.get("email", "")
            esperado = _nonce_para_email(self.optout_secret, email_guardado)
            if not hmac.compare_digest(nonce, esperado):
                return None
            return email_guardado

    def marcar_enviado_manualmente(self, submission_id: str, estagio: str) -> None:
        """Marca um estágio como enviado, útil para reconciliação manual."""
        with self._lock, self._lock_processo():
            self._carregar()
            lead = self._leads.get(submission_id)
            if not lead:
                raise ValueError(f"lead {submission_id} não encontrado")
            if lead.setdefault("envios", {}).get(estagio) != "uncertain":
                raise ValueError("reconciliação manual só aceita estágio uncertain")
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
                                    envios[estagio] = "uncertain"
                                    reconciliados += 1
                            except ValueError:
                                envios[estagio] = "uncertain"
                                reconciliados += 1
                        else:
                            # Se não houver timestamp mas está em sending, recupera por precaução
                            envios[estagio] = "uncertain"
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
        nonce = _nonce_para_email(self.optout_secret, lead["email"].strip().lower())
        token_record = self._optout_tokens.get(nonce)
        try:
            expira = datetime.fromisoformat(token_record["expires_at"]) if token_record else datetime.min
            if expira.tzinfo is None:
                expira = expira.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            expira = datetime.min.replace(tzinfo=timezone.utc)
        if expira <= datetime.now(timezone.utc):
            nonce = self._gerar_optout_token_locked(lead["email"], datetime.now(timezone.utc))
        return {
            "nome": lead["nome"],
            "produto": _NOME_PRODUTO.get(lead["teste"], lead["teste"]),
            "resultado_texto": resultado_texto,
            "cta_url": self.cta_url,
            "optout_url": f"{self.optout_base_url}/optout?token={quote(nonce)}",
        }

    def purgar_dados_expirados(self, agora: Optional[datetime] = None) -> int:
        """Remove leads locais e tokens vencidos pela retenção de PII."""
        agora = agora or datetime.now(timezone.utc)
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=timezone.utc)
        limite = agora - timedelta(days=PII_RETENTION_DIAS)
        removidos = 0
        with self._lock, self._lock_processo():
            self._carregar()
            for submission_id, lead in list(self._leads.items()):
                try:
                    criado = datetime.fromisoformat(lead["data_criacao"])
                except (KeyError, TypeError, ValueError):
                    continue
                if criado.tzinfo is None:
                    criado = criado.replace(tzinfo=timezone.utc)
                if criado < limite:
                    del self._leads[submission_id]
                    removidos += 1
            for token, registro in list(self._optout_tokens.items()):
                try:
                    expira = datetime.fromisoformat(registro["expires_at"])
                except (KeyError, TypeError, ValueError):
                    del self._optout_tokens[token]
                    continue
                if expira.tzinfo is None:
                    expira = expira.replace(tzinfo=timezone.utc)
                if expira <= agora:
                    del self._optout_tokens[token]
                    removidos += 1
            for email in list(self._opt_out_emails):
                timestamp = self._opt_out_registered_at.get(email)
                if not isinstance(timestamp, str):
                    self._opt_out_registered_at.pop(email, None)
                    self._opt_out_emails.discard(email)
                    removidos += 1
                    continue
                try:
                    registrado = datetime.fromisoformat(timestamp)
                except ValueError:
                    self._opt_out_registered_at.pop(email, None)
                    self._opt_out_emails.discard(email)
                    removidos += 1
                    continue
                if registrado.tzinfo is None:
                    registrado = registrado.replace(tzinfo=timezone.utc)
                if registrado < limite:
                    self._opt_out_registered_at.pop(email, None)
                    self._opt_out_emails.discard(email)
                    removidos += 1
            if removidos:
                self._persistir_tudo_locked()
        return removidos

    def _persistir_tudo(self) -> None:
        with self._lock:
            with self._lock_processo():
                self._persistir_tudo_locked()

    def _persistir_tudo_locked(self) -> None:
        temporario = self.path.with_name(f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with temporario.open("w", encoding="utf-8") as arquivo:
            for email in sorted(self._opt_out_emails):
                registro_optout = {"record_type": "opt_out", "email": email}
                if email in self._opt_out_registered_at:
                    registro_optout["registered_at"] = self._opt_out_registered_at[email]
                arquivo.write(json.dumps(registro_optout, ensure_ascii=False))
                arquivo.write("\n")
            for token, registro in self._optout_tokens.items():
                arquivo.write(json.dumps({
                    "record_type": "optout_token",
                    "token": token,
                    "email": registro["email"],
                    "expires_at": registro["expires_at"],
                }, ensure_ascii=False))
                arquivo.write("\n")
            for lead in self._leads.values():
                arquivo.write(json.dumps(lead, ensure_ascii=False))
                arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, self.path)
