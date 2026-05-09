from __future__ import annotations

import json
import os
import pathlib
import re
import time
import uuid
from typing import Any, Optional, TypedDict

import httpx
from langgraph.graph import END, StateGraph
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.confidence import ConfidenceInputs, deterministic_score, fuse
from src.db import dead_letter as db_dead_letter
from src.db import get_run, init_db, save_run
from src.guards import detect_injection
from src.llm.base import LLM
from src.routing import decide
from src.tracing import StageLog, iso8601_utc
from src.validation import validate_or_repair


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "materials" / "schemas"
EXTRACTION_SCHEMA = json.loads(
    (SCHEMA_DIR / "scenario2_contract_extraction_schema.json").read_text(encoding="utf-8")
)
RUN_RESULT_SCHEMA = json.loads(
    (SCHEMA_DIR / "agent_run_result_schema.json").read_text(encoding="utf-8")
)
PROMPT_TEMPLATE = (
    REPO_ROOT / "solution" / "src" / "prompts" / "scenario2_contract.txt"
).read_text(encoding="utf-8")
REQUIRED_FIELDS = ["contract_type", "parties", "effective_date", "term", "governing_law"]


class AgentState(TypedDict, total=False):
    trace_id: str
    document_id: str
    document_text: str
    hint: Optional[str]
    llm: Any
    sor_url: str
    out_dir: Optional[str]
    started_at: str
    log: list
    extraction: dict
    confidence: float
    next: str
    branch: str
    dl_reason: str
    evidence_verified: bool
    unverifiable_count: int
    missing_required: int
    injection_penalty: float
    injection_reasons: list[str]


