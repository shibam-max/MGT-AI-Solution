from __future__ import annotations


HIGH = 0.75
LOW = 0.40


def decide(
    confidence: float,
    *,
    missing_required: int = 0,
    evidence_verified: bool = True,
    model_flagged: bool = False,
) -> str:
    if confidence < LOW:
        return "dead_letter"
    if missing_required > 0:
        return "needs_review"
    if not evidence_verified:
        return "needs_review"
    if model_flagged:
        return "needs_review"
    if confidence >= HIGH:
        return "complete"
    return "needs_review"
