from __future__ import annotations

import random
import secrets
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict


app = FastAPI(title="Mock SOR")
_STORE: dict[str, dict[str, Any]] = {}


class ContractIn(BaseModel):
    document_id: str
    model_config = ConfigDict(extra="allow")


@app.post("/contracts")
def create_contract(payload: ContractIn) -> dict[str, str]:
    if payload.document_id.endswith("_poison"):
        raise HTTPException(status_code=500, detail="poison")

    if payload.document_id.endswith("_flaky") and random.random() < 0.5:
        raise HTTPException(status_code=503, detail="flaky")

    sor_id = "sor_" + secrets.token_hex(5)
    _STORE[sor_id] = payload.model_dump()
    return {"sor_id": sor_id}


@app.get("/contracts/{sor_id}")
def get_contract(sor_id: str) -> dict[str, Any]:
    payload = _STORE.get(sor_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="not found")
    return payload


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
