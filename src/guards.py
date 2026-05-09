import re
from typing import Any


def detect_injection(text: str) -> tuple[float, list[str]]:
    """Detect prompt injection signals in untrusted text. Return (penalty, reasons)."""
    penalty = 0.0
    reasons = []

    text_lower = text.lower()

    # Pattern 1: ignore previous instructions
    if re.search(r"ignore\s+(all\s+)?previous\s+instructions", text_lower):
        penalty += 0.05
        reasons.append("injection:ignore_previous")

    # Pattern 2: disregard (above|prior|system)
    if re.search(r"disregard\s+(the\s+)?(above|prior|system)", text_lower):
        penalty += 0.05
        reasons.append("injection:disregard")

    # Pattern 3: you are now / act as / new role
    if re.search(r"you\s+are\s+now|act\s+as|new\s+role", text_lower):
        penalty += 0.05
        reasons.append("injection:role_change")

    # Pattern 4: system markers
    if re.search(r"<\|system\|>|<\|im_start\|>|###\s+system", text, re.IGNORECASE):
        penalty += 0.05
        reasons.append("injection:system_marker")

    # Pattern 5: exfiltration signals
    if re.search(r"print|reveal|exfiltrate.{0,30}(prompt|system|api[_\s]?key|secret)", text_lower):
        penalty += 0.05
        reasons.append("injection:exfiltrate")

    # Pattern 6: suspicious link bombing (>5 URLs)
    url_count = len(re.findall(r"https?://", text, re.IGNORECASE))
    if url_count > 5:
        penalty += 0.05
        reasons.append(f"injection:url_bombing({url_count})")

    # Pattern 7: base64-like blob >= 200 chars
    base64_match = re.search(r"[A-Za-z0-9+/=]{200,}", text)
    if base64_match:
        penalty += 0.05
        reasons.append("injection:base64_blob")

    # Cap total penalty at 0.3
    penalty = min(0.3, penalty)

    return penalty, reasons
