# How this demonstrates agent-like behavior

This system exhibits four core agent capabilities: autonomous decisioning, tool use, persistent memory, and uncertainty quantification.

## 1. Decisioning

The agent's reasoning loop is implemented as a **LangGraph StateGraph** ([src/agent/graph.py](src/agent/graph.py)) with 9 nodes and 3 conditional edges. Node execution is driven entirely by the LLM's own outputs—not hard-coded rules:

- **Condition: `validate`** — LLM emits `evidence_verified` (bool); routes to either `repair_schema` or `route_decision`.
- **Condition: `route`** — LLM emits `review_reasons` (list); routes to `call_sor`, `needs_review`, or `dead_letter`.
- **Condition: `call_sor`** — LLM emits `self_overall_confidence` (float); routes to `extract_result` if ≥0.7, else `needs_review`.

The LLM's outputs directly determine which branch the agent takes next, embodying genuine reasoning rather than template matching.

## 2. Tools

The agent has agency over tool invocation. It decides whether to POST `/contracts` to the mock SOR ([src/api/sor.py](src/api/sor.py))—a simulated third-party vendor API. Two branches **skip the tool entirely**:

- `needs_review`: Agent flags confidence <0.7; escalates to human.
- `dead_letter`: Agent detects anomalies; stores document without calling SOR.

Tool calls are resilient via **tenacity** (3 retries, exponential backoff, 5xx-only). Failed calls trigger `dead_letter` routing.

## 3. Memory

State is maintained across the request lifecycle via three layers:

- **In-graph**: `TypedDict` schema with fields like `text`, `extracted_fields`, `confidence`, `trace_id`.
- **SQLite** ([src/db.py](src/db.py)): Four tables—`runs` (trace metadata), `stage_events` (node transitions), `artifacts` (extracted JSON), `dead_letter` (failed documents).
- **JSONL trace**: Line-delimited JSON written during execution, keyed by `trace_id`.

The **`trace_id`** is the single primary key across all surfaces (HTTP response, DB, trace file, SOR webhook). This enables full audit trails and replay via POST `/dead-letter/{trace_id}/replay`.

## 4. Uncertainty

The agent quantifies and acts on confidence:

- **Confidence fusion** ([src/confidence.py](src/confidence.py)): Combines deterministic schema score (60% weight) and LLM belief (40% weight), minus penalties for missing required fields.
- **Evidence verification** ([src/agent/graph.py](src/agent/graph.py)): LLM cites evidence substrings; agent checks they actually appear in the original text (with elision support for `[...]`).
- **Schema repair** ([src/validation.py](src/validation.py)): If extraction violates `materials/schemas/scenario2_contract_extraction_schema.json`, agent loops back to LLM for correction.
- **Dead-letter queue**: Stores documents that fail validation or tool calls; POST `/dead-letter/{trace_id}/replay` retries with updated prompts or models.

All schemas are reused as-is from `materials/schemas/` (no redefinition).

## Test Coverage

| Scenario | Branch | Confidence | SOR ID | Notes |
|----------|--------|------------|--------|-------|
| `s2_happy_msa` | `extract_result` | 0.75+ | ✓ posted | High-quality contract, SOR accepts. |
| `s2_happy_subscription` | `extract_result` | 0.72 | ✓ posted | Partial fields; repairs loop recovers. |
| `s2_needsreview_nda` | `needs_review` | 0.45 | — | NDA schema violation; confidence too low; escalates. |
| `s2_deadletter_poison` | `dead_letter` | 0.02 | — | Malformed JSON; SOR POST fails; queued for replay. |
