"""HTTP boundary checks for the general agent factory.

The generic engine's registry-injection and provider-stub tests cover arbitrary
capability extensibility. These tests exercise the real local application's
registered adapters, editable agent specifications, authorization and effects.
They do not claim a live external model or external business-system integration.
"""

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

try:
    from . import test_integration as http_harness
except ImportError:  # Support direct execution from the tests directory.
    import test_integration as http_harness


class FactoryHttpTests(unittest.TestCase):
    request = http_harness.HttpBoundaryTests.request
    switch = http_harness.HttpBoundaryTests.switch
    setUp = http_harness.HttpBoundaryTests.setUp

    @classmethod
    def setUpClass(cls):
        http_harness.HttpBoundaryTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        http_harness.HttpBoundaryTests.tearDownClass.__func__(cls)

    def factory(self):
        status, result, _ = self.request("GET", "/api/agent-factory")
        self.assertEqual(200, status, result)
        for key in ("specs", "tools", "runs", "scenarios", "provider"):
            self.assertIn(key, result)
        return result

    def editable_spec(self, source):
        keys = ("name", "mission", "instructions", "contextFields",
                "inputSchema", "outputSchema", "allowedTools", "limits",
                "requiredEvidenceTools", "stopRules", "policyRefs",
                "evaluationCases")
        result = {key: copy.deepcopy(source[key]) for key in keys if key in source}
        result["name"] = "HTTP agent factory verification"
        return result

    def effects(self):
        db_path = Path(self.work.name) / "integration.sqlite3"
        db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        try:
            rows = db.execute(
                "SELECT id,node_id,operation_key,action_fingerprint,state,data "
                "FROM effects WHERE node_id LIKE 'agent:%' ORDER BY id"
            ).fetchall()
        finally:
            db.close()
        return [
            {
                "id": ident,
                "nodeId": node_id,
                "operationKey": operation_key,
                "actionFingerprint": fingerprint,
                "state": state,
                "data": json.loads(data),
            }
            for ident, node_id, operation_key, fingerprint, state, data in rows
        ]

    def poll_agent(self, run_id, statuses, timeout=20):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            status, latest, _ = self.request("GET", "/api/agent-runs/" + run_id)
            self.assertEqual(200, status, latest)
            if latest["status"] in statuses:
                return latest
            time.sleep(0.05)
        self.fail(f"Agent did not reach {statuses}: {latest}")

    def test_custom_agent_spec_roles_unknown_tool_and_stale_revision(self):
        catalog = self.factory()
        self.assertTrue(catalog["tools"])
        self.assertTrue(catalog["specs"])
        body = self.editable_spec(catalog["specs"][0])
        self.switch("contributor")
        status, denied, _ = self.request("POST", "/api/agent-specs", body)
        self.assertEqual(403, status, denied)
        self.switch("admin")
        invalid = copy.deepcopy(body)
        invalid["allowedTools"] = ["unregistered_http_verification_tool"]
        status, rejected, _ = self.request("POST", "/api/agent-specs", invalid)
        self.assertIn(status, (400, 422), rejected)
        self.assertIn("error", rejected)
        status, created, _ = self.request("POST", "/api/agent-specs", body)
        self.assertIn(status, (200, 201), created)
        self.assertNotEqual(catalog["specs"][0]["id"], created["id"])
        self.assertEqual("draft", created["status"])
        status, agents, _ = self.request("GET", "/api/agents")
        self.assertEqual(200, status, agents)
        self.assertFalse(any(agent.get("factorySpecId") == created["id"] for agent in agents))
        update = {"expectedRevision": created["draftRevision"], "mission": created["mission"] + " Keep an inspectable observation trail."}
        status, saved, _ = self.request("PUT", "/api/agent-specs/" + created["id"], update)
        self.assertEqual(200, status, saved)
        self.assertGreater(saved["draftRevision"], created["draftRevision"])
        status, stale, _ = self.request("PUT", "/api/agent-specs/" + created["id"], update)
        self.assertEqual(409, status, stale)
        status, denied, _ = self.request("POST", "/api/agent-specs/" + created["id"] + "/publish", {"expectedRevision": saved["draftRevision"]})
        self.assertEqual(403, status, denied)
        self.switch("reviewer")
        status, published, _ = self.request("POST", "/api/agent-specs/" + created["id"] + "/publish", {"expectedRevision": saved["draftRevision"]})
        self.assertEqual(200, status, published)
        self.assertEqual(published["publishedVersion"], published["version"])
        status, agents, _ = self.request("GET", "/api/agents")
        self.assertEqual(200, status, agents)
        alias = next(agent for agent in agents if agent.get("factorySpecId") == created["id"])
        self.assertEqual("goal-agent", alias["implementationId"])
        self.assertEqual(published["publishedVersion"], alias["factorySpecVersion"])
        self.switch("contributor")
        fixture_input = {
            key: "fixture-value"
            for key in published["inputSchema"].get("required", [])
        }
        status, unsupported, _ = self.request("POST", "/api/agent-runs", {
            "specId": published["id"], "specVersion": published["publishedVersion"],
            "mode": "fixture", "input": fixture_input,
        })
        self.assertIn(status, (400, 409, 422), unsupported)
        self.assertIn("FIXTURE", unsupported["error"]["code"])

    def test_input_schema_host_limits_and_unconfigured_provider_fail_closed(self):
        self.switch("admin")
        catalog = self.factory()
        source = catalog["specs"][0]
        body = self.editable_spec(source)
        invalid = copy.deepcopy(body)
        invalid["inputSchema"]["additionalProperties"] = True
        status, rejected, _ = self.request("POST", "/api/agent-specs", invalid)
        self.assertIn(status, (400, 422), rejected)
        self.assertIn("error", rejected)
        invalid = copy.deepcopy(body)
        invalid.setdefault("limits", {})["maxWriteCalls"] = 999999
        status, rejected, _ = self.request("POST", "/api/agent-specs", invalid)
        self.assertIn(status, (400, 422), rejected)
        self.assertIn("error", rejected)
        status, rejected, _ = self.request("POST", "/api/agent-runs", {
            "specId": source["id"], "mode": "fixture", "input": {"undeclared_http_input": True},
        })
        self.assertIn(status, (400, 422), rejected)
        self.assertIn("error", rejected)
        if not catalog["provider"]["configured"]:
            status, unavailable, _ = self.request("POST", "/api/agent-runs", {
                "specId": source["id"], "mode": "model", "input": {},
            })
            self.assertEqual(503, status, unavailable)
            self.assertIn("PROVIDER", unavailable["error"]["code"])

    def test_observed_existing_record_changes_next_action_and_new_write_needs_exact_approval(self):
        self.switch("contributor")
        catalog = self.factory()
        scenarios = {scenario["input"]["requestId"]: scenario for scenario in catalog["scenarios"]
                     if scenario.get("input", {}).get("requestId") in {"SR-EXISTING", "SR-NEW"}}
        self.assertEqual({"SR-EXISTING", "SR-NEW"}, set(scenarios))
        before = len(self.effects())
        runs = {}
        for request_id in ("SR-EXISTING", "SR-NEW"):
            scenario = scenarios[request_id]
            status, run, _ = self.request("POST", "/api/agent-runs", {
                "specId": scenario["specId"], "mode": "fixture", "scenario": scenario["id"],
                "input": scenario["input"],
            })
            self.assertIn(status, (200, 201), run)
            runs[request_id] = self.poll_agent(run["id"], {"completed", "awaiting_approval", "failed", "stopped"})
        existing, new = runs["SR-EXISTING"], runs["SR-NEW"]
        self.assertEqual(existing["specId"], new["specId"])
        self.assertEqual("completed", existing["status"], existing)
        self.assertEqual("awaiting_approval", new["status"], new)
        self.assertTrue(
            existing.get("outcomeValidation", {}).get("businessOutcomeVerified"),
            existing,
        )
        self.assertEqual(before + 1, len(self.effects()))
        self.assertIn("prepared", {effect["state"] for effect in self.effects()})
        existing_results = [event for event in existing["events"] if event["type"] == "tool.observed" and "result" in event]
        self.assertTrue(any(event["result"].get("existingTicket") == "LOCAL-INC-208" for event in existing_results))
        self.assertFalse(any(event.get("action", {}).get("effect") == "write" for event in existing["events"]))
        action = new["pendingAction"]
        self.assertEqual("service.create_ticket", action["toolId"])
        self.assertEqual("write", action["effect"])
        self.assertEqual("SR-NEW", action["arguments"]["requestId"])
        self.assertEqual("KB-LOGIN-07", action["arguments"]["runbookReference"])
        for run in runs.values():
            labels = [event.get("provider", "") for event in run["events"] if event["type"] == "model.decision"]
            self.assertTrue(labels)
            self.assertTrue(all(label.startswith("scripted") for label in labels), labels)
        decision_path = "/api/agent-runs/" + new["id"] + "/decision"
        decision = {"decision": "approve", "expectedActionHash": action["actionHash"], "comment": "Reviewed exact local action"}
        status, denied, _ = self.request("POST", decision_path, decision)
        self.assertEqual(403, status, denied)
        self.switch("reviewer")
        status, changed, _ = self.request("POST", decision_path, {**decision, "expectedActionHash": "0" * 64})
        self.assertIn(status, (409, 422), changed)
        self.assertEqual(before + 1, len(self.effects()))
        for _ in range(2):
            status, accepted, _ = self.request("POST", decision_path, decision)
            self.assertEqual(200, status, accepted)
        finished = self.poll_agent(new["id"], {"completed", "failed", "stopped"})
        self.assertEqual("completed", finished["status"], finished)
        self.assertTrue(
            finished.get("outcomeValidation", {}).get("businessOutcomeVerified"),
            finished,
        )
        effects = self.effects()
        self.assertEqual(before + 1, len(effects))
        matching = [effect for effect in effects if effect.get("actionHash") == action["actionHash"]]
        if not matching:
            matching = [effect for effect in effects if effect["actionFingerprint"] == action["actionHash"]]
        self.assertEqual(1, len(matching))
        self.assertTrue(matching[0]["nodeId"].startswith("agent:"))
        self.assertIn(matching[0]["state"], {"acknowledged", "reconciled"})
        serialized_effect = json.dumps(matching[0]["data"], sort_keys=True)
        self.assertIn("SR-NEW", serialized_effect)
        self.assertIn("KB-LOGIN-07", serialized_effect)
        self.assertFalse(matching[0]["data"].get("externalEffect", False))
        self.assertTrue(finished["evidence"])


