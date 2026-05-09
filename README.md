# Solution: Agent-Driven Contract Extraction

LangGraph agent with LLM-driven decisioning, confidence fusion, tool-call autonomy, and dead-letter replay for contract field extraction.

## What the brief asked for and where it lives

| Requirement | File(s) |
|-------------|---------|
| Real LLM integration | `src/llm/{openai_client.py, ollama_client.py, mock_client.py}` |
| Orchestration framework | `src/agent/graph.py` (LangGraph StateGraph, 9 nodes, 3 conditional edges) |
| HTTP API trigger | `src/api/main.py` (`POST /agent/extract`) |
| Persistence | `src/db.py` (SQLite: runs, stage_events, artifacts, dead_letter) |
| Separate service call | `src/api/sor.py` (mock SOR POST /contracts) |
| Retry logic | `src/api/sor.py` (tenacity, 3x exponential backoff, 5xx-only) |
| Dead-letter + replay | `src/db.py`, `src/api/main.py` (POST `/dead-letter/{trace_id}/replay`) |
| Write-ups | `AGENT_BEHAVIOR.md`, `ARCHITECTURE.md` |
| Schemas | `../materials/schemas/scenario2_contract_extraction_schema.json` (reused as-is) |

## Why Scenario 2

Scenario 2 (contract extraction) is chosen because it exercises the full agent stack: high-stakes decisioning (confidence <0.7 escalates to humans), deterministic + LLM confidence fusion, schema-aware repair loops, and realistic tool-failure recovery. It demonstrates agent autonomy more richly than lead scoring or research summarization.

## Quickstart

**1. Install**
```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
```

**2. Pick LLM**
- **Ollama** (default): `ollama pull llama3.1:8b-instruct` then `$env:AGENT_LLM='ollama'`
- **OpenAI**: `$env:OPENAI_API_KEY='sk-...'`
- **Mock** (tests): No setup; used by default in tests.

**3. CLI demo**
```bash
python cli.py demo      # Run sample contract, print trace
python cli.py runs      # List all runs with confidence
python cli.py dlq       # Show dead-letter queue
```

**4. HTTP API (3 terminals)**
```bash
# Terminal 1: SOR mock service (port 8001)
python src/api/sor.py

# Terminal 2: Main agent API (port 8000)
python src/api/main.py

# Terminal 3: Smoke test
python smoke_http.py
```

## HTTP API

| Method | Endpoint | Payload | Response |
|--------|----------|---------|----------|
| POST | `/agent/extract` | `{document_id, text, hint}` | `{trace_id, confidence, sor_id, extracted_fields}` |
| GET | `/runs/{trace_id}` | — | `{trace_id, status, confidence, artifacts}` |
| GET | `/runs/{trace_id}/events` | — | `[{name, stage, timestamp, ...}]` |
| POST | `/dead-letter/{trace_id}/replay` | `{updated_model?}` | `{trace_id, new_sor_id, ...}` |
| GET | `/dead-letter` | — | `[{trace_id, reason, text_preview}]` |
| GET | `/health` | — | `{status, db, llm_client}` |

## CLI Subcommands

| Subcommand | Argument | Output |
|------------|----------|--------|
| `demo` | — | Run scenario2_happy_msa.json; print trace & artifacts. |
| `runs` | `[limit]` | List recent runs: trace_id, status, confidence, sor_id. |
| `dlq` | — | List dead-letter entries with reason & text preview. |
| `replay` | `trace_id` | Replay a dead-letter trace; return new sor_id or status. |
| `trace` | `trace_id` | Pretty-print the JSONL trace with stage breakdown. |
| `export` | `[format]` | Export all runs as JSON or CSV. |

## Sample Scenario 2 Runs

| Input | Branch | Confidence | SOR ID | Notes |
|-------|--------|------------|--------|-------|
| `s2_happy_msa` | `extract_result` | 0.76 | ✓ | High-quality MSA; SOR accepts. |
| `s2_happy_subscription` | `extract_result` | 0.72 | ✓ | Partial fields; repair loop recovers missing party. |
| `s2_needsreview_nda` | `needs_review` | 0.48 | — | Schema violation; escalates to human. |
| `s2_deadletter_poison` | `dead_letter` | 0.02 | — | Malformed text; SOR POST fails; queued. |

## Tests

```bash
python -m unittest discover -s tests -v
```

All tests pass. Coverage includes graph branching, confidence calculations, schema validation, SOR retry logic, and dead-letter replay.

## Repo Layout

```
solution/
  src/
    agent/       graph.py (LangGraph StateGraph, nodes & edges)
    api/         main.py (FastAPI), sor.py (mock SOR)
    llm/         base.py, openai_client.py, ollama_client.py, mock_client.py
    prompts/     scenario2_contract.txt (LLM system prompt)
    db.py        SQLite tables & trace writer
    confidence.py  fusion: 0.6*det + 0.4*llm − penalties
    routing.py     conditional edge logic
    validation.py  schema repair loop
    tracing.py     JSONL trace writer
  tests/           test_graph.py, test_pipeline.py
  cli.py           CLI subcommands
  smoke_http.py    HTTP smoke test (reads MSA, POSTs, GETs events & DLQ)
  requirements.txt
  ARCHITECTURE.md
  AGENT_BEHAVIOR.md
  README.md (this file)
```

## Key Design Decisions

1. **Schemas reused, not redefined**: `scenario2_contract_extraction_schema.json` from `materials/schemas/` is the single source of truth; validation & repair both reference it directly.
2. **Confidence as a first-class decision lever**: Two-source fusion (deterministic + LLM) drives routing; escalation threshold (0.7) is explicit & tunable.
3. **Tool-call autonomy**: Agent decides *whether* to call SOR (needs_review & dead_letter bypass it); tenacity handles transient failures cleanly.
4. **Trace-centric audit**: Single `trace_id` primary key across HTTP response, SQLite, JSONL, and SOR webhook; enables full replay & accountability.
5. **Mock SOR for dev-friendliness**: Separate `src/api/sor.py` service simulates vendor API; tests use MockLLM; no external dependencies required to iterate.

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed stack & [AGENT_BEHAVIOR.md](AGENT_BEHAVIOR.md) for agent capability breakdown.
