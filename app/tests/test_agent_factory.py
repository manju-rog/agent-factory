"""Generic agent tests. All models below are explicit test doubles, never AI."""
import copy
import io
import json
import unittest
from unittest.mock import patch

import agent_factory as af


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


TEXT = {"type": "string"}
NUMBER = {"type": "number"}


def capability(identifier, description, effect, input_properties, output_properties, bound=None):
    def example(schema):
        if "enum" in schema:
            return copy.deepcopy(schema["enum"][0])
        return {"string": "example", "number": 1.0, "integer": 1,
                "boolean": True, "array": [], "object": {}}[schema["type"]]

    contract = {
        "id": identifier, "version": "1.0.0", "description": description, "effect": effect,
        "inputSchema": obj(input_properties), "outputSchema": obj(output_properties),
        "semanticFields": {name: "Business meaning for " + name for name in input_properties},
        "authorization": {"scope": "test:" + identifier.split(".", 1)[0]},
        "adapterBinding": {"adapterId": "test-adapter", "adapterVersion": "1.0.0",
                           "operation": identifier, "transport": "in-process"},
        "idempotency": ({"classification": "safe-read", "retry": "bounded",
                         "reconciliation": "not-required"} if effect == "read" else
                        {"classification": "idempotent-write", "operationKey": "required",
                         "retry": "after-reconciliation", "reconciliation": "receipt-read"}),
        "examples": [{"label": "Valid contract example",
                      "input": {name: example(schema) for name, schema in input_properties.items()}}],
    }
    if bound:
        contract["boundArguments"] = bound
    return contract


def tools():
    return [
        capability("observatory.measure_focus", "Read a novel telescope calibration instrument.", "read",
                   {"instrumentId": TEXT}, {"offset": NUMBER, "needsCalibration": {"type": "boolean"}}),
        capability("observatory.lookup_standard", "Read the calibration standard after an unexpected measurement.", "read",
                   {"instrumentId": TEXT}, {"standard": NUMBER}),
        capability("observatory.capture_calibration", "Record an approved calibration proposal.", "write",
                   {"destination": TEXT, "offset": NUMBER}, {"recordId": TEXT},
                   {"destination": "input.destination"}),
    ]


def spec():
    return {"id": "focus-investigator", "version": 1, "name": "Focus investigator",
            "mission": "Investigate the supplied instrument; record a proposed calibration only when its measured focus requires one.",
            "instructions": "Cite measurements and ask for missing data.",
            "inputSchema": obj({"instrumentId": TEXT, "destination": TEXT, "privateToken": TEXT, "clarification": TEXT}, ["instrumentId", "destination"]),
            "outputSchema": obj({"summary": TEXT, "measurement": NUMBER}),
            "contextFields": ["input.instrumentId", "input.destination", "input.clarification"],
            "allowedTools": [tool["id"] for tool in tools()],
            "requiredEvidenceTools": ["observatory.measure_focus"],
            "limits": {"maxTurns": 7, "maxToolCalls": 5, "maxWriteCalls": 1}}


class ObservationConditionedTestModel:
    """Scripted verification double: next action depends on supplied observations."""
    label = "scripted-test-provider-not-ai"
    def __init__(self):
        self.calls = []

    def complete(self, messages, response_schema):
        data = json.loads(messages[-1]["content"])
        self.calls.append(copy.deepcopy(data))
        observations = data["observations"]
        if not observations:
            return {"kind": "call", "toolId": "observatory.measure_focus", "arguments": {"instrumentId": {"$ref": "input.instrumentId"}}}
        first = observations["call_0001"]
        if first.get("error"):
            return {"kind": "ask", "question": "The instrument read failed; provide diagnostic context.", "fields": ["input.clarification"]}
        if first["needsCalibration"] and len(observations) == 1:
            return {"kind": "call", "toolId": "observatory.lookup_standard", "arguments": {"instrumentId": {"$ref": "input.instrumentId"}}}
        if first["needsCalibration"] and len(observations) == 2:
            return {"kind": "call", "toolId": "observatory.capture_calibration", "arguments": {"offset": {"$ref": "facts.call_0001.offset"}}}
        return {"kind": "finish", "output": {"summary": "Measurement observed; any proposal was reviewed.", "measurement": {"$ref": "facts.call_0001.offset"}},
                "evidence": ["facts.call_0001.offset"]}


