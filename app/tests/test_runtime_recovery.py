"""Recovery contracts that keep approvals and write effects safe across restarts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import APIError, DEFAULT_CONFIG, Store, USERS, encode


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


def node(ident: str, agent_id: str, x: int, y: int, **config):
    return {
        "id": ident,
        "agentId": agent_id,
        "label": ident.replace("_", " ").title(),
        "x": x,
        "y": y,
        "config": {**copy.deepcopy(DEFAULT_CONFIG), **config},
    }


class RuntimeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "recovery.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def reopen(self):
        self.store.close()
        self.store = Store(self.path, latency=0)

    def publish(self, nodes, edges):
        template = self.call(
            "create_template",
            {"name": "Recovery contract", "description": "Focused effect recovery fixture"},
            AUTHOR,
        )
        template = self.call(
            "update_template",
            template["id"],
            {"expectedRevision": template["draftRevision"], "nodes": nodes, "edges": edges},
            AUTHOR,
        )
        validation = self.store.validate(template)
        self.assertTrue(validation["valid"], validation["issues"])
        self.call("submit_template", template["id"], AUTHOR)
        return self.call("publish_template", template["id"], REVIEWER)

    def start(self, template_id="customer-resolution", scenario="happy"):
        return self.call(
            "create_run",
            {"templateId": template_id, "mode": "fixture", "scenario": scenario},
            CONTRIBUTOR,
        )

    def run_until(self, run_id, status, node_id=None, ticks=100):
        for _ in range(ticks):
            run = self.store.get("runs", run_id)
            node_ready = node_id is None or any(
                item["nodeId"] == node_id and item["status"] == status
                for item in run["nodes"]
            )
            if (node_id is None and run["status"] == status) or (node_id is not None and node_ready):
                return run
            self.store.tick()
        self.fail(
            f"Expected {status} for {node_id or 'run'}; got {run['status']} "
            f"with {[(item['nodeId'], item['status']) for item in run['nodes']]}"
        )

    @staticmethod
    def prepared_refs(run, node_id):
        state = next(item for item in run["nodes"] if item["nodeId"] == node_id)
        return [
            {
                key: action[key]
                for key in (
                    "effectId",
                    "nodeId",
                    "operationGeneration",
                    "actionFingerprint",
                    "approvalEnvelopeHash",
                )
            }
            for action in state.get("approvalPacket", {}).get("actions", [])
        ]

    def approve(self, run, node_id):
        body = {
            "nodeId": node_id,
            "decision": "approve",
            "comment": "Reviewed exact prepared action.",
            "preparedActions": self.prepared_refs(run, node_id),
        }
        return self.call("approve", run["id"], body, REVIEWER), body

    def test_self_gated_write_approval_is_idempotent_across_restart(self):
        published = self.publish(
            [
                node("start", "intake", 0, 100),
                node("write", "ticket", 300, 100, approvalRequired=True),
                node("finish", "receipt", 600, 100),
            ],
            [
                {"id": "start_write", "source": "start", "target": "write"},
                {"id": "write_finish", "source": "write", "target": "finish"},
            ],
        )
        run = self.start(published["id"])
        waiting = self.run_until(run["id"], "waiting_approval", "write")
        effect = self.store.effects(run["id"])[0]
        self.assertEqual(["write"], effect["approvalPolicy"]["gateNodeIds"])

        _, decision_body = self.approve(waiting, "write")
        self.reopen()
        # A repeated callback after a process restart must be a no-op, not a
        # second decision or a second provider write.
        self.call("approve", run["id"], decision_body, REVIEWER)
        restarted = self.store.get("runs", run["id"])
        self.assertEqual(1, len(restarted["_decisions"]))

        finished = self.run_until(run["id"], "completed")
        self.assertEqual("completed", finished["status"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.assertEqual("acknowledged", self.store.effects(run["id"])[0]["state"])

    def test_one_gate_requires_the_complete_multi_action_packet(self):
        published = self.publish(
            [
                node("start", "intake", 0, 100),
                node("review", "approval", 250, 100),
                node("ticket_a", "ticket", 500, 20),
                node("ticket_b", "ticket", 500, 180),
                node("finish", "receipt", 800, 100),
            ],
            [
                {"id": "start_review", "source": "start", "target": "review"},
                {"id": "review_a", "source": "review", "target": "ticket_a"},
                {"id": "review_b", "source": "review", "target": "ticket_b"},
                {"id": "a_finish", "source": "ticket_a", "target": "finish"},
                {"id": "b_finish", "source": "ticket_b", "target": "finish"},
            ],
        )
        run = self.start(published["id"])
        waiting = self.run_until(run["id"], "waiting_approval", "review")
        references = self.prepared_refs(waiting, "review")
        self.assertEqual(2, len(references))
        self.assertEqual(2, len(self.store.effects(run["id"])))

        with self.assertRaises(APIError) as partial:
            self.call(
                "approve",
                run["id"],
                {
                    "nodeId": "review",
                    "decision": "approve",
                    "comment": "Only one action was reviewed.",
                    "preparedActions": references[:1],
                },
                REVIEWER,
            )
        self.assertEqual("STALE_PREPARED_ACTION", partial.exception.code)
        self.assertEqual([], self.store.get("runs", run["id"])["_decisions"])

        self.call(
            "approve",
            run["id"],
            {
                "nodeId": "review",
                "decision": "approve",
                "comment": "Both exact actions were reviewed.",
                "preparedActions": references,
            },
            REVIEWER,
        )
        self.run_until(run["id"], "completed")
        self.assertEqual(2, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.assertEqual(
            ["acknowledged", "acknowledged"],
            sorted(effect["state"] for effect in self.store.effects(run["id"])),
        )

    def test_payload_change_invalidates_packet_before_reviewer_decision(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        references = self.prepared_refs(waiting, "approval")

        changed = self.store.get("runs", run["id"])
        ticket_state = next(item for item in changed["nodes"] if item["nodeId"] == "ticket")
        ticket_state["input"]["subject"] = "Payload changed after the review packet was prepared"
        self.call("put", "runs", changed)

        with self.assertRaises(APIError) as stale:
            self.call(
                "approve",
                run["id"],
                {
                    "nodeId": "approval",
                    "decision": "approve",
                    "comment": "The old packet must not approve a changed payload.",
                    "preparedActions": references,
                },
                REVIEWER,
            )
        self.assertIn(stale.exception.code, {"PREPARED_ACTION_MISMATCH", "STALE_PREPARED_ACTION"})
        current = self.store.get("runs", run["id"])
        self.assertEqual([], current["_decisions"])
        self.assertEqual("prepared", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_mismatched_provider_record_is_never_advertised_as_safe_recovery(self):
        run = self.start(scenario="after_write_timeout")
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        self.approve(waiting, "approval")
        failed = self.run_until(run["id"], "needs_attention")
        ticket_state = next(item for item in failed["nodes"] if item["nodeId"] == "ticket")

        row = self.store.db.execute(
            "SELECT data FROM tickets WHERE operation_key=?", (ticket_state["operationKey"],)
        ).fetchone()
        provider_record = json.loads(row["data"])
        provider_record["actionFingerprint"] = "0" * 64
        self.store.db.execute(
            "UPDATE tickets SET data=? WHERE operation_key=?",
            (encode(provider_record), ticket_state["operationKey"]),
        )
        self.store.db.commit()

        repair = self.store.repair(run["id"])
        public = self.store.public_run(self.store.get("runs", run["id"]), OPERATOR)
        with self.subTest("diagnostic does not call a mismatched record safe"):
            self.assertFalse(repair["safeToRetry"])
        with self.subTest("action policy does not offer retry"):
            self.assertNotIn("retry", public["allowedActions"])

        with self.assertRaises(APIError) as refused:
            self.call("retry", run["id"], {"nodeId": "ticket"}, OPERATOR)
        self.assertIn(refused.exception.code, {"UNSAFE_RETRY", "PREPARED_ACTION_MISMATCH"})
        self.assertEqual("unknown", self.store.effects(run["id"])[0]["state"])
        self.assertEqual("needs_attention", self.store.get("runs", run["id"])["status"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_waiting_approval_expires_after_restart_without_dispatch(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        self.assertEqual(1, len(self.prepared_refs(waiting, "approval")))
        self.assertEqual("prepared", self.store.effects(run["id"])[0]["state"])

        self.reopen()
        # The persisted deadline remains authoritative after restart. Patching
        # only the clock comparison models advancing beyond that deadline.
        with patch("server.deadline_passed", return_value=True):
            self.store.tick()

        expired = self.store.get("runs", run["id"])
        self.assertEqual("expired", expired["status"])
        self.assertEqual([], expired["_decisions"])
        self.assertEqual("prepared", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
        self.assertTrue(
            any(
                json.loads(row["data"])["type"] == "approval.expired"
                for row in self.store.db.execute("SELECT data FROM events WHERE run_id=?", (run["id"],))
            )
        )

    def test_approval_gate_without_a_write_still_has_a_durable_deadline(self):
        published = self.publish(
            [
                node("start", "intake", 0, 100),
                node("approval", "approval", 300, 100),
                node("finish", "receipt", 600, 100),
            ],
            [
                {"id": "start_approval", "source": "start", "target": "approval"},
                {"id": "approval_finish", "source": "approval", "target": "finish"},
            ],
        )
        run = self.start(published["id"])
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        state = next(item for item in waiting["nodes"] if item["nodeId"] == "approval")
        self.assertTrue(state.get("approvalExpiresAt"))
        self.assertEqual([], state["approvalPacket"]["actions"])

        persisted = self.store.get("runs", run["id"])
        next(item for item in persisted["nodes"] if item["nodeId"] == "approval")[
            "approvalExpiresAt"
        ] = "2000-01-01T00:00:00Z"
        self.call("put", "runs", persisted)
        self.store.tick()

        expired = self.store.get("runs", run["id"])
        self.assertEqual("expired", expired["status"])
        event_types = [json.loads(row["data"])["type"] for row in self.store.db.execute(
            "SELECT data FROM events WHERE run_id=? ORDER BY id", (run["id"],)
        )]
        self.assertIn("approval.expired", event_types)

    def test_reconciled_result_survives_provider_deletion_and_connection_revocation(self):
        run = self.start(scenario="after_write_timeout")
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        self.approve(waiting, "approval")
        failed = self.run_until(run["id"], "needs_attention")
        ticket_state = next(item for item in failed["nodes"] if item["nodeId"] == "ticket")
        accepted_ticket = copy.deepcopy(failed["ticket"])

        self.call("retry", run["id"], {"nodeId": "ticket"}, OPERATOR)
        reconciled = self.store.effects(run["id"])[0]
        self.assertEqual("reconciled", reconciled["state"])
        self.assertEqual(accepted_ticket, reconciled["reconciledProviderRecord"])

        # Recovery has already captured the exact accepted result. A provider
        # row disappearing and its connection being revoked before the next
        # scheduler tick must not turn completion into another create call.
        self.store.db.execute(
            "DELETE FROM tickets WHERE operation_key=?", (ticket_state["operationKey"],)
        )
        self.store.db.commit()
        self.call("connection_action", "fixture-ticket", "revoke", AUTHOR)

        finished = self.run_until(run["id"], "completed")
        completed_ticket = next(
            item for item in finished["nodes"] if item["nodeId"] == "ticket"
        )["output"]["ticket"]
        effect = self.store.effects(run["id"])[0]
        self.assertEqual(accepted_ticket, completed_ticket)
        self.assertEqual(accepted_ticket["id"], effect["resourceId"])
        self.assertEqual("acknowledged", effect["state"])
        self.assertEqual(
            ["prepared", "dispatched", "unknown", "reconciled", "acknowledged"],
            [transition["state"] for transition in effect["transitions"]],
        )
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_api_error_after_write_dispatch_is_unknown_and_blocks_cancellation(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        self.approve(waiting, "approval")
        execute_adapter = self.store.execute_adapter

        def lose_acknowledgement(current_run, state, definition, agent):
            output = execute_adapter(current_run, state, definition, agent)
            if agent["implementationId"] == "ticket":
                raise APIError(
                    422,
                    "PROVIDER_RESPONSE_INVALID",
                    "The provider accepted the write but returned an invalid acknowledgement.",
                )
            return output

        with patch.object(self.store, "execute_adapter", side_effect=lose_acknowledgement):
            failed = self.run_until(run["id"], "needs_attention")

        ticket_state = next(item for item in failed["nodes"] if item["nodeId"] == "ticket")
        effect = self.store.effects(run["id"])[0]
        self.assertEqual("AMBIGUOUS_WRITE_FAILURE", ticket_state["error"]["code"])
        self.assertEqual("unknown", effect["state"])
        self.assertEqual(failed["ticket"]["id"], effect["resourceId"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

        with self.assertRaises(APIError) as refused:
            self.call("cancel", run["id"], OPERATOR)
        self.assertEqual("UNKNOWN_EFFECT_RECONCILIATION_REQUIRED", refused.exception.code)
        self.assertEqual("needs_attention", self.store.get("runs", run["id"])["status"])

    def test_later_failed_write_does_not_inherit_an_earlier_resource_id(self):
        published = self.publish(
            [
                node("start", "intake", 0, 100),
                node("write_one", "ticket", 250, 100, approvalRequired=True),
                node("write_two", "ticket", 500, 100, approvalRequired=True),
                node("finish", "receipt", 750, 100),
            ],
            [
                {"id": "start_first", "source": "start", "target": "write_one"},
                {"id": "first_second", "source": "write_one", "target": "write_two"},
                {"id": "second_finish", "source": "write_two", "target": "finish"},
            ],
        )
        run = self.start(published["id"])
        first_waiting = self.run_until(run["id"], "waiting_approval", "write_one")
        self.approve(first_waiting, "write_one")
        second_waiting = self.run_until(run["id"], "waiting_approval", "write_two")

        first_effect = next(
            effect for effect in self.store.effects(run["id"]) if effect["nodeId"] == "write_one"
        )
        first_resource_id = first_effect["resourceId"]
        self.assertEqual("acknowledged", first_effect["state"])
        self.approve(second_waiting, "write_two")
        execute_adapter = self.store.execute_adapter

        def fail_second_write(current_run, state, definition, agent):
            if state["nodeId"] == "write_two":
                raise APIError(503, "PROVIDER_UNAVAILABLE", "The second provider call failed.")
            return execute_adapter(current_run, state, definition, agent)

        with patch.object(self.store, "execute_adapter", side_effect=fail_second_write):
            failed = self.run_until(run["id"], "needs_attention")

        effects = {effect["nodeId"]: effect for effect in self.store.effects(run["id"])}
        second_state = next(item for item in failed["nodes"] if item["nodeId"] == "write_two")
        self.assertEqual("AMBIGUOUS_WRITE_FAILURE", second_state["error"]["code"])
        self.assertEqual("acknowledged", effects["write_one"]["state"])
        self.assertEqual(first_resource_id, effects["write_one"]["resourceId"])
        self.assertEqual("unknown", effects["write_two"]["state"])
        self.assertIsNone(effects["write_two"].get("resourceId"))
        self.assertNotEqual(first_resource_id, effects["write_two"].get("resourceId"))
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_identical_protected_decision_replays_after_expiry_and_revocation(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        _, decision_body = self.approve(waiting, "approval")
        effect = self.store.effects(run["id"])[0]
        effect["approvalPolicy"]["expiresAt"] = "2000-01-01T00:00:00Z"
        self.call("_save_effect", effect)
        self.call("connection_action", "fixture-ticket", "revoke", AUTHOR)

        replayed = self.call("approve", run["id"], decision_body, REVIEWER)
        self.assertEqual(1, len(replayed["decisions"]))
        self.assertEqual("approve", replayed["decisions"][0]["decision"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

        opposite = {**decision_body, "decision": "reject", "comment": "Reject instead."}
        with self.assertRaises(APIError) as conflict:
            self.call("approve", run["id"], opposite, REVIEWER)
        self.assertEqual("DECISION_ALREADY_RECORDED", conflict.exception.code)
        self.assertEqual(1, len(self.store.get("runs", run["id"])["_decisions"]))

    def test_missing_write_input_fails_before_dispatch_and_can_be_cancelled(self):
        template = self.call(
            "create_template",
            {"name": "Pre-dispatch validation", "description": "Reject an unresolved write input."},
            AUTHOR,
        )
        template = self.call(
            "update_template",
            template["id"],
            {
                "expectedRevision": template["draftRevision"],
                "inputSchema": {
                    "type": "object",
                    "properties": {"foo": {"type": "string"}},
                    "required": ["foo"],
                    "additionalProperties": False,
                },
                "nodes": [
                    node("approval", "approval", 0, 100),
                    node("write", "ticket", 300, 100),
                    node("finish", "receipt", 600, 100),
                ],
                "edges": [
                    {"id": "approval_write", "source": "approval", "target": "write"},
                    {"id": "write_finish", "source": "write", "target": "finish"},
                ],
            },
            AUTHOR,
        )
        self.assertTrue(self.store.validate(template)["valid"])
        self.call("submit_template", template["id"], AUTHOR)
        published = self.call("publish_template", template["id"], REVIEWER)
        run = self.call(
            "create_run",
            {
                "templateId": published["id"],
                "mode": "fixture",
                "input": {"foo": "ok"},
            },
            CONTRIBUTOR,
        )
        failed = self.run_until(run["id"], "needs_attention")
        approval = next(item for item in failed["nodes"] if item["nodeId"] == "approval")
        self.assertEqual("AGENT_INPUT_INVALID", approval["error"]["code"])
        self.assertEqual([], self.store.effects(run["id"]))
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

        cancelled = self.call("cancel", run["id"], CONTRIBUTOR)
        self.assertEqual("cancelled", cancelled["status"])

    def test_malformed_approval_references_are_typed_errors(self):
        run = self.start()
        waiting = self.run_until(run["id"], "waiting_approval", "approval")
        valid = self.prepared_refs(waiting, "approval")[0]
        invalid_packets = [
            [valid, "junk"],
            [{**valid, "effectId": 1}],
            [{**valid, "operationGeneration": True}],
            [{**valid, "unexpected": "field"}],
        ]
        for prepared_actions in invalid_packets:
            with self.subTest(prepared_actions=prepared_actions):
                with self.assertRaises(APIError) as raised:
                    self.call(
                        "approve",
                        run["id"],
                        {
                            "nodeId": "approval",
                            "decision": "approve",
                            "comment": "Malformed packet probe.",
                            "preparedActions": prepared_actions,
                        },
                        REVIEWER,
                    )
                self.assertEqual("INVALID_PREPARED_ACTIONS", raised.exception.code)
        self.assertEqual([], self.store.get("runs", run["id"])["_decisions"])

    def test_invalid_adapter_output_is_stopped_at_the_pinned_contract_boundary(self):
        run = self.start()
        original = self.store.execute_adapter

        def invalid_intake_output(current_run, state, definition, agent):
            if agent.get("implementationId") == "intake":
                return {}
            return original(current_run, state, definition, agent)

        with patch.object(self.store, "execute_adapter", side_effect=invalid_intake_output):
            failed = self.run_until(run["id"], "needs_attention")

        intake = next(item for item in failed["nodes"] if item["nodeId"] == "intake")
        self.assertEqual("AGENT_OUTPUT_INVALID", intake["error"]["code"])
        self.assertEqual([], self.store.effects(run["id"]))


if __name__ == "__main__":
    unittest.main()
