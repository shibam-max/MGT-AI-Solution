from __future__ import annotations

import json
from typing import Any, Optional

from src.llm.base import LLMResponse


class MockLLM:
    name = "mock"

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        hint: Optional[str] = None,
    ) -> LLMResponse:
        del system, user, temperature, max_tokens

        if hint == "contract:msa":
            parsed = self._msa()
        elif hint == "contract:subscription":
            parsed = self._subscription()
        elif hint == "contract:nda":
            parsed = self._nda()
        else:
            parsed = self._unknown()

        return LLMResponse(
            text=json.dumps(parsed, indent=2),
            parsed=parsed,
            model="mock",
            prompt_tokens=0,
            completion_tokens=0,
        )

    @staticmethod
    def _party(name: str, role: str, quote: str) -> dict[str, str]:
        return {
            "name": name,
            "role": role,
            "source_quote": quote,
        }

    @staticmethod
    def _field(value: Any, quote: str) -> dict[str, Any]:
        return {
            "value": value,
            "source_quote": quote,
        }

    @classmethod
    def _msa(cls) -> dict[str, Any]:
        return {
            "contract_type": cls._field(
                "Master Services Agreement",
                "This Master Services Agreement",
            ),
            "parties": [
                cls._party(
                    "Northwind Traders",
                    "vendor",
                    "Northwind Analytics LLC",
                ),
                cls._party(
                    "Contoso Ltd",
                    "customer",
                    "Contoso Retail Inc.",
                ),
            ],
            "effective_date": cls._field(
                "2025-01-15",
                "2026-02-15",
            ),
            "governing_law": cls._field(
                "Delaware",
                "the laws of the State of California",
            ),
            "liability_cap_usd": cls._field(
                1_000_000,
                "aggregate liability under this Agreement will not exceed the fees paid by Client",
            ),
            "term": {
                "duration_months": cls._field(
                    24,
                    "continues for twelve (12) months",
                ),
                "auto_renew": cls._field(
                    True,
                    "will automatically renew for successive one (1) year terms",
                ),
                "notice_period_days": cls._field(
                    60,
                    "at least thirty (30) days prior to the end of the then-current term",
                ),
            },
            "self_overall_confidence": 0.92,
            "review_reasons": [],
        }

    @classmethod
    def _subscription(cls) -> dict[str, Any]:
        return {
            "contract_type": cls._field(
                "Subscription Agreement",
                "This Papermind AI subscription agreement governs access to the service.",
            ),
            "parties": [
                cls._party(
                    "Papermind AI",
                    "vendor",
                    "Papermind AI provides the subscription service.",
                )
            ],
            "effective_date": cls._field(
                "2025-03-01",
                "The subscription is effective March 1, 2025.",
            ),
            "governing_law": cls._field(
                "California",
                "This subscription is governed by California law.",
            ),
            "liability_cap_usd": cls._field(
                500_000,
                "Liability shall not exceed USD 500,000.",
            ),
            "term": {
                "duration_months": cls._field(12, "The subscription term is twelve months."),
                "auto_renew": cls._field(True, "The subscription renews automatically."),
                "notice_period_days": cls._field(30, "Non-renewal requires thirty days notice."),
            },
            "self_overall_confidence": 0.95,
            "review_reasons": [],
        }

    @classmethod
    def _nda(cls) -> dict[str, Any]:
        return {
            "contract_type": cls._field(
                "Non-Disclosure Agreement",
                "MUTUAL NON-DISCLOSURE AGREEMENT",
            ),
            "parties": [
                cls._party("Acme Corp", "party", "Acme Manufacturing Co."),
                cls._party("Globex Inc", "party", "PaperMind AI, Inc."),
            ],
            "effective_date": cls._field(None, "2026-01-20"),
            "governing_law": cls._field(None, "the laws of the State of Texas"),
            "liability_cap_usd": cls._field(None, ""),
            "term": {
                "duration_months": cls._field(None, "two (2) years"),
                "auto_renew": cls._field(None, ""),
                "notice_period_days": cls._field(None, ""),
            },
            "self_overall_confidence": 0.55,
            "review_reasons": ["liability cap missing", "ambiguous term"],
        }

    @classmethod
    def _unknown(cls) -> dict[str, Any]:
        return {
            "contract_type": cls._field(None, "The contract type could not be determined."),
            "parties": [],
            "effective_date": cls._field(None, "No effective date was identified."),
            "governing_law": cls._field(None, "No governing law was identified."),
            "liability_cap_usd": cls._field(None, "No liability cap was identified."),
            "term": {
                "duration_months": cls._field(None, "No term duration was identified."),
                "auto_renew": cls._field(None, "No auto-renewal clause was identified."),
                "notice_period_days": cls._field(None, "No notice period was identified."),
            },
            "self_overall_confidence": 0.3,
            "review_reasons": ["unknown contract type"],
        }
