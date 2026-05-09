from __future__ import annotations

import os
from typing import Any, Optional

from src.llm.base import LLMResponse, safe_json_loads


class OpenAIClient:
    name = "openai"

    def __init__(self, model: Optional[str] = None) -> None:
        import openai

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required to use OpenAIClient.")

        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")

        if azure_endpoint and azure_api_version:
            self.client: Any = openai.AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_version=azure_api_version,
                api_key=api_key,
            )
        else:
            self.client = openai.OpenAI(api_key=api_key)

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

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        text = resp.choices[0].message.content or ""
        parsed = safe_json_loads(text)
        usage = getattr(resp, "usage", None)

        return LLMResponse(
            text=text,
            parsed=parsed,
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
