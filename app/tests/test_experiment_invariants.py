from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from server import APIError, Store, USERS, encode
from scenarios import scenario_from_snapshot


AUTHOR = USERS[0]


class ExperimentInvariantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "experiment-invariants.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def completed_core_experiment(self):
        experiment = self.call(
            "create_experiment",
            {"templateId": "customer-resolution", "suite": "core"},
            AUTHOR,
        )
        result = self.store.experiment(experiment["id"])
        for _ in range(80):
            if result["status"] == "completed":
                break
            self.store.tick()
            result = self.store.experiment(experiment["id"])
        self.assertEqual("completed", result["status"], result)
        self.assertEqual(4, result["metrics"]["passed"], result)
        return experiment, result

    def create_core_until_happy_effect(self):
        experiment = self.call(
            "create_experiment",
            {"templateId": "customer-resolution", "suite": "core"},
            AUTHOR,
        )
        happy_run_id = experiment["runs"][0]
        for _ in range(80):
            self.store.tick()
            run = self.store.get("runs", happy_run_id)
            attempted = [
                item for item in self.store.effects(happy_run_id)
                if item.get("dispatchedAt")
                or any(change.get("state") == "dispatched"
                       for change in item.get("transitions", []))
            ]
            if attempted and run["status"] not in {"completed", "rejected", "expired", "failed", "cancelled"}:
                return experiment, run, attempted[0]
        self.fail("Happy rehearsal did not expose an attempted effect before completion")

    def finish_experiment(self, experiment):
        result = self.store.experiment(experiment["id"])
        for _ in range(80):
            if result["status"] == "completed":
                break
            self.store.tick()
            result = self.store.experiment(experiment["id"])
        self.assertEqual("completed", result["status"], result)
        return result

    @staticmethod
    def scenario_result(result, scenario):
        return next(item for item in result["results"] if item["scenario"] == scenario)

    def test_authorization_is_measured_from_bound_decisions_at_dispatch_time(self):
        experiment, run, effect = self.create_core_until_happy_effect()
        dispatched_at = datetime.fromisoformat(
            effect["dispatchedAt"].replace("Z", "+00:00")
        )
        expires_at = dispatched_at + timedelta(milliseconds=1)
        effect["approvalPolicy"]["expiresAt"] = expires_at.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        self.store.atomic(self.store._save_effect, effect)

        if datetime.now(timezone.utc) <= expires_at:
            time.sleep(0.01)
        self.assertLess(expires_at, datetime.now(timezone.utc))
        baseline = self.finish_experiment(experiment)
        retrospective_happy = self.scenario_result(baseline, "happy")
        self.assertEqual(
            0,
            retrospective_happy["invariants"]["unauthorizedEffects"],
            retrospective_happy,
        )
        self.assertTrue(retrospective_happy["passed"], retrospective_happy)

        self.assertTrue(run["_decisions"])
        run["_decisions"] = []
        self.store.atomic(self.store.put, "runs", run)
        preserved = self.store.experiment(experiment["id"])
        self.assertEqual(baseline, preserved)

    def test_non_reviewer_decision_is_measured_as_unauthorized(self):
        experiment, run, _ = self.create_core_until_happy_effect()
        self.assertTrue(run["_decisions"])
        run["_decisions"][0]["role"] = "contributor"
        self.store.atomic(self.store.put, "runs", run)

        measured = self.finish_experiment(experiment)
        happy = self.scenario_result(measured, "happy")
        self.assertEqual(1, happy["invariants"]["unauthorizedEffects"], happy)
        self.assertFalse(happy["passed"], happy)
        self.assertEqual(3, measured["metrics"]["passed"])

    def test_isolation_reads_actual_ticket_and_outbox_provider_state(self):
        experiment = self.call(
            "create_experiment",
            {"templateId": "customer-resolution", "suite": "core"},
            AUTHOR,
        )
        happy_run = self.store.get("runs", experiment["runs"][0])
        operation_key = next(
            state["operationKey"] for state in happy_run["nodes"]
            if state["nodeId"] == "ticket"
        )
        self.store.db.execute(
            "INSERT INTO tickets(operation_key,data) VALUES (?,?)",
            (operation_key, encode({"id": "unexpected-ticket", "operationKey": operation_key})),
        )
        self.store.put("outbox", {
            "id": "unexpected-outbox", "runId": happy_run["id"],
            "operationKey": operation_key,
        })

        measured = self.finish_experiment(experiment)
        measured_happy = self.scenario_result(measured, "happy")
        self.assertEqual(
            2,
            measured_happy["invariants"]["externalWrites"],
            measured_happy,
        )
        self.assertFalse(measured_happy["passed"], measured_happy)
        self.assertEqual(3, measured["metrics"]["passed"])

    def test_effect_destination_identity_drives_isolation_check(self):
        experiment, _, effect = self.create_core_until_happy_effect()
        effect["connectionIdentity"] = {
            **effect["connectionIdentity"],
            "connectionId": "fixture-ticket",
            "principalRef": "local-fixture://ticket-store",
        }
        effect["actionTarget"]["connectionId"] = "fixture-ticket"
        self.store.atomic(self.store._save_effect, effect)

        measured = self.finish_experiment(experiment)
        happy = self.scenario_result(measured, "happy")
        isolation = next(
            item for item in happy["invariants"]["catalogChecks"]
            if item["check"] == "effects.external_count"
        )
        self.assertEqual(1, isolation["actual"], happy)
        self.assertFalse(isolation["passed"], happy)
        self.assertFalse(happy["passed"], happy)

    def test_scenario_definitions_are_pinned_and_completed_result_is_private_and_stable(self):
        experiment = self.call(
            "create_experiment",
            {"templateId": "customer-resolution", "suite": "core"},
            AUTHOR,
        )
        self.assertNotIn("_pinnedScenarios", experiment)
        stored = self.store.get("experiments", experiment["id"])
        self.assertEqual(experiment["runs"], [item["runId"] for item in stored["_pinnedScenarios"]])
        self.assertTrue(all(
            scenario_from_snapshot(item["scenario"]).fingerprint == item["scenario"]["fingerprint"]
            for item in stored["_pinnedScenarios"]
        ))

        with patch("server.required_scenarios", return_value=()):
            completed = self.finish_experiment(experiment)
            self.assertEqual(4, completed["metrics"]["passed"], completed)
        self.assertNotIn("_pinnedScenarios", completed)
        self.assertNotIn("_completedEvaluation", completed)
        stored = self.store.get("experiments", experiment["id"])
        self.assertIn("_completedEvaluation", stored)

    def test_tampered_or_missing_pinned_scenarios_fail_closed(self):
        experiment = self.call(
            "create_experiment",
            {"templateId": "customer-resolution", "suite": "core"},
            AUTHOR,
        )
        stored = self.store.get("experiments", experiment["id"])
        stored["_pinnedScenarios"][0]["scenario"]["definition"]["expected_final_state"]["status"] = "failed"
        self.store.put("experiments", stored)
        with self.assertRaises(APIError) as raised:
            self.store.experiment(experiment["id"])
        self.assertEqual("EXPERIMENT_INTEGRITY", raised.exception.code)

        second = self.call(
            "create_experiment",
            {"templateId": "customer-resolution", "suite": "core"},
            AUTHOR,
        )
        legacy = self.store.get("experiments", second["id"])
        legacy.pop("_pinnedScenarios")
        self.store.put("experiments", legacy)
        with self.assertRaises(APIError) as raised:
            self.store.experiment(second["id"])
        self.assertEqual("EXPERIMENT_INTEGRITY", raised.exception.code)

    def test_completed_experiment_rejects_missing_or_malformed_pins(self):
        experiment, _ = self.completed_core_experiment()
        baseline = self.store.get("experiments", experiment["id"])

        for corruption in ("missing", "malformed"):
            with self.subTest(corruption=corruption):
                stored = self.store.get("experiments", experiment["id"])
                if corruption == "missing":
                    stored.pop("_pinnedScenarios")
                else:
                    stored["_pinnedScenarios"] = "not-a-pin-set"
                self.store.put("experiments", stored)
                with self.assertRaises(APIError) as raised:
                    self.store.experiment(experiment["id"])
                self.assertEqual("EXPERIMENT_INTEGRITY", raised.exception.code)
                self.store.put("experiments", baseline)


if __name__ == "__main__":
    unittest.main()
