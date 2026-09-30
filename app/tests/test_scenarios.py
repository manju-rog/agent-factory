import unittest

from scenarios import (
    ScenarioError,
    ScenarioObservation,
    evaluate_scenario,
    paired_release_evaluation,
    required_scenarios,
    save_regression_case,
    validate_catalog,
)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {item.id: item for item in required_scenarios()}

    def observation(self, scenario_id, status, *, effects=(), path=("start", "end"), latency=10, run="run-1"):
        scenario = self.catalog[scenario_id]
        return ScenarioObservation(scenario.id, scenario.version, run, {"status": status}, tuple(effects), tuple(path), latency)

    def test_complete_catalog_is_versioned_and_isolated(self):
        validate_catalog(self.catalog.values())
        self.assertEqual(10, len(self.catalog))
        self.assertTrue(all(item.pins["adapter"] == "isolated-v1" for item in self.catalog.values()))
        self.assertTrue(self.catalog["malicious_content"].held_out)

    def test_completed_run_is_not_automatically_a_pass(self):
        result = evaluate_scenario(self.catalog["missing_input"], self.observation("missing_input", "completed"))
        self.assertFalse(result.passed)
        self.assertEqual("needs_attention", result.expected_final_state["status"])

    def test_known_answer_checks_effect_isolation_and_deduplication(self):
        effect = {"operationKey": "one", "external": False, "authorized": True}
        duplicate = self.observation("duplicate_callback", "completed", effects=(effect, effect))
        self.assertFalse(evaluate_scenario(self.catalog["duplicate_callback"], duplicate).passed)
        good = self.observation(
            "duplicate_callback", "completed", effects=(effect,),
            path=("start", "approval.duplicate_ignored", "end"),
        )
        self.assertTrue(evaluate_scenario(self.catalog["duplicate_callback"], good).passed)

    def test_paired_regression_blocks_promotion_even_when_faster(self):
        scenario = self.catalog["malicious_content"]
        allowed_effect = {"operationKey": "allowed", "external": False, "authorized": True}
        baseline = evaluate_scenario(scenario, self.observation("malicious_content", "completed", effects=(allowed_effect,), latency=50, run="before"))
        bad_effect = {"operationKey": "bad", "external": False, "authorized": False}
        candidate = evaluate_scenario(scenario, self.observation("malicious_content", "completed", effects=(bad_effect,), latency=1, run="after"))
        comparison = paired_release_evaluation([baseline], [candidate])
        self.assertFalse(comparison["passed"])
        self.assertLess(comparison["comparisons"][0]["latencyDeltaMs"], 0)
        self.assertIn("GOVERNANCE_REGRESSION", {issue["code"] for issue in comparison["blockingIssues"]})

    def test_failed_case_can_be_saved_as_regression(self):
        scenario = self.catalog["approval_expiry"]
        failed = evaluate_scenario(scenario, self.observation("approval_expiry", "completed", run="bad-run"))
        saved = save_regression_case(scenario, failed, title="Expiry incorrectly continued")
        self.assertEqual("bad-run", saved["sourceRunId"])
        with self.assertRaises(ScenarioError):
            save_regression_case(self.catalog["happy"], evaluate_scenario(self.catalog["happy"], self.observation("happy", "completed", effects=({"operationKey": "one", "external": False, "authorized": True},))), title="Not a failure")


if __name__ == "__main__":
    unittest.main()
