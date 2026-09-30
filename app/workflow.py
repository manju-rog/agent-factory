"""Bounded workflow graph validation and deterministic compilation.

This module deliberately has no database, HTTP, clock, or random dependency.
It turns a versioned editor graph into a compact plan that can be pinned on a
release and interpreted by the local scheduler (or another durable authority).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain import RuleError, content_hash, evaluate_rule


COMPILER_VERSION = "axiom.compiler.v1"
INTERPRETER_VERSION = "axiom.interpreter.v1"
NODE_TYPES = {
    "start", "agent", "condition", "parallel_split", "join", "approval",
    "outcome", "delay", "end",
}


@dataclass(frozen=True)
class GraphIssue:
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        result = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.node_id:
            result["nodeId"] = self.node_id
        if self.edge_id:
            result["edgeId"] = self.edge_id
        return result


class GraphCompileError(ValueError):
    def __init__(self, issues: list[GraphIssue]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def implementation_node_type(agent: dict[str, Any]) -> str:
    implementation = agent.get("implementationId", agent.get("id"))
    controls = {
        "condition": "condition", "parallel": "parallel_split", "join": "join",
        "outcome": "outcome", "end": "end",
    }
    if implementation in controls:
        return controls[implementation]
    if agent.get("kind") == "human" or implementation == "approval":
        return "approval"
    return "agent"


def node_type(node: dict[str, Any], agents: dict[str, dict[str, Any]]) -> str:
    declared = node.get("type") or node.get("config", {}).get("nodeType")
    if declared:
        return declared
    agent = agents.get(node.get("agentId"), {})
    return implementation_node_type(agent)


def _reachable(start: str, outgoing: dict[str, list[str]], *, stop: str | None = None) -> set[str]:
    seen: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in seen or current == stop:
            continue
        seen.add(current)
        queue.extend(outgoing.get(current, []))
    return seen


def _topological(ids: set[str], outgoing: dict[str, list[str]], incoming: dict[str, list[str]]) -> list[str]:
    degree = {ident: len(incoming[ident]) for ident in ids}
    queue = sorted(ident for ident, count in degree.items() if count == 0)
    result: list[str] = []
    while queue:
        current = queue.pop(0)
        result.append(current)
        for target in sorted(outgoing[current]):
            degree[target] -= 1
            if degree[target] == 0:
                queue.append(target)
                queue.sort()
    return result


def analyze_graph(template: dict[str, Any], agents: dict[str, dict[str, Any]], *, max_nodes: int = 100,
                  max_edges: int = 300, max_nesting: int = 5) -> dict[str, Any]:
    """Validate the bounded language and return normalized graph facts."""
    issues: list[GraphIssue] = []
    nodes = template.get("nodes")
    edges = template.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"valid": False, "issues": [GraphIssue("GRAPH_TYPE", "nodes and edges must be arrays.").as_dict()]}
    if not nodes:
        issues.append(GraphIssue("GRAPH_EMPTY", "A releasable workflow needs at least one executable node."))
    if len(nodes) > max_nodes or len(edges) > max_edges:
        issues.append(GraphIssue("GRAPH_LIMIT", f"Graph exceeds the {max_nodes}-node or {max_edges}-edge limit."))
    by_id: dict[str, dict[str, Any]] = {}
    types: dict[str, str] = {}
    for node in nodes:
        ident = node.get("id") if isinstance(node, dict) else None
        if not isinstance(ident, str) or not ident:
            issues.append(GraphIssue("NODE_ID", "Every node requires a non-empty string ID."))
            continue
        if ident in by_id:
            issues.append(GraphIssue("DUPLICATE_NODE", f"Node ID {ident!r} is duplicated.", ident))
            continue
        by_id[ident] = node
        kind = node_type(node, agents)
        types[ident] = kind
        declared = node.get("type") or node.get("config", {}).get("nodeType")
        registered = agents.get(node.get("agentId"))
        if declared is not None and registered and declared != implementation_node_type(registered):
            issues.append(GraphIssue(
                "NODE_TYPE_IMPLEMENTATION_MISMATCH",
                "Declared node type does not match the registered runtime implementation.",
                ident,
            ))
        if kind not in NODE_TYPES:
            issues.append(GraphIssue("NODE_TYPE", f"Node type {kind!r} is unsupported.", ident))
        if kind == "delay":
            seconds = node.get("config", {}).get("delaySeconds")
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 <= seconds <= 86400:
                issues.append(GraphIssue("DELAY_BOUND", "Delay must be between 0 and 86400 seconds.", ident))
        if kind == "outcome" and node.get("config", {}).get("outcome") not in {"rejected", "expired", "completed"}:
            issues.append(GraphIssue("OUTCOME_TYPE", "Outcome must declare rejected, expired, or completed.", ident))
    ids = set(by_id)
    incoming = {ident: [] for ident in ids}
    outgoing = {ident: [] for ident in ids}
    edges_by_source: dict[str, list[dict[str, Any]]] = {ident: [] for ident in ids}
    edge_ids: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            issues.append(GraphIssue("EDGE_TYPE", "Every edge must be an object."))
            continue
        ident = edge.get("id")
        source, target = edge.get("source"), edge.get("target")
        if not isinstance(ident, str) or not ident or ident in edge_ids:
            issues.append(GraphIssue("EDGE_ID", "Every edge requires a unique non-empty string ID.", edge_id=ident if isinstance(ident, str) else None))
        else:
            edge_ids.add(ident)
        if source not in ids or target not in ids:
            issues.append(GraphIssue("DANGLING_EDGE", "Every edge endpoint must reference an existing node.", edge_id=ident if isinstance(ident, str) else None))
            continue
        if source == target or (source, target) in pairs:
            issues.append(GraphIssue("DUPLICATE_EDGE", "Self edges and duplicate dependencies are not allowed.", target, ident if isinstance(ident, str) else None))
        pairs.add((source, target))
        outgoing[source].append(target)
        incoming[target].append(source)
        edges_by_source[source].append(edge)
    roots = sorted(ident for ident in ids if not incoming[ident])
    sinks = sorted(ident for ident in ids if not outgoing[ident])
    if len(roots) != 1:
        issues.append(GraphIssue("ONE_START", "A workflow must have exactly one starting node."))
    if len(sinks) != 1:
        issues.append(GraphIssue("ONE_END", "A workflow must have exactly one final node."))
    explicit_start = [ident for ident, kind in types.items() if kind == "start"]
    explicit_end = [ident for ident, kind in types.items() if kind == "end"]
    if explicit_start and (len(explicit_start) != 1 or explicit_start[0] not in roots):
        issues.append(GraphIssue("START_POSITION", "The single Start node must be the graph root.", explicit_start[0] if explicit_start else None))
    if explicit_end and (len(explicit_end) != 1 or explicit_end[0] not in sinks):
        issues.append(GraphIssue("END_POSITION", "The single End node must be the graph sink.", explicit_end[0] if explicit_end else None))
    order = _topological(ids, outgoing, incoming)
    if len(order) != len(ids):
        issues.append(GraphIssue("CYCLE", "The bounded workflow language does not allow cycles."))
    elif roots:
        reachable = _reachable(roots[0], outgoing)
        for ident in sorted(ids - reachable):
            issues.append(GraphIssue("UNREACHABLE_NODE", "Node is unreachable from Start.", ident))

    scopes: list[dict[str, Any]] = []
    paired_joins: set[str] = set()
    for ident in sorted(ids):
        kind = types.get(ident)
        config = by_id[ident].get("config", {}) if isinstance(by_id[ident].get("config", {}), dict) else {}
        if kind == "condition":
            try:
                evaluate_rule(config.get("rule"), {})
            except RuleError as exc:
                # Missing paths are valid and simply evaluate false. Syntax errors are not.
                if "Unsupported" in str(exc) or "requires" in str(exc) or "must" in str(exc) or "exceeds" in str(exc):
                    issues.append(GraphIssue("CONDITION_RULE", str(exc), ident))
            branches = edges_by_source[ident]
            labels = [edge.get("branch") for edge in branches]
            if len(branches) != 2 or set(labels) != {"match", "default"}:
                issues.append(GraphIssue("CONDITION_BRANCHES", "Condition requires exactly one match edge and one default edge.", ident))
            merge = config.get("mergeId")
            if merge not in ids or types.get(merge) != "join":
                issues.append(GraphIssue("CONDITION_MERGE", "Condition requires a valid Join mergeId.", ident))
            elif merge:
                paired_joins.add(merge)
                scopes.append({"kind": "condition", "source": ident, "join": merge, "branches": [edge.get("target") for edge in branches]})
        elif kind == "parallel_split":
            branches = edges_by_source[ident]
            if len(branches) < 2:
                issues.append(GraphIssue("PARALLEL_BRANCHES", "Parallel split requires at least two outgoing branches.", ident))
            join = config.get("joinId")
            if join not in ids or types.get(join) != "join":
                issues.append(GraphIssue("PARALLEL_JOIN", "Parallel split requires a valid Join joinId.", ident))
            elif join:
                paired_joins.add(join)
                scopes.append({"kind": "parallel", "source": ident, "join": join, "branches": [edge.get("target") for edge in branches]})
        elif kind == "join" and ident not in paired_joins:
            # paired_joins may be populated by a later node, so this is checked below.
            pass

    for ident, kind in types.items():
        if kind == "join" and ident not in paired_joins:
            issues.append(GraphIssue("UNPAIRED_JOIN", "Every Join must be paired with one Condition or Parallel split.", ident))
    join_owners: dict[str, str] = {}
    for scope in scopes:
        join = scope["join"]
        if join in join_owners:
            issues.append(GraphIssue("JOIN_REUSED", "A Join cannot close more than one structured scope.", join))
        join_owners[join] = scope["source"]
        branch_sets = [_reachable(branch, outgoing, stop=join) for branch in scope["branches"] if branch in ids]
        for index, branch_set in enumerate(branch_sets):
            if join not in _reachable(scope["branches"][index], outgoing):
                issues.append(GraphIssue("BRANCH_MISSING_JOIN", "Every structured branch must reach its paired Join.", scope["branches"][index]))
            for current in branch_set:
                for target in outgoing[current]:
                    if target != join and target not in branch_set:
                        issues.append(GraphIssue("BRANCH_CROSSING", "A structured branch cannot cross into another scope before its Join.", current))
        for left in range(len(branch_sets)):
            for right in range(left + 1, len(branch_sets)):
                overlap = (branch_sets[left] & branch_sets[right]) - {join}
                if overlap:
                    issues.append(GraphIssue("EARLY_BRANCH_MERGE", "Branches may merge only at their paired Join.", sorted(overlap)[0]))

    # A stack over topological order catches improperly interleaved scopes.  It
    # is conservative by design and caps nested authoring complexity.
    if len(order) == len(ids):
        opened = {scope["source"]: scope for scope in scopes}
        closed = {scope["join"]: scope for scope in scopes}
        active: list[str] = []
        max_seen = 0
        for ident in order:
            if ident in opened:
                active.append(ident)
                max_seen = max(max_seen, len(active))
            if ident in closed:
                owner = closed[ident]["source"]
                if not active or active[-1] != owner:
                    issues.append(GraphIssue("CROSSING_SCOPE", "Structured scopes must be properly nested.", ident))
                elif active:
                    active.pop()
        if max_seen > max_nesting:
            issues.append(GraphIssue("NESTING_LIMIT", f"Structured nesting exceeds {max_nesting} levels."))

    return {
        "valid": not any(issue.severity == "error" for issue in issues),
        "issues": [issue.as_dict() for issue in issues],
        "order": order,
        "roots": roots,
        "sinks": sinks,
        "types": types,
        "incoming": incoming,
        "outgoing": outgoing,
        "scopes": scopes,
        "facts": {
            "nodeCount": len(nodes), "edgeCount": len(edges),
            "conditionCount": sum(kind == "condition" for kind in types.values()),
            "parallelCount": sum(kind == "parallel_split" for kind in types.values()),
            "maximumNesting": max((len(scopes), 0)) if scopes else 0,
        },
    }


def compile_graph(template: dict[str, Any], agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    analysis = analyze_graph(template, agents)
    if not analysis["valid"]:
        raise GraphCompileError([
            GraphIssue(issue["code"], issue["message"], issue.get("nodeId"), issue.get("edgeId"), issue.get("severity", "error"))
            for issue in analysis["issues"]
        ])
    nodes = {node["id"]: node for node in template["nodes"]}
    instructions = []
    for ident in analysis["order"]:
        node = nodes[ident]
        kind = analysis["types"][ident]
        instruction = {
            "id": ident,
            "op": kind,
            "agentId": node.get("agentId"),
            "dependencies": sorted(analysis["incoming"][ident]),
            "successors": sorted(analysis["outgoing"][ident]),
            "config": node.get("config", {}),
        }
        instructions.append(instruction)
    plan = {
        "schemaVersion": "axiom.plan.v1",
        "compilerVersion": COMPILER_VERSION,
        "interpreterVersion": INTERPRETER_VERSION,
        "templateId": template.get("id"),
        "instructions": instructions,
        "scopes": analysis["scopes"],
    }
    plan["planHash"] = content_hash(plan)
    return plan


def condition_selection(plan_instruction: dict[str, Any], context: dict[str, Any], edges: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Return selected target and non-selected targets for a condition."""
    if plan_instruction.get("op") != "condition":
        raise ValueError("condition_selection requires a condition instruction")
    matched = evaluate_rule(plan_instruction.get("config", {}).get("rule"), context)
    branch = "match" if matched else "default"
    candidates = [edge for edge in edges if edge.get("source") == plan_instruction["id"]]
    selected = next((edge.get("target") for edge in candidates if edge.get("branch") == branch), None)
    if not selected:
        raise GraphCompileError([GraphIssue("CONDITION_BRANCH_MISSING", f"Condition has no {branch} branch at runtime.", plan_instruction["id"])])
    return selected, [edge["target"] for edge in candidates if edge.get("target") != selected]
