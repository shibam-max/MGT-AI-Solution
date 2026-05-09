from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class LLMResponse:
    text: str
    parsed: Optional[dict]
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


def safe_json_loads(text: str) -> Optional[dict]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        retry_text = re.sub(r",\s*([\]}])", r"\1", cleaned)
        try:
            value = json.loads(retry_text)
        except json.JSONDecodeError:
            return None

    return value if isinstance(value, dict) else None


class LLM(Protocol):
    def complete_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        hint: Optional[str] = None,
    ) -> LLMResponse: ...