class FactoryModelBridgeHttpTests(unittest.TestCase):
    """Actual HTTP transport, with a declared scripted local model test double."""

    request = http_harness.HttpBoundaryTests.request
    switch = http_harness.HttpBoundaryTests.switch
    setUp = http_harness.HttpBoundaryTests.setUp
    poll_run = http_harness.HttpBoundaryTests.poll_run

    @classmethod
    def setUpClass(cls):
        cls.model_requests = []

        class ModelDouble(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.model_requests.append(request)
                context = json.loads(request["messages"][-1]["content"])
                if not context["observations"]:
                    decision = {"kind": "call", "toolId": "service.lookup",
                                "arguments": {"requestId": {"$ref": "input.requestId"}}}
                else:
                    decision = {"kind": "finish", "output": {"ticket": {"$ref": "facts.call_0001.existingTicket"}},
                                "evidence": ["facts.call_0001.existingTicket"]}
                payload = json.dumps({"choices": [{"message": {"content": json.dumps(decision)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        cls.model_server = ThreadingHTTPServer(("127.0.0.1", 0), ModelDouble)
        cls.model_thread = threading.Thread(target=cls.model_server.serve_forever, daemon=True)
        cls.model_thread.start()
        cls.model_environment = patch.dict(os.environ, {
            "AXIOM_MODEL_ENDPOINT": f"http://127.0.0.1:{cls.model_server.server_port}/v1/chat/completions",
            "AXIOM_MODEL_NAME": "controlled-http-test-double-not-ai",
            "AXIOM_MODEL_API_KEY": "",
        })
        cls.model_environment.start()
        try:
            http_harness.HttpBoundaryTests.setUpClass.__func__(cls)
        except BaseException:
            cls.model_server.shutdown()
            cls.model_server.server_close()
            cls.model_thread.join(timeout=2)
            raise
        finally:
            cls.model_environment.stop()

    @classmethod
    def tearDownClass(cls):
        try:
            http_harness.HttpBoundaryTests.tearDownClass.__func__(cls)
        finally:
            cls.model_server.shutdown()
            cls.model_server.server_close()
            cls.model_thread.join(timeout=2)

    def test_custom_spec_is_registered_published_and_runs_as_a_pinned_workflow_child(self):
        self.switch("admin")
        object_schema = lambda fields: {"type": "object", "properties": fields,
                                       "required": list(fields), "additionalProperties": False}
        body = {"name": "HTTP custom record investigator", "mission": "Find the actual existing ticket for the supplied request.",
                "instructions": "Use observations as evidence. Do not invent records.",
                "inputSchema": object_schema({"requestId": {"type": "string"}}),
                "outputSchema": object_schema({"ticket": {"type": "string"}}),
                "contextFields": ["input.requestId"], "allowedTools": ["service.lookup"],
                "limits": {"maxTurns": 3, "maxToolCalls": 1, "maxWriteCalls": 0}}
        status, spec, _ = self.request("POST", "/api/agent-specs", body)
        self.assertIn(status, (200, 201), spec)
        self.assertEqual("draft", spec["status"])
        status, agents, _ = self.request("GET", "/api/agents")
        self.assertEqual(200, status, agents)
        self.assertFalse(any(agent.get("factorySpecId") == spec["id"] for agent in agents))
        self.switch("reviewer")
        status, spec, _ = self.request("POST", "/api/agent-specs/" + spec["id"] + "/publish", {"expectedRevision": spec["draftRevision"]})
        self.assertEqual(200, status, spec)
        self.switch("admin")
        status, agents, _ = self.request("GET", "/api/agents")
        self.assertEqual(200, status, agents)
        alias = next(
            agent for agent in agents
            if agent.get("factorySpecId") == spec["id"]
            and agent.get("factorySpecVersion") == spec["publishedVersion"]
        )
        self.assertEqual("goal-agent", alias["implementationId"])
        self.assertEqual(spec["id"], alias["factorySpecId"])
        self.assertEqual(spec["publishedVersion"], alias["factorySpecVersion"])
        self.assertEqual("model", alias["defaultFactoryMode"])
        task_schema = object_schema({"requestId": {"type": "string"}, "privateField": {"type": "string"}})
        status, template, _ = self.request("POST", "/api/templates", {
            "name": "HTTP custom agent parent", "inputSchema": task_schema,
        })
        self.assertIn(status, (200, 201), template)
        path = "/api/templates/" + template["id"]
        config = {"executionMode": "automatic", "executorRole": "contributor", "approvalRequired": False,
                  "approverRole": "reviewer", "timeoutSeconds": 30, "retries": 0,
                  "factorySpecId": spec["id"], "factorySpecVersion": spec["publishedVersion"],
                  "factoryMode": "model"}
        status, template, _ = self.request("PUT", path, {
            "expectedRevision": template["draftRevision"], "name": template["name"],
            "inputSchema": task_schema,
            "nodes": [{"id": "custom_agent", "agentId": alias["id"], "label": "Investigate observed record",
                       "x": 100, "y": 100, "config": config}], "edges": [],
        })
        self.assertEqual(200, status, template)
        status, submitted, _ = self.request("POST", path + "/submit", {})
        self.assertEqual(200, status, submitted)
        self.switch("reviewer")
        status, published, _ = self.request("POST", path + "/publish", {})
        self.assertEqual(200, status, published)
        self.switch("contributor")
        status, parent, _ = self.request("POST", "/api/runs", {
            "templateId": template["id"], "mode": "fixture", "scenario": "happy",
            "input": {"requestId": "SR-EXISTING", "privateField": "never project into the model"},
        })
        self.assertIn(status, (200, 201), parent)
        finished = self.poll_run(parent["id"], {"completed", "needs_attention", "rejected"})
        self.assertEqual("completed", finished["status"], finished)
        node = finished["nodes"][0]
        self.assertEqual({"ticket": "LOCAL-INC-208"}, node["output"])
        status, child, _ = self.request("GET", "/api/agent-runs/" + node["childAgentRunId"])
        self.assertEqual(200, status, child)
        self.assertEqual("completed", child["status"])
        self.assertTrue(child["provider"].startswith("configured-model"), child["provider"])
        self.assertEqual(spec["id"], child["specId"])
        self.assertEqual(spec["version"], child["specVersion"])
        self.assertEqual(parent["id"], child["parent"]["runId"])
        self.assertEqual({"requestId": "SR-EXISTING"}, child["input"])
        self.assertTrue(child["evidence"])
        self.assertEqual(2, len(self.model_requests))
        sent = json.dumps(self.model_requests)
        self.assertNotIn("never project into the model", sent)
        self.assertIn("LOCAL-INC-208", sent)
        self.assertTrue(node["evidence"])
        self.assertTrue(all(item["source"].startswith("facts.") for item in node["evidence"]))
        self.assertEqual("unknown", child["outcomeValidation"]["status"])
        self.assertFalse(child["outcomeValidation"]["businessOutcomeVerified"])
        db_path = Path(self.work.name) / "integration.sqlite3"
        db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        try:
            saved_child = json.loads(db.execute(
                "SELECT data FROM agent_runs WHERE id=?", (child["id"],)
            ).fetchone()[0])
        finally:
            db.close()
        initiator = next(user["id"] for user in self.bootstrap["users"] if user["role"] == "contributor")
        self.assertEqual(initiator, saved_child["_initiator"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
