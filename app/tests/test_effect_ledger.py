"""Focused invariants for prepared write effects and approval binding."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import APIError, Store, USERS


REVIEWER = USERS[1]
OPERATOR = USERS[2]
CONTRIBUTOR = USERS[3]
TEMPLATE = "customer-resolution"


class EffectLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def run_until(self, run_id, status, node_id=None, ticks=80):
        for _ in range(ticks):
            run = self.store.get("runs", run_id)
            node_matches = node_id is None or any(
                node["nodeId"] == node_id and node["status"] == status for node in run["nodes"]
            )
            if (run["status"] == status and node_matches) or (node_id is not None and node_matches):
                return run
            self.store.tick()
        self.fail(f"Expected {status} for {node_id or 'run'}; got {run['status']}")

    def start(self, scenario="happy"):
        return self.call("create_run", {
            "templateId": TEMPLATE, "mode": "fixture", "scenario": scenario
        }, CONTRIBUTOR)

    def prepared_refs(self, run, node_id="approval"):
        node = next(item for item in run["nodes"] if item["nodeId"] == node_id)
        return [{key: action[key] for key in (
            "effectId", "nodeId", "operationGeneration", "actionFingerprint", "approvalEnvelopeHash"
        )} for action in node.get("approvalPacket", {}).get("actions", [])]

    def approve_upstream_gate(self, run_id):
        waiting = self.run_until(run_id, "waiting_approval", "approval")
        self.call("approve", run_id, {
            "nodeId": "approval", "decision": "approve", "comment": "Upstream review",
            "preparedActions": self.prepared_refs(waiting),
        }, REVIEWER)

    def test_approval_binds_the_exact_prepared_action(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")

        effect = self.store.effects(run["id"])[0]
        ticket_state = next(node for node in waiting["nodes"] if node["nodeId"] == "ticket")
        gate_state = next(node for node in waiting["nodes"] if node["nodeId"] == "approval")
        self.assertEqual("prepared", effect["state"])
        self.assertEqual(effect["actionFingerprint"], ticket_state["actionFingerprint"])
        self.assertEqual(effect["actionFingerprint"], gate_state["approvalPacket"]["actions"][0]["actionFingerprint"])
        self.assertNotIn("Resolve service request", str(effect))

        with self.assertRaises(APIError) as stale:
            stale_refs = self.prepared_refs(waiting)
            stale_refs[0]["actionFingerprint"] = "0" * 64
            self.call("approve", run["id"], {
                "nodeId": "approval", "decision": "approve", "preparedActions": stale_refs
            }, REVIEWER)
        self.assertEqual("STALE_PREPARED_ACTION", stale.exception.code)

        self.call("approve", run["id"], {
            "nodeId": "approval", "decision": "approve",
            "preparedActions": self.prepared_refs(waiting),
        }, REVIEWER)
        decided = self.store.get("runs", run["id"])["_decisions"][-1]
        self.assertEqual(effect["actionFingerprint"], decided["actionFingerprint"])
        self.assertEqual(effect["approvalEnvelopeHash"], decided["approvalEnvelopeHash"])

        finished = self.run_until(run["id"], "completed")
        acknowledged = self.store.effects(run["id"])[0]
        self.assertEqual("acknowledged", acknowledged["state"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        evidence = self.store.evidence(finished["id"])
        self.assertEqual(1, evidence["effectSummary"]["states"]["acknowledged"])
        packets = evidence["evidenceGraph"]["decisionPackets"]
        self.assertEqual(1, len(packets))
        self.assertEqual(effect["actionFingerprint"], packets[0]["action_fingerprint"])
        self.assertEqual({"subject": "Resolve service request"}, packets[0]["payload"])

    def test_unknown_write_reconciles_then_acknowledges_one_ticket(self):
        run = self.start(scenario="after_write_timeout")
        self.approve_upstream_gate(run["id"])
        failed = self.run_until(run["id"], "needs_attention")
        ticket = failed["ticket"]
        before = self.store.effects(run["id"])[0]
        self.assertEqual("unknown", before["state"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

        self.store.close()
        self.store = Store(self.path, latency=0)
        self.call("retry", run["id"], {"nodeId": "ticket"}, OPERATOR)
        reconciled = self.store.effects(run["id"])[0]
        self.assertEqual("reconciled", reconciled["state"])
        self.assertEqual(before["actionFingerprint"], reconciled["actionFingerprint"])

        finished = self.run_until(run["id"], "completed")
        final_effect = self.store.effects(run["id"])[0]
        self.assertEqual("acknowledged", final_effect["state"])
        self.assertEqual(ticket["id"], finished["ticket"]["id"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.assertEqual(
            ["prepared", "dispatched", "unknown", "reconciled", "acknowledged"],
            [transition["state"] for transition in final_effect["transitions"]],
        )

    def test_same_operation_key_refuses_a_different_payload(self):
        run = self.start()
        self.run_until(run["id"], "waiting_approval", "approval")
        effect = self.store.effects(run["id"])[0]
        self.call("approve", run["id"], {
            "nodeId": "approval", "decision": "approve",
            "preparedActions": self.prepared_refs(self.store.get("runs", run["id"])),
        }, REVIEWER)

        for _ in range(10):
            self.store.tick()
            running = self.store.get("runs", run["id"])
            if next(node for node in running["nodes"] if node["nodeId"] == "ticket")["status"] == "running":
                break
        ticket_state = next(node for node in running["nodes"] if node["nodeId"] == "ticket")
        self.assertEqual("running", ticket_state["status"])
        original_key = ticket_state["operationKey"]
        ticket_state["input"]["subject"] = "A different write"
        self.store.put("runs", running)

        self.store.tick()
        refused = self.store.get("runs", run["id"])
        ticket_state = next(node for node in refused["nodes"] if node["nodeId"] == "ticket")
        self.assertEqual(original_key, ticket_state["operationKey"])
        self.assertEqual("PREPARED_ACTION_MISMATCH", ticket_state["error"]["code"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.assertEqual("prepared", self.store.effects(run["id"])[0]["state"])

    def test_protected_decision_requires_the_exact_reviewed_packet(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        with self.assertRaises(APIError) as missing:
            self.call("approve", run["id"], {
                "nodeId": "approval", "decision": "approve", "comment": "Looks correct"
            }, REVIEWER)
        self.assertEqual("PREPARED_ACTION_REFERENCE_REQUIRED", missing.exception.code)
        with self.assertRaises(APIError) as reason:
            self.call("approve", run["id"], {
                "nodeId": "approval", "decision": "reject", "comment": "",
                "preparedActions": self.prepared_refs(waiting),
            }, REVIEWER)
        self.assertEqual("REJECTION_REASON_REQUIRED", reason.exception.code)

    def test_missing_provider_record_cannot_reconcile_or_hide_unknown_effect(self):
        run = self.start(scenario="after_write_timeout")
        self.approve_upstream_gate(run["id"])
        failed = self.run_until(run["id"], "needs_attention")
        state = next(node for node in failed["nodes"] if node["nodeId"] == "ticket")
        self.store.db.execute("DELETE FROM tickets WHERE operation_key=?", (state["operationKey"],))
        definition, _, agent = self.store._definition(failed, "ticket")
        with self.assertRaises(APIError) as reconcile:
            self.call("_reconcile_effect", failed, state, definition, agent)
        self.assertEqual("EFFECT_NOT_RECONCILED", reconcile.exception.code)
        repair = self.store.repair(run["id"])
        self.assertFalse(repair["safeToRetry"])
        self.assertFalse(repair["reconciliation"]["serviceRecordFound"])
        with self.assertRaises(APIError) as cancel:
            self.call("cancel", run["id"], OPERATOR)
        self.assertEqual("UNKNOWN_EFFECT_RECONCILIATION_REQUIRED", cancel.exception.code)
        current = self.store.get("runs", run["id"])
        self.assertEqual("needs_attention", current["status"])
        self.assertEqual("unknown", self.store.effects(run["id"])[0]["state"])
        self.assertNotIn("retry", self.store.public_run(current, OPERATOR)["allowedActions"])

    def test_unexpected_failure_after_dispatch_becomes_unknown_and_reconciles(self):
        run = self.start()
        self.approve_upstream_gate(run["id"])
        original = self.store.execute_adapter

        def fail_after_ticket(run_record, state, definition, agent):
            output = original(run_record, state, definition, agent)
            if agent["implementationId"] == "ticket":
                raise RuntimeError("lost acknowledgement after provider acceptance")
            return output

        self.store.execute_adapter = fail_after_ticket
        failed = self.run_until(run["id"], "needs_attention")
        ticket_state = next(node for node in failed["nodes"] if node["nodeId"] == "ticket")
        self.assertEqual("AMBIGUOUS_WRITE_FAILURE", ticket_state["error"]["code"])
        self.assertEqual("unknown", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.store.execute_adapter = original
        self.call("retry", run["id"], {"nodeId": "ticket"}, OPERATOR)
        finished = self.run_until(run["id"], "completed")
        self.assertEqual("acknowledged", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.assertEqual(failed["ticket"]["id"], finished["ticket"]["id"])

    def test_real_prepared_action_expiry_rejects_late_decision(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        effect = self.store.effects(run["id"])[0]
        effect["approvalPolicy"]["expiresAt"] = "2000-01-01T00:00:00.000Z"
        self.store._save_effect(effect)
        with self.assertRaises(APIError) as late:
            self.call("approve", run["id"], {
                "nodeId": "approval", "decision": "approve", "comment": "Too late",
                "preparedActions": self.prepared_refs(waiting),
            }, REVIEWER)
        self.assertEqual("APPROVAL_EXPIRED", late.exception.code)


if __name__ == "__main__":
    unittest.main()
