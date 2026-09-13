#!/usr/bin/env python3
"""Simulador E2E local do contrato Supleno Integracao v1.

Somente dados sintéticos e memória do processo. Não importa cliente HTTP,
não abre socket e não conhece URL de transporte.
"""
import json
from datetime import datetime, timezone

CONTRACT = "supleno.integracao.v1"
SEQUENCE = ["imediato", "d1", "d3", "d5", "d7"]


def captura(store, request):
    if request["consent"]["granted"] is not True:
        return {"contract": CONTRACT, "status": "rejected", "submission_id": request["submission_id"], "error": {"code": "consent_required", "message": "Consentimento explícito é obrigatório."}}
    if request["submission_id"] in store:
        return {"contract": CONTRACT, "status": "duplicate", "submission_id": request["submission_id"], "sequence_state": "pending"}
    store[request["submission_id"]] = {"request": request, "sequence_state": "pending", "opt_out": False}
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
