from __future__ import annotations

import os
from typing import Optional

import requests

from src.llm.base import LLMResponse, safe_json_loads


class OllamaClient:
    name = "ollama"

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        hint: Optional[str] = None,
    ) -> LLMResponse:
        del hint

        body = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        response = requests.post(f"{self.host}/api/chat", json=body, timeout=120)
        response.raise_for_status()
        data = response.json()
        text = data["message"]["content"]
        parsed = safe_json_loads(text)

        return LLMResponse(
            text=text,
            parsed=parsed,
            model=self.model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )
