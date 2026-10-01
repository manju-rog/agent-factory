"""Durable host/runtime coverage for the Atlas Checkout Simulation Lab.

These tests drive the registered Incident Commander through ``Store`` without
HTTP or background workers.  They therefore pin the engine, effect ledger,
restart recovery, and reset boundaries independently from UI timing.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import simulation_lab  # noqa: E402
from server import APIError, Store, USERS  # noqa: E402


ADMIN, REVIEWER, _OPERATOR, CONTRIBUTOR = USERS
TERMINAL = {"completed", "failed", "stopped"}


class SimulationLabStoreTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="simulation-lab-store-")
        self.database = Path(self.work.name) / "axiom.sqlite3"
        self.store = Store(self.database, latency=0)

    def tearDown(self):
        self.store.close()
        self.work.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def create_session(self, profile_id):
        response = self.call(
            "create_simulation_world", {"profileId": profile_id}, ADMIN
        )
        world = response["world"]
        run = self.call(
            "create_agent_run",
            {
                "specId": simulation_lab.INCIDENT_COMMANDER_ID,
                "mode": "fixture",
                "input": {
                    "worldId": world["id"],
                    "alertId": "ALT-CHECKOUT-9001",
                },
            },
            CONTRIBUTOR,
        )
        return world, run

    def public_run(self, run_id):
        with self.store.lock:
            return self.store.public_agent_run(
                self.store.get("agent_runs", run_id), ADMIN
            )

    def drive(self, run_id, *, stop_on_unknown=False, limit=80):
        for _ in range(limit):
            run = self.public_run(run_id)
            if stop_on_unknown and (
                run.get("status") == "stopped"
                and run.get("error", {}).get("code")
                == "WRITE_NEEDS_RECONCILIATION"
            ):
                return run
            if run["status"] in TERMINAL:
                return run
            if run["status"] in {"ready", "awaiting_tool"}:
                self.store.advance_agent_run(run_id, CONTRIBUTOR)
                continue
            if run["status"] == "awaiting_approval":
                self.call(
                    "decide_agent_action",
                    run_id,
                    {
                        "decision": "approve",
                        "expectedActionHash": run["pendingAction"]["actionHash"],
                    },
                    REVIEWER,
                )
                continue
            if run["status"] == "awaiting_input":
                values = {
                    "input.ownerTeam": "Commerce Reliability",
                    "input.slackChannelId": "C-INCIDENTS",
                }
                self.call(
                    "clarify_agent_run",
                    run_id,
                    {
                        "answers": {
                            field: values[field]
                            for field in run["requestedFields"]
                        }
                    },
                    CONTRIBUTOR,
                )
                continue
            self.fail(f"Unexpected Incident Commander state: {run}")
        self.fail(f"Incident Commander exceeded the test step bound: {self.public_run(run_id)}")

    def raw_effects(self, run_id):
        with self.store.lock:
            return self.store._adaptive_effects(run_id)

    @staticmethod
    def tool_effects(effects, tool_id):
        return [
            effect
            for effect in effects
            if effect.get("actionTarget", {}).get("toolId") == tool_id
        ]

    def test_profiles_progress_from_observations_and_record_exact_effect_states(self):
        completed = {}
        for profile_id in (
            "fresh-incident",
            "existing-incident",
            "missing-owner",
            "confluence-unavailable",
            "slack-rate-limit",
        ):
            with self.subTest(profile=profile_id):
                world, started = self.create_session(profile_id)
                run = self.drive(started["id"])
                self.assertEqual("completed", run["status"], run.get("error"))
                self.assertTrue(
                    run["completionCheck"]["businessOutcomeVerified"], run
                )
                self.assertEqual(world["id"], run["input"]["worldId"])
                completed[profile_id] = (world, run, self.raw_effects(run["id"]))

        fresh_world, fresh, fresh_effects = completed["fresh-incident"]
        self.assertEqual("OPS-4313", fresh["output"]["incidentKey"])
        self.assertEqual(
            ["acknowledged"],
            [
                effect["state"]
                for effect in self.tool_effects(
                    fresh_effects, "simulation.jira.create_incident"
                )
            ],
        )
        persisted_fresh = self.store.get("simulation_worlds", fresh_world["id"])
        self.assertEqual(1, len(persisted_fresh["records"]["jiraIssues"]))

        _existing_world, existing, existing_effects = completed["existing-incident"]
        self.assertEqual("OPS-4312", existing["output"]["incidentKey"])
        self.assertEqual(
            [],
            self.tool_effects(existing_effects, "simulation.jira.create_incident"),
            "Observed Jira evidence must reuse the active incident.",
        )

        _missing_world, missing, _missing_effects = completed["missing-owner"]
        self.assertTrue(
            any(event["type"] == "input.requested" for event in missing["events"])
        )

        _outage_world, outage, _outage_effects = completed[
            "confluence-unavailable"
        ]
        self.assertEqual("none", outage["output"]["mitigation"])
        self.assertIn(
            "unavailable", " ".join(outage["output"]["unresolvedRisks"]).lower()
        )

        rate_world, rate_limited, rate_effects = completed["slack-rate-limit"]
        slack_effects = self.tool_effects(
            rate_effects, "simulation.slack.post_message"
        )
        self.assertEqual(["failed", "acknowledged"], [e["state"] for e in slack_effects])
        self.assertEqual("SLACK_RATE_LIMITED", slack_effects[0]["failure"]["code"])
        self.assertEqual(429, slack_effects[0]["failureReceipt"]["statusCode"])
        self.assertNotEqual(
            slack_effects[0]["operationKey"], slack_effects[1]["operationKey"]
        )
        persisted_rate_world = self.store.get("simulation_worlds", rate_world["id"])
        bot_messages = [
            message
            for channel in persisted_rate_world["records"]["slackChannels"].values()
            for message in channel["messages"]
            if message["authorId"] == "AXIOM-INCIDENT-BOT"
        ]
        self.assertEqual(1, len(bot_messages))
        self.assertEqual("posted", rate_limited["output"]["communicationState"])

    def test_lost_jira_ack_stays_unknown_until_restart_then_reconciles_once(self):
        world, started = self.create_session("jira-lost-ack")
        uncertain = self.drive(started["id"], stop_on_unknown=True)
        self.assertEqual("stopped", uncertain["status"])
        self.assertEqual(
            "WRITE_NEEDS_RECONCILIATION", uncertain["error"]["code"]
        )
        jira_effect = self.tool_effects(
            self.raw_effects(started["id"]), "simulation.jira.create_incident"
        )[0]
        self.assertEqual("unknown", jira_effect["state"])
        operation_key = jira_effect["operationKey"]
        before = self.store.get("simulation_worlds", world["id"])
        self.assertEqual(1, len(before["records"]["jiraIssues"]))
        self.assertEqual(1, len(before["operations"]))

        self.store.close()
        self.store = Store(self.database, latency=0)

        resumed = self.public_run(started["id"])
        recovered = next(
            effect
            for effect in self.raw_effects(started["id"])
            if effect["operationKey"] == operation_key
        )
        self.assertEqual("reconciled", recovered["state"])
        self.assertTrue(recovered["executionReceipt"]["recovered"])
        self.assertNotEqual(
            "WRITE_NEEDS_RECONCILIATION", resumed.get("error", {}).get("code")
        )

        finished = self.drive(started["id"])
        self.assertEqual("completed", finished["status"], finished.get("error"))
        after = self.store.get("simulation_worlds", world["id"])
        self.assertEqual(1, len(after["records"]["jiraIssues"]))
        with self.store.lock:
            operation_rows = self.store.db.execute(
                "SELECT data FROM simulation_operations WHERE operation_key=?",
                (operation_key,),
            ).fetchall()
        self.assertEqual(1, len(operation_rows))
        self.assertEqual(
            operation_key, json.loads(operation_rows[0]["data"])["operationKey"]
        )

    def test_changed_flag_precondition_escalates_and_settles_failed_effect(self):
        world, started = self.create_session("changed-flag-version")
        run = self.drive(started["id"])
        self.assertEqual("stopped", run["status"])
        self.assertEqual("AGENT_ESCALATION_REQUIRED", run["error"]["code"])
        flag_effects = self.tool_effects(
            self.raw_effects(started["id"]), "simulation.feature_flags.update"
        )
        self.assertEqual(1, len(flag_effects))
        self.assertEqual("failed", flag_effects[0]["state"])
        self.assertEqual(
            "BUSINESS_PRECONDITION_CHANGED", flag_effects[0]["failure"]["code"]
        )
        self.assertFalse(
            any(effect["state"] == "prepared" for effect in self.raw_effects(started["id"]))
        )
        persisted = self.store.get("simulation_worlds", world["id"])
        self.assertTrue(persisted["records"]["featureFlags"]["checkout-v2"]["enabled"])
        self.assertFalse(
            any(
                operation["toolId"] == "simulation.feature_flags.update"
                for operation in persisted["operations"].values()
            )
        )

    def test_reset_blocks_direct_session_and_preserves_prior_generation_audit(self):
        world, started = self.create_session("fresh-incident")
        with self.assertRaises(APIError) as caught:
            self.call("reset_simulation_world", world["id"], ADMIN)
        self.assertEqual("SIMULATION_SESSION_ACTIVE", caught.exception.code)

        finished = self.drive(started["id"])
        self.assertEqual("completed", finished["status"], finished.get("error"))
        with self.store.lock:
            event_count_before = self.store.db.execute(
                "SELECT COUNT(*) FROM simulation_events WHERE world_id=?",
                (world["id"],),
            ).fetchone()[0]
            operation_count_before = self.store.db.execute(
                "SELECT COUNT(*) FROM simulation_operations WHERE world_id=?",
                (world["id"],),
            ).fetchone()[0]
        self.assertGreater(event_count_before, 1)
        self.assertGreater(operation_count_before, 0)

        reset = self.call("reset_simulation_world", world["id"], ADMIN)["world"]
        self.assertEqual(2, reset["generation"])
        self.assertEqual([1], reset["archivedGenerations"])
        self.assertTrue(
            all(event["generation"] == 2 for event in reset["events"]),
            reset["events"],
        )
        with self.store.lock:
            event_count_after = self.store.db.execute(
                "SELECT COUNT(*) FROM simulation_events WHERE world_id=?",
                (world["id"],),
            ).fetchone()[0]
            operation_count_after = self.store.db.execute(
                "SELECT COUNT(*) FROM simulation_operations WHERE world_id=?",
                (world["id"],),
            ).fetchone()[0]
        self.assertGreater(event_count_after, event_count_before)
        self.assertEqual(operation_count_before, operation_count_after)

    def test_operation_key_cannot_replay_across_world_generations(self):
        created = self.call(
            "create_simulation_world", {"profileId": "fresh-incident"}, ADMIN
        )["world"]
        generation_one = self.store.get("simulation_worlds", created["id"])
        operation = {
            "operationKey": "generation-bound-operation",
            "actionHash": "a" * 64,
            "toolId": "simulation.slack.post_message",
            "payloadHash": "b" * 64,
            "result": {"messageId": "MSG-ONE"},
            "executionReceipt": {
                "provider": "Atlas Slack Mirror",
                "externalEffect": False,
            },
        }
        self.call(
            "_persist_simulation_transition", generation_one, [], operation
        )
        stored = self.store.simulation_operation(operation["operationKey"])
        self.assertEqual(1, stored["worldGeneration"])

        reset = self.call("reset_simulation_world", created["id"], ADMIN)["world"]
        self.assertEqual(2, reset["generation"])
        generation_two = self.store.get("simulation_worlds", created["id"])
        with self.assertRaises(APIError) as caught:
            self.call(
                "_persist_simulation_transition", generation_two, [], operation
            )
        self.assertEqual("SIMULATION_OPERATION_CONFLICT", caught.exception.code)
        self.assertIn("worldGeneration", caught.exception.details["changedFields"])
        self.assertEqual(
            1,
            self.store.simulation_operation(operation["operationKey"])[
                "worldGeneration"
            ],
        )


if __name__ == "__main__":
    unittest.main()
