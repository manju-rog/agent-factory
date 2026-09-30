"""Behavioral invariants for Axiom's durable local reference runtime."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import APIError, Store, USERS, create_server, DEFAULT_CONFIG


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS
TEMPLATE = "customer-resolution"


class RuntimeInvariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def run_until(self, run_id, status, ticks=60):
        for _ in range(ticks):
            run = self.store.get("runs", run_id)
            if run["status"] == status:
                return run
            self.store.tick()
        self.fail(f"Expected {status}; got {run['status']} with {[(n['nodeId'], n['status']) for n in run['nodes']]}")

    def start(self, mode="fixture", scenario="happy"):
        return self.call("create_run", {"templateId": TEMPLATE, "mode": mode, "scenario": scenario}, CONTRIBUTOR)

    def decision_body(self, run, node_id, decision="approve", comment="Test decision"):
        node = next(item for item in run["nodes"] if item["nodeId"] == node_id)
        actions = node.get("approvalPacket", {}).get("actions", [])
        body = {"nodeId": node_id, "decision": decision, "comment": comment}
        if actions:
            body["preparedActions"] = [{key: action[key] for key in (
                "effectId", "nodeId", "operationGeneration", "actionFingerprint", "approvalEnvelopeHash"
            )} for action in actions]
        return body

    def approve_all(self, run_id):
        run = self.run_until(run_id, "waiting_approval")
        for n in run["nodes"]:
            if n["status"] == "waiting_approval":
                self.call("approve", run_id, self.decision_body(run, n["nodeId"]), REVIEWER)

    def ticket_count(self):
        return self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]

    def test_inflight_step_resumes_after_process_restart(self):
        run = self.start()
        self.store.tick()
        self.assertEqual(self.store.get("runs", run["id"])["nodes"][0]["status"], "running")
        self.store.close()
        self.store = Store(self.path, latency=0)
        self.approve_all(run["id"])
        finished = self.run_until(run["id"], "completed")
        self.assertEqual(self.ticket_count(), 1)
        self.assertTrue(finished["ticket"]["persisted"])
        self.assertEqual(finished["nodes"][0]["attempt"], 1)

    def test_accepted_write_timeout_reconciles_one_ticket_after_restart(self):
        run = self.start(scenario="after_write_timeout")
        self.approve_all(run["id"])
        failed = self.run_until(run["id"], "needs_attention")
        ticket_id = failed["ticket"]["id"]
        self.assertEqual(self.ticket_count(), 1)
        ticket_state = next(n for n in failed["nodes"] if n["nodeId"] == "ticket")
        key = ticket_state["operationKey"]
        self.assertEqual(ticket_state["error"]["code"], "ACCEPTED_WRITE_TIMEOUT")
        self.store.close()
        self.store = Store(self.path, latency=0)
        repair = self.store.repair(run["id"])
        self.assertTrue(repair["safeToRetry"])
        self.assertEqual(repair["reconciliation"]["ticketId"], ticket_id)
        self.call("retry", run["id"], {"nodeId": "ticket"}, OPERATOR)
        finished = self.run_until(run["id"], "completed")
        self.assertEqual(self.ticket_count(), 1)
        self.assertEqual(finished["ticket"]["id"], ticket_id)
        self.assertEqual(next(n for n in finished["nodes"] if n["nodeId"] == "ticket")["operationKey"], key)

    def test_simulation_never_inserts_into_local_ticket_store(self):
        run = self.start(mode="simulation")
        self.approve_all(run["id"])
        finished = self.run_until(run["id"], "completed")
        self.assertFalse(finished["ticket"]["persisted"])
        self.assertEqual(self.ticket_count(), 0)
        self.assertTrue(any(i["kind"] == "simulated-write" for i in self.store.evidence(run["id"])["items"]))

    def test_rejection_stops_downstream_write_and_rejects_recovery(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval")
        self.call("approve", run["id"], self.decision_body(waiting, "approval", "reject", "Required evidence is insufficient."), REVIEWER)
        for _ in range(10):
            self.store.tick()
        rejected = self.store.get("runs", run["id"])
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self.ticket_count(), 0)
        self.assertEqual(next(n for n in rejected["nodes"] if n["nodeId"] == "ticket")["status"], "cancelled")
        with self.assertRaises(APIError) as failure:
            self.call("retry", run["id"], {"nodeId": "approval"}, OPERATOR)
        self.assertEqual(failure.exception.code, "UNSAFE_RETRY")

    def test_approval_is_role_restricted_and_duplicate_safe(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval")
        body = self.decision_body(waiting, "approval")
        with self.assertRaises(APIError) as failure:
            self.call("approve", run["id"], body, AUTHOR)
        self.assertEqual(failure.exception.status, 403)
        self.call("approve", run["id"], body, REVIEWER)
        self.call("approve", run["id"], body, REVIEWER)
        self.assertEqual(len(self.store.get("runs", run["id"])["_decisions"]), 1)

    def test_draft_conflicts_and_frozen_candidates_cannot_be_overwritten(self):
        template = self.store.get("templates", TEMPLATE)
        body = {"expectedRevision": template["draftRevision"], "name": "Revised workflow"}
        saved = self.call("update_template", TEMPLATE, body, AUTHOR)
        with self.assertRaises(APIError) as failure:
            self.call("update_template", TEMPLATE, body, AUTHOR)
        self.assertEqual(failure.exception.code, "REVISION_CONFLICT")
        self.call("submit_template", TEMPLATE, AUTHOR)
        with self.assertRaises(APIError) as failure:
            self.call("update_template", TEMPLATE, {"expectedRevision": saved["draftRevision"], "name": "Sneaky update"}, AUTHOR)
        self.assertEqual(failure.exception.code, "CANDIDATE_FROZEN")
        with self.assertRaises(APIError):
            self.call("publish_template", TEMPLATE, AUTHOR)

    def test_publishing_does_not_change_a_running_snapshot(self):
        old_run = self.start()
        old_hash = json.dumps(self.store.get("runs", old_run["id"])["_snapshot"], sort_keys=True)
        self.call("submit_template", TEMPLATE, AUTHOR)
        published = self.call("publish_template", TEMPLATE, REVIEWER)
        new_run = self.start()
        self.assertEqual(published["publishedVersion"], 2)
        self.assertEqual(old_run["version"], 1)
        self.assertEqual(new_run["version"], 2)
        self.assertEqual(old_hash, json.dumps(self.store.get("runs", old_run["id"])["_snapshot"], sort_keys=True))
        self.assertEqual(next(n for n in old_run["templateSnapshot"]["nodes"] if n["id"] == "policy")["config"]["threshold"], 10000)
        self.assertEqual(next(n for n in new_run["templateSnapshot"]["nodes"] if n["id"] == "policy")["config"]["threshold"], 15000)

    def test_safe_timeout_retry_keeps_operation_key_and_progress(self):
        run = self.start(mode="simulation", scenario="timeout")
        failed = self.run_until(run["id"], "needs_attention")
        old_key = next(n for n in failed["nodes"] if n["nodeId"] == "csr")["operationKey"]
        self.assertTrue(self.store.repair(run["id"])["safeToRetry"])
        self.call("retry", run["id"], {"nodeId": "csr"}, OPERATOR)
        self.approve_all(run["id"])
        completed = self.run_until(run["id"], "completed")
        csr = next(n for n in completed["nodes"] if n["nodeId"] == "csr")
        self.assertEqual(csr["operationKey"], old_key)
        self.assertEqual(csr["attempt"], 2)
        self.assertEqual(next(n for n in completed["nodes"] if n["nodeId"] == "intake")["attempt"], 1)

    def test_cycle_and_non_ancestor_mapping_are_rejected_before_execution(self):
        template = self.store.get("templates", TEMPLATE)
        template["edges"].append({"id": "cycle", "source": "receipt", "target": "intake"})
        self.assertFalse(self.store.validate(template)["valid"])
        template = self.store.get("templates", TEMPLATE)
        template["nodes"][0]["config"]["inputMapping"] = {"secret": "nodes.receipt.output.ticket"}
        result = self.store.validate(template)
        self.assertFalse(result["valid"])
        self.assertTrue(any(i["code"] == "MAPPING_DEPENDENCY" for i in result["issues"]))

    def test_planner_proposes_before_applying_and_respects_named_manual_target(self):
        old = self.store.get("templates", TEMPLATE)
        proposal = self.call("plan", {"templateId": TEMPLATE, "intent": "Make CSR manual for a contributor"}, AUTHOR)
        self.assertEqual(proposal["provider"], "local-planner")
        self.assertEqual(self.store.get("templates", TEMPLATE)["draftRevision"], old["draftRevision"])
        self.assertEqual(proposal["operations"][0]["nodeId"], "csr")
        applied = self.call("apply_plan", proposal["id"], {"expectedRevision": old["draftRevision"]}, AUTHOR)
        self.assertEqual(next(n for n in applied["nodes"] if n["id"] == "csr")["config"]["executionMode"], "manual")
        run = self.start(mode="simulation")
        self.run_until(run["id"], "waiting_execution")
        with self.assertRaises(APIError):
            self.call("execute_manual", run["id"], {"nodeId": "csr"}, REVIEWER)
        self.call("execute_manual", run["id"], {"nodeId": "csr"}, CONTRIBUTOR)
        self.approve_all(run["id"])
        self.run_until(run["id"], "completed")

    def test_four_experiment_results_come_from_actual_runs(self):
        experiment = self.call("create_experiment", {"templateId": TEMPLATE}, AUTHOR)
        for _ in range(40):
            self.store.tick()
            result = self.store.experiment(experiment["id"])
            if result["status"] == "completed":
                break
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["metrics"]["passed"], 4)
        self.assertEqual(self.ticket_count(), 0)
        self.assertEqual(len(result["runs"]), 4)
        self.assertTrue(all(r["passed"] for r in result["results"]))

    def test_registry_alias_executes_the_selected_implementation(self):
        alias = self.call("create_agent", {"name": "CSR team adapter", "description": "Team wrapper", "implementationId": "csr"}, AUTHOR)
        template = self.store.get("templates", TEMPLATE)
        next(n for n in template["nodes"] if n["id"] == "csr")["agentId"] = alias["id"]
        self.call("update_template", TEMPLATE, {"expectedRevision": template["draftRevision"], "nodes": template["nodes"]}, AUTHOR)
        run = self.start(mode="simulation")
        self.approve_all(run["id"])
        complete = self.run_until(run["id"], "completed")
        self.assertEqual(next(n for n in complete["nodes"] if n["nodeId"] == "csr")["output"]["csrRequest"]["status"], "prepared-local-fixture")

    def test_invalid_mapped_amount_is_blocked_before_run_without_affecting_published_version(self):
        template = self.store.get("templates", TEMPLATE)
        next(n for n in template["nodes"] if n["id"] == "policy")["config"]["inputMapping"] = {"amount": "input.subject"}
        updated = self.call("update_template", TEMPLATE, {"expectedRevision": template["draftRevision"], "nodes": template["nodes"]}, AUTHOR)
        self.assertIn("MAPPING_TYPE", {issue["code"] for issue in self.store.validate(updated)["issues"]})
        with self.assertRaises(APIError) as failure:
            self.start(mode="simulation")
        self.assertEqual("INVALID_GRAPH", failure.exception.code)
        healthy = self.start(mode="fixture")
        self.approve_all(healthy["id"])
        self.run_until(healthy["id"], "completed")
        self.assertEqual(self.ticket_count(), 1)

    def test_missing_label_is_rejected_before_saving_draft(self):
        template = self.store.get("templates", TEMPLATE)
        del template["nodes"][0]["label"]
        with self.assertRaises(APIError) as failure:
            self.call("update_template", TEMPLATE, {"expectedRevision": template["draftRevision"], "nodes": template["nodes"]}, AUTHOR)
        self.assertEqual(failure.exception.code, "INVALID_DRAFT")

    def test_unexpected_adapter_exception_is_recorded_and_isolated(self):
        broken = self.start(mode="simulation")
        healthy = self.start(mode="fixture")
        original = self.store.execute_adapter
        def adapter(run, state, definition, agent):
            if run["id"] == broken["id"]:
                raise TypeError("deliberately malformed fixture adapter")
            return original(run, state, definition, agent)
        self.store.execute_adapter = adapter
        failed = self.run_until(broken["id"], "needs_attention")
        self.assertEqual(failed["nodes"][0]["error"]["code"], "ADAPTER_ERROR")
        self.approve_all(healthy["id"])
        self.run_until(healthy["id"], "completed")

    def test_slow_model_does_not_hold_runtime_lock_and_stale_proposal_is_rejected(self):
        httpd = create_server(self.store, port=0)
        service = threading.Thread(target=httpd.serve_forever, daemon=True)
        service.start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        entered, release = threading.Event(), threading.Event()
        responses = []
        def slow_model(*_):
            entered.set()
            release.wait(3)
            return {"summary": "Delayed model proposal", "assumptions": [], "operations": []}
        with urlopen(base + "/api/bootstrap") as response:
            bootstrap = json.loads(response.read())
            cookie = response.headers["Set-Cookie"].split(";")[0]
        def propose():
            request = Request(base + "/api/plan", data=json.dumps({"templateId": TEMPLATE, "intent": "Make CSR manual"}).encode(), headers={"Cookie": cookie, "X-CSRF-Token": bootstrap["csrf"], "Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=5) as response:
                    responses.append(response.status)
            except HTTPError as error:
                responses.append(error.code)
        try:
            with patch.dict("os.environ", {"AXIOM_MODEL_ENDPOINT": "http://127.0.0.1/configured-model", "AXIOM_MODEL_NAME": "test-model"}), patch.object(self.store, "model_proposal", side_effect=slow_model):
                run = self.start(mode="simulation")
                request_thread = threading.Thread(target=propose)
                request_thread.start()
                self.assertTrue(entered.wait(2))
                began = time.monotonic()
                self.store.tick()
                self.assertLess(time.monotonic() - began, 0.5)
                self.assertEqual(self.store.get("runs", run["id"])["nodes"][0]["status"], "running")
                template = self.store.get("templates", TEMPLATE)
                self.call("update_template", TEMPLATE, {"expectedRevision": template["draftRevision"], "name": "Changed during model request"}, AUTHOR)
                release.set()
                request_thread.join(3)
                self.assertEqual(responses, [409])
                self.assertEqual(self.store.all("plans"), [])
        finally:
            release.set()
            httpd.shutdown()
            httpd.server_close()
            service.join(2)

    def test_blank_template_build_review_publish_and_execute(self):
        template = self.call("create_template", {"name": "Brand new process", "description": "Created from an empty canvas"}, AUTHOR)
        self.assertEqual(template["nodes"], [])
        self.assertIsNone(template["publishedVersion"])
        self.assertFalse(self.store.validate(template)["valid"])
        self.assertEqual(self.store.diff_template(template["id"])["baseVersion"], None)
        with self.assertRaises(APIError):
            self.call("submit_template", template["id"], AUTHOR)
        saved_empty = self.call("update_template", template["id"], {"expectedRevision": 1, "nodes": [], "edges": []}, AUTHOR)
        nodes = [{"id": ident, "agentId": agent, "label": label, "x": i * 270, "y": 100, "config": dict(DEFAULT_CONFIG)} for i, (ident, agent, label) in enumerate([("start", "intake", "Read task"), ("review", "approval", "Review task"), ("work", "ticket", "Create work")])]
        edges = [{"id": "first", "source": "start", "target": "review"}, {"id": "second", "source": "review", "target": "work"}]
        self.call("update_template", template["id"], {"expectedRevision": saved_empty["draftRevision"], "nodes": nodes, "edges": edges}, AUTHOR)
        self.call("submit_template", template["id"], AUTHOR)
        published = self.call("publish_template", template["id"], REVIEWER)
        self.assertEqual(published["publishedVersion"], 1)
        run = self.call("create_run", {"templateId": template["id"], "mode": "fixture"}, CONTRIBUTOR)
        self.approve_all(run["id"])
        completed = self.run_until(run["id"], "completed")
        self.assertEqual(completed["version"], 1)
        self.assertEqual(self.ticket_count(), 1)

    def test_deprecated_agent_preserves_published_execution_but_blocks_new_placement(self):
        alias = self.call("create_agent", {"name": "CSR custom adapter", "implementationId": "csr"}, AUTHOR)
        alias = self.call("update_agent", alias["id"], {"name": "Renamed CSR adapter", "description": "Updated metadata"}, AUTHOR)
        self.assertEqual(alias["implementationId"], "csr")
        template = self.store.get("templates", TEMPLATE)
        next(n for n in template["nodes"] if n["id"] == "csr")["agentId"] = alias["id"]
        self.call("update_template", TEMPLATE, {"expectedRevision": template["draftRevision"], "nodes": template["nodes"]}, AUTHOR)
        self.call("submit_template", TEMPLATE, AUTHOR)
        self.call("publish_template", TEMPLATE, REVIEWER)
        self.call("deprecate_agent", alias["id"], AUTHOR)
        self.assertEqual(self.store.get("agents", alias["id"])["status"], "deprecated")
        run = self.start(mode="fixture")
        self.approve_all(run["id"])
        self.run_until(run["id"], "completed")
        self.assertEqual(self.ticket_count(), 1)
        self.assertTrue(any(i["code"] == "DEPRECATED_AGENT" for i in self.store.validate(self.store.get("templates", TEMPLATE))["issues"]))
        fresh = self.call("create_template", {"name": "Cannot add deprecated agent"}, AUTHOR)
        node = {"id": "one", "agentId": alias["id"], "label": "Old CSR", "x": 100, "y": 100, "config": dict(DEFAULT_CONFIG)}
        with self.assertRaises(APIError) as failure:
            self.call("update_template", fresh["id"], {"expectedRevision": 1, "nodes": [node], "edges": []}, AUTHOR)
        self.assertEqual(failure.exception.code, "AGENT_DEPRECATED")
        with self.assertRaises(APIError):
            self.call("update_agent", alias["id"], {"implementationId": "ticket"}, AUTHOR)
        with self.assertRaises(APIError):
            self.call("deprecate_agent", "ticket", CONTRIBUTOR)


if __name__ == "__main__":
    unittest.main()
