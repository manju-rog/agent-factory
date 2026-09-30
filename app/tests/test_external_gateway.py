"""End-to-end security checks for the external connection gateway.

These tests use controlled transports and public test IPs. They prove Axiom's
gateway and Goal Agent bridge behavior; they do not claim live provider QA.
"""

from __future__ import annotations

import copy
import http.cookiejar
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import agent_factory
import integrations
import server


ADMIN = {"id": "author", "role": "admin"}
REVIEWER = {"id": "reviewer", "role": "reviewer"}
PUBLIC_TEST_IP = "93.184.216.34"
SECRET_VALUE = "synthetic-controlled-test-secret"


def slack_payload(ident: str, *, status: str = "draft", include_write: bool = True) -> dict:
    operations = ["slack.auth.test", "slack.conversations.history"]
    if include_write:
        operations.append("slack.chat.post_message")
    return {
        "providerId": "slack",
        "id": ident,
        "name": "Slack " + ident,
        "baseUrls": ["https://slack.com/api/"],
        "auth": {
            "mode": "bearer",
            "secretRefs": {"token": "env:AXIOM_TEST_SLACK_TOKEN"},
        },
        "allowedOperations": operations,
        "status": status,
    }


class RecordingExecutor:
    """Credential-aware transport double with an optional response gate."""

    def __init__(self):
        self.requests = []
        self.started: threading.Event | None = None
        self.release: threading.Event | None = None
        self.failure: Exception | None = None

    def gate_next_call(self) -> tuple[threading.Event, threading.Event]:
        self.started = threading.Event()
        self.release = threading.Event()
        return self.started, self.release

    def send(self, request):
        self.requests.append(request)
        started, release = self.started, self.release
        self.started = self.release = None
        if started is not None and release is not None:
            started.set()
            if not release.wait(5):
                raise RuntimeError("controlled provider gate timed out")
        if self.failure is not None:
            raise self.failure
        if request.url.endswith("auth.test"):
            payload = {"ok": True, "team_id": "T123", "user_id": "U123", "url": "https://acme.slack.com/"}
        elif "conversations.history" in request.url:
            payload = {
                "ok": True,
                "messages": [{"ts": "1710000000.000001", "text": "Observed", "user": "U123"}],
                "has_more": False,
            }
        elif request.url.endswith("chat.postMessage"):
            payload = {"ok": True, "channel": "C123", "ts": "1710000000.000002"}
        else:  # pragma: no cover - a useful failure if a new route escapes the preset
            raise AssertionError("Unexpected controlled provider URL: " + request.url)
        return integrations.TransportResponse(
            200, {"content-type": "application/json"}, json.dumps(payload).encode(), request.url
        )


class StoreGatewayTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="external-gateway-")
        self.store = server.Store(Path(self.work.name) / "axiom.sqlite3", 0)
        self.executor = RecordingExecutor()
        self.store.integration_http = self.executor
        self.environment = patch.dict(os.environ, {
            "AXIOM_TEST_SLACK_TOKEN": SECRET_VALUE,
            "AXIOM_MODEL_ENDPOINT": "https://model.invalid/v1/chat/completions",
            "AXIOM_MODEL_NAME": "controlled-model",
        })
        self.resolver = patch.object(
            integrations, "_default_resolver", lambda _host, _port: [PUBLIC_TEST_IP]
        )
        self.environment.start()
        self.resolver.start()

    def tearDown(self):
        self.resolver.stop()
        self.environment.stop()
        self.store.close()
        self.work.cleanup()

    def create_draft(self, ident: str, **kwargs):
        body = slack_payload(ident, **kwargs)
        return self.store.atomic(self.store.create_external_connection, body, ADMIN)

    def health_check(self, ident: str):
        with self.store.lock:
            capture = self.store.capture_external_connection_call(
                ident, {}, ADMIN, "test"
            )
        result = self.store.execute_external_connection_call(capture)
        return self.store.atomic(
            self.store.apply_connection_test,
            capture,
            result,
            None,
            1,
            ADMIN,
        )

    def create_connection(self, ident: str, **kwargs):
        self.create_draft(ident, **kwargs)
        health = self.health_check(ident)
        self.assertTrue(health["applied"])
        self.assertTrue(health["reachable"])
        return self.store.atomic(
            self.store.connection_action, ident, "restore", ADMIN
        )

    def test_activation_requires_a_current_health_attestation_and_revocation_resets_to_draft(self):
        with self.assertRaises(server.APIError) as bypass:
            self.create_draft("slack-bypass", status="ready")
        self.assertEqual("CONNECTION_ACTIVATION_REQUIRED", bypass.exception.code)

        draft = self.create_draft("slack-lifecycle")
        self.assertEqual("draft", draft["status"])
        self.assertEqual(1, draft["generation"])
        self.assertNotIn("restore", draft["allowedActions"])
        self.assertFalse(draft["activation"]["eligible"])
        self.assertIn("health check", draft["activation"]["reason"])
        self.assertNotIn(
            "slack-lifecycle",
            {
                item.get("adapterBinding", {}).get("connectionId")
                for item in self.store.factory_tool_catalog()
            },
        )
        with self.assertRaises(server.APIError) as unverified:
            self.store.atomic(
                self.store.connection_action, "slack-lifecycle", "restore", ADMIN
            )
        self.assertEqual("CONNECTION_HEALTH_REQUIRED", unverified.exception.code)

        health = self.health_check("slack-lifecycle")
        self.assertEqual(1, health["generation"])
        activation_ready = self.store.public_connection(
            self.store.get("connections", "slack-lifecycle")
        )
        self.assertTrue(activation_ready["activation"]["eligible"])
        self.assertIn("restore", activation_ready["allowedActions"])
        activated = self.store.atomic(
            self.store.connection_action, "slack-lifecycle", "restore", ADMIN
        )
        self.assertEqual("ready", activated["status"])
        self.assertEqual(2, activated["generation"])
        self.assertEqual("healthy", activated["health"]["status"])
        self.assertEqual(2, activated["health"]["generation"])

        revoked = self.store.atomic(
            self.store.connection_action, "slack-lifecycle", "revoke", ADMIN
        )
        self.assertEqual("revoked", revoked["status"])
        self.assertEqual(3, revoked["generation"])
        restored = self.store.atomic(
            self.store.connection_action, "slack-lifecycle", "restore", ADMIN
        )
        self.assertEqual("draft", restored["status"])
        self.assertEqual(4, restored["generation"])
        self.assertEqual("stale", restored["health"]["status"])
        self.assertFalse(restored["activation"]["eligible"])
        self.assertNotIn("restore", restored["allowedActions"])
        with self.assertRaises(server.APIError) as old_health:
            self.store.atomic(
                self.store.connection_action, "slack-lifecycle", "restore", ADMIN
            )
        self.assertEqual("CONNECTION_HEALTH_REQUIRED", old_health.exception.code)

    def test_two_connections_are_redacted_and_project_distinct_capabilities(self):
        first = self.create_connection("slack-primary")
        second = self.create_connection("slack-secondary")

        public_blob = server.encode({
            "created": [first, second],
            "listed": self.store.public_connections(),
            "bootstrap": self.store.bootstrap(ADMIN, "csrf-test"),
        })
        # Catalog setup metadata may literally name the configuration field
        # "auth.secretRefs". What must never appear is a secretRefs object or
        # the actual reference/value from a configured connection.
        self.assertNotIn('"secretRefs":', public_blob)
        self.assertNotIn("AXIOM_TEST_SLACK_TOKEN", public_blob)
        self.assertNotIn(SECRET_VALUE, public_blob)

        contracts = [
            item for item in self.store.factory_tool_catalog()
            if item.get("adapterBinding", {}).get("connectionId") in {"slack-primary", "slack-secondary"}
        ]
        by_connection = {}
        for contract in contracts:
            by_connection.setdefault(contract["adapterBinding"]["connectionId"], {})[
                contract["adapterBinding"]["operation"]
            ] = contract
            self.assertEqual(
                contract["adapterBinding"]["connectionId"],
                contract["authorization"]["connectionId"],
            )
        self.assertEqual({"slack-primary", "slack-secondary"}, set(by_connection))
        primary = by_connection["slack-primary"]["slack.conversations.history"]
        secondary = by_connection["slack-secondary"]["slack.conversations.history"]
        self.assertNotEqual(primary["id"], secondary["id"])

        first_operation = next(
            item for item in first["operations"] if item["id"] == "slack.conversations.history"
        )
        self.assertEqual(primary["id"], first_operation["capabilityId"])

        denied = slack_payload("slack-evil")
        denied["baseUrls"] = ["https://evil.example/api/"]
        with self.assertRaises(server.APIError) as origin:
            self.store.atomic(self.store.create_external_connection, denied, ADMIN)
        self.assertEqual("DESTINATION_DENIED", origin.exception.code)

    def test_direct_invocation_is_read_only_and_audited_without_secrets(self):
        self.create_connection("slack-read")
        self.executor.requests.clear()
        with self.store.lock:
            capture = self.store.capture_external_connection_call(
                "slack-read",
                {
                    "operationId": "slack.conversations.history",
                    "arguments": {"channel": "C123", "limit": 1},
                    "operationKey": "diagnostic:slack-read:history-1",
                },
                ADMIN,
                "invoke",
            )
        result = self.store.execute_external_connection_call(capture)
        audit_state = self.store.atomic(
            self.store.audit_connection_invoke, capture, result, None, ADMIN
        )
        self.assertFalse(audit_state["staleAuthorityAfterCall"])
        self.assertEqual("Observed", result.output["messages"][0]["text"])
        self.assertEqual("diagnostic:slack-read:history-1", result.operation_key)
        self.assertEqual("Bearer " + SECRET_VALUE, self.executor.requests[-1].headers["Authorization"])

        audit_blob = server.encode(self.store.all("audit"))
        self.assertIn("external_connection.read_invoked", audit_blob)
        self.assertNotIn("AXIOM_TEST_SLACK_TOKEN", audit_blob)
        self.assertNotIn(SECRET_VALUE, audit_blob)

        before = len(self.executor.requests)
        with self.assertRaises(server.APIError) as write:
            self.store.capture_external_connection_call(
                "slack-read",
                {"operationId": "slack.chat.post_message", "arguments": {"channel": "C123", "text": "no"}},
                ADMIN,
                "invoke",
            )
        self.assertEqual("READ_ONLY_OPERATION_REQUIRED", write.exception.code)
        self.assertEqual(before, len(self.executor.requests))

        with self.assertRaises(server.APIError) as health:
            self.store.capture_external_connection_call(
                "slack-read",
                {"operationId": "slack.conversations.history", "arguments": {"channel": "C123", "limit": 1}},
                ADMIN,
                "test",
            )
        self.assertEqual("HEALTH_OPERATION_FIXED", health.exception.code)

    def _external_agent(self, connection_id: str, *, parent: dict | None = None):
        write_tool = next(
            item for item in self.store.factory_tool_catalog()
            if item.get("adapterBinding", {}).get("connectionId") == connection_id
            and item.get("adapterBinding", {}).get("operation") == "slack.chat.post_message"
        )
        spec_body = {
            "name": "External Slack writer",
            "mission": "Prepare one reviewed Slack update.",
            "instructions": "Use the registered Slack capability once.",
            "inputSchema": {
                "type": "object",
                "properties": {"subject": {"type": "string", "minLength": 1}},
                "required": ["subject"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
                "additionalProperties": False,
            },
            "contextFields": ["input.subject"],
            "allowedTools": [write_tool["id"]],
            "requiredEvidenceTools": [],
            "limits": {"maxTurns": 4, "maxToolCalls": 2, "maxWriteCalls": 1},
            "stopRules": {},
            "policyRefs": ["external-write-review.v1"],
            "evaluationCases": [],
        }
        created = self.store.atomic(self.store.create_agent_spec, spec_body, ADMIN)
        published = self.store.atomic(
            self.store.publish_agent_spec,
            created["id"],
            {"expectedRevision": created["draftRevision"]},
            REVIEWER,
        )
        run_arguments = (
            {"specId": created["id"], "specVersion": published["publishedVersion"], "mode": "model", "input": {"subject": "Release ready"}},
            ADMIN,
        )
        run = (
            self.store.atomic(self.store.create_agent_run, *run_arguments, None, parent)
            if parent is not None
            else self.store.atomic(self.store.create_agent_run, *run_arguments)
        )
        claimed = self.store.atomic(self.store._claim_agent_work, run["id"])
        decision = {
            "kind": "call",
            "toolId": write_tool["id"],
            "arguments": {"channel": "C123", "text": "Release ready"},
            "reason": "Send the reviewed release update.",
        }
        next_state = agent_factory.apply_decision(
            claimed["_compiled"], claimed["_state"], decision,
            "configured-test-model",
            {"model": "controlled-model", "totalTokens": 10, "estimatedCostMicros": 1, "costKnown": True},
        )
        lease = claimed["_lease"]
        applied = self.store.atomic(
            self.store._finish_agent_model,
            run["id"], lease["token"], lease["claimedRevision"], next_state, None,
        )
        self.assertTrue(applied)
        return self.store.get("agent_runs", run["id"])

    def test_external_goal_agent_write_dispatches_once_after_exact_approval(self):
        self.create_connection("slack-agent")
        self.executor.requests.clear()
        run = self._external_agent("slack-agent")
        action = run["_state"]["pendingAction"]
        self.assertEqual("awaiting_approval", run["_state"]["status"])
        self.assertEqual([], self.executor.requests)

        effects = self.store._adaptive_effects(run["id"])
        self.assertEqual(1, len(effects))
        self.assertEqual("prepared", effects[0]["state"])
        self.assertEqual("slack-agent", effects[0]["connectionIdentity"]["connectionId"])
        self.assertEqual(
            effects[0]["integrationPlanHash"],
            effects[0]["preparedIntegrationCall"]["planHash"],
        )

        with self.assertRaises(server.APIError) as stale:
            self.store.atomic(
                self.store.decide_agent_action,
                run["id"], {"decision": "approve", "expectedActionHash": "0" * 64}, REVIEWER,
            )
        self.assertEqual("STALE_AGENT_ACTION", stale.exception.code)

        approved = self.store.atomic(
            self.store.decide_agent_action,
            run["id"], {"decision": "approve", "expectedActionHash": action["actionHash"]}, REVIEWER,
        )
        self.assertEqual("awaiting_tool", approved["status"])
        self.assertEqual([], self.executor.requests)

        advanced = self.store.advance_agent_run(run["id"], ADMIN)
        self.assertEqual("ready", advanced["status"])
        self.assertEqual(1, len(self.executor.requests))
        request_body = json.loads(self.executor.requests[0].body.decode())
        self.assertEqual({"channel": "C123", "text": "Release ready"}, request_body)
        self.assertEqual("Bearer " + SECRET_VALUE, self.executor.requests[0].headers["Authorization"])

        effect = self.store._adaptive_effects(run["id"])[0]
        self.assertEqual("acknowledged", effect["state"])
        self.assertTrue(effect["executionReceipt"]["externalEffect"])
        public_blob = server.encode(self.store.public_agent_run(self.store.get("agent_runs", run["id"]), ADMIN))
        self.assertNotIn(SECRET_VALUE, public_blob)
        self.assertNotIn("AXIOM_TEST_SLACK_TOKEN", public_blob)
        self.assertNotIn("authBindingHash", public_blob)

    def test_connection_revocation_invalidates_prepared_agent_write(self):
        self.create_connection("slack-stale")
        self.executor.requests.clear()
        run = self._external_agent("slack-stale")
        action = copy.deepcopy(run["_state"]["pendingAction"])
        revoked = self.store.atomic(self.store.connection_action, "slack-stale", "revoke", ADMIN)
        self.assertEqual(3, revoked["generation"])
        with self.assertRaises(server.APIError) as changed:
            self.store.atomic(
                self.store.decide_agent_action,
                run["id"], {"decision": "approve", "expectedActionHash": action["actionHash"]}, REVIEWER,
            )
        self.assertEqual("CONNECTION_CHANGED", changed.exception.code)
        self.assertEqual([], self.executor.requests)

    def test_external_write_unknown_outcome_stops_without_blind_retry(self):
        self.create_connection("slack-unknown")
        self.executor.requests.clear()
        run = self._external_agent("slack-unknown")
        action = run["_state"]["pendingAction"]
        self.store.atomic(
            self.store.decide_agent_action,
            run["id"],
            {"decision": "approve", "expectedActionHash": action["actionHash"]},
            REVIEWER,
        )
        self.executor.failure = integrations.IntegrationError(
            "ADAPTER_UNAVAILABLE", "The controlled provider outcome is unknown."
        )

        stopped = self.store.advance_agent_run(run["id"], ADMIN)
        self.assertEqual("stopped", stopped["status"])
        self.assertEqual("WRITE_NEEDS_RECONCILIATION", stopped["error"]["code"])
        self.assertEqual(1, len(self.executor.requests))
        effect = self.store._adaptive_effects(run["id"])[0]
        self.assertEqual("unknown", effect["state"])
        self.assertNotIn("executionReceipt", effect)

        unchanged = self.store.advance_agent_run(run["id"], ADMIN)
        self.assertEqual("stopped", unchanged["status"])
        self.assertEqual(1, len(self.executor.requests))

    def test_parent_simulation_never_dispatches_an_external_write(self):
        self.create_connection("slack-simulation")
        self.executor.requests.clear()
        run = self._external_agent(
            "slack-simulation",
            parent={
                "runId": "controlled-missing-parent",
                "nodeId": "goal-agent",
                "simulation": True,
                "deadlineAt": time.time() + 30,
            },
        )
        action = run["_state"]["pendingAction"]
        self.store.atomic(
            self.store.decide_agent_action,
            run["id"],
            {"decision": "approve", "expectedActionHash": action["actionHash"]},
            REVIEWER,
        )

        observed = self.store.advance_agent_run(run["id"], ADMIN)
        self.assertEqual([], self.executor.requests)
        self.assertEqual("simulation", observed["effectMode"])
        self.assertEqual("ready", observed["status"])
        failed_fact = observed["facts"]["call_0001"]
        self.assertEqual("failed", observed["factSources"]["call_0001"]["status"])
        self.assertEqual("EXTERNAL_WRITE_SUPPRESSED", failed_fact["error"]["code"])
        self.assertFalse(failed_fact["error"]["outcomeUnknown"])


class HttpLockAndStaleHealthTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="external-http-")
        self.store = server.Store(Path(self.work.name) / "axiom.sqlite3", 0)
        self.executor = RecordingExecutor()
        self.store.integration_http = self.executor
        self.environment = patch.dict(os.environ, {"AXIOM_TEST_SLACK_TOKEN": SECRET_VALUE})
        self.resolver = patch.object(
            integrations, "_default_resolver", lambda _host, _port: [PUBLIC_TEST_IP]
        )
        self.environment.start()
        self.resolver.start()
        self.httpd = server.create_server(self.store, 0)
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = None
        status, bootstrap = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status)
        self.csrf = bootstrap["csrf"]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
        self.store.close()
        self.resolver.stop()
        self.environment.stop()
        self.work.cleanup()

    def request(self, method: str, path: str, data: dict | None = None):
        headers = {"Accept": "application/json"}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            response = self.client.open(request, timeout=7)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode())

    def test_slow_health_probe_releases_lock_and_stale_result_is_discarded(self):
        status, created = self.request("POST", "/api/connections", slack_payload("slack-slow"))
        self.assertEqual(200, status, created)
        self.assertEqual("draft", created["status"])
        status, healthy = self.request("POST", "/api/connections/slack-slow/test", {})
        self.assertEqual(200, status, healthy)
        self.assertTrue(healthy["reachable"])
        self.assertEqual(1, healthy["generation"])
        status, activated = self.request("POST", "/api/connections/slack-slow/restore", {})
        self.assertEqual(200, status, activated)
        self.assertEqual("ready", activated["status"])
        self.assertEqual(2, activated["generation"])
        self.assertEqual(2, activated["health"]["generation"])

        status, observed = self.request(
            "POST",
            "/api/connections/slack-slow/invoke",
            {
                "operationId": "slack.conversations.history",
                "arguments": {"channel": "C123", "limit": 1},
                "operationKey": "http:slack-slow:history-1",
            },
        )
        self.assertEqual(200, status, observed)
        self.assertEqual("Observed", observed["output"]["messages"][0]["text"])
        self.assertEqual(2, observed["generation"])
        before_rejected_write = len(self.executor.requests)
        status, rejected_write = self.request(
            "POST",
            "/api/connections/slack-slow/invoke",
            {
                "operationId": "slack.chat.post_message",
                "arguments": {"channel": "C123", "text": "must not dispatch"},
            },
        )
        self.assertEqual(409, status, rejected_write)
        self.assertEqual("READ_ONLY_OPERATION_REQUIRED", rejected_write["error"]["code"])
        self.assertEqual(before_rejected_write, len(self.executor.requests))

        started, release = self.executor.gate_next_call()
        result = {}

        def slow_probe():
            result["response"] = self.request("POST", "/api/connections/slack-slow/test", {})

        probe = threading.Thread(target=slow_probe)
        probe.start()
        self.assertTrue(started.wait(2), "controlled provider request did not start")

        acquired = self.store.lock.acquire(timeout=1)
        self.assertTrue(acquired, "provider I/O held the persistence lock")
        if acquired:
            self.store.lock.release()
        revoked = self.store.atomic(self.store.connection_action, "slack-slow", "revoke", ADMIN)
        self.assertEqual(3, revoked["generation"])
        self.assertEqual("stale", revoked["health"]["status"])
        self.assertIsNone(revoked["health"]["reachable"])

        release.set()
        probe.join(5)
        self.assertFalse(probe.is_alive())
        code, stale = result["response"]
        self.assertEqual(200, code, stale)
        self.assertEqual("stale", stale["status"])
        self.assertFalse(stale["applied"])
        self.assertEqual(2, stale["generation"])

        persisted = self.store._connection_health("slack-slow")
        self.assertEqual(2, persisted["generation"])
        public = self.store.public_connection(self.store.get("connections", "slack-slow"))
        self.assertEqual("stale", public["health"]["status"])
        self.assertEqual(3, public["health"]["generation"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
