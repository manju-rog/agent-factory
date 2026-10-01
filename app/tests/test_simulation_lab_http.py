"""HTTP and restart invariants for the stateful enterprise Simulation Lab.

These tests intentionally use the public HTTP surface for the user journeys and
inspect SQLite only for facts that must not be inferred from presentation data:
stable operation identity, durable reconciliation state, and the absence of an
external effect.  No provider request leaves the local process.
"""

from __future__ import annotations

import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import server  # noqa: E402


PROFILE_IDS = {
    "fresh-incident",
    "existing-incident",
    "missing-owner",
    "confluence-unavailable",
    "slack-rate-limit",
    "jira-lost-ack",
    "changed-flag-version",
}
TERMINAL_AGENT_STATES = {"completed", "failed", "stopped"}


class RunningAxiom:
    """Small restartable loopback server around one durable database."""

    def __init__(self, database: Path):
        self.database = database
        self.store: server.Store | None = None
        self.httpd = None
        self.thread: threading.Thread | None = None
        self.base = ""

    def start(self) -> "RunningAxiom":
        self.store = server.Store(self.database, latency=0)
        self.store.start()
        self.httpd = server.create_server(self.store, port=0)
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            daemon=True,
            name="simulation-lab-http-test",
        )
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        return self

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=3)
        if self.store is not None:
            self.store.close()
        self.store = None
        self.httpd = None
        self.thread = None

    def restart(self) -> "RunningAxiom":
        self.stop()
        return self.start()


class SimulationLabHttpTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="simulation-lab-http-")
        self.database = Path(self.work.name) / "axiom.sqlite3"
        self.live = RunningAxiom(self.database).start()
        self._new_session()

    def tearDown(self):
        self.live.stop()
        self.work.cleanup()

    def _new_session(self):
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        self.csrf = None
        status, bootstrap, _ = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status, bootstrap)
        self.bootstrap = bootstrap
        self.csrf = bootstrap["csrf"]
        return bootstrap

    def request(self, method, path, data=None, *, csrf=True):
        headers = {"Accept": "application/json"}
        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode("utf-8")
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(
            self.live.base + path,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            response = self.client.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else None
            return response.status, body, response.headers

    def switch(self, role):
        user = next(item for item in self.bootstrap["users"] if item["role"] == role)
        status, body, _ = self.request("POST", "/api/session", {"userId": user["id"]})
        self.assertEqual(200, status, body)
        self.csrf = body["csrf"]
        return body

    def assert_error(self, response, status, code):
        actual_status, body, headers = response
        self.assertEqual(status, actual_status, body)
        self.assertEqual(code, body.get("error", {}).get("code"), body)
        self.assertEqual(code, body.get("error", {}).get("errorCode"), body)
        self.assertEqual(
            headers.get("X-Correlation-ID"),
            body.get("error", {}).get("correlationId"),
            body,
        )

    def create_world(self, profile_id):
        status, body, _ = self.request(
            "POST", "/api/simulation-lab/worlds", {"profileId": profile_id}
        )
        self.assertEqual(200, status, body)
        world = body["world"]
        self.assertEqual(profile_id, world["profileId"])
        self.assertEqual(
            {"isolated": True, "externalNetwork": False, "externalEffects": False},
            world["sandbox"],
        )
        return world

    def start_world(self, world):
        status, body, _ = self.request(
            "POST", f"/api/simulation-lab/worlds/{world['id']}/start", {}
        )
        self.assertEqual(200, status, body)
        self.assertIsInstance(body.get("run"), dict, body)
        return body

    def get_world(self, world_id):
        status, body, _ = self.request(
            "GET", f"/api/simulation-lab/worlds/{world_id}"
        )
        self.assertEqual(200, status, body)
        return body["world"]

    def get_run(self, run_id):
        status, body, _ = self.request("GET", f"/api/runs/{run_id}")
        self.assertEqual(200, status, body)
        return body

    def get_agent_run(self, run_id):
        status, body, _ = self.request("GET", f"/api/agent-runs/{run_id}")
        self.assertEqual(200, status, body)
        return body

    def wait_until(self, fetch, predicate, description, timeout=15):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            latest = fetch()
            if predicate(latest):
                return latest
            time.sleep(0.03)
        self.fail(f"Timed out waiting for {description}: {latest}")

    def wait_for_child(self, parent_id):
        parent = self.wait_until(
            lambda: self.get_run(parent_id),
            lambda run: any(node.get("childAgentRunId") for node in run["nodes"]),
            "the flagship workflow to create its Goal Agent child",
        )
        node = next(item for item in parent["nodes"] if item.get("childAgentRunId"))
        return parent, node["childAgentRunId"]

    def wait_for_parent_approval(self, parent_id):
        return self.wait_until(
            lambda: self.get_run(parent_id),
            lambda run: run["status"] == "waiting_approval"
            and any(
                node.get("status") == "waiting_approval"
                and node.get("approvalPacket", {}).get("actions")
                for node in run["nodes"]
            ),
            "an exact adaptive action approval",
        )

    @staticmethod
    def approval_node(parent):
        return next(
            node for node in parent["nodes"]
            if node.get("status") == "waiting_approval"
            and node.get("approvalPacket", {}).get("actions")
        )

    @staticmethod
    def public_fault(world, fault_id):
        return next(item for item in world["faults"] if item["id"] == fault_id)

    @staticmethod
    def exact_approval_body(parent):
        node = SimulationLabHttpTests.approval_node(parent)
        action = node["approvalPacket"]["actions"][0]
        keys = (
            "effectId",
            "nodeId",
            "operationGeneration",
            "actionFingerprint",
            "approvalEnvelopeHash",
        )
        return {
            "nodeId": node["nodeId"],
            "decision": "approve",
            "comment": "Controlled Simulation Lab approval",
            "preparedActions": [{key: action[key] for key in keys}],
        }

    def approve_exact(self, parent):
        body = self.exact_approval_body(parent)
        status, result, _ = self.request(
            "POST", f"/api/runs/{parent['id']}/approve", body
        )
        self.assertEqual(200, status, result)
        return result

    def test_schema_13_catalog_exposes_exactly_seven_pinned_profiles(self):
        status, health, _ = self.request("GET", "/api/health", csrf=False)
        self.assertEqual(200, status, health)
        self.assertEqual(13, health["schemaVersion"])

        status, catalog, _ = self.request("GET", "/api/simulation-lab")
        self.assertEqual(200, status, catalog)
        self.assertEqual(PROFILE_IDS, {item["id"] for item in catalog["profiles"]})
        self.assertEqual(7, len(catalog["profiles"]))
        for profile in catalog["profiles"]:
            self.assertEqual("axiom.simulation-profile.v1", profile["schemaVersion"])
            self.assertRegex(profile["definitionHash"], r"^[0-9a-f]{64}$")
            self.assertTrue(profile["name"])
            self.assertTrue(profile["description"])
        self.assertIn("simulationLab", self.bootstrap)
        self.assertEqual(
            PROFILE_IDS,
            {item["id"] for item in self.bootstrap["simulationLab"]["profiles"]},
        )

    def test_create_get_fault_toggle_and_reset_are_real_world_transitions(self):
        world = self.create_world("fresh-incident")
        original = self.get_world(world["id"])
        self.assertEqual("axiom.simulation-world.v1", original["schemaVersion"])
        self.assertGreaterEqual(len(original["events"]), 1)
        self.assertEqual("world.created", original["events"][0]["kind"])

        status, changed, _ = self.request(
            "POST",
            f"/api/simulation-lab/worlds/{world['id']}/faults",
            {"faultId": "confluenceUnavailable", "enabled": True},
        )
        self.assertEqual(200, status, changed)
        changed_world = changed["world"]
        self.assertTrue(
            self.public_fault(changed_world, "confluence-unavailable")["enabled"]
        )
        self.assertGreater(changed_world["revision"], original["revision"])
        self.assertTrue(
            any(event["kind"] == "fault.changed" for event in changed_world["events"]),
            changed_world["events"],
        )

        status, reset, _ = self.request(
            "POST", f"/api/simulation-lab/worlds/{world['id']}/reset", {}
        )
        self.assertEqual(200, status, reset)
        reset_world = reset["world"]
        self.assertEqual(world["id"], reset_world["id"])
        self.assertEqual("fresh-incident", reset_world["profileId"])
        self.assertFalse(
            self.public_fault(reset_world, "confluence-unavailable")["enabled"]
        )
        self.assertEqual(0, reset_world["operationCount"])
        self.assertGreater(reset_world["generation"], original["generation"])

    def test_mutations_enforce_csrf_and_the_declared_role_boundary(self):
        self.assert_error(
            self.request(
                "POST",
                "/api/simulation-lab/worlds",
                {"profileId": "fresh-incident"},
                csrf=False,
            ),
            403,
            "CSRF_DENIED",
        )

        self.switch("reviewer")
        status, readable, _ = self.request("GET", "/api/simulation-lab")
        self.assertEqual(200, status, readable)
        self.assert_error(
            self.request(
                "POST", "/api/simulation-lab/worlds", {"profileId": "fresh-incident"}
            ),
            403,
            "ROLE_DENIED",
        )

        self.switch("operator")
        world = self.create_world("existing-incident")
        status, toggled, _ = self.request(
            "POST",
            f"/api/simulation-lab/worlds/{world['id']}/faults",
            {"faultId": "confluenceUnavailable", "enabled": True},
        )
        self.assertEqual(200, status, toggled)

        self.switch("contributor")
        self.assert_error(
            self.request(
                "POST", f"/api/simulation-lab/worlds/{world['id']}/reset", {}
            ),
            403,
            "ROLE_DENIED",
        )
        # Starting a governed workflow is deliberately distinct from changing
        # its sandbox. Contributors may start it, but cannot approve its writes.
        started = self.start_world(world)
        parent = self.wait_for_parent_approval(started["run"]["id"])
        exact = self.exact_approval_body(parent)
        self.assert_error(
            self.request(
                "POST", f"/api/runs/{parent['id']}/approve", exact
            ),
            403,
            "ROLE_DENIED",
        )

    def test_fresh_start_creates_the_flagship_workflow_and_goal_agent_child(self):
        world = self.create_world("fresh-incident")
        started = self.start_world(world)
        parent, child_id = self.wait_for_child(started["run"]["id"])
        child = self.wait_until(
            lambda: self.get_agent_run(child_id),
            lambda run: run["status"] == "awaiting_approval",
            "the Incident Commander to prepare its first consequential action",
        )
        self.assertEqual("atlas-incident-commander", child["specId"])
        self.assertEqual(parent["id"], child["parent"]["runId"])
        self.assertEqual("simulation.jira.create_incident", child["pendingAction"]["toolId"])
        self.assertEqual("write", child["pendingAction"]["effect"])
        self.assertRegex(child["pendingAction"]["actionHash"], r"^[0-9a-f]{64}$")
        self.assertRegex(child["pendingAction"]["operationKey"], r"^adaptive:")

        stored_parent = self.live.store.get("runs", parent["id"])
        goal_nodes = [
            item for item in stored_parent["_snapshot"]["nodes"]
            if stored_parent["_snapshot"]["agentManifests"][item["id"]]
            .get("implementationId") == "goal-agent"
        ]
        self.assertEqual(1, len(goal_nodes))
        self.assertEqual(
            "atlas-incident-commander",
            goal_nodes[0]["config"]["factorySpecId"],
        )

    def test_actual_jira_evidence_changes_the_next_tool_sequence(self):
        fresh = self.create_world("fresh-incident")
        fresh_start = self.start_world(fresh)
        _, fresh_child_id = self.wait_for_child(fresh_start["run"]["id"])
        fresh_child = self.wait_until(
            lambda: self.get_agent_run(fresh_child_id),
            lambda run: run["status"] == "awaiting_approval",
            "the fresh path's first exact action",
        )

        existing = self.create_world("existing-incident")
        existing_start = self.start_world(existing)
        _, existing_child_id = self.wait_for_child(existing_start["run"]["id"])
        existing_child = self.wait_until(
            lambda: self.get_agent_run(existing_child_id),
            lambda run: run["status"] == "awaiting_approval",
            "the duplicate-aware path's first exact action",
        )

        def observed_tools(run):
            return [
                event["toolId"] for event in run["events"]
                if event.get("type") == "tool.observed"
            ]

        required_reads = {
            "simulation.metrics.query",
            "simulation.catalog.get_service",
            "simulation.deployments.list_recent",
            "simulation.jira.search_incidents",
            "simulation.confluence.get_page",
            "simulation.feature_flags.get",
        }
        self.assertTrue(required_reads <= set(observed_tools(fresh_child)))
        self.assertTrue(required_reads <= set(observed_tools(existing_child)))
        self.assertEqual(
            "simulation.jira.create_incident",
            fresh_child["pendingAction"]["toolId"],
        )
        self.assertEqual(
            "simulation.feature_flags.update",
            existing_child["pendingAction"]["toolId"],
        )
        self.assertNotIn(
            "simulation.jira.create_incident", observed_tools(existing_child)
        )
        existing_world = self.get_world(existing["id"])
        self.assertEqual(1, len(existing_world["records"]["jiraIssues"]))
        self.assertEqual(0, existing_world["operationCount"])

    def test_exact_approval_rejects_missing_or_stale_reference_and_stays_local(self):
        world = self.create_world("fresh-incident")
        started = self.start_world(world)
        parent = self.wait_for_parent_approval(started["run"]["id"])
        self.switch("reviewer")
        parent = self.get_run(parent["id"])
        node = self.approval_node(parent)

        self.assert_error(
            self.request(
                "POST",
                f"/api/runs/{parent['id']}/approve",
                {"nodeId": node["nodeId"], "decision": "approve"},
            ),
            400,
            "PREPARED_ACTION_REFERENCE_REQUIRED",
        )
        stale = self.exact_approval_body(parent)
        stale["preparedActions"][0]["actionFingerprint"] = "0" * 64
        self.assert_error(
            self.request("POST", f"/api/runs/{parent['id']}/approve", stale),
            409,
            "STALE_PREPARED_ACTION",
        )

        child_id = node["childAgentRunId"]
        self.approve_exact(parent)
        child = self.wait_until(
            lambda: self.get_agent_run(child_id),
            lambda run: any(
                effect.get("state") in {"acknowledged", "reconciled"}
                for effect in run.get("effects", [])
            ),
            "the approved Jira operation receipt",
        )
        committed = next(
            effect for effect in child["effects"]
            if effect.get("state") in {"acknowledged", "reconciled"}
        )
        self.assertFalse(committed["executionReceipt"]["externalEffect"])
        current_world = self.get_world(world["id"])
        self.assertFalse(current_world["sandbox"]["externalEffects"])
        self.assertEqual(1, current_world["operationCount"])
        self.assertEqual(1, len(current_world["records"]["jiraIssues"]))

    def test_lost_ack_reconciles_one_operation_after_restart_and_world_persists(self):
        world = self.create_world("jira-lost-ack")
        started = self.start_world(world)
        parent = self.wait_for_parent_approval(started["run"]["id"])
        node = self.approval_node(parent)
        child_id = node["childAgentRunId"]
        self.switch("reviewer")
        self.approve_exact(self.get_run(parent["id"]))

        uncertain_before_restart = self.wait_until(
            lambda: self.get_agent_run(child_id),
            lambda run: run.get("status") == "stopped"
            and run.get("error", {}).get("code") == "WRITE_NEEDS_RECONCILIATION"
            and any(effect.get("state") == "unknown" for effect in run.get("effects", [])),
            "the lost acknowledgement to remain an explicit unknown outcome",
        )
        unknown_effect = next(
            effect for effect in uncertain_before_restart["effects"]
            if effect["state"] == "unknown"
        )
        operation_key = unknown_effect["operationKey"]
        self.assertEqual(504, unknown_effect["failureReceipt"]["statusCode"])
        host_types = [event.get("type") for event in uncertain_before_restart["hostEvents"]]
        self.assertIn("tool.failed", host_types)
        self.assertNotIn("effect.reconciled", host_types)

        before_restart = self.get_world(world["id"])
        self.assertEqual(1, before_restart["operationCount"])
        self.assertEqual(1, len(before_restart["records"]["jiraIssues"]))
        before_event_count = len(before_restart["events"])
        with self.live.store.lock:
            operation_rows = self.live.store.db.execute(
                "SELECT data FROM simulation_operations WHERE world_id=?",
                (world["id"],),
            ).fetchall()
        self.assertEqual(1, len(operation_rows))
        recorded_operation = json.loads(operation_rows[0]["data"])
        self.assertEqual(operation_key, recorded_operation["operationKey"])
        self.assertFalse(recorded_operation["receipt"]["externalEffect"])

        self.live.restart()
        self._new_session()
        persisted = self.get_world(world["id"])
        self.assertEqual("jira-lost-ack", persisted["profileId"])
        self.assertEqual(1, persisted["operationCount"])
        self.assertEqual(1, len(persisted["records"]["jiraIssues"]))
        self.assertGreaterEqual(len(persisted["events"]), before_event_count)

        recovered = self.wait_until(
            lambda: self.get_agent_run(child_id),
            lambda run: any(
                effect.get("operationKey") == operation_key
                and effect.get("state") == "reconciled"
                and effect.get("executionReceipt", {}).get("recovered") is True
                for effect in run.get("effects", [])
            ),
            "startup reconciliation of the durable unknown Jira operation",
        )
        recovered_effect = next(
            effect for effect in recovered["effects"]
            if effect.get("operationKey") == operation_key
        )
        self.assertNotEqual(
            "WRITE_NEEDS_RECONCILIATION", recovered.get("error", {}).get("code"),
            "A recovered session must not retain its obsolete reconciliation error.",
        )
        self.assertTrue(recovered_effect["executionReceipt"]["recovered"])
        self.assertFalse(recovered_effect["executionReceipt"]["externalEffect"])
        self.assertTrue(
            any(
                event.get("type") in {"effect.reconciled", "agent.recovered"}
                for event in recovered["hostEvents"]
            ),
            recovered["hostEvents"],
        )
        with self.live.store.lock:
            count = self.live.store.db.execute(
                "SELECT COUNT(*) FROM simulation_operations WHERE world_id=?",
                (world["id"],),
            ).fetchone()[0]
        self.assertEqual(1, count)


if __name__ == "__main__":
    unittest.main()
