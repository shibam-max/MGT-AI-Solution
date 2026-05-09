import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator

# Load schema
schema_path = Path("../materials/schemas/scenario2_contract_extraction_schema.json")
schema = json.loads(schema_path.read_text())

# Mock extraction output from LLM (what llm_extract produces)
extraction = {
    "contract_type": "Master Services Agreement",
    "parties": ["Company A", "Company B"],
    "effective_date": "2024-01-01",
    "term": "2 years",
    "governing_law": "State of NY",
    "self_overall_confidence": 0.85,
    "review_reasons": [],
}

# Transform via _with_schema_fields logic (what validate node does)
payload = {
    "document_id": "test_doc",
    "fields": [
        {"name": k, "value": v, "confidence": 0.85, "evidence": "extracted"}
        for k, v in extraction.items()
        if k not in ["self_overall_confidence", "review_reasons"]
    ],
    "overall_confidence": 0.85,
    "needs_review": False,
    "review_reasons": [],
}

# Validate
validator = Draft202012Validator(schema)
errors = list(validator.iter_errors(payload))

if errors:
    print("❌ SCHEMA VALIDATION FAILED:")
    for e in errors:
        print(f"  - {e.message}")
    sys.exit(1)
else:
    print("✅ SCHEMA VALIDATION PASSED")
    print(f"  document_id: {payload['document_id']}")
    print(f"  fields count: {len(payload['fields'])}")
    print(f"  confidence: {payload['overall_confidence']}")
    print(f"  needs_review: {payload['needs_review']}")
    print("\nPayload structure matches schema requirements:")
    print(f"  - Required fields present: ✓")
    print(f"  - Fields array structure: ✓")
    print(f"  - Confidence range [0-1]: ✓")
