"""Connection authority contracts for prepared and dispatched writes."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import APIError, Store, USERS


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


class ConnectionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "connections.sqlite3", latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def wait_for_approval(self):
        run = self.call(
            "create_run",
            {"templateId": "customer-resolution", "mode": "fixture", "scenario": "happy"},
            CONTRIBUTOR,
        )
        for _ in range(100):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            approval = next(item for item in current["nodes"] if item["nodeId"] == "approval")
            if approval["status"] == "waiting_approval":
                return current, approval
        self.fail("Run did not reach its approval gate")

    @staticmethod
    def references(approval):
        return [{key: action[key] for key in (
            "effectId", "nodeId", "operationGeneration",
            "actionFingerprint", "approvalEnvelopeHash",
        )} for action in approval["approvalPacket"]["actions"]]

    def test_connection_mutation_is_admin_only_versioned_and_audited(self):
        initial = self.store.get("connections", "fixture-ticket")
        self.assertEqual("ready", initial["status"])
        with self.assertRaises(APIError) as denied:
            self.call("connection_action", "fixture-ticket", "revoke", OPERATOR)
        self.assertEqual("ROLE_DENIED", denied.exception.code)

        tested = self.call("connection_action", "fixture-ticket", "test", AUTHOR)
        self.assertTrue(tested["reachable"])
        revoked = self.call("connection_action", "fixture-ticket", "revoke", AUTHOR)
        self.assertEqual("revoked", revoked["status"])
        self.assertEqual(initial["generation"] + 1, revoked["generation"])
        restored = self.call("connection_action", "fixture-ticket", "restore", AUTHOR)
        self.assertEqual("ready", restored["status"])
        self.assertEqual(revoked["generation"] + 1, restored["generation"])
        actions = [json.loads(row[0])["action"] for row in self.store.db.execute(
            "SELECT data FROM audit ORDER BY id"
        )]
        self.assertIn("connection.tested", actions)
        self.assertIn("connection.revoked", actions)
        self.assertIn("connection.restored", actions)

    def test_revocation_invalidates_packet_before_decision(self):
        run, approval = self.wait_for_approval()
        refs = self.references(approval)
        self.call("connection_action", "fixture-ticket", "revoke", AUTHOR)

        with self.assertRaises(APIError) as denied:
            self.call("approve", run["id"], {
                "nodeId": "approval", "decision": "approve",
                "comment": "This stale packet must not be accepted.",
                "preparedActions": refs,
            }, REVIEWER)
        self.assertEqual("CONNECTION_NOT_READY", denied.exception.code)
        current = self.store.get("runs", run["id"])
        self.assertEqual([], current["_decisions"])
        self.assertEqual("prepared", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_authority_is_rechecked_after_approval_before_dispatch(self):
        run, approval = self.wait_for_approval()
        self.call("approve", run["id"], {
            "nodeId": "approval", "decision": "approve",
            "comment": "Reviewed while the local authority was active.",
            "preparedActions": self.references(approval),
        }, REVIEWER)
        self.call("connection_action", "fixture-ticket", "revoke", AUTHOR)

        for _ in range(20):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            if current["status"] == "needs_attention":
                break
        ticket_state = next(item for item in current["nodes"] if item["nodeId"] == "ticket")
        self.assertEqual("needs_attention", current["status"])
        self.assertEqual("CONNECTION_NOT_READY", ticket_state["error"]["code"])
        self.assertEqual("prepared", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_revocation_does_not_hide_or_repeat_an_already_accepted_write(self):
        run = self.call(
            "create_run",
            {"templateId": "customer-resolution", "mode": "fixture",
             "scenario": "after_write_timeout"},
            CONTRIBUTOR,
        )
        for _ in range(100):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            approval = next(item for item in current["nodes"] if item["nodeId"] == "approval")
            if approval["status"] == "waiting_approval":
                break
        self.call("approve", run["id"], {
            "nodeId": "approval", "decision": "approve", "comment": "Exact write reviewed.",
            "preparedActions": self.references(approval),
        }, REVIEWER)
        for _ in range(100):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            if current["status"] == "needs_attention":
                break
        ticket = next(item for item in current["nodes"] if item["nodeId"] == "ticket")
        self.assertEqual("unknown", self.store.effects(run["id"])[0]["state"])
        self.call("connection_action", "fixture-ticket", "revoke", AUTHOR)

        self.call("retry", run["id"], {"nodeId": ticket["nodeId"]}, OPERATOR)
        for _ in range(100):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            if current["status"] == "completed":
                break
        self.assertEqual("completed", current["status"], current["nodes"])
        self.assertEqual("acknowledged", self.store.effects(run["id"])[0]["state"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
