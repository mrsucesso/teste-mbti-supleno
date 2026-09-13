#!/usr/bin/env python3
"""Simulador E2E local do contrato Supleno Integracao v1.

Somente dados sintéticos e memória do processo. Não importa cliente HTTP,
não abre socket e não conhece URL de transporte.
"""
import json
import hashlib
import re
from datetime import datetime, timezone

CONTRACT = "supleno.integracao.v1"
SEQUENCE = ["imediato", "d1", "d3", "d5", "d7"]
PRODUCTS = {"tipos", "estilos", "tracos"}
REQUIRED = {"contract", "submission_id", "product", "person", "result", "consent", "attribution"}
ROOT_FIELDS = REQUIRED | {"scores", "opt_out"}
ORIGIN_PII = re.compile(r"(?:@|\b\d{8,}\b)")


def _error(code, submission_id=""):
    return {"contract": CONTRACT, "status": "rejected", "submission_id": submission_id,
            "error": {"code": code, "message": "Request inválido para o contrato Supleno."}}


def _valid_origin(origin):
    if not isinstance(origin, str) or len(origin) > 2048 or not origin:
        return False
    if any(mark in origin for mark in ("?", "#", "@", "\\")) or ORIGIN_PII.search(origin):
        return False
    if origin == "local":
        return True
    if not (origin.startswith("https" + "://") or origin.startswith("http" + "://")):
        return False
    return "/" not in origin.split("://", 1)[1]


def _valid_text(value, maximum):
    return isinstance(value, str) and len(value) <= maximum


def _valid_email(value):
    return _valid_text(value, 254) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)


def validar_request(request):
    if not isinstance(request, dict) or not REQUIRED.issubset(request) or set(request) - ROOT_FIELDS:
        return False
    if request.get("contract") != CONTRACT or not isinstance(request.get("submission_id"), str) or not 1 <= len(request["submission_id"]) <= 128:
        return False
    if request.get("product") not in PRODUCTS or not isinstance(request.get("result"), dict):
        return False
    if "scores" in request and not isinstance(request["scores"], dict):
        return False
    person = request.get("person")
    if (not isinstance(person, dict) or set(person) - {"name", "email", "whatsapp"}
            or not _valid_text(person.get("name"), 160) or not person["name"]
            or not _valid_email(person.get("email"))):
        return False
    if "whatsapp" in person and not _valid_text(person["whatsapp"], 32):
        return False
    consent = request.get("consent")
    if not isinstance(consent, dict) or set(consent) != {"granted", "captured_at", "purpose", "version"} or consent.get("granted") is not True or consent.get("purpose") != "resultado_e_sequencia_supleno" or not isinstance(consent.get("version"), str) or not consent["version"]:
        return False
    try:
        captured_at = datetime.fromisoformat(consent["captured_at"].replace("Z", "+00:00"))
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            return False
    except (ValueError, TypeError):
        return False
    attribution = request.get("attribution")
    if not isinstance(attribution, dict) or set(attribution) - {"utm_source", "utm_medium", "utm_campaign", "origin"}:
        return False
    for field, maximum in (("utm_source", 120), ("utm_medium", 120), ("utm_campaign", 160)):
        if field in attribution and not _valid_text(attribution[field], maximum):
            return False
    if "origin" in attribution and not _valid_origin(attribution["origin"]):
        return False
    if "opt_out" in request and request["opt_out"] is not False:
        return False
    return True


def fingerprint(request):
    """Fingerprint estável do conteúdo, sem depender da ordem das chaves."""
    canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def captura(store, request):
    submission_id = request.get("submission_id", "") if isinstance(request, dict) else ""
    if isinstance(request, dict) and isinstance(request.get("consent"), dict) and request["consent"].get("granted") is not True:
        return _error("consent_required", submission_id)
    if not validar_request(request):
        return _error("invalid_request", submission_id)
    current_fingerprint = fingerprint(request)
    if submission_id in store:
        if store[submission_id].get("opt_out"):
            return {"contract": CONTRACT, "status": "suppressed", "submission_id": submission_id, "sequence_state": "opt_out"}
        if store[submission_id]["fingerprint"] != current_fingerprint:
            return {"contract": CONTRACT, "status": "rejected", "submission_id": submission_id, "error": {"code": "duplicate_payload_conflict", "message": "O submission_id já foi usado com outro conteúdo."}}
        return {"contract": CONTRACT, "status": "duplicate", "submission_id": submission_id, "sequence_state": "pending"}
    store[submission_id] = {"request": request, "fingerprint": current_fingerprint, "sequence_state": "pending", "opt_out": False}
    return {"contract": CONTRACT, "status": "accepted", "submission_id": request["submission_id"], "sequence_state": "pending"}


def main():
    agora = datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc).isoformat()
    request = {
        "contract": CONTRACT,
        "submission_id": "synthetic-10e-0001",
        "product": "tipos",
        "person": {"name": "Pessoa Sintética", "email": "sintetico@example.invalid"},
        "result": {"code": "INTJ", "gender": "F"},
        "scores": {"E": 2, "I": 5},
        "consent": {"granted": True, "captured_at": agora, "purpose": "resultado_e_sequencia_supleno", "version": "1"},
        "attribution": {"utm_source": "sintetico", "utm_medium": "teste", "utm_campaign": "fase-10e", "origin": "local"},
        "opt_out": False,
    }
    store = {}
    accepted = captura(store, request)
    duplicate = captura(store, request)
    store[request["submission_id"]]["opt_out"] = True
    suppressed = {"contract": CONTRACT, "status": "suppressed", "submission_id": request["submission_id"], "sequence_state": "opt_out"}
    print(json.dumps({
        "contrato": CONTRACT,
        "rede_real": False,
        "captura": accepted,
        "duplicata": duplicate,
        "opt_out": suppressed,
        "sequencia": SEQUENCE,
        "exportacao": {"formato": "json", "registros": len(store), "inclui": ["submission_id", "product", "result", "attribution", "sequence_state", "opt_out"]},
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
