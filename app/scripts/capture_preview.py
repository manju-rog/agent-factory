"""Build a portable, network-free preview from actual local runtime records.

Run from axiom_app: python3 scripts/capture_preview.py --output ../output_v2
The temporary execution database is removed; the generated preview cannot write.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from server import DEMO_WORKFLOWS, Store, USERS
import factory_fixtures


def capture():
    author, reviewer, operator, contributor = USERS
    with tempfile.TemporaryDirectory() as temp:
        store = Store(Path(temp) / "preview.sqlite3", latency=0)
        try:
            def call(method, *args):
                return store.atomic(getattr(store, method), *args)

            def until(run_id, status):
                for _ in range(100):
                    run = store.get("runs", run_id)
                    if run["status"] == status:
                        return run
                    store.tick()
                raise RuntimeError(f"Preview case did not reach {status}: {run['status']}")

            def start(subject, scenario="happy", *, template_id="customer-resolution",
                      mode="fixture", task_input=None):
                payload = {"subject": subject} if task_input is None else task_input
                return call("create_run", {
                    "templateId": template_id, "mode": mode,
                    "scenario": scenario, "input": payload,
                }, contributor)

            def approve(run_id):
                run = until(run_id, "waiting_approval")
                for node in run["nodes"]:
                    if node["status"] == "waiting_approval":
                        prepared = [{
                            key: action[key]
                            for key in ("effectId", "nodeId", "operationGeneration",
                                        "actionFingerprint", "approvalEnvelopeHash")
                        } for action in node.get("approvalPacket", {}).get("actions", [])]
                        call("approve", run_id, {"nodeId": node["nodeId"],
                             "decision": "approve", "comment": "Reviewed local fixture evidence.",
                             "preparedActions": prepared}, reviewer)

            def run_factory_case(scenario):
                """Record one explicitly scripted Goal Agent case for the offline preview."""
                public = call("create_agent_run", {
                    "specId": scenario["specId"],
                    "goal": scenario["description"],
                    "input": scenario["input"],
                    "mode": "fixture",
                    "scenario": scenario["id"],
                }, author)
                run_id = public["id"]
                for _ in range(40):
                    internal = store.get("agent_runs", run_id)
                    status = internal["_state"]["status"]
                    if status in {"completed", "failed", "stopped"}:
                        return run_id
                    if status == "awaiting_approval":
                        action = internal["_state"]["pendingAction"]
                        call("decide_agent_action", run_id, {
                            "decision": "approve",
                            "expectedActionHash": action["actionHash"],
                            "comment": "Approved only for the recorded local fixture preview.",
                        }, reviewer)
                    elif status == "awaiting_input":
                        answers = scenario.get("resumeAnswers")
                        if not isinstance(answers, dict) or not answers:
                            raise RuntimeError(
                                f"Factory preview case needs an undeclared answer: {scenario['id']}"
                            )
                        call("clarify_agent_run", run_id, {"answers": answers}, author)
                    else:
                        # advance_agent_run owns its own short revision-bound claims and
                        # deliberately performs provider/tool I/O outside Store.atomic.
                        store.advance_agent_run(run_id, author)
                raise RuntimeError(f"Factory preview case did not finish: {scenario['id']}")

            completed = start("Resolve a service request with reviewed evidence")
            approve(completed["id"])
            until(completed["id"], "completed")
            ambiguous = start("Reconcile a ticket after its response was lost", "after_write_timeout")
            approve(ambiguous["id"])
            until(ambiguous["id"], "needs_attention")
            waiting = start("Review an incoming service request")
            until(waiting["id"], "waiting_approval")
            demo_runs = []
            for spec in DEMO_WORKFLOWS:
                demo = start(
                    spec["exampleInput"]["subject"], template_id=spec["id"],
                    mode="simulation", task_input=spec["exampleInput"],
                )
                approve(demo["id"])
                until(demo["id"], "completed")
                demo_runs.append(demo["id"])
            factory_case_ids = [run_factory_case(scenario)
                                for scenario in factory_fixtures.demo_scenarios()]
            experiment = call("create_experiment", {
                "templateId": DEMO_WORKFLOWS[0]["id"], "suite": "required",
            }, author)
            for _ in range(300):
                store.tick()
                if store.experiment(experiment["id"])["status"] == "completed":
                    break
            data = store.bootstrap(author, "preview-no-session")
            data["preview"] = {"recorded": True, "description": "Recorded local fixture executions; interface actions do not contact a server."}
            data["preview"]["demoRuns"] = demo_runs
            data["preview"]["factoryRuns"] = factory_case_ids
            data["runEvidence"] = {run["id"]: store.evidence(run["id"]) for run in data["runs"]}
            data["runEffects"] = {
                run["id"]: {"runId": run["id"], "effects": store.effect_summary(run["id"])["items"],
                            "summary": store.effect_summary(run["id"])}
                for run in data["runs"]
            }
            data["repairs"] = {run["id"]: store.repair(run["id"]) for run in data["runs"]}
            data["experiments"] = [store.experiment(experiment["id"])]
            data["audit"] = [{"id": row["id"], **json.loads(row["data"])}
                             for row in store.db.execute("SELECT id,data FROM audit ORDER BY id DESC LIMIT 200")]
            data["capturedValidations"] = {
                template["id"]: store.validate(template) for template in data["templates"]
            }
            data["capturedDiffs"] = {
                template["id"]: store.diff_template(template["id"])
                for template in data["templates"]
            }
            return data
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=APP.parent / "output_v2")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = capture()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (APP / "public/index.html").read_text()
    html = html.replace('<script src="/theme.js"></script>',
                        '<script>' + (APP / "public/theme.js").read_text() + '</script>')
    html = html.replace('<link rel="stylesheet" href="/styles.css">',
                        '<style>' + (APP / "public/styles.css").read_text() + '</style>')
    html = html.replace('<script src="/icons.js"></script>',
                        '<script>' + (APP / "public/icons.js").read_text() + '</script>')
    html = html.replace('<script src="/app.js"></script>',
                        '<script>window.AXIOM_PREVIEW_DATA=' + payload + ';</script>\n<script>'
                        + (APP / "public/app.js").read_text() + '</script>')
    target = args.output / "Axiom_Studio_Preview.html"
    target.write_text(html)
    (args.output / "preview_data.json").write_text(json.dumps(data, ensure_ascii=False))
    print(json.dumps({"preview": str(target), "recordedRuns": len(data["runs"]),
                      "experiment": data["experiments"][0]["metrics"]}))


if __name__ == "__main__":
    main()
