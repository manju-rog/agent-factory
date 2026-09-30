import copy
import unittest

from workflow import GraphCompileError, analyze_graph, compile_graph, condition_selection


AGENTS = {
    "work": {"id": "work", "kind": "agent", "implementationId": "work"},
    "approval": {"id": "approval", "kind": "human", "implementationId": "approval"},
}


def structured_template():
    nodes = [
        {"id": "start", "type": "start", "x": 0, "y": 0, "config": {}},
        {"id": "condition", "type": "condition", "x": 1, "y": 0,
         "config": {"rule": {"op": "gte", "path": "amount", "value": 100}, "mergeId": "merge"}},
        {"id": "large", "agentId": "work", "x": 2, "y": 0, "config": {}},
        {"id": "small", "agentId": "work", "x": 2, "y": 1, "config": {}},
        {"id": "merge", "type": "join", "x": 3, "y": 0, "config": {}},
        {"id": "split", "type": "parallel_split", "x": 4, "y": 0, "config": {"joinId": "join"}},
        {"id": "left", "agentId": "work", "x": 5, "y": 0, "config": {}},
        {"id": "right", "agentId": "work", "x": 5, "y": 1, "config": {}},
        {"id": "join", "type": "join", "x": 6, "y": 0, "config": {}},
        {"id": "end", "type": "end", "x": 7, "y": 0, "config": {}},
    ]
    raw = [
        ("start", "condition", None), ("condition", "large", "match"),
        ("condition", "small", "default"), ("large", "merge", None),
        ("small", "merge", None), ("merge", "split", None),
        ("split", "left", None), ("split", "right", None),
        ("left", "join", None), ("right", "join", None), ("join", "end", None),
    ]
    edges = [{"id": f"e{i}", "source": source, "target": target, **({"branch": branch} if branch else {})}
             for i, (source, target, branch) in enumerate(raw)]
    return {"id": "structured", "nodes": nodes, "edges": edges}


class WorkflowCompilerTests(unittest.TestCase):
    def test_compiles_condition_and_parallel_scopes_deterministically(self):
        template = structured_template()
        analysis = analyze_graph(template, AGENTS)
        self.assertTrue(analysis["valid"], analysis["issues"])
        plan = compile_graph(template, AGENTS)
        self.assertEqual([scope["kind"] for scope in plan["scopes"]], ["condition", "parallel"])
        self.assertEqual(plan["planHash"], compile_graph(copy.deepcopy(template), AGENTS)["planHash"])

    def test_condition_selects_exactly_one_branch(self):
        template = structured_template()
        plan = compile_graph(template, AGENTS)
        instruction = next(item for item in plan["instructions"] if item["id"] == "condition")
        self.assertEqual(("large", ["small"]), condition_selection(instruction, {"amount": 100}, template["edges"]))
        self.assertEqual(("small", ["large"]), condition_selection(instruction, {"amount": 99}, template["edges"]))

    def test_condition_requires_default_and_pair(self):
        template = structured_template()
        next(edge for edge in template["edges"] if edge.get("branch") == "default")["branch"] = "match"
        result = analyze_graph(template, AGENTS)
        self.assertFalse(result["valid"])
        self.assertIn("CONDITION_BRANCHES", {issue["code"] for issue in result["issues"]})

    def test_branch_crossing_is_rejected(self):
        template = structured_template()
        template["edges"].append({"id": "cross", "source": "large", "target": "small"})
        result = analyze_graph(template, AGENTS)
        self.assertFalse(result["valid"])
        self.assertTrue({"BRANCH_CROSSING", "EARLY_BRANCH_MERGE"} & {issue["code"] for issue in result["issues"]})

    def test_cycles_fail_compilation(self):
        template = structured_template()
        template["edges"].append({"id": "cycle", "source": "end", "target": "start"})
        with self.assertRaises(GraphCompileError):
            compile_graph(template, AGENTS)

    def test_legacy_agent_dag_remains_supported(self):
        template = {
            "id": "legacy",
            "nodes": [
                {"id": "one", "agentId": "work", "config": {}, "x": 0, "y": 0},
                {"id": "two", "agentId": "approval", "config": {}, "x": 1, "y": 0},
            ],
            "edges": [{"id": "e", "source": "one", "target": "two"}],
        }
        self.assertTrue(analyze_graph(template, AGENTS)["valid"])
        self.assertEqual(["agent", "approval"], [item["op"] for item in compile_graph(template, AGENTS)["instructions"]])


if __name__ == "__main__":
    unittest.main()
