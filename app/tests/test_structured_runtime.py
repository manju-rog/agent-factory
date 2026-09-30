import copy
from pathlib import Path
import tempfile
import time
import unittest

from server import DEFAULT_CONFIG, Store, USERS


AUTHOR, REVIEWER, _, CONTRIBUTOR = USERS


def node(ident, agent, x, y, **config):
    return {"id": ident, "agentId": agent, "label": ident.replace("_", " ").title(),
            "x": x, "y": y, "config": {**copy.deepcopy(DEFAULT_CONFIG), **config}}


class StructuredRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "structured.sqlite3", latency=0.05)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def publish(self, nodes, edges):
        template = self.call("create_template", {"name": "Structured workflow", "description": "Condition and parallel semantics"}, AUTHOR)
        self.call("update_template", template["id"], {"expectedRevision": 1, "nodes": nodes, "edges": edges}, AUTHOR)
        self.call("submit_template", template["id"], AUTHOR)
        return self.call("publish_template", template["id"], REVIEWER)

    def settle(self, run_id, limit=100):
        for _ in range(limit):
            self.store.tick()
            run = self.store.get("runs", run_id)
            if run["status"] in {"completed", "rejected", "expired", "needs_attention"}:
                return run
            time.sleep(0.01)
        self.fail("structured run did not settle")

    def test_condition_skips_one_branch_and_parallel_work_overlaps(self):
        nodes = [
            node("intake", "intake", 0, 100),
            node("choose", "condition", 250, 100, rule={"op": "gte", "path": "amount", "value": 100}, mergeId="choice_join"),
            node("high", "policy", 500, 20), node("low", "enrich", 500, 200),
            node("choice_join", "join", 750, 100),
            node("split", "parallel", 1000, 100, joinId="parallel_join"),
            node("owner", "ownership", 1250, 20), node("research", "enrich", 1250, 200),
            node("parallel_join", "join", 1500, 100), node("finish", "end", 1750, 100),
        ]
        raw_edges = [
            ("intake", "choose", None), ("choose", "high", "match"), ("choose", "low", "default"),
            ("high", "choice_join", None), ("low", "choice_join", None),
            ("choice_join", "split", None), ("split", "owner", None), ("split", "research", None),
            ("owner", "parallel_join", None), ("research", "parallel_join", None), ("parallel_join", "finish", None),
        ]
        edges = [{"id": f"edge_{index}", "source": source, "target": target, **({"branch": branch} if branch else {})}
                 for index, (source, target, branch) in enumerate(raw_edges)]
        published = self.publish(nodes, edges)
        snapshot = published["versions"][-1]["snapshot"]
        self.assertEqual("axiom.contract.v1", snapshot["schemaVersion"])
        self.assertEqual("axiom.plan.v1", snapshot["compiledPlan"]["schemaVersion"])
        self.assertNotEqual(snapshot["semanticHash"], snapshot["layoutHash"])
        run = self.call("create_run", {"templateId": published["id"], "mode": "fixture", "input": {"amount": 150}}, CONTRIBUTOR)
        saw_overlap = False
        for _ in range(100):
            self.store.tick()
            current = self.store.get("runs", run["id"])
            states = {item["nodeId"]: item["status"] for item in current["nodes"]}
            if states["owner"] == states["research"] == "running":
                saw_overlap = True
            if current["status"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual("completed", current["status"])
        self.assertTrue(saw_overlap, "parallel branches should be active during the same scheduler interval")
        self.assertEqual("succeeded", states["high"])
        self.assertEqual("skipped", states["low"])
        self.assertEqual("succeeded", states["choice_join"])

    def test_terminal_outcome_stops_successors(self):
        nodes = [
            node("intake", "intake", 0, 100),
            node("decline", "outcome", 250, 100, outcome="rejected", reason="Required information is incomplete"),
            node("finish", "end", 500, 100),
        ]
        edges = [
            {"id": "first", "source": "intake", "target": "decline"},
            {"id": "second", "source": "decline", "target": "finish"},
        ]
        published = self.publish(nodes, edges)
        run = self.call("create_run", {"templateId": published["id"], "mode": "fixture"}, CONTRIBUTOR)
        finished = self.settle(run["id"])
        states = {item["nodeId"]: item["status"] for item in finished["nodes"]}
        self.assertEqual("rejected", finished["status"])
        self.assertEqual("succeeded", states["decline"])
        self.assertEqual("cancelled", states["finish"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

    def test_mapping_from_only_one_conditional_path_is_rejected(self):
        nodes = [
            node("intake", "intake", 0, 100),
            node("choose", "condition", 250, 100,
                 rule={"op": "gte", "path": "amount", "value": 100}, mergeId="choice_join"),
            node("high", "policy", 500, 20),
            node("low", "enrich", 500, 200),
            node("choice_join", "join", 750, 100),
            node("finish", "receipt", 1000, 100,
                 inputMapping={"subject": "nodes.high.output.subject"}),
        ]
        raw_edges = [
            ("intake", "choose", None), ("choose", "high", "match"),
            ("choose", "low", "default"), ("high", "choice_join", None),
            ("low", "choice_join", None), ("choice_join", "finish", None),
        ]
        edges = [{"id": f"edge_{index}", "source": source, "target": target,
                  **({"branch": branch} if branch else {})}
                 for index, (source, target, branch) in enumerate(raw_edges)]
        template = self.call(
            "create_template",
            {"name": "Path-invalid mapping", "description": "Mapping must dominate target"},
            AUTHOR,
        )
        saved = self.call("update_template", template["id"], {
            "expectedRevision": template["draftRevision"], "nodes": nodes, "edges": edges,
        }, AUTHOR)
        validation = self.store.validate(saved)
        self.assertFalse(validation["valid"])
        self.assertIn(
            ("MAPPING_PATH", "finish"),
            {(issue["code"], issue.get("nodeId")) for issue in validation["issues"]},
        )


if __name__ == "__main__":
    unittest.main()
