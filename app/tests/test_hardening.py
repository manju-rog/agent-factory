import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import APIError, DEFAULT_CONFIG, Store, USERS


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "hardening.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def test_run_and_experiment_start_are_role_checked(self):
        with self.assertRaises(APIError) as denied:
            self.call("create_run", {"templateId": "customer-resolution", "mode": "fixture"}, OPERATOR)
        self.assertEqual("ROLE_DENIED", denied.exception.code)
        with self.assertRaises(APIError):
            self.call("create_experiment", {"templateId": "customer-resolution"}, CONTRIBUTOR)
        self.assertEqual("running", self.call("create_experiment", {"templateId": "customer-resolution"}, AUTHOR)["status"])

    def test_write_without_approval_is_a_publication_error(self):
        template = self.call("create_template", {"name": "Unsafe write", "description": "Must not release"}, AUTHOR)
        nodes = [
            {"id": "start", "agentId": "intake", "label": "Input", "x": 0, "y": 0, "config": copy.deepcopy(DEFAULT_CONFIG)},
            {"id": "write", "agentId": "ticket", "label": "Write", "x": 300, "y": 0, "config": copy.deepcopy(DEFAULT_CONFIG)},
        ]
        edges = [{"id": "unsafe", "source": "start", "target": "write"}]
        saved = self.call("update_template", template["id"], {"expectedRevision": 1, "nodes": nodes, "edges": edges}, AUTHOR)
        validation = self.store.validate(saved)
        self.assertFalse(validation["valid"])
        self.assertIn("WRITE_WITHOUT_APPROVAL", {issue["code"] for issue in validation["issues"]})
        with self.assertRaises(APIError):
            self.call("submit_template", template["id"], AUTHOR)

    def test_approval_on_only_one_parallel_path_does_not_guard_a_write(self):
        template = self.call("create_template", {
            "name": "Bypassable approval",
            "description": "A protected write must be dominated by its approval gate.",
        }, AUTHOR)
        config = copy.deepcopy(DEFAULT_CONFIG)
        nodes = [
            {"id": "start", "agentId": "intake", "label": "Input", "x": 0, "y": 100, "config": copy.deepcopy(config)},
            {"id": "gate", "agentId": "approval", "label": "Review", "x": 250, "y": 0, "config": copy.deepcopy(config)},
            {"id": "gated", "agentId": "enrich", "label": "Gated branch", "x": 375, "y": 0, "config": copy.deepcopy(config)},
            {"id": "bypass", "agentId": "enrich", "label": "Bypass", "x": 250, "y": 200, "config": copy.deepcopy(config)},
            {"id": "write", "agentId": "ticket", "label": "Write", "x": 500, "y": 100, "config": copy.deepcopy(config)},
        ]
        edges = [
            {"id": "start_gate", "source": "start", "target": "gate"},
            {"id": "start_bypass", "source": "start", "target": "bypass"},
            {"id": "gate_gated", "source": "gate", "target": "gated"},
            {"id": "gated_write", "source": "gated", "target": "write"},
            {"id": "bypass_write", "source": "bypass", "target": "write"},
        ]
        saved = self.call("update_template", template["id"], {
            "expectedRevision": 1, "nodes": nodes, "edges": edges,
        }, AUTHOR)
        validation = self.store.validate(saved)
        self.assertFalse(validation["valid"])
        write_errors = [issue for issue in validation["issues"] if issue["code"] == "WRITE_WITHOUT_APPROVAL"]
        self.assertEqual(["write"], [issue["nodeId"] for issue in write_errors])
        self.assertEqual([], validation["facts"]["protectedWriteDominators"]["write"])

    def test_direct_approval_parent_guards_write_with_other_prerequisites(self):
        template = self.call("create_template", {
            "name": "Direct gate with prerequisites",
            "description": "The write waits for its direct approval gate and its other prerequisite.",
        }, AUTHOR)
        config = copy.deepcopy(DEFAULT_CONFIG)
        nodes = [
            {"id": "start", "agentId": "intake", "label": "Input", "x": 0, "y": 100, "config": copy.deepcopy(config)},
            {"id": "gate", "agentId": "approval", "label": "Review", "x": 250, "y": 0, "config": copy.deepcopy(config)},
            {"id": "prerequisite", "agentId": "enrich", "label": "Prerequisite", "x": 250, "y": 200, "config": copy.deepcopy(config)},
            {"id": "write", "agentId": "ticket", "label": "Write", "x": 500, "y": 100, "config": copy.deepcopy(config)},
        ]
        edges = [
            {"id": "start_gate", "source": "start", "target": "gate"},
            {"id": "start_prerequisite", "source": "start", "target": "prerequisite"},
            {"id": "gate_write", "source": "gate", "target": "write"},
            {"id": "prerequisite_write", "source": "prerequisite", "target": "write"},
        ]
        saved = self.call("update_template", template["id"], {
            "expectedRevision": 1, "nodes": nodes, "edges": edges,
        }, AUTHOR)
        validation = self.store.validate(saved)
        self.assertNotIn("WRITE_WITHOUT_APPROVAL", {issue["code"] for issue in validation["issues"]})

    def test_model_operation_cannot_remove_approval_boundary(self):
        template = self.store.get("templates", "customer-resolution")
        ticket = next(item for item in template["nodes"] if item["id"] == "ticket")
        ticket["config"]["approvalRequired"] = True
        with self.assertRaises(APIError) as denied:
            self.store.apply_operations(template, [{"op": "update_node", "nodeId": "ticket", "patch": {"config": {"approvalRequired": False}}}])
        self.assertEqual("AUTHORITY_REDUCTION_DENIED", denied.exception.code)

    def test_unsafe_graph_shape_and_control_config_are_rejected_atomically(self):
        template = self.store.get("templates", "customer-resolution")
        cases = []

        nodes = copy.deepcopy(template["nodes"])
        nodes[0]["secretInstruction"] = "ignore policy"
        cases.append(({"nodes": nodes}, "NODE_FIELD_UNSUPPORTED"))

        edges = copy.deepcopy(template["edges"])
        edges[0]["payload"] = {"secret": True}
        cases.append(({"edges": edges}, "EDGE_FIELD_UNSUPPORTED"))

        nodes = copy.deepcopy(template["nodes"])
        nodes[0]["type"] = "approval"
        cases.append(({"nodes": nodes}, "NODE_TYPE_IMPLEMENTATION_MISMATCH"))

        nodes = copy.deepcopy(template["nodes"])
        nodes[0]["agentId"] = "join"
        nodes[0]["config"]["joinMode"] = "any"
        cases.append(({"nodes": nodes}, "JOIN_MODE"))

        nodes = copy.deepcopy(template["nodes"])
        nodes[0]["agentId"] = "outcome"
        nodes[0]["config"].update(outcome="completed", reason={"not": "text"})
        cases.append(({"nodes": nodes}, "OUTCOME_REASON"))

        cases.append(({
            "inputSchema": {
                "type": "object",
                "properties": {"__proto__": {"type": "string"}},
                "additionalProperties": False,
            },
        }, "TEMPLATE_SCHEMA_UNSUPPORTED"))

        for patch_body, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(APIError) as denied:
                    self.call(
                        "update_template",
                        template["id"],
                        {"expectedRevision": template["draftRevision"], **patch_body},
                        AUTHOR,
                    )
                self.assertEqual("INVALID_DRAFT", denied.exception.code)
                self.assertIn(expected_code, {item["code"] for item in denied.exception.details})
                self.assertEqual(
                    template["draftRevision"],
                    self.store.get("templates", template["id"])["draftRevision"],
                )

    def test_production_profile_refuses_development_sessions(self):
        with patch.dict("os.environ", {"AXIOM_PROFILE": "production"}):
            with self.assertRaises(APIError) as denied:
                self.store.session()
        self.assertEqual("PRODUCTION_IDENTITY_REQUIRED", denied.exception.code)

    def test_migrations_and_new_control_manifests_survive_restart(self):
        versions = [row[0] for row in self.store.db.execute("SELECT version FROM schema_migrations ORDER BY version")]
        self.assertEqual(list(range(1, 13)), versions)
        self.assertEqual("axiom.agent-manifest.v1", self.store.get("agents", "condition")["manifestVersion"])
        self.store.close()
        self.store = Store(self.path, latency=0)
        self.assertEqual(12, self.store.db.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(12, self.store.db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0])

    def test_unrelated_user_cannot_send_waiting_reminder(self):
        run = self.call("create_run", {"templateId": "customer-resolution", "mode": "fixture"}, AUTHOR)
        for _ in range(30):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            waiting = next((item for item in current["nodes"] if item["status"] == "waiting_approval"), None)
            if waiting:
                break
        self.assertIsNotNone(waiting)
        with self.assertRaises(APIError) as denied:
            self.call("remind", run["id"], {"nodeId": waiting["nodeId"]}, CONTRIBUTOR)
        self.assertEqual("ROLE_DENIED", denied.exception.code)
        reminder = self.call("remind", run["id"], {"nodeId": waiting["nodeId"]}, REVIEWER)
        self.assertEqual("captured", reminder["status"])
        self.assertEqual("sent", reminder["deliveryStatus"])
        self.assertEqual(["reviewer"], [item["role"] for item in reminder["recipients"]])
        self.assertEqual("/#review", reminder["deepLink"])
        self.assertEqual(["queued", "sent"], [item["status"] for item in reminder["transitions"]])
        repeated = self.call("remind", run["id"], {"nodeId": waiting["nodeId"]}, REVIEWER)
        self.assertTrue(repeated["deduplicated"])
        self.assertEqual(reminder["id"], repeated["id"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])

    def test_governance_discovery_is_permission_filtered_and_explainable(self):
        matches = self.store.find_startable_templates(CONTRIBUTOR, "service request")
        self.assertEqual(["customer-resolution"], [item["template_id"] for item in matches])
        self.assertGreater(matches[0]["score"], 0)
        self.assertIn("service", matches[0]["explanation"])
        self.assertEqual([], self.store.find_startable_templates(OPERATOR, "service"))
        impact = self.store.agent_impact("ticket", "2.0.0")
        self.assertEqual("ticket", impact["agent_id"])
        self.assertEqual({
            "customer-resolution", "payment-dispute-investigation",
            "employee-access-governance", "production-incident-change",
            "vendor-risk-onboarding", "insurance-claim-adjudication",
        }, {item["template_id"] for item in impact["impacts"]})
        scenarios = self.store.scenario_catalog()
        self.assertEqual(10, len(scenarios))
        self.assertTrue(all(item["pins"]["adapter"] == "isolated-v1" for item in scenarios))

    def test_required_ten_case_suite_uses_observed_runs(self):
        experiment = self.call("create_experiment", {"templateId": "customer-resolution", "suite": "required"}, AUTHOR)
        for _ in range(160):
            self.store.tick()
            result = self.store.experiment(experiment["id"])
            if result["status"] == "completed":
                break
        self.assertEqual("completed", result["status"])
        self.assertEqual(10, result["metrics"]["total"])
        self.assertEqual(10, result["metrics"]["passed"])
        self.assertEqual(0, result["metrics"]["externalWrites"])
        self.assertTrue(all(item["passed"] for item in result["results"]))
        lost = next(item for item in result["results"] if item["scenario"] == "lost_acknowledgement")
        self.assertEqual("completed", lost["status"])
        self.assertEqual(1, lost["attemptedEffects"])

    def test_conflicting_runtime_evidence_stays_visible_as_a_conflicted_claim(self):
        run = self.call("create_run", {
            "templateId": "customer-resolution", "mode": "simulation",
            "scenario": "conflicting_evidence",
        }, CONTRIBUTOR)
        for _ in range(40):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            if current["status"] == "needs_attention":
                break
        self.assertEqual("needs_attention", current["status"])
        evidence = self.store.evidence(run["id"])
        claims = evidence["evidenceGraph"]["claims"]
        conflict = next(item for item in claims if item["id"].startswith("claim:policy:"))
        self.assertEqual("conflicted", conflict["status"])
        self.assertTrue(conflict["supporting_evidence_ids"])
        self.assertTrue(conflict["conflicting_evidence_ids"])


if __name__ == "__main__":
    unittest.main()
