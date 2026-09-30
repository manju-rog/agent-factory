#!/usr/bin/env python3
"""Run paired paths and controlled variations through one generic agent kernel.

This test harness automatically approves local fixture writes only. It does not
use a model, contact services or persist business records. The app's server adds
durable sessions, review decisions and an idempotent local-effect ledger.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_factory as kernel
import factory_fixtures as fixtures


def run_scenario(scenario, pause_before_write=False):
    spec = next(item for item in fixtures.agent_specs() if item["id"] == scenario["specId"])
    compiled = kernel.compile_agent(spec, fixtures.tool_catalog())
    state = kernel.create_state(compiled, scenario["input"])
    local_effects = {}
    clarification_count = 0
    write_attempt_count = 0
    duplicate_operation_prevented = False
    for _ in range(32):
        if state["status"] == "ready":
            decision = fixtures.fixture_decision(compiled, state, scenario["id"])
            state = kernel.apply_decision(compiled, state, decision, "scripted-fixture")
        elif state["status"] == "awaiting_approval":
            if pause_before_write:
                break
            state = kernel.approve_action(compiled, state, True, "local-fixture-test-harness",
                                          state["pendingAction"]["actionHash"])
        elif state["status"] == "awaiting_input":
            answers = scenario.get("resumeAnswers")
            if not isinstance(answers, dict) or not answers:
                break
            state = kernel.supply_input(compiled, state, answers)
            clarification_count += 1
        elif state["status"] == "awaiting_tool":
            action = kernel.executable_action(compiled, state)
            try:
                if action["effect"] == "read":
                    result = fixtures.execute_read(action["toolId"], action["arguments"])
                else:
                    operation_key = action["operationKey"]
                    result = fixtures.prepare_write_result(action["toolId"], action["arguments"], operation_key)
                    write_attempt_count += 1
                    local_effects[operation_key] = {"actionHash": action["actionHash"], "output": result}
                    if scenario.get("duplicateWriteReplay"):
                        replay = fixtures.prepare_write_result(action["toolId"], action["arguments"], operation_key)
                        write_attempt_count += 1
                        duplicate_operation_prevented = replay == result and len(local_effects) == 1
                        if not duplicate_operation_prevented:
                            raise RuntimeError("The controlled duplicate operation did not reconcile to one stable local receipt.")
                state = kernel.record_tool_result(compiled, state, result)
            except fixtures.FixtureToolError as exc:
                state = kernel.record_tool_error(
                    compiled, state, exc.code, exc.message,
                    retryable=exc.retryable, condition=exc.condition,
                )
        else:
            break
    else:
        raise RuntimeError("The demonstration exceeded its test-harness turn limit.")
    return {"scenario": scenario["id"], "name": scenario.get("name", scenario["id"]),
            "variationKind": scenario.get("variationKind", "observation-dependent-path"),
            "agentId": spec["id"], "agentHash": compiled["agentHash"],
            "provider": "scripted-fixture", "liveModelCalled": False, "status": state["status"],
            "orderedToolTrace": [event["toolId"] for event in state["events"]
                                 if event["type"] in {"tool.observed", "tool.failed"}],
            "localEffectCount": len(local_effects), "externalEffectCount": 0,
            "writeAttemptCount": write_attempt_count,
            "duplicateOperationPrevented": duplicate_operation_prevented,
            "clarificationCount": clarification_count,
            "boundaryOutcome": state.get("boundaryOutcome"), "error": state.get("error"),
            "output": state["output"], "evidence": state["evidence"],
            "outcomeValidation": fixtures.validate_outcome(spec["id"], state), "state": state}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="Write the complete inspectable trace JSON to this path.")
    args = parser.parse_args(argv)
    stable_scenarios = fixtures.scenarios()
    runs = [run_scenario(scenario) for scenario in fixtures.demo_scenarios()]
    stable_ids = {scenario["id"] for scenario in stable_scenarios}
    pairs = []
    for spec in fixtures.agent_specs():
        cases = [run for run in runs if run["agentId"] == spec["id"] and run["scenario"] in stable_ids]
        pairs.append({"agentId": spec["id"], "sameCompiledAgent": len({r["agentHash"] for r in cases}) == 1,
                      "differentObservedPaths": len({tuple(r["orderedToolTrace"]) for r in cases}) == 2,
                      "cases": [{"scenario": r["scenario"], "tools": r["orderedToolTrace"],
                                 "outcome": (r.get("output") or {}).get("outcome")} for r in cases]})
    variations = [{"scenario": run["scenario"], "name": run["name"],
                   "variationKind": run["variationKind"], "status": run["status"],
                   "tools": run["orderedToolTrace"],
                   "outcome": (run.get("output") or {}).get("outcome"),
                   "boundaryOutcome": run.get("boundaryOutcome"),
                   "clarificationCount": run["clarificationCount"],
                   "writeAttemptCount": run["writeAttemptCount"],
                   "uniqueLocalEffects": run["localEffectCount"],
                   "duplicateOperationPrevented": run["duplicateOperationPrevented"]}
                  for run in runs if run["scenario"] not in stable_ids]
    payload = json.dumps({"mode": "scripted-fixture", "liveModelCalled": False,
                          "approvalMode": "automatic test harness for local fixture actions only",
                          "purpose": "Verify generic runtime behavior, not model intelligence or enterprise integrations.",
                          "comparisons": pairs, "controlledVariations": variations,
                          "runs": runs}, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "cases": len(runs),
                          "controlledVariations": len(variations)}))
    else:
        print(payload)


if __name__ == "__main__":
    main()
