"""HTTP-level security and release-integrity checks for the local server."""

from contextlib import closing
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request


APP = Path(__file__).resolve().parents[1]


class HttpHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix="http-hardening-", dir=APP)
        cls.db_path = Path(cls.work.name) / "hardening.sqlite3"
        with socket.socket() as port_picker:
            port_picker.bind(("127.0.0.1", 0))
            port = port_picker.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.log_path = Path(cls.work.name) / "server.log"
        cls.log = cls.log_path.open("w+")
        cls.process = subprocess.Popen(
            [sys.executable, str(APP / "server.py"), "--port", str(port),
             "--db", str(cls.db_path), "--latency", "0.01"],
            cwd=APP,
            stdout=cls.log,
            stderr=subprocess.STDOUT,
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
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        self.csrf = None
        status, self.bootstrap, _ = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status, self.bootstrap)
        self.csrf = self.bootstrap["csrf"]
        self.template_id = "customer-resolution"

    def request(self, method, path, data=None, csrf=True, client=None):
        headers = {"Accept": "application/json"}
        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode()
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(
            self.base + path, data=payload, headers=headers, method=method
        )
        opener = client or self.client
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            body = json.loads(raw) if "application/json" in content_type else raw
            return response.status, body, response.headers

    def raw_json_request(self, method, path, raw, csrf=True):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(
            self.base + path,
            data=raw.encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            response = self.client.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body, response.headers

    def switch(self, role):
        user = next(user for user in self.bootstrap["users"] if user["role"] == role)
        status, body, _ = self.request("POST", "/api/session", {"userId": user["id"]})
        self.assertEqual(200, status, body)
        self.csrf = body["csrf"]
        return body

    def poll_run(self, run_id, statuses, timeout=12):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            status, latest, _ = self.request("GET", f"/api/runs/{run_id}")
            self.assertEqual(200, status, latest)
            if latest["status"] in statuses:
                return latest
            time.sleep(0.03)
        self.fail(f"Run did not reach {statuses}: {latest}")

    def assert_typed_error(self, status, body, headers, expected_status, expected_code):
        self.assertEqual(expected_status, status, body)
        error = body.get("error", {})
        for field in ("code", "message", "errorCode", "userMessage", "correlationId"):
            self.assertIsInstance(error.get(field), str, body)
            self.assertTrue(error[field], body)
        self.assertEqual(expected_code, error["code"])
        self.assertEqual(expected_code, error["errorCode"])
        correlation = headers.get("X-Correlation-ID")
        self.assertTrue(correlation, headers)
        self.assertEqual(correlation, error["correlationId"])

    def valid_template(self, name):
        self.switch("admin")
        status, draft, _ = self.request("POST", "/api/templates", {
            "name": name,
            "description": "Candidate integrity verification.",
        })
        self.assertEqual(200, status, draft)
        config = {
            "executionMode": "automatic",
            "executorRole": "contributor",
            "approvalRequired": False,
            "approverRole": "reviewer",
            "timeoutSeconds": 30,
            "retries": 2,
        }
        status, draft, _ = self.request("PUT", f"/api/templates/{draft['id']}", {
            "expectedRevision": draft["draftRevision"],
            "nodes": [
                {"id": "receive", "agentId": "intake", "label": "Receive", "x": 70,
                 "y": 225, "config": config},
                {"id": "record", "agentId": "receipt", "label": "Record", "x": 330,
                 "y": 225, "config": config},
            ],
            "edges": [{"id": "receive_record", "source": "receive", "target": "record"}],
        })
        self.assertEqual(200, status, draft)
        status, submitted, _ = self.request(
            "POST", f"/api/templates/{draft['id']}/submit", {}
        )
        self.assertEqual(200, status, submitted)
        self.assertEqual("in_review", submitted["status"])
        return submitted

    def tamper_template(self, template_id, mutation):
        with closing(sqlite3.connect(self.db_path, timeout=5)) as database:
            row = database.execute(
                "SELECT data FROM templates WHERE id=?", (template_id,)
            ).fetchone()
            self.assertIsNotNone(row)
            template = json.loads(row[0])
            mutation(template)
            database.execute(
                "UPDATE templates SET data=? WHERE id=?",
                (json.dumps(template, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                 template_id),
            )
            database.commit()

    def test_health_is_sessionless_and_reports_runtime_schema(self):
        client = urllib.request.build_opener()
        status, body, headers = self.request(
            "GET", "/api/health", csrf=False, client=client
        )
        self.assertEqual(200, status, body)
        self.assertEqual("ready", body["status"])
        self.assertEqual("local-durable-sqlite", body["runtime"])
        self.assertEqual("2.2.0", body["version"])
        self.assertEqual(13, body["schemaVersion"])
        self.assertIsNone(headers.get("Set-Cookie"), headers)

    def test_strict_request_json_rejects_constants_and_duplicate_keys_then_recovers(self):
        status, before, _ = self.request("GET", "/api/runs")
        self.assertEqual(200, status, before)

        invalid_documents = (
            '{"templateId":"customer-resolution","mode":"simulation","input":{"value":NaN}}',
            '{"templateId":"customer-resolution","mode":"simulation","input":{"value":Infinity}}',
            '{"templateId":"customer-resolution","mode":"simulation","input":{"value":-Infinity}}',
            '{"templateId":"customer-resolution","mode":"simulation","input":{"value":"\\ud800"}}',
            '{"templateId":"customer-resolution","templateId":"customer-resolution","mode":"simulation"}',
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                status, body, headers = self.raw_json_request(
                    "POST", "/api/runs", document
                )
                self.assert_typed_error(
                    status, body, headers, 400, "INVALID_JSON"
                )

        status, after, _ = self.request("GET", "/api/runs")
        self.assertEqual(200, status, after)
        self.assertEqual(len(before), len(after))
        status, health, _ = self.request("GET", "/api/health", csrf=False)
        self.assertEqual(200, status, health)
        self.assertEqual("ready", health["status"])
        self.assertIsNone(self.process.poll(), "Server exited after invalid JSON")

    def test_api_errors_are_typed_and_correlation_id_matches_header(self):
        status, body, headers = self.request("GET", "/api/not-a-real-resource")
        self.assert_typed_error(status, body, headers, 404, "ROUTE_NOT_FOUND")

    def test_connection_authority_routes_are_role_checked_and_versioned(self):
        self.switch("contributor")
        status, body, headers = self.request(
            "POST", "/api/connections/fixture-ticket/revoke", {}
        )
        self.assert_typed_error(status, body, headers, 403, "ROLE_DENIED")

        self.switch("admin")
        status, tested, _ = self.request(
            "POST", "/api/connections/fixture-ticket/test", {}
        )
        self.assertEqual(200, status, tested)
        self.assertTrue(tested["reachable"])
        generation = tested["generation"]
        try:
            status, revoked, _ = self.request(
                "POST", "/api/connections/fixture-ticket/revoke", {}
            )
            self.assertEqual(200, status, revoked)
            self.assertEqual("revoked", revoked["status"])
            self.assertEqual(generation + 1, revoked["generation"])
        finally:
            status, restored, _ = self.request(
                "POST", "/api/connections/fixture-ticket/restore", {}
            )
            self.assertEqual(200, status, restored)
            self.assertEqual("ready", restored["status"])

    def test_openapi_inspection_is_admin_only_non_executable_and_metadata_audited(self):
        marker = "SPEC_BODY_MUST_NOT_ENTER_AUDIT_7f90"
        document = {
            "openapi": "3.1.0",
            "info": {"title": "Inspection contract", "version": "2026-09"},
            "servers": [{"url": "https://api.example.com/v1/"}],
            "paths": {
                "/widgets/{widgetId}": {
                    "get": {
                        "operationId": "getWidget",
                        "description": "Inspect a widget candidate.",
                        "parameters": [{
                            "name": "widgetId", "in": "path", "required": True,
                            "schema": {"type": "string", "minLength": 1, "maxLength": 100},
                        }],
                        "responses": {
                            "200": {
                                "description": "Widget response",
                                "content": {"application/json": {"schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "description": marker},
                                    },
                                    "required": ["id"],
                                    "additionalProperties": False,
                                }}},
                            },
                        },
                    },
                },
            },
        }

        self.switch("contributor")
        status, body, headers = self.request(
            "POST", "/api/integrations/openapi/inspect", {"document": document}
        )
        self.assert_typed_error(status, body, headers, 403, "ROLE_DENIED")

        self.switch("admin")
        status, before_connections, _ = self.request("GET", "/api/connections")
        self.assertEqual(200, status, before_connections)
        status, body, headers = self.request(
            "POST", "/api/integrations/openapi/inspect",
            {"document": document, "activate": True},
        )
        self.assert_typed_error(
            status, body, headers, 400, "OPENAPI_INSPECT_REQUEST"
        )

        status, inspected, _ = self.request(
            "POST", "/api/integrations/openapi/inspect", {"document": document}
        )
        self.assertEqual(200, status, inspected)
        expected_hash = hashlib.sha256(json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode()).hexdigest()
        self.assertEqual(expected_hash, inspected["documentHash"])
        self.assertFalse(inspected["executable"])
        self.assertEqual("developer-review-required", inspected["activation"])
        candidate = inspected["report"]["candidates"][0]
        self.assertEqual("unclassified", candidate["reviewState"])
        self.assertNotIn("effect", candidate)
        self.assertNotIn("approvalRequired", candidate)

        status, after_connections, _ = self.request("GET", "/api/connections")
        self.assertEqual(200, status, after_connections)
        self.assertEqual(before_connections, after_connections)
        status, audit, _ = self.request("GET", "/api/audit")
        self.assertEqual(200, status, audit)
        event = next(
            item for item in audit
            if item.get("action") == "external_openapi.inspected"
            and item.get("target") == expected_hash
        )
        self.assertEqual({
            "activation", "candidateCount", "documentHash", "executable",
            "hashAlgorithm", "openapiVersion", "sourceVersion", "title",
        }, set(event["detail"]))
        self.assertNotIn(marker, json.dumps(event, sort_keys=True))
        self.assertNotIn("paths", event["detail"])

    def test_task_attachment_route_persists_hash_only_in_public_views(self):
        content = b"bounded local attachment"
        status, run, _ = self.request("POST", "/api/runs", {
            "templateId": self.template_id,
            "mode": "fixture",
            "scenario": "happy",
            "artifacts": [{
                "name": "context.txt",
                "mimeType": "text/plain",
                "contentBase64": base64.b64encode(content).decode("ascii"),
            }],
        })
        self.assertEqual(200, status, run)
        self.assertEqual(hashlib.sha256(content).hexdigest(), run["artifacts"][0]["sha256"])
        self.assertNotIn("contentBase64", run["artifacts"][0])

        status, payload, _ = self.request("GET", f"/api/runs/{run['id']}/artifacts")
        self.assertEqual(200, status, payload)
        self.assertEqual(["context.txt"], [item["name"] for item in payload["artifacts"]])
        self.assertNotIn("contentBase64", payload["artifacts"][0])

    def test_contributor_cannot_create_templates_or_experiments(self):
        before_templates = len(self.bootstrap["templates"])
        status, experiments, _ = self.request("GET", "/api/experiments")
        self.assertEqual(200, status, experiments)
        before_experiments = len(experiments)
        self.switch("contributor")

        status, body, headers = self.request("POST", "/api/templates", {
            "name": "Unauthorized workflow", "description": "Must not persist."
        })
        self.assert_typed_error(status, body, headers, 403, "ROLE_DENIED")
        status, body, headers = self.request("POST", "/api/experiments", {
            "templateId": self.template_id, "suite": "core"
        })
        self.assert_typed_error(status, body, headers, 403, "ROLE_DENIED")

        status, templates, _ = self.request("GET", "/api/templates")
        self.assertEqual(200, status, templates)
        self.assertEqual(before_templates, len(templates))
        status, experiments, _ = self.request("GET", "/api/experiments")
        self.assertEqual(200, status, experiments)
        self.assertEqual(before_experiments, len(experiments))

    def test_reminder_requires_initiator_or_eligible_role(self):
        status, run, _ = self.request("POST", "/api/runs", {
            "templateId": self.template_id,
            "mode": "fixture",
            "scenario": "happy",
            "input": {"subject": "Reminder authorization check"},
        })
        self.assertEqual(200, status, run)
        waiting = self.poll_run(run["id"], {"waiting_approval", "needs_attention"})
        self.assertEqual("waiting_approval", waiting["status"], waiting)
        node = next(item for item in waiting["nodes"] if item["status"] == "waiting_approval")

        self.switch("contributor")
        status, body, headers = self.request(
            "POST", f"/api/runs/{run['id']}/remind", {"nodeId": node["nodeId"]}
        )
        self.assert_typed_error(status, body, headers, 403, "ROLE_DENIED")

        self.switch("reviewer")
        status, reminder, _ = self.request(
            "POST", f"/api/runs/{run['id']}/remind", {"nodeId": node["nodeId"]}
        )
        self.assertEqual(200, status, reminder)
        self.assertEqual("reviewer", reminder["recipient"])
        self.assertEqual("reviewer", reminder["initiatedBy"])
        self.assertFalse(reminder["deduplicated"])

    def test_publish_rechecks_submitted_content_hash_and_revision(self):
        cases = (
            ("content", lambda template: template.update(
                description=template["description"] + " Altered after submission."
            )),
            ("revision", lambda template: template.update(
                draftRevision=template["draftRevision"] + 1
            )),
        )
        for label, mutation in cases:
            with self.subTest(label=label):
                submitted = self.valid_template(f"Frozen candidate {label}")
                self.tamper_template(submitted["id"], mutation)
                self.switch("reviewer")
                status, body, headers = self.request(
                    "POST", f"/api/templates/{submitted['id']}/publish", {}
                )
                self.assert_typed_error(
                    status, body, headers, 409, "SUBMITTED_SNAPSHOT_CHANGED"
                )
                status, current, _ = self.request(
                    "GET", f"/api/templates/{submitted['id']}"
                )
                self.assertEqual(200, status, current)
                self.assertEqual("in_review", current["status"])
                self.assertFalse(current["publishedVersion"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
