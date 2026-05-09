from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfidenceInputs:
    deterministic: float
    llm: float
    penalties: list[float] = field(default_factory=list)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def fuse(inputs: ConfidenceInputs) -> float:
    fused = 0.6 * inputs.deterministic + 0.4 * inputs.llm - sum(inputs.penalties)
    return round(clamp01(fused), 3)


def deterministic_score(extraction: dict, required_fields: list[str]) -> float:
    score = 1.0

    for field_name in required_fields:
        if extraction.get(field_name) in (None, "", [], {}):
            score -= 0.15

    bonus = 0.0
    for value in extraction.values():
        if isinstance(value, dict) and value.get("source_quote"):
            bonus += 0.02
            if bonus >= 0.10:
                bonus = 0.10
                break

    return round(clamp01(score + bonus), 3)
