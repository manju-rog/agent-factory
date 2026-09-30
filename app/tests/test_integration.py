"""HTTP boundary integration checks for the runnable local Axiom reference.

These checks use the actual server in an isolated subprocess and temporary DB.
They do not claim browser layout, production authentication, or external-service QA.
Run from axiom_app: python -m unittest discover -s tests -p test_integration.py -v
"""

import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request


APP = Path(__file__).resolve().parents[1]


class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix="http-check-", dir=APP)
        with socket.socket() as port_picker:
            port_picker.bind(("127.0.0.1", 0))
            port = port_picker.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.log_path = Path(cls.work.name) / "server.log"
        cls.log = cls.log_path.open("w+")
        cls.process = subprocess.Popen(
            [sys.executable, str(APP / "server.py"), "--port", str(port),
             "--db", str(Path(cls.work.name) / "integration.sqlite3"), "--latency", "0.05"],
            cwd=APP, stdout=cls.log, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(cls.base + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.05)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.log.flush()
        raise RuntimeError("Server failed to become ready:\n" + cls.log_path.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)
        cls.log.close()
        cls.work.cleanup()

    def setUp(self):
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = None
        status, self.bootstrap, _ = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status)
        self.csrf = self.bootstrap["csrf"]
        self.template_id = next(template["id"] for template in self.bootstrap["templates"]
                                if template["id"] == "customer-resolution")

    def request(self, method, path, data=None, csrf=True):
        headers = {"Accept": "application/json"}
        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode()
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(self.base + path, data=payload, headers=headers, method=method)
        try:
            result = self.client.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            result = error
        with result:
            raw = result.read().decode("utf-8")
            kind = result.headers.get("Content-Type", "")
            body = json.loads(raw) if "application/json" in kind else raw
            return result.status, body, result.headers

    def switch(self, role):
        user = next(user for user in self.bootstrap["users"] if user["role"] == role)
        status, payload, _ = self.request("POST", "/api/session", {"userId": user["id"]})
        self.assertEqual(200, status, payload)
        self.assertEqual(role, payload["user"]["role"])
        self.csrf = payload["csrf"]
        return payload

    def poll_run(self, run_id, statuses, timeout=25):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            code, latest, _ = self.request("GET", f"/api/runs/{run_id}")
            self.assertEqual(200, code, latest)
            if latest["status"] in statuses:
                return latest
            time.sleep(0.05)
        self.fail(f"Run did not reach {statuses}: {latest}")

    def test_bootstrap_static_assets_and_server_source_boundary(self):
        for key in ("user", "users", "csrf", "agents", "templates", "runs", "approvals", "capabilities"):
            self.assertIn(key, self.bootstrap)
        self.assertTrue(self.bootstrap["csrf"])
        self.assertGreaterEqual(len(self.bootstrap["agents"]), 7)
        for path, marker in (("/", "Axiom"), ("/theme.js", "axiom.theme"),
                             ("/app.js", "api"), ("/styles.css", "{"),
                             ("/icons.js", "ICONS")):
            status, content, _ = self.request("GET", path)
            self.assertEqual(200, status, path)
            self.assertIn(marker, content, path)
        for path in ("/server.py", "/CONTRACT.md", "/tests/test_integration.py"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(404, status, path)

    def test_mutation_requires_csrf_and_author_role(self):
        self.switch("contributor")
        request = {"name": "Unauthorized registry entry", "description": "HTTP check", "implementationId": "csr"}
        status, body, _ = self.request("POST", "/api/agents", request, csrf=False)
        self.assertEqual(403, status, body)
        self.assertIn("error", body)
        status, body, _ = self.request("POST", "/api/agents", request)
        self.assertEqual(403, status, body)
        self.assertIn("message", body["error"])

    def test_create_blank_workflow_publish_and_execute(self):
        self.switch("admin")
        status, draft, _ = self.request("POST", "/api/templates", {
            "name": "From-scratch HTTP workflow", "description": "Created and released through public API calls.",
        })
        self.assertIn(status, (200, 201), draft)
        self.assertEqual([], draft["nodes"])
        self.assertEqual([], draft["edges"])
        self.assertFalse(draft["publishedVersion"])
        config = {"executionMode": "automatic", "executorRole": "contributor", "approvalRequired": False,
                  "approverRole": "reviewer", "timeoutSeconds": 30, "retries": 2}
        status, draft, _ = self.request("PUT", f"/api/templates/{draft['id']}", {
            "expectedRevision": draft["draftRevision"], "name": draft["name"],
            "nodes": [{"id": "receive", "agentId": "intake", "label": "Receive request", "x": 70, "y": 225, "config": config},
                      {"id": "record", "agentId": "receipt", "label": "Record evidence", "x": 330, "y": 225, "config": config}],
            "edges": [{"id": "receive_record", "source": "receive", "target": "record"}],
        })
        self.assertEqual(200, status, draft)
        status, validation, _ = self.request("GET", f"/api/templates/{draft['id']}/validate")
        self.assertEqual(200, status, validation)
        self.assertTrue(validation["valid"], validation)
        status, diff, _ = self.request("GET", f"/api/templates/{draft['id']}/diff")
        self.assertEqual(200, status, diff)
        self.assertTrue(diff["changes"])
        status, submitted, _ = self.request("POST", f"/api/templates/{draft['id']}/submit", {})
        self.assertEqual(200, status, submitted)
        self.assertEqual("in_review", submitted["status"])
        self.switch("reviewer")
        status, published, _ = self.request("POST", f"/api/templates/{draft['id']}/publish", {})
        self.assertEqual(200, status, published)
        self.assertEqual(1, published["publishedVersion"])
        status, run, _ = self.request("POST", "/api/runs", {
            "templateId": draft["id"], "mode": "fixture", "scenario": "happy", "input": {"subject": "A new process"},
        })
        self.assertIn(status, (200, 201), run)
        finished = self.poll_run(run["id"], {"completed", "needs_attention", "rejected"})
        self.assertEqual("completed", finished["status"], finished)
        self.assertEqual(2, len(finished["nodes"]))
        self.assertEqual(1, finished["version"])
        status, templates, _ = self.request("GET", "/api/templates")
        self.assertEqual(200, status, templates)
        self.assertTrue(any(template["id"] == draft["id"] for template in templates))

    def test_published_fixture_approval_evidence_and_duplicate_decision(self):
        self.switch("contributor")
        status, run, _ = self.request("POST", "/api/runs", {
            "templateId": self.template_id, "mode": "fixture", "scenario": "happy",
            "input": {"customer": "HTTP verification", "request": "Create support case", "amount": 250},
        })
        self.assertIn(status, (200, 201), run)
        run = self.poll_run(run["id"], {"waiting_approval", "needs_attention", "completed"})
        self.assertEqual("waiting_approval", run["status"], run)
        node = next(node for node in run["nodes"] if node["status"] == "waiting_approval")
        decision = {"nodeId": node["nodeId"], "decision": "approve", "comment": "HTTP integration decision",
                    "preparedActions": [{key: action[key] for key in (
                        "effectId", "nodeId", "operationGeneration", "actionFingerprint", "approvalEnvelopeHash"
                    )} for action in node.get("approvalPacket", {}).get("actions", [])]}
        status, body, _ = self.request("POST", f"/api/runs/{run['id']}/approve", decision)
        self.assertEqual(403, status, body)
        self.switch("reviewer")
        status, body, _ = self.request("POST", f"/api/runs/{run['id']}/approve", decision)
        self.assertEqual(200, status, body)
        status, body, _ = self.request("POST", f"/api/runs/{run['id']}/approve", decision)
        self.assertEqual(200, status, body)
        finished = self.poll_run(run["id"], {"completed", "needs_attention", "rejected"})
        self.assertEqual("completed", finished["status"], finished)
        self.assertTrue(finished.get("ticket"), finished)
        status, evidence, _ = self.request("GET", f"/api/runs/{run['id']}/evidence")
        self.assertEqual(200, status, evidence)
        self.assertEqual(run["id"], evidence["runId"])
        self.assertTrue(evidence["items"])
        self.assertEqual(64, len(evidence["artifactHash"]))
        status, exported, headers = self.request("POST", f"/api/runs/{run['id']}/export", {})
        self.assertEqual(200, status, exported)
        self.assertIn("application/json", headers.get("Content-Type", ""))

    def test_stale_template_revision_is_rejected(self):
        self.switch("admin")
        status, template, _ = self.request("GET", f"/api/templates/{self.template_id}")
        self.assertEqual(200, status, template)
        update = {"expectedRevision": template["draftRevision"], "name": template["name"],
                  "description": template.get("description", ""), "nodes": template["nodes"], "edges": template["edges"]}
        status, updated, _ = self.request("PUT", f"/api/templates/{self.template_id}", update)
        self.assertEqual(200, status, updated)
        self.assertGreater(updated["draftRevision"], template["draftRevision"])
        status, conflict, _ = self.request("PUT", f"/api/templates/{self.template_id}", update)
        self.assertEqual(409, status, conflict)
        self.assertIn("error", conflict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
