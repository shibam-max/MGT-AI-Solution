from __future__ import annotations

import os
import pathlib
import socket
import tempfile
import threading
import time
import unittest

import httpx
import uvicorn


class _SorServer:
    def __init__(self) -> None:
        self.port = self._free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        config = uvicorn.Config(
            app="src.api.sor:app",
            host="127.0.0.1",
            port=self.port,
            log_level="error",
            lifespan="off",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                response = httpx.get(f"{self.url}/health", timeout=0.2)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.05)
        raise RuntimeError("SOR server did not start within 5 seconds")

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=5.0)

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


class TestGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        cls._tmp.close()
        cls._old_db = os.environ.get("AGENT_DB")
        os.environ["AGENT_DB"] = cls._tmp.name
        from src.db import init_db

        init_db()
        cls.sor = _SorServer()
        cls.sor.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.sor.stop()
        if cls._old_db is None:
            os.environ.pop("AGENT_DB", None)
        else:
            os.environ["AGENT_DB"] = cls._old_db
        os.unlink(cls._tmp.name)

    def _run(self, document_id: str, hint: str, contract_filename: str) -> dict:
        from src.agent.graph import run_extract
        from src.llm.mock_client import MockLLM

        text = (
            pathlib.Path("..") / "materials" / "contracts" / contract_filename
        ).read_text(encoding="utf-8")
        return run_extract(
            document_id=document_id,
            document_text=text,
            hint=hint,
            llm=MockLLM(),
            sor_url=self.sor.url,
        )

    def test_complete_branch_calls_sor_and_persists(self) -> None:
        result = self._run(
            "msa_demo",
            "contract:msa",
            "contract_01_master_services_agreement.txt",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["decision"]["branch"], "complete")
        self.assertTrue(result["decision"]["sor_id"].startswith("sor_"))

    def test_needs_review_branch_skips_sor(self) -> None:
        result = self._run(
            "nda_demo",
            "contract:nda",
            "contract_03_non_disclosure_agreement.txt",
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertIsNone(result["decision"]["sor_id"])
        self.assertEqual(result["decision"]["branch"], "needs_review")

    def test_sor_poison_lands_in_dlq(self) -> None:
        result = self._run(
            "msa_poison",
            "contract:msa",
            "contract_01_master_services_agreement.txt",
        )
        self.assertEqual(result["decision"]["branch"], "dead_letter")
        self.assertEqual(result["status"], "failed")
        from src.db import list_dead_letter

        self.assertTrue(
            any(row["trace_id"] == result["trace_id"] for row in list_dead_letter())
        )

    def test_dlq_replay_payload_available(self) -> None:
        from src.db import list_dead_letter, replay_dead_letter

        rows = list_dead_letter()
        if not rows:
            self._run(
                "replay_poison",
                "contract:msa",
                "contract_01_master_services_agreement.txt",
            )
            rows = list_dead_letter()
        trace_id = rows[0]["trace_id"]
        payload = replay_dead_letter(trace_id)
        self.assertTrue(payload["document_id"].endswith("_poison") or payload["document_id"])
        self.assertIn("text", payload)
