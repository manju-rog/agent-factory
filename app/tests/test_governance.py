"""Unit tests for Axiom's self-contained P2 governance domain services."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance import (  # noqa: E402
    AgentUse,
    BlockEdge,
    BlockNode,
    BudgetExceededError,
    ExecutionBudget,
    InsertionBlock,
    PlannedTeamTurn,
    Principal,
    ScenarioResult,
    SingleAgentBaselineResult,
    TeamParticipant,
    TeamRecipe,
    TemplateRecord,
    ValidationError,
    WorkflowRelease,
    analyze_agent_version_impact,
    evaluate_release_experiment,
    expand_insertion_block,
    find_templates,
    plan_team_execution,
)


class InsertionBlockTests(unittest.TestCase):
    def make_block(self):
        source_config = {"mapping": {"supplier": "task.supplier"}, "attempts": [1, 2]}
        block = InsertionBlock(
            block_id="supplier-checks",
            version=3,
            name="Supplier checks",
            nodes=(
                BlockNode("lookup", "supplier-lookup", "Lookup supplier", source_config),
                BlockNode("policy", "policy-check", "Check policy", {"strict": True}),
            ),
            edges=(BlockEdge("lookup-policy", "lookup", "policy", "out", "in"),),
        )
        return block, source_config

    def test_expansion_creates_fresh_ids_provenance_and_new_template(self):
        block, source_config = self.make_block()
        template = {
            "id": "template-1",
            "nodes": [{"id": "start", "agentId": "intake", "config": {}}],
            "edges": [],
            "metadata": {"owner": "author"},
        }
        original_template = deepcopy(template)

        expansion = expand_insertion_block(block, template, "insert-100")
        result = expansion.to_template()

        self.assertEqual(template, original_template)
        self.assertEqual(len(result["nodes"]), 3)
        self.assertEqual(len(result["edges"]), 1)
        self.assertNotIn("lookup", expansion.node_id_map.values())
        self.assertNotEqual(expansion.node_id_map["lookup"], expansion.node_id_map["policy"])
        self.assertEqual(result["edges"][0]["source"], expansion.node_id_map["lookup"])
        self.assertEqual(result["edges"][0]["target"], expansion.node_id_map["policy"])
        self.assertEqual(result["edges"][0]["sourcePort"], "out")
        self.assertEqual(result["edges"][0]["targetPort"], "in")
        provenance = result["nodes"][1]["provenance"]
        self.assertEqual(provenance["sourceBlockId"], "supplier-checks")
        self.assertEqual(provenance["sourceBlockVersion"], 3)
        self.assertEqual(provenance["sourceNodeKey"], "lookup")
        self.assertEqual(provenance["insertionId"], "insert-100")

        source_config["mapping"]["supplier"] = "changed.after.creation"
        result["nodes"][1]["config"]["mapping"]["supplier"] = "changed.in.result"
        second = expand_insertion_block(block, template, "insert-101").to_template()
        self.assertEqual(second["nodes"][1]["config"]["mapping"]["supplier"], "task.supplier")
        self.assertEqual(template, original_template)

    def test_different_insertions_are_deterministic_and_disjoint(self):
        block, _ = self.make_block()
        template = {"nodes": [], "edges": []}
        first_a = expand_insertion_block(block, template, "operation-a")
        first_a_again = expand_insertion_block(block, template, "operation-a")
        second = expand_insertion_block(block, template, "operation-b")
        self.assertEqual(dict(first_a.node_id_map), dict(first_a_again.node_id_map))
        self.assertTrue(set(first_a.node_id_map.values()).isdisjoint(second.node_id_map.values()))

    def test_reusing_insertion_identity_in_expanded_template_fails_closed(self):
        block, _ = self.make_block()
        first = expand_insertion_block(block, {"nodes": [], "edges": []}, "same-operation")
        with self.assertRaisesRegex(ValidationError, "already been used"):
            expand_insertion_block(block, first.to_template(), "same-operation")

    def test_invalid_block_topology_and_template_references_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, "unknown node"):
            InsertionBlock(
                "bad",
                1,
                "Bad",
                (BlockNode("one", "a", "One"),),
                (BlockEdge("edge", "one", "missing"),),
            )
        with self.assertRaisesRegex(ValidationError, "acyclic"):
            InsertionBlock(
                "cycle",
                1,
                "Cycle",
                (BlockNode("one", "a", "One"), BlockNode("two", "b", "Two")),
                (BlockEdge("one-two", "one", "two"), BlockEdge("two-one", "two", "one")),
            )
        block, _ = self.make_block()
        with self.assertRaisesRegex(ValidationError, "unknown node"):
            expand_insertion_block(
                block,
                {"nodes": [{"id": "one"}], "edges": [{"id": "bad", "source": "one", "target": "two"}]},
                "insert",
            )

    def test_block_payload_must_be_json_compatible(self):
        with self.assertRaisesRegex(ValidationError, "unsupported value type"):
            BlockNode("node", "agent", "Node", {"unsafe": object()})


class TemplateFindingTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("person-1", "workspace-1", frozenset({"contributor"}))
        self.templates = (
            TemplateRecord(
                "supplier-onboarding",
                4,
                "workspace-1",
                "Supplier onboarding",
                "Check a supplier then create a service ticket",
                ("procurement", "supplier"),
                allowed_roles=frozenset({"contributor"}),
            ),
            TemplateRecord(
                "csr-to-ticket",
                2,
                "workspace-1",
                "CSR request",
                "Prepare CSR data and create a ticket",
                ("certificate",),
                allowed_principal_ids=frozenset({"person-1"}),
            ),
            TemplateRecord(
                "admin-only",
                1,
                "workspace-1",
                "Supplier administration",
                allowed_roles=frozenset({"administrator"}),
            ),
            TemplateRecord(
                "other-workspace",
                1,
                "workspace-2",
                "Supplier onboarding elsewhere",
                allowed_roles=frozenset({"contributor"}),
            ),
            TemplateRecord(
                "draft-template",
                1,
                "workspace-1",
                "Supplier draft",
                lifecycle="draft",
                allowed_roles=frozenset({"contributor"}),
            ),
            TemplateRecord(
                "old-supplier-version",
                1,
                "workspace-1",
                "Old supplier process",
                lifecycle="published",
                is_active=False,
                allowed_roles=frozenset({"contributor"}),
            ),
        )

    def test_search_filters_permissions_and_explains_deterministic_scores(self):
        matches = find_templates(self.templates, self.principal, "supplier ticket")
        self.assertEqual([match.template_id for match in matches], ["supplier-onboarding", "csr-to-ticket"])
        self.assertGreater(matches[0].score, matches[1].score)
        self.assertIn("supplier: name, tag, description (+10)", matches[0].explanation)
        self.assertIn("ticket: description (+1)", matches[0].explanation)
        supplied_ids = {template.template_id for template in self.templates}
        self.assertTrue(all(match.template_id in supplied_ids for match in matches))

    def test_empty_query_lists_only_eligible_active_published_templates(self):
        matches = find_templates(self.templates, self.principal, "   ")
        self.assertEqual([match.template_id for match in matches], ["csr-to-ticket", "supplier-onboarding"])
        self.assertTrue(all(match.score == 0 for match in matches))
        self.assertTrue(all("Eligible active published" in match.explanation for match in matches))

    def test_empty_permissions_fail_closed_and_limit_is_enforced(self):
        stranger = Principal("stranger", "workspace-1", frozenset())
        self.assertEqual(find_templates(self.templates, stranger, "supplier"), ())
        self.assertEqual(len(find_templates(self.templates, self.principal, "", limit=1)), 1)
        with self.assertRaisesRegex(ValidationError, "positive integer"):
            find_templates(self.templates, self.principal, "", limit=0)
        with self.assertRaisesRegex(ValidationError, "not a scalar"):
            Principal("person", "workspace-1", "contributor")

    def test_duplicate_active_published_template_id_is_rejected(self):
        duplicate = TemplateRecord(
            "supplier-onboarding",
            5,
            "workspace-1",
            "Supplier onboarding v5",
            allowed_roles=frozenset({"contributor"}),
        )
        with self.assertRaisesRegex(ValidationError, "multiple active published"):
            find_templates(self.templates + (duplicate,), self.principal, "supplier")


class AgentImpactTests(unittest.TestCase):
    def setUp(self):
        self.releases = (
            WorkflowRelease(
                "release-a1",
                "template-a",
                1,
                "archived",
                (
                    AgentUse("lookup", "lookup-agent", "1.0"),
                    AgentUse("ticket", "ticket-agent", "1.0"),
                ),
            ),
            WorkflowRelease(
                "release-a2",
                "template-a",
                2,
                "published",
                (
                    AgentUse("lookup", "lookup-agent", "1.1"),
                    AgentUse("backup-lookup", "lookup-agent", "1.0"),
                ),
            ),
            WorkflowRelease(
                "release-b1",
                "template-b",
                1,
                "draft",
                (AgentUse("lookup", "lookup-agent", "2.0"),),
            ),
        )

    def test_impact_analysis_is_precise_sorted_and_non_mutating(self):
        before = self.releases
        result = analyze_agent_version_impact(self.releases, "lookup-agent", "2.0")
        self.assertIs(self.releases, before)
        self.assertEqual([impact.release_id for impact in result.impacts], ["release-a1", "release-a2"])
        self.assertEqual(result.impacts[1].node_ids, ("backup-lookup", "lookup"))
        self.assertEqual(result.impacts[1].current_versions, ("1.0", "1.1"))
        self.assertTrue(result.impacts[1].affects_future_starts)
        self.assertFalse(result.impacts[0].affects_future_starts)

    def test_from_version_limits_impact(self):
        result = analyze_agent_version_impact(
            self.releases,
            "lookup-agent",
            "2.0",
            from_version="1.0",
        )
        self.assertEqual([impact.release_id for impact in result.impacts], ["release-a1", "release-a2"])
        self.assertEqual(result.impacts[1].node_ids, ("backup-lookup",))
        self.assertEqual(result.impacts[1].current_versions, ("1.0",))

    def test_impact_rejects_ambiguous_releases_and_noop_versions(self):
        with self.assertRaisesRegex(ValidationError, "must differ"):
            analyze_agent_version_impact(self.releases, "lookup-agent", "1.0", from_version="1.0")
        with self.assertRaisesRegex(ValidationError, "release IDs must be unique"):
            analyze_agent_version_impact(self.releases + (self.releases[0],), "lookup-agent", "3.0")
        with self.assertRaisesRegex(ValidationError, "duplicate node IDs"):
            WorkflowRelease(
                "bad",
                "template",
                1,
                "draft",
                (AgentUse("same", "a", "1"), AgentUse("same", "b", "1")),
            )


class TeamPlanningTests(unittest.TestCase):
    def setUp(self):
        self.budget = ExecutionBudget(4, 1_000, 90, Decimal("2.50"))
        self.recipe = TeamRecipe(
            recipe_id="supplier-research-team",
            version=2,
            participants=(
                TeamParticipant("researcher", "researcher", frozenset({"directory.read"})),
                TeamParticipant(
                    "executor",
                    "executor",
                    frozenset({"ticket.prepare", "ticket.commit"}),
                    can_commit=True,
                ),
            ),
            approved_roles=frozenset({"researcher", "executor"}),
            approved_tools=frozenset({"directory.read", "ticket.prepare", "ticket.commit"}),
            budget=self.budget,
            commit_actor_id="executor",
        )
        self.baseline = SingleAgentBaselineResult(
            "single-agent",
            self.budget,
            True,
            "completed",
            3,
            750,
            70,
            Decimal("1.90"),
        )

    def valid_turns(self):
        return (
            PlannedTeamTurn("researcher", 200, 20, Decimal("0.30"), "directory.read"),
            PlannedTeamTurn("executor", 250, 25, Decimal("0.50"), "ticket.prepare"),
            PlannedTeamTurn(
                "executor",
                100,
                10,
                Decimal("0.25"),
                "ticket.commit",
                commits_effect=True,
                action_id="ticket-action-1",
            ),
        )

    def test_valid_plan_enforces_one_committer_and_attaches_matched_baseline(self):
        plan = plan_team_execution(self.recipe, self.valid_turns(), self.baseline)
        self.assertEqual(plan.commit_actor_id, "executor")
        self.assertEqual(plan.turns_reserved, 3)
        self.assertEqual(plan.tokens_reserved, 550)
        self.assertEqual(plan.time_reserved_seconds, 55)
        self.assertEqual(plan.cost_reserved, Decimal("1.05"))
        self.assertEqual(plan.turns_remaining, 1)
        self.assertEqual(plan.tokens_remaining, 450)
        self.assertEqual(plan.cost_remaining, Decimal("1.45"))
        self.assertTrue(plan.matched_budget)
        self.assertIs(plan.baseline, self.baseline)

    def test_recipe_rejects_unapproved_roles_tools_and_committers(self):
        with self.assertRaisesRegex(ValidationError, "unapproved role"):
            TeamRecipe(
                "bad-role",
                1,
                (TeamParticipant("critic", "critic", can_commit=True),),
                frozenset({"executor"}),
                frozenset(),
                self.budget,
                "critic",
            )
        with self.assertRaisesRegex(ValidationError, "unapproved tools"):
            TeamRecipe(
                "bad-tool",
                1,
                (TeamParticipant("executor", "executor", frozenset({"shell"}), True),),
                frozenset({"executor"}),
                frozenset({"ticket.commit"}),
                self.budget,
                "executor",
            )
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            TeamRecipe(
                "two-committers",
                1,
                (
                    TeamParticipant("one", "executor", can_commit=True),
                    TeamParticipant("two", "executor", can_commit=True),
                ),
                frozenset({"executor"}),
                frozenset(),
                self.budget,
                "one",
            )

    def test_plan_rejects_unknown_participant_unapproved_tool_and_wrong_committer(self):
        with self.assertRaisesRegex(ValidationError, "unapproved participant"):
            plan_team_execution(
                self.recipe,
                (PlannedTeamTurn("intruder", 1, 1, Decimal("0")),),
                self.baseline,
            )
        with self.assertRaisesRegex(ValidationError, "unapproved tool"):
            plan_team_execution(
                self.recipe,
                (PlannedTeamTurn("researcher", 1, 1, Decimal("0"), "ticket.prepare"),),
                self.baseline,
            )
        with self.assertRaisesRegex(ValidationError, "designated commit actor"):
            plan_team_execution(
                self.recipe,
                (
                    PlannedTeamTurn(
                        "researcher",
                        1,
                        1,
                        Decimal("0"),
                        "directory.read",
                        commits_effect=True,
                        action_id="wrong-actor",
                    ),
                ),
                self.baseline,
            )

    def test_every_budget_is_fail_closed(self):
        overages = (
            tuple(PlannedTeamTurn("researcher", 0, 0, Decimal("0")) for _ in range(5)),
            (PlannedTeamTurn("researcher", 1_001, 0, Decimal("0")),),
            (PlannedTeamTurn("researcher", 0, 91, Decimal("0")),),
            (PlannedTeamTurn("researcher", 0, 0, Decimal("2.51")),),
        )
        for turns in overages:
            with self.subTest(turns=turns):
                with self.assertRaises(BudgetExceededError):
                    plan_team_execution(self.recipe, turns, self.baseline)

    def test_baseline_must_have_exactly_the_same_budget(self):
        other_budget = ExecutionBudget(4, 1_000, 90, Decimal("2.51"))
        other_baseline = SingleAgentBaselineResult(
            "single-agent",
            other_budget,
            True,
            "completed",
            1,
            1,
            1,
            Decimal("0"),
        )
        with self.assertRaisesRegex(ValidationError, "exactly the team recipe budget"):
            plan_team_execution(self.recipe, self.valid_turns(), other_baseline)

    def test_duplicate_action_reservations_are_rejected(self):
        turns = (
            PlannedTeamTurn(
                "executor", 1, 1, Decimal("0"), "ticket.commit", True, "same-action"
            ),
            PlannedTeamTurn(
                "executor", 1, 1, Decimal("0"), "ticket.commit", True, "same-action"
            ),
        )
        with self.assertRaisesRegex(ValidationError, "duplicate committed action"):
            plan_team_execution(self.recipe, turns, self.baseline)


class ReleaseExperimentTests(unittest.TestCase):
    def baseline(self):
        return (
            ScenarioResult("happy", "v1", True, effect_ids=("ticket-1",)),
            ScenarioResult("missing", "v1", True),
        )

    def safe_candidate(self):
        return (
            ScenarioResult("happy", "v2", True, effect_ids=("ticket-2",)),
            ScenarioResult("missing", "v2", True),
        )

    def test_safe_candidate_is_selected_only_for_future_starts(self):
        pins = {"run-1": "v1", "run-2": "v0"}
        original = deepcopy(pins)
        decision = evaluate_release_experiment(
            "v1", "v2", self.baseline(), self.safe_candidate(), "v1", pins
        )
        self.assertTrue(decision.promoted)
        self.assertEqual(decision.selected_future_version, "v2")
        self.assertEqual(decision.blockers, ())
        self.assertEqual(decision.active_run_pin_map(), original)
        self.assertEqual(pins, original)
        self.assertEqual([item.case_id for item in decision.paired_results], ["happy", "missing"])

    def test_any_candidate_permission_violation_blocks_promotion(self):
        candidate = (
            ScenarioResult("happy", "v2", True, ("ticket.write denied",), ("ticket-2",)),
            ScenarioResult("missing", "v2", True),
        )
        decision = evaluate_release_experiment(
            "v1", "v2", self.baseline(), candidate, "v1", {"active": "v1"}
        )
        self.assertFalse(decision.promoted)
        self.assertEqual(decision.selected_future_version, "v1")
        self.assertIn("permission violations", decision.blockers[0])
        self.assertEqual(decision.active_run_pin_map(), {"active": "v1"})

    def test_repeated_or_reported_duplicate_effect_blocks_promotion(self):
        repeated = (
            ScenarioResult("happy", "v2", True, effect_ids=("ticket-2", "ticket-2")),
            ScenarioResult("missing", "v2", True, duplicate_effect_count=1),
        )
        decision = evaluate_release_experiment(
            "v1", "v2", self.baseline(), repeated, "v1", {}
        )
        self.assertFalse(decision.promoted)
        self.assertEqual(len(decision.blockers), 2)
        self.assertTrue(any("repeated effect IDs" in blocker for blocker in decision.blockers))
        self.assertTrue(any("reported 1 duplicate" in blocker for blocker in decision.blockers))

    def test_failed_candidate_invariant_and_regression_block_promotion(self):
        candidate = (
            ScenarioResult("happy", "v2", False),
            ScenarioResult("missing", "v2", True),
        )
        decision = evaluate_release_experiment(
            "v1", "v2", self.baseline(), candidate, "v1", {"run": "v1"}
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(decision.paired_results[0].regressed)
        self.assertTrue(any("failed declared invariants" in blocker for blocker in decision.blockers))

    def test_unpaired_duplicate_or_wrong_version_results_fail_closed(self):
        with self.assertRaisesRegex(ValidationError, "identical case IDs"):
            evaluate_release_experiment(
                "v1",
                "v2",
                self.baseline(),
                (ScenarioResult("happy", "v2", True),),
                "v1",
                {},
            )
        with self.assertRaisesRegex(ValidationError, "duplicate baseline case"):
            evaluate_release_experiment(
                "v1",
                "v2",
                self.baseline() + (ScenarioResult("happy", "v1", True),),
                self.safe_candidate(),
                "v1",
                {},
            )
        with self.assertRaisesRegex(ValidationError, "expected v2"):
            evaluate_release_experiment(
                "v1",
                "v2",
                self.baseline(),
                (
                    ScenarioResult("happy", "v3", True),
                    ScenarioResult("missing", "v2", True),
                ),
                "v1",
                {},
            )


if __name__ == "__main__":
    unittest.main()
