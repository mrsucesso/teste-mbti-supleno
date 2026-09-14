#!/usr/bin/env python3
"""Simulador E2E local do contrato Supleno Integracao v1.

Somente dados sintéticos e memória do processo. Não importa cliente HTTP,
não abre socket e não conhece URL de transporte.
"""
import json
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

CONTRACT = "supleno.integracao.v1"
SEQUENCE = ["imediato", "d1", "d3", "d5", "d7"]
SEQUENCE_STATES = {"pending", "sending", "sent", "uncertain", "opt_out"}
PRODUCTS = {"tipos", "estilos", "tracos"}
ROOT_FIELDS = {"contract", "submission_id", "product", "person", "result", "scores", "consent", "attribution", "honeypot", "opt_out", "access_token"}
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
    return (_valid_text(value, 254) and
            re.fullmatch(r"(?=.{1,254}$)[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}", value) is not None)


def _valid_name(value):
    return (_valid_text(value, 100) and bool(value) and
            all(char.isalpha() or unicodedata.category(char).startswith("M") or char in " '.-" for char in value))


def _integer_in_range(value, minimum, maximum):
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _valid_trait(value):
    if not isinstance(value, dict) or set(value) != {"sum", "percent", "faixa"}:
        return False
    if not _integer_in_range(value["sum"], 5, 25):
        return False
    expected_percent = round(((value["sum"] - 5) / 20) * 100)
    expected_range = "baixo" if expected_percent < 34 else "medio" if expected_percent < 67 else "alto"
    return value["percent"] == expected_percent and value["faixa"] == expected_range


def _valid_product_data(product, result, scores):
    if not isinstance(result, dict) or not isinstance(scores, dict):
        return False
    if product == "tipos":
        keys = {"E", "I", "S", "N", "T", "F", "J", "P"}
        if set(result) != {"code", "gender"} or set(scores) != keys:
            return False
        if result["gender"] not in {"M", "F"} or not all(_integer_in_range(scores[key], 0, 7) for key in keys):
            return False
        if not all(scores[a] + scores[b] == 7 for a, b in (("E", "I"), ("S", "N"), ("T", "F"), ("J", "P"))):
            return False
        expected = (("E" if scores["E"] >= scores["I"] else "I") +
                    ("S" if scores["S"] >= scores["N"] else "N") +
                    ("T" if scores["T"] >= scores["F"] else "F") +
                    ("J" if scores["J"] >= scores["P"] else "P"))
        return result["code"] == expected
    if product == "estilos":
        keys = ("D", "I", "S", "C")
        if set(result) != {"code"} or set(scores) != set(keys):
            return False
        if not all(_integer_in_range(scores[key], 0, 24) for key in keys) or sum(scores.values()) != 24:
            return False
        expected = max(keys, key=lambda key: scores[key])
        return result["code"] == expected
    keys = {"SO", "AN", "OM", "TE", "CO"}
    return (set(result) == keys and set(scores) == keys and
            all(_valid_trait(scores[key]) and result[key] == scores[key] for key in keys))


def validar_request(request):
    if not isinstance(request, dict) or set(request) != ROOT_FIELDS:
        return False
    if request.get("contract") != CONTRACT or not isinstance(request.get("submission_id"), str) or not 1 <= len(request["submission_id"]) <= 128:
        return False
    if request.get("product") not in PRODUCTS:
        return False
    if not isinstance(request.get("access_token"), str) or not 1 <= len(request["access_token"]) <= 256:
        return False
    if not _valid_text(request.get("honeypot"), 256):
        return False
    person = request.get("person")
    if (not isinstance(person, dict) or set(person) - {"name", "email", "whatsapp"}
            or not {"name", "email"}.issubset(person) or not _valid_name(person.get("name"))
            or not _valid_email(person.get("email"))):
        return False
    if ("whatsapp" in person and
            (not _valid_text(person["whatsapp"], 20) or re.fullmatch(r"[0-9 ()+\-]*", person["whatsapp"]) is None)):
        return False
    consent = request.get("consent")
    if not isinstance(consent, dict) or set(consent) != {"granted", "captured_at", "purpose", "version"} or consent.get("granted") is not True or consent.get("purpose") != "resultado_e_sequencia_supleno" or not _valid_text(consent.get("version"), 32) or not consent["version"]:
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
    if request["opt_out"] is not False:
        return False
    return _valid_product_data(request["product"], request["result"], request["scores"])


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
        state = store[submission_id]["sequence_state"]
        if state not in SEQUENCE_STATES:
            return _error("invalid_sequence_state", submission_id)
        return {"contract": CONTRACT, "status": "duplicate", "submission_id": submission_id,
                "sequence_state": state}
    store[submission_id] = {"request": request, "fingerprint": current_fingerprint, "sequence_state": "pending", "opt_out": False}
    return {"contract": CONTRACT, "status": "accepted", "submission_id": request["submission_id"], "sequence_state": "pending"}


def main():
    agora = datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc).isoformat()
    request = {
        "contract": CONTRACT,
        "submission_id": "synthetic-10e-0001",
        "access_token": "test-access-token",
        "product": "tipos",
        "person": {"name": "Pessoa Sintética", "email": "sintetico@example.invalid"},
        "result": {"code": "INTJ", "gender": "F"},
        "scores": {"E": 2, "I": 5, "S": 3, "N": 4, "T": 4, "F": 3, "J": 5, "P": 2},
        "consent": {"granted": True, "captured_at": agora, "purpose": "resultado_e_sequencia_supleno", "version": "1"},
        "attribution": {"utm_source": "sintetico", "utm_medium": "teste", "utm_campaign": "fase-10e", "origin": "local"},
        "honeypot": "",
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
