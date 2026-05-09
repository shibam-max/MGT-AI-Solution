from __future__ import annotations

import argparse
import json
import os
import pathlib
from typing import Any

import uvicorn

from src.agent.graph import run_extract


ROOT = pathlib.Path(__file__).resolve().parent
CONTRACTS_DIR = ROOT.parent / "materials" / "contracts"


def make_llm(name):
    name = (name or os.environ.get("AGENT_LLM", "mock")).lower()
    if name == "ollama":
        from src.llm.ollama_client import OllamaClient

        return OllamaClient()
    if name == "openai":
        from src.llm.openai_client import OpenAIClient

        return OpenAIClient()
    from src.llm.mock_client import MockLLM

    return MockLLM()


def cmd_extract(args: argparse.Namespace) -> None:
    input_path = pathlib.Path(args.input)
    text = input_path.read_text(encoding="utf-8")
    doc_id = args.doc_id or input_path.stem
    result = run_extract(
        document_id=doc_id,
        document_text=text,
        hint=args.hint,
        llm=make_llm(args.llm),
        sor_url=args.sor_url or os.environ.get("SOR_URL", "http://localhost:8001"),
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("trace_id", "status", "confidence", "decision")
            },
            indent=2,
        )
    )


def cmd_demo(args: argparse.Namespace) -> None:
    scenarios = [
        (
            "s2_happy_msa",
            "contract:msa",
            "contract_01_master_services_agreement.txt",
            None,
        ),
        (
            "s2_happy_subscription",
            "contract:subscription",
            "contract_02_software_subscription_agreement.txt",
            None,
        ),
        (
            "s2_needsreview_nda",
            "contract:nda",
            "contract_03_non_disclosure_agreement.txt",
            None,
        ),
        (
            "s2_deadletter_poison",
            "contract:msa",
            "contract_01_master_services_agreement.txt",
            "msa_poison",
        ),
    ]
    summary: list[dict[str, Any]] = []

    for name, hint, contract_file, doc_id_override in scenarios:
        contract_path = CONTRACTS_DIR / contract_file
        text = contract_path.read_text(encoding="utf-8")
        doc_id = doc_id_override or contract_path.stem
        result = run_extract(
            document_id=doc_id,
            document_text=text,
            hint=hint,
            llm=make_llm(args.llm),
            sor_url=args.sor_url or os.environ.get("SOR_URL", "http://localhost:8001"),
            out_dir=str(ROOT / "runs" / name),
        )
        summary.append(
            {
                "name": name,
                "trace_id": result["trace_id"],
                "scenario": "scenario_2_contract",
                "status": result["status"],
                "confidence": result["confidence"],
                "decision": result["decision"],
            }
        )

    runs_dir = ROOT / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


def cmd_serve(args: argparse.Namespace) -> None:
    del args
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000)


def cmd_serve_sor(args: argparse.Namespace) -> None:
    del args
    uvicorn.run("src.api.sor:app", host="0.0.0.0", port=8001)


def cmd_runs(args: argparse.Namespace) -> None:
    del args
    from src.db import list_runs

    _print_table(
        list_runs(),
        ["trace_id", "document_id", "status", "confidence", "branch", "sor_id", "created_at"],
    )


def cmd_dlq(args: argparse.Namespace) -> None:
    del args
    from src.db import list_dead_letter

    _print_table(list_dead_letter(), ["trace_id", "reason", "created_at"])


def _print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("(none)")
        return

    widths = {
        column: max(len(column), *(len(str(row.get(column, ""))) for row in rows))
        for column in columns
    }
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    print(header)
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Document automation agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="extract contract metadata")
    extract.add_argument("--input", required=True)
    extract.add_argument("--hint", required=True)
    extract.add_argument("--out", required=True)
    extract.add_argument("--llm")
    extract.add_argument("--sor-url")
    extract.add_argument("--doc-id")
    extract.set_defaults(func=cmd_extract)

    demo = subparsers.add_parser("demo", help="run scenario 2 demos")
    demo.add_argument("--llm")
    demo.add_argument("--sor-url")
    demo.set_defaults(func=cmd_demo)

    serve = subparsers.add_parser("serve", help="serve the agent API")
    serve.set_defaults(func=cmd_serve)

    serve_sor = subparsers.add_parser("serve-sor", help="serve the mock SOR API")
    serve_sor.set_defaults(func=cmd_serve_sor)

    runs = subparsers.add_parser("runs", help="list persisted runs")
    runs.set_defaults(func=cmd_runs)

    dlq = subparsers.add_parser("dlq", help="list dead-letter items")
    dlq.set_defaults(func=cmd_dlq)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
