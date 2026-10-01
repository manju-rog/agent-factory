import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server as server_module
from domain import template_hashes
from server import APIError, DEMO_WORKFLOWS, Store, USERS, decode_json_strict, digest


AUTHOR, REVIEWER, _, CONTRIBUTOR = USERS
DEMO_IDS = tuple(spec["id"] for spec in DEMO_WORKFLOWS)


class DemoWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "demos.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        if self.store is not None:
            self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def until(self, run_id, statuses, limit=160):
        statuses = {statuses} if isinstance(statuses, str) else set(statuses)
        for _ in range(limit):
            self.store.tick()
            run = self.store.get("runs", run_id)
            if run["status"] in statuses:
                return run
        self.fail(f"run {run_id} did not reach {sorted(statuses)}; observed {run['status']}")

    def approve(self, run):
        gate = next(node for node in run["nodes"] if node["status"] == "waiting_approval")
        references = [{
            key: action[key]
            for key in (
                "effectId", "nodeId", "operationGeneration",
                "actionFingerprint", "approvalEnvelopeHash",
            )
        } for action in gate["approvalPacket"]["actions"]]
        return self.call("approve", run["id"], {
            "nodeId": gate["nodeId"], "decision": "approve",
            "comment": "Verified the deterministic demonstration evidence.",
            "preparedActions": references,
        }, REVIEWER)

    def test_fresh_workspace_contains_published_complex_demos_and_flagship(self):
        templates = {item["id"]: item for item in self.store.all("templates")}
        self.assertEqual(
            {"customer-resolution", "atlas-checkout-incident-command", *DEMO_IDS},
            set(templates),
        )
        for spec in DEMO_WORKFLOWS:
            with self.subTest(template=spec["id"]):
                template = templates[spec["id"]]
                self.assertEqual("published", template["status"])
                self.assertEqual(1, template["publishedVersion"])
                self.assertEqual(spec["exampleInput"], template["exampleInput"])
                self.assertEqual(
                    set(spec["inputProperties"]),
                    set(template["inputSchema"]["required"]) - {"requestId", "customerId", "subject", "amount", "priority"},
                )
                self.assertGreaterEqual(len(template["nodes"]), 14)
                self.assertTrue(self.store.validate(template)["valid"])
                release = self.store._verified_release(template)
                self.assertEqual(template["demoFixture"], release["snapshot"]["demoFixture"])
                bundle = release["snapshot"]["demoFixture"]
                self.assertEqual(
                    bundle["contentHash"],
                    digest({key: value for key, value in bundle.items() if key != "contentHash"}),
                )
                ticket = next(node for node in template["nodes"] if node["id"] == "ticket")
                self.assertEqual(bundle["actionFields"], ticket["config"]["actionFields"])
                self.assertEqual("axiom.contract.v1", release["snapshot"]["schemaVersion"])
                self.assertEqual("axiom.plan.v1", release["snapshot"]["compiledPlan"]["schemaVersion"])
                self.assertEqual(2, len(release["snapshot"]["compiledPlan"]["scopes"]))

    def test_restart_backfills_missing_ids_without_overwriting_existing_demo(self):
        customized = self.store.get("templates", DEMO_IDS[0])
        customized["name"] = "Team-customized payment flow"
        customized["tags"] = ["owned-by-team"]
        self.store.put("templates", customized)
        missing = DEMO_IDS[1:]
        for ident in missing:
            self.store.db.execute("DELETE FROM templates WHERE id=?", (ident,))
        audit_before = self.store.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        self.store.close()
        self.store = Store(self.path, latency=0)

        self.assertEqual("Team-customized payment flow", self.store.get("templates", DEMO_IDS[0])["name"])
        self.assertEqual(["owned-by-team"], self.store.get("templates", DEMO_IDS[0])["tags"])
        self.assertTrue(all(self.store.get("templates", ident) for ident in missing))
        audit_after_backfill = self.store.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        self.assertEqual(audit_before + len(missing), audit_after_backfill)

        self.store.close()
        self.store = Store(self.path, latency=0)
        self.assertEqual(
            audit_after_backfill,
            self.store.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0],
            "an idempotent restart must not reseed or append audit records",
        )

    def test_legacy_demo_release_gets_hashed_compatibility_without_rewrite(self):
        spec = DEMO_WORKFLOWS[0]
        template = self.store.get("templates", spec["id"])
        release = template["versions"][0]
        legacy = copy.deepcopy(release["snapshot"])
        legacy.pop("demoFixture")
        next(node for node in legacy["nodes"] if node["id"] == "ticket")["config"].pop("actionFields")
        legacy["inputSchema"]["required"] = ["requestId", "customerId", "subject", "amount", "priority"]
        hashes = template_hashes(self.store._release_hash_basis(legacy))
        legacy.update(hashes)
        release["snapshot"] = legacy
        release["hash"] = digest(legacy)
        release.update(hashes)
        legacy_hash = release["hash"]
        template.pop("demoFixture")
        next(node for node in template["nodes"] if node["id"] == "ticket")["config"].pop("actionFields")
        template["inputSchema"]["required"] = ["requestId", "customerId", "subject", "amount", "priority"]
        template.pop("releaseCompatibility", None)
        template.pop("releaseCompatibilityHistory", None)
        self.store.put("templates", template)

        self.store.close()
        self.store = Store(self.path, latency=0)
        migrated = self.store.get("templates", spec["id"])
        self.assertEqual(legacy_hash, migrated["versions"][0]["hash"])
        self.assertNotIn("demoFixture", migrated["versions"][0]["snapshot"])
        self.assertIn("demoFixture", migrated)
        compatibility = migrated["releaseCompatibility"]["1"]
        self.assertEqual(legacy_hash, compatibility["sourceHash"])
        self.assertIn("pin-immutable-demo-fixture", compatibility["reasons"])
        executable = self.store._verified_release(migrated)["snapshot"]
        self.assertIn("demoFixture", executable)
        self.assertEqual(set(spec["inputProperties"]), set(executable["inputSchema"]["required"]) - {
            "requestId", "customerId", "subject", "amount", "priority",
        })

    def test_tampered_pinned_demo_fixture_blocks_release_start(self):
        spec = DEMO_WORKFLOWS[0]
        template = self.store.get("templates", spec["id"])
        template["versions"][0]["snapshot"]["demoFixture"]["recordPrefix"] = "BAD"
        self.store.put("templates", template)
        with self.assertRaises(APIError) as raised:
            self.call("create_run", {
                "templateId": spec["id"], "mode": "fixture",
                "input": copy.deepcopy(spec["exampleInput"]),
            }, CONTRIBUTOR)
        self.assertEqual("RELEASE_INTEGRITY_FAILED", raised.exception.code)
        self.assertEqual([], self.store.all("runs"))

    def test_every_demo_completes_realistic_happy_simulation(self):
        for spec in DEMO_WORKFLOWS:
            with self.subTest(template=spec["id"]):
                created = self.call("create_run", {
                    "templateId": spec["id"], "mode": "simulation",
                    "scenario": "happy", "input": copy.deepcopy(spec["exampleInput"]),
                }, CONTRIBUTOR)
                waiting = self.until(created["id"], {"waiting_approval", "needs_attention"})
                self.assertEqual("waiting_approval", waiting["status"])
                action = next(
                    action
                    for node in waiting["nodes"]
                    for action in node.get("approvalPacket", {}).get("actions", [])
                )
                self.assertEqual(spec["resource"], action["actionTarget"]["resource"])
                expected_record = {
                    field: spec["exampleInput"][field]
                    for field in ["requestId", "customerId", "subject", "amount", "priority", *spec["inputProperties"]]
                }
                self.assertEqual(expected_record, action["payload"])
                self.approve(waiting)
                finished = self.until(created["id"], {"completed", "needs_attention"})
                self.assertEqual("completed", finished["status"])
                self.assertTrue(finished["ticket"]["id"].startswith(spec["recordPrefix"] + "-SIM-"))
                self.assertFalse(finished["ticket"]["persisted"])
                self.assertEqual(spec["resource"], finished["ticket"]["resource"])
                self.assertEqual(expected_record, finished["ticket"]["record"])
                self.assertEqual(1, len(self.store.effects(created["id"])))
                self.assertEqual("acknowledged", self.store.effects(created["id"])[0]["state"])
                self.assertEqual(1, sum(node["status"] == "skipped" for node in finished["nodes"]))
                self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
                evidence = [item for node in finished["nodes"] for item in node["evidence"]]
                self.assertTrue(any(
                    item["source"].startswith(f"fixture://demo/{spec['id']}/")
                    for item in evidence
                ))
                policy = next(node for node in finished["nodes"] if node["nodeId"] == "policy")
                self.assertEqual(spec["policy"]["id"], policy["output"]["policy"]["policyId"])

    def test_every_domain_field_is_required_in_draft_and_release_runs(self):
        for spec in DEMO_WORKFLOWS:
            for field in spec["inputProperties"]:
                for mode in ("simulation", "fixture"):
                    with self.subTest(template=spec["id"], field=field, mode=mode):
                        supplied = copy.deepcopy(spec["exampleInput"])
                        supplied.pop(field)
                        before = len(self.store.all("runs"))
                        with self.assertRaises(APIError) as raised:
                            self.call("create_run", {
                                "templateId": spec["id"], "mode": mode,
                                "scenario": "happy", "input": supplied,
                            }, CONTRIBUTOR)
                        self.assertEqual("INPUT_SCHEMA_INVALID", raised.exception.code)
                        self.assertIn(field, " ".join(str(item) for item in raised.exception.details))
                        self.assertEqual(before, len(self.store.all("runs")))
                        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM effects").fetchone()[0])
                        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_claim_loss_date_must_be_a_real_calendar_date(self):
        spec = next(item for item in DEMO_WORKFLOWS if item["id"] == "insurance-claim-adjudication")
        supplied = {**copy.deepcopy(spec["exampleInput"]), "incidentDate": "2026-02-30"}
        with self.assertRaises(APIError) as raised:
            self.call("create_run", {
                "templateId": spec["id"], "mode": "simulation", "input": supplied,
            }, CONTRIBUTOR)
        self.assertEqual("INPUT_SCHEMA_INVALID", raised.exception.code)
        self.assertIn("incidentDate", " ".join(str(item) for item in raised.exception.details))

    def test_published_fixture_and_default_input_ignore_live_registry_changes(self):
        original = copy.deepcopy(DEMO_WORKFLOWS[0])
        replacement = copy.deepcopy(original)
        replacement["record"]["name"] = "Changed live registry name"
        replacement["policy"]["id"] = "CHANGED-LIVE-POLICY"
        replacement["recordPrefix"] = "BAD"
        replacement["resource"] = "changed-live-resource"
        replacement["exampleInput"]["subject"] = "Changed unpinned default"
        template = self.store.get("templates", original["id"])
        release_hash = template["versions"][0]["hash"]
        template["exampleInput"] = copy.deepcopy(replacement["exampleInput"])
        self.store.put("templates", template)

        with patch.dict(server_module.DEMO_WORKFLOW_BY_ID, {original["id"]: replacement}):
            created = self.call("create_run", {
                "templateId": original["id"], "mode": "fixture", "scenario": "happy",
            }, CONTRIBUTOR)
            self.assertEqual(original["exampleInput"], created["input"])
            waiting = self.until(created["id"], "waiting_approval")
            record = next(node for node in waiting["nodes"] if node["nodeId"] == "record")
            self.assertEqual(original["record"]["name"], record["output"]["customer"]["name"])
            policy = next(node for node in waiting["nodes"] if node["nodeId"] == "policy")
            self.assertEqual(original["policy"]["id"], policy["output"]["policy"]["policyId"])
            action = next(
                action for node in waiting["nodes"]
                for action in node.get("approvalPacket", {}).get("actions", [])
            )
            self.assertEqual(original["resource"], action["actionTarget"]["resource"])
            self.approve(waiting)
            finished = self.until(created["id"], "completed")
            self.assertTrue(finished["ticket"]["id"].startswith(original["recordPrefix"] + "-"))
        self.assertEqual(release_hash, self.store.get("templates", original["id"])["versions"][0]["hash"])

    def test_non_subject_domain_change_invalidates_prepared_approval(self):
        spec = next(item for item in DEMO_WORKFLOWS if item["id"] == "employee-access-governance")
        created = self.call("create_run", {
            "templateId": spec["id"], "mode": "simulation", "scenario": "happy",
            "input": copy.deepcopy(spec["exampleInput"]),
        }, CONTRIBUTOR)
        waiting = self.until(created["id"], "waiting_approval")
        changed = self.store.get("runs", created["id"])
        ticket = next(node for node in changed["nodes"] if node["nodeId"] == "ticket")
        ticket["input"]["durationDays"] = 60
        self.store.put("runs", changed)
        with self.assertRaises(APIError) as raised:
            self.approve(waiting)
        self.assertEqual("PREPARED_ACTION_MISMATCH", raised.exception.code)
        current = self.store.get("runs", created["id"])
        self.assertEqual([], current["_decisions"])
        self.assertIsNone(current.get("ticket"))
        self.assertEqual("prepared", self.store.effects(created["id"])[0]["state"])

    def test_each_demo_standard_branch_is_named_and_observable(self):
        alternates = {
            "payment-dispute-investigation": {"amount": 250},
            "employee-access-governance": {"accessLevel": "standard"},
            "production-incident-change": {"severity": "sev2"},
            "vendor-risk-onboarding": {"amount": 45000},
            "insurance-claim-adjudication": {"amount": 12000},
        }
        for spec in DEMO_WORKFLOWS:
            with self.subTest(template=spec["id"]):
                supplied = {**copy.deepcopy(spec["exampleInput"]), **alternates[spec["id"]]}
                created = self.call("create_run", {
                    "templateId": spec["id"], "mode": "simulation",
                    "scenario": "happy", "input": supplied,
                }, CONTRIBUTOR)
                waiting = self.until(created["id"], "waiting_approval")
                self.assertEqual(
                    "skipped",
                    next(node for node in waiting["nodes"] if node["nodeId"] == spec["routes"][0][0])["status"],
                )
                selected = next(node for node in waiting["nodes"] if node["nodeId"] == spec["routes"][1][0])
                self.assertEqual("succeeded", selected["status"])
                self.assertTrue(any(
                    item["source"].endswith(f"/{spec['routes'][1][0]}/v1")
                    for item in selected["evidence"]
                ))
                self.approve(waiting)
                self.assertEqual("completed", self.until(created["id"], "completed")["status"])

    def test_demo_export_import_preserves_sample_and_fixture_behavior(self):
        spec = DEMO_WORKFLOWS[3]
        package = self.store.export_template(spec["id"])
        imported = self.call("import_template", package, AUTHOR)
        self.assertEqual(spec["tags"], imported["tags"])
        self.assertEqual(spec["exampleInput"], imported["exampleInput"])
        self.assertEqual(self.store.get("templates", spec["id"])["demoFixture"], imported["demoFixture"])
        created = self.call("create_run", {
            "templateId": imported["id"], "mode": "simulation", "scenario": "happy",
        }, CONTRIBUTOR)
        self.assertEqual(spec["exampleInput"], created["input"])
        waiting = self.until(created["id"], "waiting_approval")
        action = next(
            action for node in waiting["nodes"]
            for action in node.get("approvalPacket", {}).get("actions", [])
        )
        self.assertEqual(spec["resource"], action["actionTarget"]["resource"])

    def test_fixture_action_record_matches_the_reviewed_payload(self):
        spec = DEMO_WORKFLOWS[4]
        created = self.call("create_run", {
            "templateId": spec["id"], "mode": "fixture", "scenario": "happy",
            "input": copy.deepcopy(spec["exampleInput"]),
        }, CONTRIBUTOR)
        waiting = self.until(created["id"], "waiting_approval")
        action = next(
            action for node in waiting["nodes"]
            for action in node.get("approvalPacket", {}).get("actions", [])
        )
        self.approve(waiting)
        finished = self.until(created["id"], "completed")
        stored = self.store.db.execute("SELECT data FROM tickets").fetchone()[0]
        record = decode_json_strict(stored)
        self.assertEqual(action["payload"], record["record"])
        self.assertEqual(action["actionTarget"]["resource"], record["resource"])
        self.assertEqual(record, finished["ticket"])

    def test_bounded_fixture_profile_survives_template_duplication(self):
        spec = DEMO_WORKFLOWS[0]
        duplicate = self.call("duplicate_template", spec["id"], AUTHOR)
        self.assertEqual(spec["exampleInput"], duplicate["exampleInput"])
        created = self.call("create_run", {
            "templateId": duplicate["id"], "mode": "simulation",
            "scenario": "happy", "input": copy.deepcopy(spec["exampleInput"]),
        }, CONTRIBUTOR)
        waiting = self.until(created["id"], "waiting_approval")
        self.assertEqual(spec["resource"], next(
            action["actionTarget"]["resource"]
            for node in waiting["nodes"]
            for action in node.get("approvalPacket", {}).get("actions", [])
        ))
        self.approve(waiting)
        finished = self.until(created["id"], "completed")
        self.assertTrue(finished["ticket"]["id"].startswith(spec["recordPrefix"] + "-SIM-"))
        evidence = [item for node in finished["nodes"] for item in node["evidence"]]
        self.assertTrue(any(item["source"].startswith(
            f"fixture://demo/{spec['id']}/"
        ) for item in evidence))

        invalid = copy.deepcopy(duplicate)
        next(node for node in invalid["nodes"] if node["id"] == "record")["config"]["fixtureProfile"] = "unbounded:profile"
        validation = self.store.validate(invalid)
        self.assertFalse(validation["valid"])
        self.assertIn("FIXTURE_PROFILE", {issue["code"] for issue in validation["issues"]})

    def test_every_demo_passes_the_required_ten_case_rehearsal(self):
        experiments = [
            self.call("create_experiment", {"templateId": ident, "suite": "required"}, AUTHOR)
            for ident in DEMO_IDS
        ]
        for _ in range(500):
            self.store.tick()
            observed = [self.store.experiment(item["id"]) for item in experiments]
            if all(item["status"] == "completed" for item in observed):
                break
        else:
            self.fail("the demo rehearsal suites did not settle")
        for result in observed:
            with self.subTest(template=result["templateId"]):
                self.assertEqual(10, result["metrics"]["total"])
                self.assertEqual(10, result["metrics"]["settled"])
                self.assertEqual(10, result["metrics"]["passed"])
                self.assertEqual(0, result["metrics"]["externalWrites"])
                self.assertEqual(0, result["metrics"]["unauthorizedEffects"])


if __name__ == "__main__":
    unittest.main()
