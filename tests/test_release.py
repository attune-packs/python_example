"""Offline release checks using the installed SDK, not mocked action execution.

Sensor and artifact success paths require Attune services and are not covered.
"""

import ast
import functools
import hashlib
import http.server
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_complete_mit_license(self):
        # https://opensource.org/license/mit, retaining the original attribution.
        license_bytes = (ROOT / "LICENSE").read_bytes()
        self.assertEqual(
            hashlib.sha256(license_bytes).hexdigest(),
            "19c3c4853b1e6ef6a7dabf41fdf427e44579637de81c40cd91b2275257f5d935",
        )
        self.assertEqual(
            license_bytes.splitlines()[2], b"Copyright (c) 2025 Attune Automation"
        )

    def test_manifest_license_and_version(self):
        manifest = yaml.safe_load((ROOT / "pack.yaml").read_text())
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["version"], "1.0.1")

    def test_yaml_syntax(self):
        for path in ROOT.rglob("*.yaml"):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsInstance(yaml.safe_load(path.read_text()), dict)
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsInstance(yaml.safe_load(path.read_text()), dict)

    def test_python_syntax(self):
        for directory in ("actions", "sensors"):
            for path in (ROOT / directory).glob("*.py"):
                with self.subTest(path=path.relative_to(ROOT)):
                    ast.parse(path.read_text(), filename=str(path))

    def run_action(self, name, parameters, success=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / "actions" / f"{name}.py")],
            input=json.dumps(parameters) + "\n",
            text=True,
            capture_output=True,
            timeout=15,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stderr + result.stdout

    def test_hello_default(self):
        self.assertEqual(self.run_action("hello", {}), {"message": "Hello, Python"})

    def test_hello_custom(self):
        self.assertEqual(
            self.run_action("hello", {"name": "License check"}),
            {"message": "Hello, License check"},
        )

    def test_counter_default(self):
        result = self.run_action("read_counter", {})
        self.assertEqual(result["counter"], 0)
        self.assertEqual(result["rule_ref"], "unknown")

    def test_counter_custom(self):
        result = self.run_action("read_counter", {"counter": 42, "rule_ref": "test.rule"})
        self.assertEqual(result["counter"], 42)
        self.assertEqual(result["rule_ref"], "test.rule")

    def test_list_numbers_default(self):
        self.assertEqual(self.run_action("list_numbers", {}), {"items": list(range(10))})

    def test_list_numbers_custom_and_empty(self):
        self.assertEqual(self.run_action("list_numbers", {"start": -2, "n": 3}), {"items": [-2, -1, 0]})
        self.assertEqual(self.run_action("list_numbers", {"n": 0}), {"items": []})

    def test_simulate_work_success(self):
        result = self.run_action("simulate_work", {"duration_seconds": 0, "output_data": {"ok": True}})
        self.assertTrue(result["success"])
        self.assertEqual(result["output_data"], {"ok": True})

    def test_simulate_work_failure(self):
        output = self.run_action("simulate_work", {"duration_seconds": 0, "fail": True}, success=False)
        self.assertIn("Simulated immediate failure", output)

    def test_flaky_fail_success(self):
        result = self.run_action("flaky_fail", {"failure_probability": 0})
        self.assertEqual(result["failure_probability"], 0)

    def test_flaky_fail_failure(self):
        output = self.run_action("flaky_fail", {"failure_probability": 1}, success=False)
        self.assertIn("Random failure triggered", output)

    def test_queue_ack_all_outcomes(self):
        items = [
            {"order_id": "ok", "quantity": 1},
            {"order_id": "retry", "inventory_available": False, "retryable": True},
            {"order_id": "failed", "quantity": 0},
            {"order_id": "review", "requires_manual_review": True},
        ]
        result = self.run_action("process_order_queue", {
            "items": items,
            "queue_items": [{"id": i} for i in range(1, 5)],
            "queue": {"ref": "test.queue", "ack_contract_version": 1},
        })
        self.assertEqual(result["processed_count"], 4)
        self.assertEqual(result["queue_ack"]["version"], 1)
        self.assertEqual(
            [item["status"] for item in result["queue_ack"]["items"]],
            ["completed", "retry", "failed", "skipped"],
        )
        self.assertEqual([item["id"] for item in result["queue_ack"]["items"]], [1, 2, 3, 4])

    def test_queue_rejects_empty_batch(self):
        output = self.run_action("process_order_queue", {"items": []}, success=False)
        self.assertIn("non-empty 'items' array", output)

    def test_queue_rejects_missing_id(self):
        output = self.run_action("process_order_queue", {"items": [{}]}, success=False)
        self.assertIn("Missing queue item id", output)

    def test_artifact_rejects_invalid_input_before_api_calls(self):
        output = self.run_action("artifact_demo", {"iterations": 0}, success=False)
        self.assertIn("iterations must be >= 1", output)

    def test_http_real_loopback_request(self):
        with tempfile.TemporaryDirectory() as directory:
            body = "release HTTP smoke\n"
            Path(directory, "index.html").write_text(body)
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self.run_action("http_example", {"url": f"http://127.0.0.1:{server.server_port}/"})
                self.assertEqual(result["status_code"], 200)
                self.assertEqual(result["snippet"], body)
                self.assertTrue(result["success"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