class SingleResponseTestModel:
    label = "scripted-test-provider-not-ai"
    def __init__(self, response):
        self.response = response

    def complete(self, messages, response_schema):
        return copy.deepcopy(self.response)


class AgentFactoryTests(unittest.TestCase):
    def setUp(self):
        self.compiled = af.compile_agent(spec(), tools())
        self.state = af.create_state(self.compiled, {"instrumentId": "TEL-42", "destination": "lab-journal", "privateToken": "DO_NOT_EXPOSE"})

    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(af.AgentError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def measure(self, offset=0.1, needs=False):
        model = ObservationConditionedTestModel()
        state = af.advance(self.compiled, self.state, model)
        self.assertEqual(af.executable_action(self.compiled, state)["toolId"], "observatory.measure_focus")
        return af.record_tool_result(self.compiled, state, {"offset": offset, "needsCalibration": needs}), model

    def pending_write(self):
        return af.apply_decision(self.compiled, self.state, {"kind": "call", "toolId": "observatory.capture_calibration", "arguments": {"offset": 4.2}})

    def test_novel_registered_tools_run_without_domain_engine_branches(self):
        state, model = self.measure()
        state = af.advance(self.compiled, state, model)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["output"]["measurement"], 0.1)
        self.assertEqual(state["provider"], "scripted-test-provider-not-ai")
        self.assertFalse(state["completionCheck"]["businessOutcomeVerified"])
        self.assertEqual(state["evidence"], [{"source": "facts.call_0001.offset", "value": 0.1}])

    def test_actual_observation_changes_next_action_in_same_agent(self):
        ordinary, ordinary_model = self.measure(0.1, False)
        unexpected, unexpected_model = self.measure(4.2, True)
        finished = af.advance(self.compiled, ordinary, ordinary_model)
        investigating = af.advance(self.compiled, unexpected, unexpected_model)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(investigating["pendingAction"]["toolId"], "observatory.lookup_standard")
        self.assertEqual(unexpected_model.calls[-1]["observations"]["call_0001"]["offset"], 4.2)
        investigating = af.record_tool_result(self.compiled, investigating, {"standard": 0.0})
        proposed = af.advance(self.compiled, investigating, unexpected_model)
        self.assertEqual(proposed["status"], "awaiting_approval")
        self.assertEqual(proposed["pendingAction"]["arguments"], {"offset": 4.2, "destination": "lab-journal"})
        approved = af.approve_action(self.compiled, proposed, True, "reviewer-1", proposed["pendingAction"]["actionHash"])
        action = af.executable_action(self.compiled, approved)
        self.assertEqual(action["effect"], "write")
        observed = af.record_tool_result(self.compiled, approved, {"recordId": "CAPTURE-9"})
        final = af.advance(self.compiled, observed, unexpected_model)
        self.assertEqual(final["status"], "completed")
        self.assertIn("call_0003", unexpected_model.calls[-1]["observations"])

    def test_factory_uses_provider_generated_spec_and_does_not_save_it(self):
        response = spec()
        response.update(id="novel-lab-agent", mission="Investigate another instrument using the registered contracts.")
        result = af.propose_agent("Make an instrument investigator", tools(), SingleResponseTestModel(response))
        self.assertEqual(result["spec"]["id"], "novel-lab-agent")
        self.assertTrue(result["requiresReview"])
        self.assertFalse(result["saved"])
        self.assertEqual(result["provider"], "scripted-test-provider-not-ai")

    def test_missing_model_has_no_fake_ai_fallback(self):
        result = af.advance(self.compiled, self.state, None)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "MODEL_NOT_CONFIGURED")
        self.assertEqual(result["facts"], {})
        self.assert_error("MODEL_NOT_CONFIGURED", af.propose_agent, "Build something", tools(), None)

    def test_minimal_projection_excludes_unselected_fields_every_turn(self):
        self.assertNotIn("privateToken", self.state["input"])
        self.assertNotIn("DO_NOT_EXPOSE", str(af.model_messages(self.compiled, self.state)))
        self.assert_error("MISSING_REFERENCE", af.apply_decision, self.compiled, self.state,
                          {"kind": "call", "toolId": "observatory.measure_focus", "arguments": {"instrumentId": {"$ref": "input.privateToken"}}})

    def test_model_observations_include_exact_tool_and_arguments_without_full_history(self):
        registry = tools()
        alternate = copy.deepcopy(registry[0])
        alternate["id"] = "observatory.measure_backup"
        registry.append(alternate)
        definition = spec()
        definition["allowedTools"].append(alternate["id"])
        compiled = af.compile_agent(definition, registry)
        state = af.create_state(compiled, {"instrumentId": "TEL-42", "destination": "lab-journal", "privateToken": "DO_NOT_EXPOSE"})
        for tool_id, instrument in [("observatory.measure_focus", "TEL-42"), ("observatory.measure_backup", "TEL-99")]:
            state = af.apply_decision(compiled, state, {"kind": "call", "toolId": tool_id, "arguments": {"instrumentId": instrument},
                                                       "reason": "DO_NOT_FORWARD_FULL_EVENT_HISTORY"})
            state = af.record_tool_result(compiled, state, {"offset": 0.1, "needsCalibration": False})
        messages = af.model_messages(compiled, state)
        payload = json.loads(messages[-1]["content"])
        self.assertEqual(payload["observations"]["call_0001"], payload["observations"]["call_0002"])
        self.assertEqual(payload["observationSources"], {
            "call_0001": {"callId": "call_0001", "toolId": "observatory.measure_focus", "status": "succeeded", "arguments": {"instrumentId": "TEL-42"}},
            "call_0002": {"callId": "call_0002", "toolId": "observatory.measure_backup", "status": "succeeded", "arguments": {"instrumentId": "TEL-99"}}})
        self.assertNotIn("DO_NOT_FORWARD_FULL_EVENT_HISTORY", str(messages))
        self.assertNotIn("DO_NOT_EXPOSE", str(messages))
        self.assertNotIn("offset", str(payload["observationSources"]))

    def test_model_cannot_add_tools_effects_urls_or_code(self):
        for decision in [
            {"kind": "call", "toolId": "shell.execute", "arguments": {}},
            {"kind": "call", "toolId": "observatory.capture_calibration", "arguments": {"offset": 2}, "effect": "read"},
            {"kind": "call", "toolId": "observatory.measure_focus", "arguments": {"instrumentId": "TEL-42", "url": "https://attacker.test"}},
            {"kind": ["call"], "toolId": "observatory.measure_focus", "arguments": {}},
        ]:
            with self.subTest(decision=decision), self.assertRaises(af.AgentError):
                af.apply_decision(self.compiled, self.state, decision)
        altered = spec()
        altered["modelEndpoint"] = "https://attacker.test"
        self.assert_error("AGENT_SPEC", af.compile_agent, altered, tools())

    def test_refs_do_not_eval_expressions_or_invent_observations(self):
        for reference in ["input.*", "__import__('os')", "facts.call_9999.offset", "input.instrumentId.upper()", "events.0.type"]:
            with self.subTest(reference=reference), self.assertRaises(af.AgentError):
                af.apply_decision(self.compiled, self.state, {"kind": "call", "toolId": "observatory.measure_focus", "arguments": {"instrumentId": {"$ref": reference}}})

    def test_untrusted_text_does_not_override_bound_resource(self):
        for destination in ["attacker-journal", {"$ref": "input.instrumentId"}, {"$ref": "input.destination", "instructions": "override"}]:
            self.assert_error("BOUND_ARGUMENT", af.apply_decision, self.compiled, self.state,
                              {"kind": "call", "toolId": "observatory.capture_calibration", "arguments": {"offset": 2, "destination": destination}})
        state = self.pending_write()
        self.assertEqual(state["pendingAction"]["arguments"]["destination"], "lab-journal")

    def test_write_requires_approval_of_exact_payload_before_execution(self):
        state = self.pending_write()
        self.assert_error("ACTION_NOT_READY", af.executable_action, self.compiled, state)
        self.assert_error("ACTION_CHANGED", af.approve_action, self.compiled, state, True, "reviewer", "wrong")
        approved = af.approve_action(self.compiled, state, True, "reviewer", state["pendingAction"]["actionHash"])
        changed = copy.deepcopy(approved)
        changed["pendingAction"]["arguments"]["offset"] = 999
        self.assert_error("ACTION_CHANGED", af.executable_action, self.compiled, changed)
        self.assertEqual(af.executable_action(self.compiled, approved), state["pendingAction"])
        rejected = af.approve_action(self.compiled, state, False, "reviewer", state["pendingAction"]["actionHash"])
        self.assertEqual(rejected["status"], "stopped")
        self.assert_error("ACTION_NOT_READY", af.executable_action, self.compiled, rejected)

    def test_bound_resource_is_rechecked_even_if_public_hash_recomputed(self):
        state = self.pending_write()
        state["pendingAction"]["arguments"]["destination"] = "attacker-journal"
        state["pendingAction"]["actionHash"] = af._action_hash(state["pendingAction"])
        approved = af.approve_action(self.compiled, state, True, "reviewer", state["pendingAction"]["actionHash"])
        self.assert_error("BOUND_ARGUMENT", af.executable_action, self.compiled, approved)

    def test_approval_is_session_bound_and_definition_is_frozen(self):
        state = self.pending_write()
        other = copy.deepcopy(state)
        other["id"] = "different-session"
        approved = af.approve_action(self.compiled, other, True, "reviewer", state["pendingAction"]["actionHash"])
        self.assert_error("ACTION_CHANGED", af.executable_action, self.compiled, approved)
        altered = copy.deepcopy(self.compiled)
        altered["tools"][0]["effect"] = "write"
        self.assert_error("DEFINITION_CHANGED", af.model_messages, altered, self.state)

    def test_budgets_stop_model_and_tool_loops(self):
        short = spec()
        short["limits"].update(maxTurns=1, maxToolCalls=1)
        compiled = af.compile_agent(short, tools())
        state = af.create_state(compiled, {"instrumentId": "TEL-42", "destination": "lab"})
        model = ObservationConditionedTestModel()
        state = af.advance(compiled, state, model)
        state = af.record_tool_result(compiled, state, {"offset": 4.2, "needsCalibration": True})
        state = af.advance(compiled, state, model)
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(state["error"]["code"], "TURN_BUDGET")
        self.assertEqual(len(model.calls), 1)
        no_tools = spec()
        no_tools["limits"].update(maxToolCalls=0)
        compiled = af.compile_agent(no_tools, tools())
        state = af.create_state(compiled, {"instrumentId": "TEL-42", "destination": "lab"})
        self.assertEqual(af.advance(compiled, state, model)["error"]["code"], "TOOL_BUDGET")

    def test_host_caps_are_not_model_overridable(self):
        excessive = spec()
        excessive["limits"]["maxTurns"] = 100000
        self.assert_error("AGENT_LIMIT", af.compile_agent, excessive, tools())
        self.assert_error("AGENT_LIMIT", af.compile_agent, spec(), tools(), {"maxToolCalls": 1})

    def test_provider_usage_and_business_boundaries_are_frozen_and_budgeted(self):
        definition = spec()
        definition.update(
            stopRules={"deniedCapability": "escalate", "budgetExhausted": "stop"},
            policyRefs=["calibration-policy:v3"],
            evaluationCases=[{"id": "nominal", "description": "Nominal reading",
                              "input": {"instrumentId": "TEL-42"},
                              "expectedState": {"completed": True}}],
        )
        definition["limits"].update(maxModelTokens=12, maxEstimatedCostMicros=9)
        compiled = af.compile_agent(definition, tools())
        state = af.create_state(compiled, {"instrumentId": "TEL-42", "destination": "lab"})
        decision = {"kind": "call", "toolId": "observatory.measure_focus",
                    "arguments": {"instrumentId": {"$ref": "input.instrumentId"}}}
        state = af.apply_decision(
            compiled, state, decision, "controlled-provider",
            {"responseId": "resp-1", "model": "controlled", "promptTokens": 4,
             "completionTokens": 2, "totalTokens": 6, "estimatedCostMicros": 4,
             "costKnown": True},
        )
        self.assertEqual(state["counters"]["modelTokens"], 6)
        self.assertEqual(state["counters"]["estimatedCostMicros"], 4)
        self.assertTrue(state["usage"]["costKnown"])
        self.assertEqual(compiled["spec"]["stopRules"]["deniedCapability"], "escalate")
        state = af.record_tool_result(compiled, state, {"offset": 0.1, "needsCalibration": False})
        self.assert_error(
            "MODEL_TOKEN_BUDGET", af.apply_decision, compiled, state,
            {"kind": "finish", "output": {"summary": "done", "measurement": 0.1},
             "evidence": ["facts.call_0001.offset"]}, "controlled-provider",
            {"totalTokens": 7, "estimatedCostMicros": 1, "costKnown": True},
        )

    def test_configured_provider_without_usage_is_conservatively_debited(self):
        state = af.apply_decision(
            self.compiled, self.state,
            {"kind": "ask", "question": "What diagnostic detail is missing?",
             "fields": ["input.clarification"]},
            "configured-model:no-usage", {"model": "no-usage"},
        )
        self.assertGreater(state["counters"]["modelTokens"], 0)
        self.assertGreater(state["counters"]["estimatedCostMicros"], 0)
        self.assertFalse(state["usage"]["costKnown"])
        usage = state["usage"]["providerResponses"][-1]
        self.assertTrue(usage["usageEstimated"])
        self.assertIn("host-utf8-byte-upper-bound", usage["accountingBasis"])
        zero_budget = spec()
        zero_budget["limits"]["maxEstimatedCostMicros"] = 0
        compiled = af.compile_agent(zero_budget, tools())
        initial = af.create_state(compiled, {"instrumentId": "TEL-42", "destination": "lab"})
        self.assert_error(
            "MODEL_COST_BUDGET", af.apply_decision, compiled, initial,
            {"kind": "ask", "question": "What diagnostic detail is missing?",
             "fields": ["input.clarification"]}, "configured-model:no-usage", {"model": "no-usage"})

    def test_chat_provider_estimates_missing_usage_instead_of_calling_it_free(self):
        body = json.dumps({"id": "response-1", "model": "local-model", "choices": [{"message": {
            "content": json.dumps({"kind": "ask", "question": "What detail is missing?",
                                   "fields": ["input.clarification"]})}}]}).encode()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        class Opener:
            def open(self, _request, timeout):
                self.timeout = timeout
                return Response(body)

        provider = af.ChatCompletionProvider("http://127.0.0.1:9999/chat/completions", "local-model")
        with patch.object(af.urllib.request, "build_opener", return_value=Opener()), patch.dict(af.os.environ, {}, clear=True):
            decision = provider.complete([{"role": "user", "content": "Choose one action."}], {})
        self.assertEqual(decision["kind"], "ask")
        self.assertTrue(provider.last_metadata["usageEstimated"])
        self.assertGreater(provider.last_metadata["totalTokens"], 0)
        self.assertGreater(provider.last_metadata["estimatedCostMicros"], 0)
        self.assertFalse(provider.last_metadata["costKnown"])

    def test_deadline_applies_to_approvals_and_pre_execution(self):
        state = self.pending_write()
        with patch.object(af.time, "time", return_value=state["createdAt"] + 9999):
            self.assert_error("DEADLINE_EXCEEDED", af.approve_action, self.compiled, state, True, "reviewer", state["pendingAction"]["actionHash"])
        approved = af.approve_action(self.compiled, state, True, "reviewer", state["pendingAction"]["actionHash"])
        with patch.object(af.time, "time", return_value=state["createdAt"] + 9999):
            self.assert_error("DEADLINE_EXCEEDED", af.executable_action, self.compiled, approved)
        awaiting = af.apply_decision(self.compiled, self.state, {
            "kind": "ask", "question": "What did you observe?", "fields": ["input.clarification"]})
        with patch.object(af.time, "time", return_value=awaiting["createdAt"] + 9999):
            self.assert_error("DEADLINE_EXCEEDED", af.supply_input, self.compiled, awaiting,
                              {"input.clarification": "Too late"})

    def test_failed_read_becomes_observation_for_adaptive_next_turn(self):
        model = ObservationConditionedTestModel()
        state = af.advance(self.compiled, self.state, model)
        state = af.record_tool_error(self.compiled, state, "SENSOR_OFFLINE", "Instrument did not respond", True)
        self.assertEqual(state["factSources"]["call_0001"]["status"], "failed")
        source = json.loads(af.model_messages(self.compiled, state)[-1]["content"])["observationSources"]["call_0001"]
        self.assertEqual(source, {"callId": "call_0001", "toolId": "observatory.measure_focus", "status": "failed", "arguments": {"instrumentId": "TEL-42"}})
        state = af.advance(self.compiled, state, model)
        self.assertEqual(state["status"], "awaiting_input")
        self.assertIn("error", model.calls[-1]["observations"]["call_0001"])

    def test_classified_tool_errors_enforce_stop_and_escalation_rules(self):
        cases = [("stop", "SENSOR_OFFLINE", None, "AGENT_BOUNDARY_STOPPED"),
                 ("escalate", "ADAPTER_REJECTED", "deniedCapability", "AGENT_ESCALATION_REQUIRED")]
        for action, code, condition, expected_code in cases:
            with self.subTest(action=action):
                definition = spec()
                definition["stopRules"] = {"unavailableService" if action == "stop" else "deniedCapability": action}
                compiled = af.compile_agent(definition, tools())
                state = af.create_state(compiled, {"instrumentId": "TEL-42", "destination": "lab"})
                state = af.apply_decision(compiled, state, {
                    "kind": "call", "toolId": "observatory.measure_focus",
                    "arguments": {"instrumentId": {"$ref": "input.instrumentId"}}})
                state = af.record_tool_error(compiled, state, code, "Sanitized adapter failure", True, condition)
                self.assertEqual(state["status"], "stopped")
                self.assertEqual(state["error"]["code"], expected_code)
                self.assertEqual(state["boundaryOutcome"]["action"], action)
                self.assertEqual(state["factSources"]["call_0001"]["status"], "failed")

    def test_unknown_write_effect_requires_reconciliation_not_blind_model_retry(self):
        state = self.pending_write()
        state = af.approve_action(self.compiled, state, True, "reviewer", state["pendingAction"]["actionHash"])
        result = af.record_tool_error(self.compiled, state, "TIMEOUT", "Write response was lost", True)
        self.assertEqual(result["error"]["code"], "WRITE_NEEDS_RECONCILIATION")
        self.assertNotEqual(result["status"], "ready")
        self.assertIsNotNone(result["pendingAction"])

    def test_known_undispatched_write_failure_is_observable_and_adaptable(self):
        state = self.pending_write()
        state = af.approve_action(
            self.compiled, state, True, "reviewer",
            state["pendingAction"]["actionHash"],
        )
        result = af.record_tool_error(
            self.compiled, state, "EXTERNAL_WRITE_SUPPRESSED",
            "Simulation policy prevented dispatch.", False,
            outcome_unknown=False,
        )
        self.assertEqual("ready", result["status"])
        self.assertIsNone(result["pendingAction"])
        error = result["facts"]["call_0001"]["error"]
        self.assertFalse(error["outcomeUnknown"])
        self.assertEqual("EXTERNAL_WRITE_SUPPRESSED", error["code"])

    def test_second_write_rechecks_reads_without_treating_prior_write_receipts_as_reads(self):
        registry = [
            capability("record.read", "Read one mutable record.", "read",
                       {"recordId": TEXT}, {"version": NUMBER}),
            capability("record.write", "Write one reviewed record change.", "write",
                       {"recordId": TEXT, "value": NUMBER}, {"receiptId": TEXT}),
        ]
        definition = {
            "id": "two-write-agent", "version": 1, "name": "Two write agent",
            "mission": "Read one record and prepare two separately reviewed updates.",
            "inputSchema": obj({"recordId": TEXT}),
            "outputSchema": obj({"summary": TEXT}),
            "contextFields": ["input.recordId"],
            "allowedTools": [item["id"] for item in registry],
            "limits": {"maxTurns": 8, "maxToolCalls": 4, "maxWriteCalls": 2},
        }
        compiled = af.compile_agent(definition, registry)
        state = af.create_state(compiled, {"recordId": "R-1"})
        state = af.apply_decision(compiled, state, {
            "kind": "call", "toolId": "record.read", "arguments": {"recordId": "R-1"},
        })
        state = af.record_tool_result(compiled, state, {"version": 1})
        read_hash = state["factSources"]["call_0001"]["resultHash"]

        state = af.apply_decision(compiled, state, {
            "kind": "call", "toolId": "record.write",
            "arguments": {"recordId": "R-1", "value": 2},
        })
        state = af.approve_action(
            compiled, state, True, "reviewer", state["pendingAction"]["actionHash"]
        )
        state = af.record_tool_result(compiled, state, {"receiptId": "W-1"})

        state = af.apply_decision(compiled, state, {
            "kind": "call", "toolId": "record.write",
            "arguments": {"recordId": "R-1", "value": 3},
            "evidence": ["facts.call_0001.version"],
        })
        self.assertEqual({"call_0001": read_hash}, state["pendingAction"]["sourceVersions"])
        self.assertNotIn("call_0002", state["pendingAction"]["sourceVersions"])

    def test_write_evidence_must_name_an_existing_exact_observation(self):
        registry = [
            capability("record.read", "Read one mutable record.", "read",
                       {"recordId": TEXT}, {"version": NUMBER}),
            capability("record.write", "Write one reviewed record change.", "write",
                       {"recordId": TEXT, "value": NUMBER}, {"receiptId": TEXT}),
        ]
        definition = {
            "id": "evidence-bound-write-agent", "version": 1,
            "name": "Evidence-bound write agent",
            "mission": "Read one record and prepare an evidence-bound update.",
            "inputSchema": obj({"recordId": TEXT}),
            "outputSchema": obj({"summary": TEXT}),
            "contextFields": ["input.recordId"],
            "allowedTools": [item["id"] for item in registry],
            "limits": {"maxTurns": 4, "maxToolCalls": 3, "maxWriteCalls": 1},
        }
        compiled = af.compile_agent(definition, registry)
        state = af.create_state(compiled, {"recordId": "R-1"})
        state = af.apply_decision(compiled, state, {
            "kind": "call", "toolId": "record.read",
            "arguments": {"recordId": "R-1"},
        })
        state = af.record_tool_result(compiled, state, {"version": 1})

        self.assert_error(
            "MISSING_REFERENCE", af.apply_decision, compiled, state,
            {
                "kind": "call", "toolId": "record.write",
                "arguments": {"recordId": "R-1", "value": 2},
                "evidence": ["facts.call_9999.version"],
            },
        )
        prepared = af.apply_decision(
            compiled, state,
            {
                "kind": "call", "toolId": "record.write",
                "arguments": {"recordId": "R-1", "value": 2},
                "evidence": ["facts.call_0001.version"],
            },
        )
        changed = copy.deepcopy(prepared)
        changed["pendingAction"]["evidenceRefs"] = ["facts.call_9999.version"]
        self.assert_error(
            "ACTION_CHANGED", af.approve_action, compiled, changed, True,
            "reviewer", prepared["pendingAction"]["actionHash"],
        )
        rehashed = copy.deepcopy(prepared)
        rehashed["pendingAction"]["evidenceRefs"] = [
            "facts.call_9999.version"
        ]
        rehashed["pendingAction"]["sourceVersions"] = {}
        rehashed["pendingAction"]["actionHash"] = af._action_hash(
            rehashed["pendingAction"]
        )
        rehashed = af.approve_action(
            compiled, rehashed, True, "reviewer",
            rehashed["pendingAction"]["actionHash"],
        )
        self.assert_error(
            "ACTION_CHANGED", af.executable_action, compiled, rehashed
        )

    def test_missing_input_is_requested_and_supplied_only_in_declared_scope(self):
        state = af.apply_decision(self.compiled, self.state, {"kind": "ask", "question": "What did you observe?", "fields": ["input.clarification"]})
        self.assert_error("INPUT_SCOPE", af.supply_input, self.compiled, state, {"input.privateToken": "anything"})
        result = af.supply_input(self.compiled, state, {"input.clarification": "Instrument was powered off."})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["input"]["clarification"], "Instrument was powered off.")
        self.assertNotIn("clarification", self.state["input"])

    def test_clarification_cannot_switch_resource_after_observation(self):
        registry = [
            capability("resource.observe", "Read one scoped resource.", "read",
                       {"resourceId": TEXT}, {"resourceId": TEXT, "value": TEXT},
                       {"resourceId": "input.resourceId"}),
            capability("resource.record", "Record a proposal for the same scoped resource.", "write",
                       {"resourceId": TEXT, "value": TEXT}, {"recordId": TEXT},
                       {"resourceId": "input.resourceId"}),
        ]
        definition = {"id": "resource-agent", "version": 1, "name": "Resource agent",
                      "mission": "Observe one resource and prepare a proposal for that same resource.",
                      "inputSchema": obj({"resourceId": TEXT}),
                      "outputSchema": obj({"summary": TEXT}),
                      "contextFields": ["input.resourceId"],
                      "allowedTools": [tool["id"] for tool in registry], "limits": {}}
        compiled = af.compile_agent(definition, registry)
        state = af.create_state(compiled, {"resourceId": "RESOURCE-A"})
        state = af.apply_decision(compiled, state, {"kind": "call", "toolId": "resource.observe",
                                                    "arguments": {}})
        state = af.record_tool_result(compiled, state, {"resourceId": "RESOURCE-A", "value": "observed"})
        self.assert_error("INPUT_ALREADY_BOUND", af.apply_decision, compiled, state,
                          {"kind": "ask", "question": "Use another resource?", "fields": ["input.resourceId"]})

        forged = copy.deepcopy(state)
        forged.update(status="awaiting_input", question="Use another resource?",
                      requestedFields=["input.resourceId"])
        self.assert_error("INPUT_ALREADY_BOUND", af.supply_input, compiled, forged,
                          {"input.resourceId": "RESOURCE-B"})
        self.assertEqual(state["input"]["resourceId"], "RESOURCE-A")

    def test_finish_validates_schema_actual_evidence_and_required_tool(self):
        self.assert_error("EVIDENCE_POLICY", af.apply_decision, self.compiled, self.state,
                          {"kind": "finish", "output": {"summary": "Done", "measurement": 0}, "evidence": ["input.instrumentId"]})
        state, _ = self.measure()
        for output, evidence in [({"summary": "Missing number"}, ["facts.call_0001.offset"]),
                                 ({"summary": "Done", "measurement": 0}, []),
                                 ({"summary": "Done", "measurement": 0}, ["facts.call_9999.offset"])]:
            with self.subTest(output=output, evidence=evidence), self.assertRaises(af.AgentError):
                af.apply_decision(self.compiled, state, {"kind": "finish", "output": output, "evidence": evidence})

    def test_unsupported_schemas_fail_instead_of_ignoring_constraints(self):
        for modification in [ {"pattern": ".*"}, {"type": ["string", "null"]}, {"$ref": "https://remote.test/schema"}, {"type": "object", "additionalProperties": True}]:
            invalid = spec()
            invalid["outputSchema"] = modification
            self.assert_error("UNSUPPORTED_SCHEMA", af.compile_agent, invalid, tools())

    def test_capability_contract_is_complete_and_object_typed(self):
        invalid_registries = []
        for field in ("version", "description", "semanticFields", "authorization",
                      "adapterBinding", "idempotency", "examples"):
            registry = tools()
            registry[0].pop(field)
            invalid_registries.append(("missing-" + field, registry))
        registry = tools()
        registry[0]["outputSchema"] = TEXT
        invalid_registries.append(("scalar-output", registry))
        registry = tools()
        registry[0]["semanticFields"] = {}
        invalid_registries.append(("unmapped-input", registry))
        registry = tools()
        registry[0]["examples"][0]["input"] = {"instrumentId": 7}
        invalid_registries.append(("invalid-example", registry))
        for label, registry in invalid_registries:
            with self.subTest(label=label):
                self.assert_error("TOOL_REGISTRY", af.compile_agent, spec(), registry)

    def test_state_roundtrip_and_registry_edits_preserve_prepared_action(self):
        state = self.pending_write()
        serialized = json.loads(json.dumps(state))
        self.assertEqual(serialized, state)
        original_tools = tools()
        compiled = af.compile_agent(spec(), original_tools)
        original_tools[0]["description"] = "Changed registry after compile"
        self.assertEqual(compiled["agentHash"], self.compiled["agentHash"])
        self.assertEqual(compiled["tools"][0]["description"], self.compiled["tools"][0]["description"])

    def test_malformed_model_response_fails_visibly_without_any_action(self):
        result = af.advance(self.compiled, self.state, SingleResponseTestModel("```json not a json object```"))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "MODEL_RESPONSE")
        self.assertIsNone(result["pendingAction"])

    def test_provider_requires_host_configuration_and_disallows_remote_plain_http(self):
        with patch.dict(af.os.environ, {}, clear=True):
            self.assert_error("MODEL_NOT_CONFIGURED", af.ChatCompletionProvider.from_environment)
        self.assert_error("MODEL_CONFIGURATION", af.ChatCompletionProvider, "http://remote.test/api", "model")
        self.assert_error("MODEL_CONFIGURATION", af.ChatCompletionProvider, "https://user:secret@remote.test/api", "model")
        local = af.ChatCompletionProvider("http://127.0.0.1:9999/chat/completions", "local-model")
        self.assertEqual(local.label, "configured-model:local-model")


if __name__ == "__main__":
    unittest.main()
