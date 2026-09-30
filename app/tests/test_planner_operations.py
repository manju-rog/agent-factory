"""Bounded proposal operations and authority limits."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import APIError, DEFAULT_CONFIG, Store, USERS


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


def node(ident, agent, x):
    return {"id": ident, "agentId": agent, "label": ident.title(), "x": x, "y": 100,
            "config": copy.deepcopy(DEFAULT_CONFIG)}


class PlannerOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "planner.sqlite3", latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    @staticmethod
    def candidate(nodes, edges):
        return {"id": "candidate", "name": "Candidate", "description": "Planner fixture",
                "nodes": nodes, "edges": edges}

    def test_insert_approval_turns_an_unprotected_write_into_a_valid_graph(self):
        template = self.candidate(
            [node("start", "intake", 0), node("write", "ticket", 500)],
            [{"id": "start_write", "source": "start", "target": "write"}],
        )
        self.assertIn("WRITE_WITHOUT_APPROVAL", {
            issue["code"] for issue in self.store.validate(template)["issues"]
        })
        result = self.store.apply_operations(template, [{
            "op": "insert_approval", "beforeNodeId": "write",
            "nodeId": "review", "label": "Review exact write",
        }])
        self.assertTrue(self.store.validate(result)["valid"], self.store.validate(result)["issues"])
        self.assertEqual(
            {("start", "review"), ("review", "write")},
            {(edge["source"], edge["target"]) for edge in result["edges"]},
        )

    def test_field_bindings_and_edge_edits_are_deterministic(self):
        template = self.candidate(
            [node("start", "intake", 0), node("context", "enrich", 250),
             node("finish", "receipt", 500)],
            [{"id": "direct", "source": "start", "target": "finish"}],
        )
        operations = [
            {"op": "add_edge", "source": "start", "target": "context"},
            {"op": "add_edge", "source": "context", "target": "finish"},
            {"op": "remove_edge", "edgeId": "direct"},
            {"op": "bind_field", "nodeId": "finish", "target": "subject",
             "source": "nodes.context.output.subject"},
        ]
        first = self.store.apply_operations(template, operations)
        second = self.store.apply_operations(template, operations)
        self.assertEqual(first, second)
        self.assertEqual(
            "nodes.context.output.subject",
            next(item for item in first["nodes"] if item["id"] == "finish")["config"]["inputMapping"]["subject"],
        )
        self.assertTrue(self.store.validate(first)["valid"], self.store.validate(first)["issues"])

    def test_planner_cannot_remove_an_approval_boundary(self):
        template = self.store.get("templates", "customer-resolution")
        with self.assertRaises(APIError) as denied:
            self.store.apply_operations(template, [{"op": "remove_node", "nodeId": "approval"}])
        self.assertEqual("AUTHORITY_REDUCTION_DENIED", denied.exception.code)

    def test_agent_replacement_is_limited_to_same_active_implementation(self):
        alias = self.call("create_agent", {
            "name": "Alternate policy registration", "implementationId": "policy",
        }, AUTHOR)
        template = self.store.get("templates", "customer-resolution")
        replaced = self.store.apply_operations(template, [{
            "op": "replace_agent", "nodeId": "policy", "agentId": alias["id"],
        }])
        self.assertEqual(alias["id"], next(
            item for item in replaced["nodes"] if item["id"] == "policy"
        )["agentId"])

        with self.assertRaises(APIError) as denied:
            self.store.apply_operations(template, [{
                "op": "replace_agent", "nodeId": "policy", "agentId": "ticket",
            }])
        self.assertEqual("AUTHORITY_EXPANSION_DENIED", denied.exception.code)

    def test_remove_node_is_bounded_to_known_non_approval_nodes(self):
        template = self.candidate(
            [node("start", "intake", 0), node("context", "enrich", 250),
             node("finish", "receipt", 500)],
            [{"id": "one", "source": "start", "target": "context"},
             {"id": "two", "source": "context", "target": "finish"}],
        )
        result = self.store.apply_operations(template, [{
            "op": "remove_node", "nodeId": "context",
        }])
        self.assertEqual(["start", "finish"], [item["id"] for item in result["nodes"]])
        self.assertEqual([], result["edges"])
        with self.assertRaises(APIError) as denied:
            self.store.apply_operations(template, [{"op": "remove_node", "nodeId": "missing"}])
        self.assertEqual("INVALID_PROPOSAL", denied.exception.code)

    def test_unused_custom_agent_can_be_deleted_but_references_are_preserved(self):
        unused = self.call("create_agent", {
            "name": "Disposable enrichment", "implementationId": "enrich",
        }, AUTHOR)
        with self.assertRaises(APIError) as denied:
            self.call("delete_agent", unused["id"], CONTRIBUTOR)
        self.assertEqual("ROLE_DENIED", denied.exception.code)
        deleted = self.call("delete_agent", unused["id"], AUTHOR)
        self.assertTrue(deleted["deleted"])

        referenced = self.call("create_agent", {
            "name": "Referenced enrichment", "implementationId": "enrich",
        }, AUTHOR)
        draft = self.call("create_template", {
            "name": "Reference holder", "description": "Protect registry history",
        }, AUTHOR)
        self.call("update_template", draft["id"], {
            "expectedRevision": draft["draftRevision"],
            "nodes": [node("start", "intake", 0), node("custom", referenced["id"], 250)],
            "edges": [{"id": "start_custom", "source": "start", "target": "custom"}],
        }, AUTHOR)
        with self.assertRaises(APIError) as denied:
            self.call("delete_agent", referenced["id"], AUTHOR)
        self.assertEqual("AGENT_IN_USE", denied.exception.code)
        with self.assertRaises(APIError) as denied:
            self.call("delete_agent", "intake", AUTHOR)
        self.assertEqual("BUILTIN_AGENT_IMMUTABLE", denied.exception.code)


if __name__ == "__main__":
    unittest.main()
