"""Host, persistence and parent-workflow invariants for generic goal agents."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_factory
import factory_fixtures
from server import APIError, Store, USERS, DEFAULT_CONFIG, create_server

AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


class FactoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "agents.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def start(self, request_id="SR-NEW", mode="fixture"):
        return self.call("create_agent_run", {"specId": "service-investigator", "mode": mode, "input": {"requestId": request_id}}, CONTRIBUTOR)

    def until(self, ident, status, limit=40):
        for _ in range(limit):
            run = self.store.public_agent_run(self.store.get("agent_runs", ident), AUTHOR)
            if run["status"] == status:
                return run
            if run["status"] in {"failed", "stopped", "completed"}:
                self.fail(f"Expected {status}; got {run['status']}: {run.get('error')}")
            self.store.advance_agent_run(ident, AUTHOR)
        self.fail(f"Agent never reached {status}: {run}")

    def effects(self):
        return self.store.db.execute(
            "SELECT COUNT(*) FROM effects WHERE node_id LIKE 'agent:%'"
        ).fetchone()[0]

    def effect_rows(self):
        rows = self.store.db.execute(
            "SELECT id,node_id,operation_key,action_fingerprint,state,data "
            "FROM effects WHERE node_id LIKE 'agent:%' ORDER BY id"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "nodeId": row["node_id"],
                "operationKey": row["operation_key"],
                "actionFingerprint": row["action_fingerprint"],
                "state": row["state"],
                "data": json.loads(row["data"]),
            }
            for row in rows
        ]

    def approve(self, run):
        return self.call("decide_agent_action", run["id"], {"decision": "approve", "expectedActionHash": run["pendingAction"]["actionHash"]}, REVIEWER)

    @staticmethod
    def parent_decision_body(run, node_id, decision="approve"):
        node = next(item for item in run["nodes"] if item["nodeId"] == node_id)
        body = {"nodeId": node_id, "decision": decision, "comment": "Factory integration test"}
        actions = node.get("approvalPacket", {}).get("actions", [])
        if actions:
            body["preparedActions"] = [
                {
                    key: action[key]
                    for key in (
                        "effectId", "nodeId", "operationGeneration",
                        "actionFingerprint", "approvalEnvelopeHash",
                    )
                }
                for action in actions
            ]
        return body

    def published_alias(self, spec):
        version = spec.get("publishedVersion") or spec.get("version")
        return next(
            agent
            for agent in self.store.all("agents")
            if agent.get("implementationId") == "goal-agent"
            and agent.get("factorySpecId") == spec["id"]
            and agent.get("factorySpecVersion") == version
        )

    def parent_template(self, manual=False, approval=False):
        spec = self.store.get("agent_specs", "service-investigator")
        version = spec.get("publishedVersion") or spec.get("version")
        alias = self.published_alias(spec)
        task_schema = {
            "type": "object",
            "properties": {"requestId": {"type": "string"}},
            "required": ["requestId"],
            "additionalProperties": False,
        }
        template = self.call(
            "create_template",
            {"name": "Agent-based service process", "inputSchema": task_schema},
            AUTHOR,
        )
        nodes = [{
            "id": "investigate",
            "agentId": alias["id"],
            "label": "Investigate using observed context",
            "x": 160,
            "y": 180,
            "config": {
                **DEFAULT_CONFIG,
                "factoryMode": "fixture",
                "factorySpecId": spec["id"],
                "factorySpecVersion": version,
                "executionMode": "manual" if manual else "automatic",
                "approvalRequired": approval,
            },
        }]
        self.call(
            "update_template",
            template["id"],
            {"expectedRevision": 1, "inputSchema": task_schema, "nodes": nodes, "edges": []},
            AUTHOR,
        )
        self.call("submit_template", template["id"], AUTHOR)
        return self.call("publish_template", template["id"], REVIEWER)

    def parent_until(self, run_id, status, limit=60, drive_children=True):
        for _ in range(limit):
            run = self.store.get("runs", run_id)
            if run["status"] == status:
                return run
            self.store.tick()
            if drive_children:
                for child in self.store.all("agent_runs"):
                    if child.get("_parent", {}).get("runId") == run_id:
                        self.store.advance_agent_run(child["id"], AUTHOR)
        self.fail(f"Parent did not reach {status}: {run['status']} {run['nodes']}")

    def test_approved_effect_resumes_after_restart_and_stable_key_prevents_duplicates(self):
        run = self.start()
        awaiting = self.until(run["id"], "awaiting_approval")
        self.assertEqual(self.effects(), 1)
        self.assertEqual("prepared", self.effect_rows()[0]["state"])
        self.approve(awaiting)
        approved_state = copy.deepcopy(self.store.get("agent_runs", run["id"])["_state"])
        self.store.close()
        self.store = Store(self.path, latency=0)
        completed = self.until(run["id"], "completed")
        self.assertEqual(self.effects(), 1)
        self.assertEqual(completed["provider"], "scripted-fixture")
        stored = self.store.get("agent_runs", run["id"])
        stored["_state"] = approved_state
        self.store.put("agent_runs", stored)
        replayed = self.until(run["id"], "completed")
        self.assertEqual(self.effects(), 1)
        self.assertEqual(replayed["output"], completed["output"])
        row = self.effect_rows()[0]
        self.assertTrue(row["nodeId"].startswith("agent:"))
        self.assertIn(row["state"], {"acknowledged", "reconciled"})
        observations = [e for e in replayed["events"] if e["type"] == "tool.observed"]
        self.assertEqual(len(observations), 3)

    def test_labeled_duplicate_variation_records_two_attempts_and_one_effect(self):
        run = self.call(
            "create_agent_run",
            {
                "specId": "service-investigator", "mode": "fixture",
                "scenario": "service-duplicate-operation",
                "input": {"requestId": "SR-NEW"},
            },
            CONTRIBUTOR,
        )
        awaiting = self.until(run["id"], "awaiting_approval")
        self.approve(awaiting)
        completed = self.until(run["id"], "completed")
        self.assertEqual(1, self.effects())
        replay = next(
            event for event in completed["hostEvents"]
            if event["type"] == "effect.duplicate_replay_verified"
        )
        self.assertEqual(2, replay["writeAttempts"])
        self.assertEqual(1, replay["uniqueEffectCount"])
        self.assertEqual("work_item_captured", completed["output"]["outcome"])

    def test_tampered_approved_action_never_reaches_adapter(self):
        run = self.start()
        awaiting = self.until(run["id"], "awaiting_approval")
        self.approve(awaiting)
        stored = self.store.get("agent_runs", run["id"])
        stored["_state"]["pendingAction"]["arguments"]["summary"] = "A different unauthorized effect"
        self.store.put("agent_runs", stored)
        failed = self.store.advance_agent_run(run["id"], AUTHOR)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.effects(), 1)
        self.assertEqual("prepared", self.effect_rows()[0]["state"])
        self.assertNotIn("executionReceipt", self.effect_rows()[0]["data"])

    def test_definition_version_is_pinned_before_the_next_runtime_turn(self):
        run = self.start("SR-EXISTING")
        spec = self.store.get("agent_specs", "service-investigator")
        self.call(
            "update_agent_spec",
            spec["id"],
            {"expectedRevision": spec["draftRevision"], "mission": "A changed future mission"},
            AUTHOR,
        )
        finished = self.until(run["id"], "completed")
        self.assertEqual(finished["specVersion"], 1)
        self.assertIn("service.lookup", finished["specSnapshot"]["allowedTools"])
        edited = self.store.get("agent_specs", spec["id"])
        self.assertGreater(edited["version"], finished["specVersion"])
        self.assertEqual(edited["publishedVersion"], finished["specVersion"])

    def test_clarification_is_scoped_and_then_changes_the_next_observed_action(self):
        run = self.start("")
        waiting = self.until(run["id"], "awaiting_input")
        self.assertEqual(waiting["requestedFields"], ["input.requestId"])
        with self.assertRaises(APIError) as denied:
            self.call("clarify_agent_run", run["id"], {"answers": {"input.unapprovedField": "secret"}}, CONTRIBUTOR)
        self.assertEqual("INPUT_SCOPE", denied.exception.code)
        self.call("clarify_agent_run", run["id"], {"answers": {"input.requestId": "SR-EXISTING"}}, CONTRIBUTOR)
        finished = self.until(run["id"], "completed")
        self.assertEqual(finished["output"]["outcome"], "existing_work_item")
        self.assertEqual(self.effects(), 0)

    def test_workflow_start_gate_is_distinct_from_child_write_approval(self):
        template = self.parent_template(manual=True, approval=True)
        parent = self.call("create_run", {"templateId": template["id"], "mode": "fixture", "input": {"requestId": "SR-NEW"}}, CONTRIBUTOR)
        waiting = self.parent_until(parent["id"], "waiting_approval")
        self.assertFalse(waiting["nodes"][0].get("childAgentRunId"))
        self.call("approve", parent["id"], self.parent_decision_body(waiting, "investigate"), REVIEWER)
        manual = self.parent_until(parent["id"], "waiting_execution")
        with self.assertRaises(APIError):
            self.call("execute_manual", parent["id"], {"nodeId": "investigate"}, REVIEWER)
        self.call("execute_manual", parent["id"], {"nodeId": "investigate"}, CONTRIBUTOR)
        action_waiting = self.parent_until(parent["id"], "waiting_approval")
        node = action_waiting["nodes"][0]
        self.assertTrue(node["childAgentRunId"])
        self.assertTrue(node["approvalPacket"]["actions"])
        self.assertTrue(node["approvalPacket"]["actions"][0]["actionFingerprint"])
        self.assertEqual(self.effects(), 1)
        self.assertEqual("prepared", self.effect_rows()[0]["state"])
        with self.assertRaises(APIError) as missing:
            self.call("approve", parent["id"], {"nodeId": "investigate", "decision": "approve"}, REVIEWER)
        self.assertIn(missing.exception.code, {
            "PREPARED_ACTIONS_REQUIRED", "APPROVAL_PACKET_REQUIRED",
            "PREPARED_ACTION_REFERENCE_REQUIRED",
        })
        stale_body = self.parent_decision_body(action_waiting, "investigate")
        stale_body["preparedActions"][0]["actionFingerprint"] = "0" * 64
        with self.assertRaises(APIError) as stale:
            self.call("approve", parent["id"], stale_body, REVIEWER)
        self.assertIn(stale.exception.code, {
            "STALE_APPROVAL_PACKET", "STALE_PREPARED_ACTION",
            "ACTION_CHANGED", "STALE_AGENT_ACTION",
        })
        self.assertEqual(self.store.get("agent_runs", node["childAgentRunId"])["_state"]["status"], "awaiting_approval")
        self.call("approve", parent["id"], self.parent_decision_body(action_waiting, "investigate"), REVIEWER)
        completed = self.parent_until(parent["id"], "completed")
        self.assertEqual(completed["nodes"][0]["output"]["outcome"], "work_item_captured")
        self.assertEqual(self.effects(), 1)

    def test_parent_simulation_suppresses_factory_effects(self):
        template = self.parent_template()
        parent = self.call("create_run", {"templateId": template["id"], "mode": "simulation", "input": {"requestId": "SR-NEW"}}, CONTRIBUTOR)
        waiting = self.parent_until(parent["id"], "waiting_approval")
        self.call("approve", parent["id"], self.parent_decision_body(waiting, "investigate"), REVIEWER)
        self.parent_until(parent["id"], "completed")
        self.assertEqual(self.effects(), 0)
        child = self.store.get("agent_runs", waiting["nodes"][0]["childAgentRunId"])
        captures = [fact for fact in child["_state"]["facts"].values() if "capturedLocally" in fact]
        self.assertTrue(captures)
        self.assertTrue(all(f["status"] == "simulated" and not f["capturedLocally"] for f in captures))

    def test_parent_uses_published_compiled_spec_without_recompiling_mutable_registry(self):
        template = self.parent_template()
        original_hash = template["versions"][-1]["snapshot"]["factoryPlans"]["investigate"]["compiled"]["agentHash"]
        spec = self.store.get("agent_specs", "service-investigator")
        self.call("update_agent_spec", spec["id"], {"expectedRevision": spec["draftRevision"], "mission": "New draft mission"}, AUTHOR)
        with patch.object(self.store, "compile_agent_spec", side_effect=AssertionError("Published compiled agent must stay pinned")):
            parent = self.call("create_run", {"templateId": template["id"], "mode": "fixture", "input": {"requestId": "SR-EXISTING"}}, CONTRIBUTOR)
            completed = self.parent_until(parent["id"], "completed")
        child = self.store.get("agent_runs", completed["nodes"][-1]["childAgentRunId"])
        self.assertEqual(child["_compiled"]["agentHash"], original_hash)
        self.assertEqual(child["specVersion"], 1)

    def test_parent_cancellation_stops_pending_child_before_effect(self):
        template = self.parent_template()
        parent = self.call("create_run", {"templateId": template["id"], "mode": "fixture", "input": {"requestId": "SR-NEW"}}, CONTRIBUTOR)
        waiting = self.parent_until(parent["id"], "waiting_approval")
        child_id = waiting["nodes"][0]["childAgentRunId"]
        self.call("cancel", parent["id"], CONTRIBUTOR)
        child = self.store.advance_agent_run(child_id, AUTHOR)
        self.assertEqual(child["status"], "stopped")
        self.assertEqual(self.effects(), 1)
        effect = self.effect_rows()[0]
        self.assertEqual("prepared", effect["state"])
        self.assertNotIn("executionReceipt", effect["data"])

    def test_paused_agent_and_parent_node_deadlines_expire_and_propagate(self):
        template = self.parent_template()
        parent = self.call(
            "create_run",
            {"templateId": template["id"], "mode": "fixture", "input": {"requestId": "SR-NEW"}},
            CONTRIBUTOR,
        )
        waiting_action = self.parent_until(parent["id"], "waiting_approval")
        node = waiting_action["nodes"][0]
        child = self.store.get("agent_runs", node["childAgentRunId"])
        child["_parent"]["deadlineAt"] = time.time() - 1
        self.store.put("agent_runs", child)
        self.store.tick()
        expired_child = self.store.get("agent_runs", node["childAgentRunId"])
        expired_parent = self.store.get("runs", parent["id"])
        self.assertEqual("failed", expired_child["_state"]["status"])
        self.assertEqual("PARENT_NODE_TIMEOUT", expired_child["_state"]["error"]["code"])
        self.assertEqual("needs_attention", expired_parent["status"])
        self.assertEqual("failed", expired_parent["nodes"][0]["status"])

        direct = self.start("")
        waiting_input = self.until(direct["id"], "awaiting_input")
        stored = self.store.get("agent_runs", waiting_input["id"])
        stored["_state"]["createdAt"] -= stored["_compiled"]["spec"]["limits"]["timeoutSeconds"] + 1
        self.store.put("agent_runs", stored)
        self.store.start()
        for _ in range(50):
            if self.store.get("agent_runs", direct["id"])["_state"]["status"] == "failed":
                break
            time.sleep(0.02)
        expired = self.store.public_agent_run(self.store.get("agent_runs", direct["id"]), AUTHOR)
        self.assertEqual("failed", expired["status"])
        self.assertEqual("AGENT_DEADLINE_EXCEEDED", expired["error"]["code"])

    def test_trusted_contradicted_outcome_fails_child_and_parent(self):
        contradicted = {
            "validatorId": "fixture-outcome-validator.v1",
            "agentId": "service-investigator",
            "businessOutcomeVerified": False,
            "status": "contradicted",
            "checks": [{"id": "forced", "status": "contradicted"}],
            "reason": "Controlled contradiction for the host propagation test.",
        }
        template = self.parent_template()
        parent = self.call(
            "create_run",
            {"templateId": template["id"], "mode": "fixture", "input": {"requestId": "SR-EXISTING"}},
            CONTRIBUTOR,
        )
        with patch.object(factory_fixtures, "validate_outcome", return_value=contradicted):
            failed_parent = self.parent_until(parent["id"], "needs_attention")
        child_id = failed_parent["nodes"][0]["childAgentRunId"]
        child = self.store.public_agent_run(self.store.get("agent_runs", child_id), AUTHOR)
        self.assertEqual("failed", child["status"])
        self.assertEqual("OUTCOME_VALIDATION_FAILED", child["error"]["code"])
        self.assertEqual("contradicted", child["outcomeValidation"]["status"])
        self.assertFalse(child["completionCheck"]["businessOutcomeVerified"])
        self.assertEqual("failed", failed_parent["nodes"][0]["status"])

    def test_local_unknown_effect_reconciles_after_restart_without_duplicate(self):
        run = self.start("SR-NEW")
        awaiting = self.until(run["id"], "awaiting_approval")
        self.approve(awaiting)
        effect = self.effect_rows()[0]["data"]
        self.call("_transition_effect", effect, "dispatched")
        effect = self.effect_rows()[0]["data"]
        self.call("_transition_effect", effect, "unknown", {"fault": "controlled-crash"})
        operation_key = effect["operationKey"]
        self.store.close()
        self.store = Store(self.path, latency=0)
        recovered = self.effect_rows()
        self.assertEqual(1, len(recovered))
        self.assertEqual(operation_key, recovered[0]["operationKey"])
        self.assertEqual("reconciled", recovered[0]["state"])
        self.assertTrue(recovered[0]["data"]["executionReceipt"]["recovered"])
        completed = self.until(run["id"], "completed")
        self.assertEqual("work_item_captured", completed["output"]["outcome"])
        self.assertEqual(1, self.effects())

    def test_parent_cancellation_detects_unresolved_child_effect(self):
        template = self.parent_template()
        parent = self.call(
            "create_run",
            {"templateId": template["id"], "mode": "fixture", "input": {"requestId": "SR-NEW"}},
            CONTRIBUTOR,
        )
        waiting = self.parent_until(parent["id"], "waiting_approval")
        child_id = waiting["nodes"][0]["childAgentRunId"]
        effect = self.effect_rows()[0]["data"]
        self.call("_transition_effect", effect, "dispatched")
        with self.assertRaises(APIError) as blocked:
            self.call("cancel", parent["id"], CONTRIBUTOR)
        self.assertEqual("UNKNOWN_EFFECT_RECONCILIATION_REQUIRED", blocked.exception.code)
        self.assertIn(child_id, blocked.exception.details["childAgentRunIds"])
        self.assertEqual("dispatched", self.effect_rows()[0]["state"])

    def test_external_unknown_effect_is_not_generically_reconciled_on_restart(self):
        run = self.start("SR-NEW")
        awaiting = self.until(run["id"], "awaiting_approval")
        self.approve(awaiting)
        effect = self.effect_rows()[0]["data"]
        effect["actionTarget"]["adapterBinding"] = {
            "adapterId": "external.example", "transport": "https",
            "adapterVersion": "1.0.0", "operation": effect["actionTarget"]["toolId"],
        }
        self.call("_save_effect", effect)
        self.call("_transition_effect", effect, "dispatched")
        effect = self.effect_rows()[0]["data"]
        self.call("_transition_effect", effect, "unknown", {"fault": "controlled-external-ambiguity"})
        self.store.close()
        self.store = Store(self.path, latency=0)
        unresolved = self.effect_rows()[0]
        self.assertEqual("unknown", unresolved["state"])
        self.assertNotIn("executionReceipt", unresolved["data"])
        self.assertEqual("awaiting_tool", self.store.get("agent_runs", run["id"])["_state"]["status"])

    def test_slow_model_does_not_block_workflow_scheduler_and_stop_discards_response(self):
        entered, release = threading.Event(), threading.Event()
        class SlowProvider:
            label = "controlled-test-provider"
            def complete(self, messages, response_schema):
                entered.set()
                release.wait(3)
                return {"kind": "call", "toolId": "service.lookup", "arguments": {"requestId": {"$ref": "input.requestId"}}}
        with patch.dict("os.environ", {"AXIOM_MODEL_ENDPOINT": "http://127.0.0.1/test", "AXIOM_MODEL_NAME": "controlled"}), patch.object(agent_factory.ChatCompletionProvider, "from_environment", return_value=SlowProvider()):
            run = self.start("SR-EXISTING", mode="model")
            worker = threading.Thread(target=self.store.advance_agent_run, args=(run["id"], AUTHOR))
            worker.start()
            self.assertTrue(entered.wait(2))
            ordinary = self.call("create_run", {"templateId": "customer-resolution", "mode": "simulation"}, AUTHOR)
            before = time.monotonic()
            self.store.tick()
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertEqual(self.store.get("runs", ordinary["id"])["nodes"][0]["status"], "running")
            self.call("stop_agent_run", run["id"], CONTRIBUTOR)
            release.set()
            worker.join(3)
            stopped = self.store.public_agent_run(self.store.get("agent_runs", run["id"]), AUTHOR)
            self.assertEqual(stopped["status"], "stopped")
            self.assertEqual(stopped["facts"], {})
            self.assertIsNone(stopped["pendingAction"])

    def test_agent_generation_uses_real_configured_http_transport_without_saving(self):
        spec = copy.deepcopy(factory_fixtures.agent_specs()[0])
        requests = []
        class ModelHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(payload)
                encoded = json.dumps({"choices": [{"message": {"content": json.dumps(spec)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            def log_message(self, *_):
                pass
        provider = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
        provider_thread.start()
        app = create_server(self.store, port=0)
        app_thread = threading.Thread(target=app.serve_forever, daemon=True)
        app_thread.start()
        base = f"http://127.0.0.1:{app.server_port}"
        before_count = len(self.store.all("agent_specs"))
        try:
            with urlopen(base + "/api/bootstrap") as response:
                bootstrap = json.loads(response.read())
                cookie = response.headers["Set-Cookie"].split(";")[0]
            with patch.dict("os.environ", {"AXIOM_MODEL_ENDPOINT": f"http://127.0.0.1:{provider.server_port}/chat", "AXIOM_MODEL_NAME": "controlled-http-test"}):
                request = Request(base + "/api/agent-specs/propose", data=json.dumps({"brief": "Draft a request investigator."}).encode(), headers={"Cookie": cookie, "X-CSRF-Token": bootstrap["csrf"], "Content-Type": "application/json"})
                with urlopen(request) as response:
                    proposal = json.loads(response.read())
                self.assertFalse(proposal["saved"])
                self.assertTrue(proposal["requiresReview"])
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]["model"], "controlled-http-test")
                self.assertEqual(len(self.store.all("agent_specs")), before_count)
        finally:
            app.shutdown()
            app.server_close()
            provider.shutdown()
            provider.server_close()
            app_thread.join(2)
            provider_thread.join(2)


if __name__ == "__main__":
    unittest.main()
