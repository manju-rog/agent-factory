import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factory_fixtures as fixtures
import agent_factory as kernel
from scripts.demo_agent_factory import run_scenario


class FactoryFixtureTests(unittest.TestCase):
    def test_catalog_contains_separate_contracts_for_reads_and_local_writes(self):
        catalog = fixtures.tool_catalog()
        self.assertEqual(len({t["id"] for t in catalog}), len(catalog))
        for tool in catalog:
            self.assertIn(tool["effect"], {"read", "write"})
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
            self.assertFalse(tool["outputSchema"]["additionalProperties"])
            self.assertEqual(tool["version"], "1.0.0")
            self.assertIn("scope", tool["authorization"])
            self.assertIn("adapterId", tool["adapterBinding"])
            self.assertIn("reconciliation", tool["idempotency"])
            self.assertTrue(tool["examples"])
            self.assertEqual(tool["verification"]["status"], "fixture-verified")
        catalog[0]["id"] = "changed"
        self.assertEqual(fixtures.tool_catalog()[0]["id"], "service.lookup")

    def test_record_facts_differ_without_changing_agent_contract(self):
        existing = fixtures.execute_read("service.lookup", {"requestId": "SR-EXISTING"})
        new = fixtures.execute_read("service.lookup", {"requestId": "SR-NEW"})
        self.assertTrue(existing["existingTicket"])
        self.assertFalse(new["existingTicket"])
        self.assertEqual(existing["summary"], new["summary"])
        existing["existingTicket"] = "tampered"
        self.assertNotEqual(fixtures.execute_read("service.lookup", {"requestId": "SR-EXISTING"})["existingTicket"], "tampered")

    def test_missing_record_is_an_error_not_invented_data(self):
        with self.assertRaisesRegex(ValueError, "No local fixture"):
            fixtures.execute_read("finance.inspect_invoice", {"invoiceId": "DOES-NOT-EXIST"})
        with self.assertRaisesRegex(ValueError, "No local fixture"):
            fixtures.execute_read("finance.lookup_policy", {"currency": "XYZ"})

    def test_fixture_argument_failures_are_typed_and_never_key_errors(self):
        for tool_id in ("service.lookup", "service.search_runbook", "finance.inspect_invoice",
                        "finance.lookup_policy", "access.inspect_request", "access.lookup_entitlements"):
            with self.subTest(tool=tool_id), self.assertRaises(fixtures.FixtureToolError) as raised:
                fixtures.execute_read(tool_id, {})
            self.assertEqual("FIXTURE_ARGUMENT_INVALID", raised.exception.code)

    def test_fixture_reader_cannot_execute_writes(self):
        with self.assertRaisesRegex(ValueError, "not a registered fixture read"):
            fixtures.execute_read("service.create_ticket", {})

    def test_write_result_is_stable_and_never_claims_external_effect(self):
        a = fixtures.prepare_write_result("service.create_ticket", {"summary": "Example"}, "same-key")
        b = fixtures.prepare_write_result("service.create_ticket", {"summary": "Example"}, "same-key")
        c = fixtures.prepare_write_result("service.create_ticket", {"summary": "Example"}, "different-key")
        self.assertEqual(a, b)
        self.assertNotEqual(a["recordId"], c["recordId"])
        self.assertTrue(a["capturedLocally"])
        self.assertTrue(a["fixture"])
        self.assertFalse(a["externalWrite"])
        with self.assertRaisesRegex(ValueError, "not a registered fixture write"):
            fixtures.prepare_write_result("finance.inspect_invoice", {}, "key")

    def test_same_three_agents_follow_different_observation_paths(self):
        runs = [run_scenario(case) for case in fixtures.scenarios()]
        for spec in fixtures.agent_specs():
            cases = [run for run in runs if run["agentId"] == spec["id"]]
            self.assertEqual(len(cases), 2)
            self.assertEqual(len({run["agentHash"] for run in cases}), 1)
            self.assertEqual(len({tuple(run["orderedToolTrace"]) for run in cases}), 2)
            self.assertTrue(all(run["status"] == "completed" for run in cases))
            self.assertTrue(all(run["externalEffectCount"] == 0 for run in cases))
        existing = next(run for run in runs if run["scenario"] == "service-existing")
        self.assertEqual(existing["orderedToolTrace"], ["service.lookup"])
        self.assertEqual(existing["localEffectCount"], 0)
        self.assertEqual(next(run for run in runs if run["scenario"] == "invoice-exception")["orderedToolTrace"][-1], "finance.request_review")
        self.assertEqual(next(run for run in runs if run["scenario"] == "access-privileged")["orderedToolTrace"][-1], "access.request_review")
        self.assertTrue(all(run["outcomeValidation"]["businessOutcomeVerified"] for run in runs))

    def test_controlled_behavior_variations_are_labeled_and_evidence_driven(self):
        variations = fixtures.behavior_variations()
        by_kind = {item["variationKind"]: item for item in variations}
        self.assertEqual(
            {
                "missing-evidence", "conflicting-records", "denied-capability",
                "unavailable-service", "unavailable-capability", "duplicate-operation",
                "changed-business-condition",
            },
            set(by_kind),
        )
        runs = {item["variationKind"]: run_scenario(item) for item in variations}

        missing = runs["missing-evidence"]
        self.assertEqual("completed", missing["status"])
        self.assertEqual(1, missing["clarificationCount"])
        self.assertEqual(["service.lookup"], missing["orderedToolTrace"])

        conflict = runs["conflicting-records"]
        self.assertEqual("stopped", conflict["status"])
        self.assertEqual("conflictingEvidence", conflict["boundaryOutcome"]["condition"])
        self.assertEqual(0, conflict["localEffectCount"])

        denied = runs["denied-capability"]
        self.assertEqual("stopped", denied["status"])
        self.assertEqual("deniedCapability", denied["boundaryOutcome"]["condition"])
        self.assertEqual(0, denied["localEffectCount"])

        unavailable_service = runs["unavailable-service"]
        self.assertEqual("completed", unavailable_service["status"])
        self.assertEqual("service_unavailable", unavailable_service["output"]["outcome"])
        self.assertEqual("unavailableService", unavailable_service["boundaryOutcome"]["condition"])
        self.assertEqual(0, unavailable_service["localEffectCount"])
        self.assertTrue(unavailable_service["outcomeValidation"]["businessOutcomeVerified"])

        unavailable_capability = runs["unavailable-capability"]
        self.assertEqual("completed", unavailable_capability["status"])
        self.assertEqual("capability_gap", unavailable_capability["output"]["outcome"])
        self.assertEqual(0, unavailable_capability["localEffectCount"])

        duplicate = runs["duplicate-operation"]
        self.assertEqual("completed", duplicate["status"])
        self.assertEqual(2, duplicate["writeAttemptCount"])
        self.assertEqual(1, duplicate["localEffectCount"])
        self.assertTrue(duplicate["duplicateOperationPrevented"])
        self.assertTrue(duplicate["outcomeValidation"]["businessOutcomeVerified"])

        changed = runs["changed-business-condition"]
        self.assertEqual("stopped", changed["status"])
        self.assertEqual("changedBusinessState", changed["boundaryOutcome"]["condition"])
        self.assertEqual(0, changed["localEffectCount"])
        self.assertTrue(all(run["externalEffectCount"] == 0 for run in runs.values()))

    def test_combined_demo_catalog_and_agent_evaluations_include_variations(self):
        stable = fixtures.scenarios()
        variations = fixtures.behavior_variations()
        combined = fixtures.demo_scenarios()
        self.assertEqual(len(stable) + len(variations), len(combined))
        self.assertEqual(len({item["id"] for item in combined}), len(combined))
        expected_ids = {item["id"] for item in combined}
        evaluation_ids = {case["id"] for spec in fixtures.agent_specs() for case in spec["evaluationCases"]}
        self.assertEqual(expected_ids, evaluation_ids)
        missing = next(item for item in combined if item["variationKind"] == "missing-evidence")
        self.assertEqual({"input.requestId": "SR-EXISTING"}, missing["resumeAnswers"])

    def test_outcome_validators_are_domain_owned_and_fail_closed(self):
        scenario = next(item for item in fixtures.scenarios() if item["id"] == "invoice-exception")
        run = run_scenario(scenario)
        self.assertEqual(run["outcomeValidation"]["status"], "satisfied")
        tampered = dict(run["state"])
        tampered["output"] = dict(run["state"]["output"], recordId="invented")
        validation = fixtures.validate_outcome("invoice-reviewer", tampered)
        self.assertEqual(validation["status"], "contradicted")
        self.assertFalse(validation["businessOutcomeVerified"])
        unknown = fixtures.validate_outcome("custom-domain", run["state"])
        self.assertEqual(unknown["status"], "unknown")

    def test_fixture_decision_uses_observation_not_scenario_name(self):
        spec = fixtures.agent_specs()[0]
        compiled = kernel.compile_agent(spec, fixtures.tool_catalog())
        state = kernel.create_state(compiled, {"requestId": "SR-EXISTING"})
        state = kernel.apply_decision(compiled, state, fixtures.fixture_decision(compiled, state), "scripted-fixture")
        observed = fixtures.execute_read("service.lookup", {"requestId": "SR-EXISTING"})
        observed["existingTicket"] = ""
        state = kernel.record_tool_result(compiled, state, observed)
        decision = fixtures.fixture_decision(compiled, state, scenario="service-existing")
        self.assertEqual(decision["toolId"], "service.search_runbook")

    def test_fixture_write_pauses_before_local_effect(self):
        scenario = next(item for item in fixtures.scenarios() if item["id"] == "service-new")
        run = run_scenario(scenario, pause_before_write=True)
        self.assertEqual(run["status"], "awaiting_approval")
        self.assertEqual(run["localEffectCount"], 0)
        self.assertEqual(run["state"]["pendingAction"]["toolId"], "service.create_ticket")

    def test_missing_id_asks_then_resumes_with_scoped_answer(self):
        spec = fixtures.agent_specs()[0]
        compiled = kernel.compile_agent(spec, fixtures.tool_catalog())
        state = kernel.create_state(compiled, {"requestId": ""})
        state = kernel.apply_decision(compiled, state, fixtures.fixture_decision(compiled, state), "scripted-fixture")
        self.assertEqual(state["status"], "awaiting_input")
        self.assertEqual(state["counters"]["toolCalls"], 0)
        state = kernel.supply_input(compiled, state, {"input.requestId": "SR-NEW"})
        decision = fixtures.fixture_decision(compiled, state)
        self.assertEqual(decision["toolId"], "service.lookup")

    def test_scripted_provider_does_not_pretend_to_handle_custom_agent(self):
        spec = fixtures.agent_specs()[0]
        spec["id"] = "my-custom-agent"
        compiled = kernel.compile_agent(spec, fixtures.tool_catalog())
        state = kernel.create_state(compiled, {"requestId": "SR-NEW"})
        with self.assertRaisesRegex(ValueError, "Configure a model"):
            fixtures.fixture_decision(compiled, state)

    def test_final_summary_follows_simulated_write_observation(self):
        specs = {item["id"]: item for item in fixtures.agent_specs()}
        for scenario in fixtures.scenarios():
            if scenario["id"] == "service-existing":
                continue
            with self.subTest(scenario=scenario["id"]):
                compiled = kernel.compile_agent(specs[scenario["specId"]], fixtures.tool_catalog())
                state = kernel.create_state(compiled, scenario["input"])
                for _ in range(20):
                    if state["status"] == "ready":
                        state = kernel.apply_decision(compiled, state, fixtures.fixture_decision(compiled, state), "scripted-fixture")
                    elif state["status"] == "awaiting_approval":
                        state = kernel.approve_action(compiled, state, True, "fixture-test", state["pendingAction"]["actionHash"])
                    elif state["status"] == "awaiting_tool":
                        action = kernel.executable_action(compiled, state)
                        if action["effect"] == "read":
                            output = fixtures.execute_read(action["toolId"], action["arguments"])
                        else:
                            output = fixtures.prepare_write_result(action["toolId"], action["arguments"], action["id"])
                            output.update(status="simulated", capturedLocally=False, recordId="SIM-" + output["recordId"])
                        state = kernel.record_tool_result(compiled, state, output)
                    else:
                        break
                self.assertEqual(state["status"], "completed")
                self.assertTrue(state["output"]["outcome"].endswith("_simulated"))
                self.assertIn("No local record was captured", state["output"]["summary"])
                self.assertTrue(state["output"]["recordId"].startswith("SIM-"))


if __name__ == "__main__":
    unittest.main()
