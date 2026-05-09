from __future__ import annotations

import json
from datetime import datetime, timezone
from time import perf_counter


def iso8601_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StageLog:
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.events: list[dict] = []

    def start(self, name: str) -> int:
        self.events.append(
            {
                "name": name,
                "status": "started",
                "ts": iso8601_utc(),
                "_t0": perf_counter(),
            }
        )
        return len(self.events) - 1

    def ok(self, idx: int, summary=None) -> None:
        now = perf_counter()
        event = self.events[idx]
        event["status"] = "ok"
        event["latency_ms"] = int((now - event["_t0"]) * 1000)
        event["summary"] = summary
        del event["_t0"]

    def fail(self, idx: int, reason: str) -> None:
        now = perf_counter()
        event = self.events[idx]
        event["status"] = "fail"
        event["latency_ms"] = int((now - event["_t0"]) * 1000)
        event["reason"] = reason
        del event["_t0"]

    def dump(self) -> list[dict]:
        return [{key: value for key, value in event.items() if key != "_t0"} for event in self.events]

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(event, ensure_ascii=False) for event in self.dump())