def ingest(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("ingest")
    log.ok(
        idx,
        {
            "document_id": state["document_id"],
            "len": len(state["document_text"]),
        },
    )
    state["next"] = "llm_extract"
    state["log"] = log.dump()
    return state


def llm_extract(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("llm_extract")
    try:
        system, user_template = PROMPT_TEMPLATE.split("---USER---", 1)
        user = user_template.format(
            hint=state.get("hint") or "",
            document_text=state["document_text"],
        )
        resp = state["llm"].complete_json(
            system,
            user,
            temperature=0.0,
            hint=state.get("hint"),
        )
        parsed = resp.parsed if isinstance(resp.parsed, dict) else {}
        state["extraction"] = parsed
        
        # Detect injection signals in the document text
        injection_penalty, injection_reasons = detect_injection(state["document_text"])
        state["injection_penalty"] = injection_penalty
        state["injection_reasons"] = injection_reasons
        
        state["next"] = "evidence_check"
        log.ok(idx, {"fields": list(parsed)})
    except Exception as exc:
        log.fail(idx, str(exc))
        state["_dl_reason"] = str(exc)
        state["dl_reason"] = str(exc)
        state["injection_penalty"] = 0.0
        state["injection_reasons"] = []
        state["next"] = "dead_letter"
    state["log"] = log.dump()
    return state


def evidence_check(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("evidence_check")
    extraction = state.get("extraction") or {}
    document_text = state["document_text"]
    unverifiable = 0

    for value in extraction.values():
        if isinstance(value, dict) and "source_quote" in value:
            quote = value.get("source_quote")
            if quote and not _evidence_in_text(str(quote), document_text):
                unverifiable += 1

    for party in extraction.get("parties", []) if isinstance(extraction, dict) else []:
        if isinstance(party, dict) and "source_quote" in party:
            quote = party.get("source_quote")
            if quote and not _evidence_in_text(str(quote), document_text):
                unverifiable += 1

    state["evidence_verified"] = unverifiable == 0
    state["unverifiable_count"] = unverifiable
    state["next"] = "validate"
    log.ok(
        idx,
        {
            "evidence_verified": state["evidence_verified"],
            "unverifiable_count": unverifiable,
        },
    )
    state["log"] = log.dump()
    return state


def validate(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("validate")
    extraction = _with_schema_fields(state.get("extraction") or {}, state["document_id"])
    ok, repaired, err = validate_or_repair(
        extraction,
        EXTRACTION_SCHEMA,
        state["llm"],
    )
    if not ok:
        reason = f"schema invalid: {err}"
        log.fail(idx, reason)
        state["_dl_reason"] = reason
        state["dl_reason"] = reason
        state["next"] = "dead_letter"
    else:
        state["extraction"] = repaired
        log.ok(idx, {"schema": "valid"})
        state["next"] = "compute_confidence"
    state["log"] = log.dump()
    return state


def compute_confidence(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("compute_confidence")
    ext = state["extraction"]
    missing = sum(1 for key in REQUIRED_FIELDS if not ext.get(key))
    state["missing_required"] = missing
    det = deterministic_score(ext, REQUIRED_FIELDS)
    llm_score = float(ext.get("self_overall_confidence", 0.0))
    penalties = [
        0.10 * state.get("unverifiable_count", 0),
        0.15 * missing,
        state.get("injection_penalty", 0.0),
    ]
    state["confidence"] = fuse(ConfidenceInputs(det, llm_score, penalties))
    state["next"] = "route"
    log.ok(
        idx,
        {
            "det": det,
            "llm": llm_score,
            "fused": state["confidence"],
            "injection_penalty": state.get("injection_penalty", 0.0),
            "injection_reasons": state.get("injection_reasons", []),
        },
    )
    state["log"] = log.dump()
    return state


def route(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("route")
    flagged = bool(state["extraction"].get("review_reasons"))
    branch = decide(
        state["confidence"],
        missing_required=state.get("missing_required", 0),
        evidence_verified=state.get("evidence_verified", True),
        model_flagged=flagged,
    )
    state["_branch"] = branch
    state["branch"] = branch
    state["next"] = branch
    log.ok(idx, {"branch": branch})
    state["log"] = log.dump()
    return state


def call_sor(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("call_sor")
    body = {"document_id": state["document_id"], **state["extraction"]}
    try:
        resp = _post_with_retry(state["sor_url"] + "/contracts", body)
        state["extraction"]["sor_id"] = resp["sor_id"]
        state["_branch"] = "complete"
        state["branch"] = "complete"
        state["next"] = "persist"
        log.ok(idx, {"sor_id": resp["sor_id"]})
    except RetryError as exc:
        last = exc.last_attempt.exception()
        status = getattr(getattr(last, "response", None), "status_code", "?")
        state["_dl_reason"] = f"sor_error: server {status}"
        state["_branch"] = "dead_letter"
        state["dl_reason"] = state["_dl_reason"]
        state["branch"] = "dead_letter"
        state["next"] = "dead_letter"
        log.fail(idx, state["_dl_reason"])
    except httpx.HTTPStatusError as exc:
        status = getattr(exc.response, "status_code", "?")
        state["_dl_reason"] = f"sor_error: server {status}"
        state["_branch"] = "dead_letter"
        state["dl_reason"] = state["_dl_reason"]
        state["branch"] = "dead_letter"
        state["next"] = "dead_letter"
        log.fail(idx, state["_dl_reason"])
    except Exception as exc:
        state["_dl_reason"] = f"sor_error: {exc}"
        state["_branch"] = "dead_letter"
        state["dl_reason"] = state["_dl_reason"]
        state["branch"] = "dead_letter"
        state["next"] = "dead_letter"
        log.fail(idx, state["_dl_reason"])
    state["log"] = log.dump()
    return state


def dead_letter(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("dead_letter")
    reason = state.get("dl_reason") or state.get("_dl_reason", "unknown")
    payload = {
        "document_id": state["document_id"],
        "text": state["document_text"],
        "hint": state.get("hint"),
    }
    db_dead_letter(state["trace_id"], reason, payload, iso8601_utc())
    state["_branch"] = "dead_letter"
    state["branch"] = "dead_letter"
    state["next"] = "persist"
    log.ok(idx, {"reason": reason})
    state["log"] = log.dump()
    return state


def persist(state: AgentState) -> AgentState:
    log = _get_log(state)
    idx = log.start("persist")
    branch = state.get("branch") or state.get("_branch", "needs_review")
    status = "completed" if branch == "complete" else "needs_review" if branch == "needs_review" else "failed"
    result = {
        "trace_id": state["trace_id"],
        "document_id": state["document_id"],
        "status": status,
        "confidence": state.get("confidence", 0.0),
        "decision": {
            "branch": branch,
            "needs_review": branch == "needs_review",
            "sor_id": state.get("extraction", {}).get("sor_id"),
        },
        "log": log.dump(),
        "started_at": state["started_at"],
        "finished_at": iso8601_utc(),
    }
    summary = {"status": status}
    try:
        from jsonschema import Draft202012Validator

        Draft202012Validator(RUN_RESULT_SCHEMA).validate(result)
    except Exception as exc:
        summary["persist_warn"] = str(exc)[:120]

    log.ok(idx, summary)
    state["log"] = log.dump()
    result["log"] = state["log"]

    save_run(
        {
            **result,
            "request_payload": {
                "document_id": state["document_id"],
                "hint": state.get("hint"),
            },
            "artifact": state.get("extraction", {}),
        }
    )
    if state.get("out_dir"):
        out = pathlib.Path(state["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "agent_run_result.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
        (out / "artifact.json").write_text(
            json.dumps(state.get("extraction", {}), indent=2),
            encoding="utf-8",
        )
        (out / "trace.log").write_text(log.to_jsonl(), encoding="utf-8")
    return state


def _get_log(state: AgentState) -> StageLog:
    log = state.setdefault("_log", StageLog(state["trace_id"]))
    if not log.events and state.get("log"):
        log.events = list(state["log"])
    return log


def _with_schema_fields(extraction: dict, document_id: str) -> dict:
    enriched = dict(extraction)
    enriched.setdefault("document_id", document_id)
    enriched.setdefault("fields", _fields_from_extraction(enriched))
    enriched.setdefault(
        "overall_confidence",
        enriched.get("self_overall_confidence", 0.0),
    )
    enriched.setdefault("needs_review", bool(enriched.get("review_reasons")))
    return enriched


def _fields_from_extraction(extraction: dict) -> list[dict[str, Any]]:
    fields = []
    confidence = float(extraction.get("self_overall_confidence", 0.0))
    for name in REQUIRED_FIELDS:
        value = extraction.get(name)
        evidence = None
        raw_value = value
        if isinstance(value, dict):
            evidence = value.get("source_quote")
            raw_value = value.get("value")
        fields.append(
            {
                "name": name,
                "value": raw_value,
                "confidence": confidence,
                "evidence": evidence or "",
            }
        )
    return fields


def _evidence_in_text(quote: str, document_text: str) -> bool:
    chunks = re.split(r"\.{3,}", quote.strip())
    pos = 0
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        found_at = document_text.lower().find(chunk.lower(), pos)
        if found_at < 0:
            return False
        pos = found_at + len(chunk)
    return True


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2.0),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    reraise=True,
)
def _post_with_retry(url, body):
    response = httpx.post(url, json=body, timeout=10.0)
    if response.status_code >= 500:
        response.raise_for_status()
    response.raise_for_status()
    return response.json()


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("ingest", ingest)
    g.add_node("llm_extract", llm_extract)
    g.add_node("evidence_check", evidence_check)
    g.add_node("validate", validate)
    g.add_node("compute_confidence", compute_confidence)
    g.add_node("route", route)
    g.add_node("call_sor", call_sor)
    g.add_node("dead_letter", dead_letter)
    g.add_node("persist", persist)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "llm_extract")
    g.add_edge("llm_extract", "evidence_check")
    g.add_edge("evidence_check", "validate")
    g.add_conditional_edges(
        "validate",
        lambda state: state["next"],
        {
            "compute_confidence": "compute_confidence",
            "dead_letter": "dead_letter",
        },
    )
    g.add_edge("compute_confidence", "route")
    g.add_conditional_edges(
        "route",
        lambda state: state["next"],
        {
            "complete": "call_sor",
            "needs_review": "persist",
            "dead_letter": "dead_letter",
        },
    )
    g.add_conditional_edges(
        "call_sor",
        lambda state: state["next"],
        {
            "persist": "persist",
            "dead_letter": "dead_letter",
        },
    )
    g.add_edge("dead_letter", "persist")
    g.add_edge("persist", END)
    return g.compile()


_APP = None


def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP


def run_extract(
    *,
    document_id,
    document_text,
    hint,
    llm,
    sor_url,
    out_dir=None,
    trace_id=None,
) -> dict:
    init_db()
    trace_id = trace_id or "trc_" + uuid.uuid4().hex[:12]
    state: AgentState = {
        "trace_id": trace_id,
        "document_id": document_id,
        "document_text": document_text,
        "hint": hint,
        "llm": llm,
        "sor_url": sor_url,
        "out_dir": out_dir,
        "started_at": iso8601_utc(),
        "log": [],
    }
    get_app().invoke(state)
    return get_run(trace_id)
