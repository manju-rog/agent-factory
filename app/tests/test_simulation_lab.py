"""Focused verification for the isolated Atlas Checkout simulation lab."""
import copy
import pathlib
import sys
import unittest


APP = pathlib.Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import agent_factory as af  # noqa: E402
import simulation_lab as lab  # noqa: E402


PROFILE_IDS = [
    "fresh-incident",
    "existing-incident",
    "missing-owner",
    "confluence-unavailable",
    "slack-rate-limit",
    "jira-lost-ack",
    "changed-flag-version",
]


class SimulationLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = af.compile_agent(lab.incident_commander_spec(), lab.tool_catalog())

    def assert_simulation_error(self, code, function, *args, **kwargs):
        with self.assertRaises(lab.SimulationError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def execute_direct(self, world, tool_id, arguments, operation_key=None):
        return lab.execute_tool(
            world,
            tool_id,
            {"worldId": world["id"], **arguments},
            operation_key=operation_key,
        )

    def run_agent(self, profile_id, *, mutate_before_execute=None):
        world = lab.create_world(profile_id, "world-" + profile_id)
        state = af.create_state(
            self.compiled,
            {"worldId": world["id"], "alertId": "ALT-CHECKOUT-9001"},
        )
        for _ in range(40):
            if state["status"] == "ready":
                decision = lab.fixture_decision(self.compiled, state, scenario="ignored")
                state = af.apply_decision(
                    self.compiled,
                    state,
                    decision,
                    provider_label="scripted-atlas-simulation",
                )
                continue
            if state["status"] == "awaiting_input":
                values = {
                    "input.ownerTeam": "Commerce Reliability",
                    "input.slackChannelId": "C-INCIDENTS",
                }
                state = af.supply_input(
                    self.compiled,
                    state,
                    {field: values[field] for field in state["requestedFields"]},
                )
                continue
            if state["status"] == "awaiting_approval":
                action_hash = state["pendingAction"]["actionHash"]
                state = af.approve_action(
                    self.compiled, state, True, "simulation-reviewer", action_hash
                )
                continue
            if state["status"] == "awaiting_tool":
                action = af.executable_action(self.compiled, state)
                if mutate_before_execute:
                    mutate_before_execute(world, action, state)
                envelope = lab.execute(
                    world,
                    action["toolId"],
                    action["arguments"],
                    operation_key=(action["operationKey"] if action["effect"] == "write" else None),
                    action_hash=action["actionHash"],
                )
                if envelope["ok"]:
                    state = af.record_tool_result(self.compiled, state, envelope["output"])
                else:
                    fault = envelope["fault"]
                    state = af.record_tool_error(
                        self.compiled,
                        state,
                        fault["code"],
                        fault["message"],
                        retryable=fault["retryable"],
                        condition=fault["condition"],
                        outcome_unknown=fault["outcomeUnknown"],
                    )
                continue
            if state["status"] in {"completed", "stopped", "failed"}:
                return world, state
            self.fail("Unexpected agent status: " + str(state["status"]))
        self.fail("The fixture did not reach a terminal state within its bounded turns.")

    def test_profiles_are_versioned_canonical_and_alias_is_hidden(self):
        self.assertEqual([item["id"] for item in lab.profiles()], PROFILE_IDS)
        self.assertEqual([item["id"] for item in lab.scenarios()], PROFILE_IDS)
        self.assertTrue(all(len(item["definitionHash"]) == 64 for item in lab.profiles()))
        alias = lab.create_world("changed-flag")
        self.assertEqual(alias["profileId"], "changed-flag-version")
        self.assertNotIn("changed-flag", PROFILE_IDS)

    def test_worlds_are_isolated_deterministic_and_generation_pinned(self):
        first = lab.create_world("fresh-incident", generation=2)
        second = lab.create_world("fresh-incident", generation=2)
        self.assertEqual(first, second)
        self.assertEqual(first["id"], "atlas-fresh-incident-g2")
        self.assertEqual(first["generation"], 2)
        self.assertEqual(
            first["sandbox"],
            {"isolated": True, "externalNetwork": False, "externalEffects": False},
        )
        first["records"]["metrics"]["atlas-checkout"]["state"] = "tampered"
        self.assertEqual(second["records"]["metrics"]["atlas-checkout"]["state"], "degraded")
        self.assert_simulation_error(
            "WORLD_GENERATION_INVALID", lab.create_world, "fresh-incident", None, 0
        )

    def test_contracts_compile_and_bind_only_in_process_adapters(self):
        tools = lab.tool_catalog()
        self.assertEqual(len(tools), 11)
        self.assertEqual({item["effect"] for item in tools}, {"read", "write"})
        self.assertTrue(
            all(item["adapterBinding"]["transport"] == "in-process" for item in tools)
        )
        self.assertTrue(
            all(item["verification"]["externalIntegration"] is False for item in tools)
        )
        compiled = af.compile_agent(lab.agent_specs()[0], tools)
        self.assertEqual(compiled["spec"]["id"], lab.INCIDENT_COMMANDER_ID)

    def test_read_receipt_is_provider_shaped_and_has_no_external_effect(self):
        world = lab.create_world("fresh-incident")
        result = self.execute_direct(
            world,
            "simulation.metrics.query",
            {"alertId": "ALT-CHECKOUT-9001", "advanceSeconds": 0},
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.output["errorRatePercent"], 18.7)
        self.assertTrue(result.receipt["simulated"])
        self.assertFalse(result.receipt["externalEffect"])
        self.assertEqual(world["events"][-1]["kind"], "capability.observed")

    def test_existing_incident_and_missing_owner_profiles_change_evidence(self):
        existing = lab.create_world("existing-incident")
        found = self.execute_direct(
            existing,
            "simulation.jira.search_incidents",
            {"serviceId": "atlas-checkout", "status": "Investigating"},
        )
        self.assertEqual(found.output["issues"][0]["key"], "OPS-4312")
        missing = lab.create_world("missing-owner")
        owner = self.execute_direct(
            missing, "simulation.catalog.get_service", {"serviceId": "atlas-checkout"}
        )
        self.assertEqual(owner.output["ownerTeam"], "")
        self.assertEqual(owner.output["slackChannelId"], "")

    def test_confluence_unavailable_is_a_controlled_retryable_fault(self):
        world = lab.create_world("confluence-unavailable")
        outcome = self.execute_direct(
            world, "simulation.confluence.get_page", {"pageId": "CONF-RUNBOOK-77"}
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.receipt["statusCode"], 503)
        self.assertEqual(outcome.fault["code"], "CONFLUENCE_SERVICE_UNAVAILABLE")
        self.assertTrue(outcome.fault["retryable"])
        self.assertFalse(outcome.fault["outcomeUnknown"])

    def test_slack_rate_limit_then_idempotent_success_without_duplicate(self):
        world = lab.create_world("slack-rate-limit")
        arguments = {
            "channelId": "C-INCIDENTS",
            "text": "OPS-4313 | Atlas Checkout | mitigation pending",
        }
        limited = self.execute_direct(
            world, "simulation.slack.post_message", arguments, "notify:one"
        )
        self.assertFalse(limited.ok)
        self.assertEqual(limited.receipt["statusCode"], 429)
        self.assertEqual(limited.fault["retryAfterSeconds"], 30)
        posted = self.execute_direct(
            world, "simulation.slack.post_message", arguments, "notify:one"
        )
        replayed = self.execute_direct(
            world, "simulation.slack.post_message", arguments, "notify:one"
        )
        self.assertTrue(posted.ok)
        self.assertTrue(replayed.ok)
        self.assertTrue(replayed.receipt["replayed"])
        messages = world["records"]["slackChannels"]["C-INCIDENTS"]["messages"]
        self.assertEqual(sum(item["authorId"] == "AXIOM-INCIDENT-BOT" for item in messages), 1)
        conflict = self.execute_direct(
            world,
            "simulation.slack.post_message",
            {**arguments, "text": "Different exact payload"},
            "notify:one",
        )
        self.assertEqual(conflict.fault["code"], "IDEMPOTENCY_KEY_CONFLICT")

    def test_jira_lost_ack_commits_once_and_reconciles_by_operation_key(self):
        world = lab.create_world("jira-lost-ack")
        arguments = {
            "projectKey": "OPS",
            "serviceId": "atlas-checkout",
            "summary": "Atlas Checkout errors after 2026.09.30.417",
            "severity": "SEV-1",
        }
        lost = self.execute_direct(
            world, "simulation.jira.create_incident", arguments, "incident:create:one"
        )
        self.assertFalse(lost.ok)
        self.assertTrue(lost.fault["outcomeUnknown"])
        self.assertEqual(len(world["records"]["jiraIssues"]), 1)
        reconciled = lab.reconcile_operation(world, "incident:create:one")
        self.assertTrue(reconciled.ok)
        self.assertTrue(reconciled.receipt["reconciled"])
        self.assertTrue(reconciled.receipt["recovered"])
        self.assertEqual(reconciled.output["key"], "OPS-4313")
        replayed = self.execute_direct(
            world, "simulation.jira.create_incident", arguments, "incident:create:one"
        )
        self.assertTrue(replayed.ok)
        self.assertEqual(len(world["records"]["jiraIssues"]), 1)

    def test_changed_flag_revision_rejects_stale_write(self):
        world = lab.create_world("changed-flag-version")
        observed = self.execute_direct(
            world, "simulation.feature_flags.get", {"flagKey": "checkout-v2"}
        )
        lab.advance_clock(world, 60)
        stale = self.execute_direct(
            world,
            "simulation.feature_flags.update",
            {
                "flagKey": "checkout-v2",
                "enabled": False,
                "expectedRevision": observed.output["revision"],
                "reason": "Approved mitigation",
            },
            "flag:disable:one",
        )
        self.assertFalse(stale.ok)
        self.assertEqual(stale.receipt["statusCode"], 412)
        self.assertEqual(stale.fault["condition"], "changedBusinessState")
        self.assertTrue(world["records"]["featureFlags"]["checkout-v2"]["enabled"])

    def test_successful_flag_update_drives_deterministic_recovery(self):
        world = lab.create_world("fresh-incident")
        changed = self.execute_direct(
            world,
            "simulation.feature_flags.update",
            {
                "flagKey": "checkout-v2",
                "enabled": False,
                "expectedRevision": 7,
                "reason": "Runbook mitigation",
            },
            "flag:disable:one",
        )
        self.assertTrue(changed.ok)
        lab.advance_clock(world, 180)
        metrics = world["records"]["metrics"]["atlas-checkout"]
        self.assertEqual(metrics["state"], "healthy")
        self.assertEqual(metrics["consecutiveHealthyWindows"], 2)
        self.assertEqual(world["records"]["alerts"]["ALT-CHECKOUT-9001"]["status"], "resolved")

    def test_stable_execute_envelope_binds_host_action_hash(self):
        world = lab.create_world("fresh-incident")
        arguments = {
            "worldId": world["id"],
            "channelId": "C-INCIDENTS",
            "text": "Approved exact update",
        }
        result = lab.execute(
            world,
            "simulation.slack.post_message",
            arguments,
            operation_key="notify:approved",
            action_hash="engine-action-hash-1",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"]["approvedActionHash"], "engine-action-hash-1")
        self.assertEqual(result["world"]["id"], world["id"])
        self.assertTrue(any(item["kind"] == "operation.approval_bound" for item in result["events"]))
        self.assert_simulation_error(
            "ACTION_HASH_CHANGED",
            lab.execute,
            world,
            "simulation.slack.post_message",
            arguments,
            "notify:approved",
            "engine-action-hash-2",
        )

    def test_fault_controls_and_event_integrity_are_auditable(self):
        world = lab.create_world("fresh-incident")
        changed = lab.set_fault(world, "slack-rate-limit", True)
        self.assertEqual(changed["faults"]["slackRateLimitRemaining"], 1)
        self.assertEqual(world["events"][-1]["kind"], "fault.changed")
        lab.validate_world(world)
        corrupt = copy.deepcopy(world)
        corrupt["events"][0]["details"]["profileId"] = "tampered"
        self.assert_simulation_error("EVENT_HISTORY_CHANGED", lab.validate_world, corrupt)
        corrupt = copy.deepcopy(world)
        corrupt["records"]["metrics"]["atlas-checkout"]["errorRatePercent"] = 0
        self.assert_simulation_error("WORLD_STATE_CHANGED", lab.validate_world, corrupt)

    def test_fresh_and_existing_incidents_take_different_real_tool_sequences(self):
        fresh_world, fresh = self.run_agent("fresh-incident")
        existing_world, existing = self.run_agent("existing-incident")
        self.assertEqual(fresh["status"], "completed")
        self.assertEqual(existing["status"], "completed")
        fresh_tools = [item.get("toolId") for item in fresh["events"] if item["type"] == "tool.observed"]
        existing_tools = [item.get("toolId") for item in existing["events"] if item["type"] == "tool.observed"]
        self.assertIn("simulation.jira.create_incident", fresh_tools)
        self.assertNotIn("simulation.jira.create_incident", existing_tools)
        self.assertEqual(existing["output"]["incidentKey"], "OPS-4312")
        self.assertEqual(len(fresh_world["records"]["jiraIssues"]), 1)
        self.assertEqual(len(existing_world["records"]["jiraIssues"]), 1)

    def test_clarification_rate_limit_and_unavailable_runbook_paths_resume(self):
        _, missing = self.run_agent("missing-owner")
        _, limited = self.run_agent("slack-rate-limit")
        _, unavailable = self.run_agent("confluence-unavailable")
        self.assertEqual(missing["status"], "completed")
        self.assertTrue(any(item["type"] == "input.requested" for item in missing["events"]))
        self.assertEqual(limited["status"], "completed")
        slack_calls = [
            item for item in limited["events"]
            if item.get("toolId") == "simulation.slack.post_message"
            and item["type"] in {"tool.failed", "tool.observed"}
        ]
        self.assertEqual([item["type"] for item in slack_calls], ["tool.failed", "tool.observed"])
        self.assertEqual(unavailable["status"], "completed")
        self.assertEqual(unavailable["output"]["mitigation"], "none")
        self.assertIn("unavailable", " ".join(unavailable["output"]["unresolvedRisks"]).lower())

    def test_outcome_validator_uses_authoritative_world_not_prose(self):
        world, state = self.run_agent("fresh-incident")
        report = lab.validate_outcome(world, state)
        self.assertTrue(report["businessOutcomeVerified"])
        tampered = copy.deepcopy(state)
        tampered["output"]["recoveryVerified"] = False
        contradicted = lab.validate_outcome(world, tampered)
        self.assertFalse(contradicted["businessOutcomeVerified"])
        self.assertEqual(contradicted["status"], "contradicted")
        self.assertEqual(
            next(item for item in contradicted["checks"] if item["id"] == "recovery-claim")["status"],
            "contradicted",
        )

    def test_changed_state_during_agent_approval_escalates_without_write(self):
        advanced = False

        def mutate(world, action, _state):
            nonlocal advanced
            if action["toolId"] == "simulation.feature_flags.update" and not advanced:
                lab.advance_clock(world, 60)
                advanced = True

        world, state = self.run_agent(
            "changed-flag-version", mutate_before_execute=mutate
        )
        self.assertTrue(advanced)
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(state["error"]["code"], "AGENT_ESCALATION_REQUIRED")
        self.assertTrue(world["records"]["featureFlags"]["checkout-v2"]["enabled"])
        self.assertFalse(
            any(
                operation["toolId"] == "simulation.feature_flags.update"
                for operation in world["operations"].values()
            )
        )


if __name__ == "__main__":
    unittest.main()
