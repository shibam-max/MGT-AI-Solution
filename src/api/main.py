from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agent.graph import run_extract
from src import db


class ExtractRequest(BaseModel):
    document_id: str
    text: str
    hint: Optional[str] = None


def _make_llm():
    name = os.environ.get("AGENT_LLM", "mock").lower()
    if name == "ollama":
        from src.llm.ollama_client import OllamaClient

        return OllamaClient()
    if name == "openai":
        from src.llm.openai_client import OpenAIClient

        return OpenAIClient()
    from src.llm.mock_client import MockLLM

    return MockLLM()


app = FastAPI(title="Document Automation Agent")


@app.on_event("startup")
def _startup() -> None:
    from src.db import init_db

    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agent/extract")
def extract(req: ExtractRequest) -> dict:
    result = run_extract(
        document_id=req.document_id,
        document_text=req.text,
        hint=req.hint,
        llm=_make_llm(),
        sor_url=os.environ.get("SOR_URL", "http://localhost:8001"),
    )
    if result is None:
        raise HTTPException(status_code=500, detail="run not persisted")
    return result


@app.get("/runs/{trace_id}")
def get_run(trace_id: str) -> dict:
    result = db.get_run(trace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@app.get("/runs/{trace_id}/events")
def get_events(trace_id: str) -> list[dict]:
    return db.get_events(trace_id)


@app.get("/dead-letter")
def list_dead_letter() -> list[dict]:
    return db.list_dead_letter()


@app.post("/dead-letter/{trace_id}/replay")
def replay_dead_letter(trace_id: str) -> dict:
    payload = db.replay_dead_letter(trace_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="dead letter not found")
    return payload
