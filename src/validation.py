from __future__ import annotations

import json
from typing import Optional, Tuple

from jsonschema import Draft202012Validator


def validate_or_repair(
    payload: dict,
    schema: dict,
    llm,
    *,
    max_repairs: int = 1,
) -> Tuple[bool, dict, Optional[str]]:
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    except Exception as exc:
        return False, payload, str(exc)

    if not errors:
        return True, payload, None

    error_str = "; ".join(error.message for error in errors)

    if max_repairs <= 0 or llm is None:
        return False, payload, error_str

    system = "You repair JSON to match a JSON Schema. Output ONLY a valid JSON object."
    user = (
        "SCHEMA:\n"
        + json.dumps(schema)
        + "\n\nINVALID JSON:\n"
        + json.dumps(payload)
        + "\n\nVALIDATION ERROR:\n"
        + error_str
    )

    try:
        resp = llm.complete_json(system, user, temperature=0.0)
    except Exception as exc:
        return False, payload, str(exc)

    if isinstance(resp.parsed, dict):
        return validate_or_repair(
            resp.parsed,
            schema,
            llm,
            max_repairs=max_repairs - 1,
        )

    return False, payload, error_str
