"""Deterministic P2 governance services for the local Axiom application.

The module is deliberately independent of HTTP, SQLite, and the browser.  It
validates complete inputs before returning a result and never mutates caller
owned records.  Server routes can be added later around these domain services.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional, Sequence
import unicodedata


class GovernanceError(ValueError):
    """Base error for governance validation failures."""


class ValidationError(GovernanceError):
    """The supplied domain object is incomplete, ambiguous, or unsafe."""


class BudgetExceededError(ValidationError):
    """A team execution plan exceeds one of its declared limits."""


_TOKEN = re.compile(r"[a-z0-9]+")
_LIFECYCLES = frozenset({"draft", "submitted", "published", "archived"})


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{field_name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field_name} must be a non-negative integer")
    return value


def _decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError(f"{field_name} must use Decimal, int, or a decimal string")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a finite decimal") from None
    if not result.is_finite():
        raise ValidationError(f"{field_name} must be a finite decimal")
    return result


def _string_tuple(values: Iterable[Any], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, Mapping)):
        raise ValidationError(f"{field_name} must be an iterable of strings, not a scalar or object")
    try:
        items = tuple(_required_text(value, field_name) for value in values)
    except TypeError:
        raise ValidationError(f"{field_name} must be an iterable of strings") from None
    if len(items) != len(set(items)):
        raise ValidationError(f"{field_name} must not contain duplicates")
    return items


def _string_set(values: Iterable[Any], field_name: str) -> frozenset[str]:
    return frozenset(_string_tuple(values, field_name))


def _freeze_json(value: Any, path: str = "value") -> Any:
    """Validate and freeze a JSON-compatible value without retaining mutability."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} contains a non-string object key")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, f"{path}[]") for item in value)
    raise ValidationError(f"{path} contains unsupported value type {type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _tokens(value: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return frozenset(_TOKEN.findall(normalized))


# ---------------------------------------------------------------------------
# Versioned reusable insertion blocks


@dataclass(frozen=True)
class BlockNode:
    node_key: str
    agent_id: str
    label: str
    config: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_key", _required_text(self.node_key, "node_key"))
        object.__setattr__(self, "agent_id", _required_text(self.agent_id, "agent_id"))
        object.__setattr__(self, "label", _required_text(self.label, "label"))
        object.__setattr__(self, "config", _freeze_json(self.config, "node.config"))
        object.__setattr__(self, "metadata", _freeze_json(self.metadata, "node.metadata"))


@dataclass(frozen=True)
class BlockEdge:
    edge_key: str
    source_key: str
    target_key: str
    source_port: Optional[str] = None
    target_port: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_key", _required_text(self.edge_key, "edge_key"))
        object.__setattr__(self, "source_key", _required_text(self.source_key, "source_key"))
        object.__setattr__(self, "target_key", _required_text(self.target_key, "target_key"))
        if self.source_port is not None:
            object.__setattr__(self, "source_port", _required_text(self.source_port, "source_port"))
        if self.target_port is not None:
            object.__setattr__(self, "target_port", _required_text(self.target_port, "target_port"))
        object.__setattr__(self, "metadata", _freeze_json(self.metadata, "edge.metadata"))


@dataclass(frozen=True)
class InsertionBlock:
    block_id: str
    version: int
    name: str
    nodes: tuple[BlockNode, ...]
    edges: tuple[BlockEdge, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", _required_text(self.block_id, "block_id"))
        object.__setattr__(self, "version", _positive_int(self.version, "block.version"))
        object.__setattr__(self, "name", _required_text(self.name, "block.name"))
        try:
            nodes = tuple(self.nodes)
            edges = tuple(self.edges)
        except TypeError:
            raise ValidationError("block nodes and edges must be iterable") from None
        if not nodes or any(not isinstance(node, BlockNode) for node in nodes):
            raise ValidationError("block must contain at least one BlockNode")
        if any(not isinstance(edge, BlockEdge) for edge in edges):
            raise ValidationError("block edges must contain only BlockEdge values")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)

        node_keys = [node.node_key for node in nodes]
        edge_keys = [edge.edge_key for edge in edges]
        if len(node_keys) != len(set(node_keys)):
            raise ValidationError("block node keys must be unique")
        if len(edge_keys) != len(set(edge_keys)):
            raise ValidationError("block edge keys must be unique")
        known = set(node_keys)
        for edge in edges:
            if edge.source_key not in known or edge.target_key not in known:
                raise ValidationError(f"block edge {edge.edge_key} references an unknown node")
            if edge.source_key == edge.target_key:
                raise ValidationError(f"block edge {edge.edge_key} creates a self-cycle")
        _require_acyclic(node_keys, edges)


def _require_acyclic(node_keys: Sequence[str], edges: Sequence[BlockEdge]) -> None:
    indegree = {key: 0 for key in node_keys}
    outgoing = {key: [] for key in node_keys}
    for edge in edges:
        indegree[edge.target_key] += 1
        outgoing[edge.source_key].append(edge.target_key)
    ready = sorted(key for key, count in indegree.items() if count == 0)
    visited = 0
    while ready:
        key = ready.pop(0)
        visited += 1
        for target in sorted(outgoing[key]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if visited != len(node_keys):
        raise ValidationError("insertion block graph must be acyclic")


@dataclass(frozen=True)
class BlockExpansion:
    template: Mapping[str, Any]
    node_id_map: Mapping[str, str]
    edge_id_map: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "template", _freeze_json(self.template, "expanded_template"))
        object.__setattr__(self, "node_id_map", MappingProxyType(dict(self.node_id_map)))
        object.__setattr__(self, "edge_id_map", MappingProxyType(dict(self.edge_id_map)))

    def to_template(self) -> dict[str, Any]:
        """Return an independent mutable copy suitable for later draft editing."""

        return _thaw_json(self.template)


def _derived_id(kind: str, block: InsertionBlock, insertion_id: str, local_key: str) -> str:
    raw = f"{kind}\x00{block.block_id}\x00{block.version}\x00{insertion_id}\x00{local_key}"
    return f"{kind}-{sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def expand_insertion_block(
    block: InsertionBlock,
    template: Mapping[str, Any],
    insertion_id: str,
) -> BlockExpansion:
    """Expand ``block`` into a copied template using deterministic fresh IDs.

    ``insertion_id`` is an operation identity supplied by the caller. Reusing it
    in the same template fails on ID collision instead of silently duplicating or
    rewriting nodes.
    """

    if not isinstance(block, InsertionBlock):
        raise ValidationError("block must be an InsertionBlock")
    insertion_id = _required_text(insertion_id, "insertion_id")
    if not isinstance(template, Mapping):
        raise ValidationError("template must be an object")
    expanded = _thaw_json(_freeze_json(template, "template"))
    nodes = expanded.get("nodes")
    edges = expanded.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValidationError("template must contain nodes and edges arrays")

    existing_node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValidationError(f"template.nodes[{index}] must be an object")
        node_id = _required_text(node.get("id"), f"template.nodes[{index}].id")
        if node_id in existing_node_ids:
            raise ValidationError(f"duplicate template node id {node_id}")
        existing_node_ids.add(node_id)

    existing_edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValidationError(f"template.edges[{index}] must be an object")
        edge_id = _required_text(edge.get("id"), f"template.edges[{index}].id")
        source = _required_text(edge.get("source"), f"template.edges[{index}].source")
        target = _required_text(edge.get("target"), f"template.edges[{index}].target")
        if edge_id in existing_edge_ids:
            raise ValidationError(f"duplicate template edge id {edge_id}")
        if source not in existing_node_ids or target not in existing_node_ids:
            raise ValidationError(f"template edge {edge_id} references an unknown node")
        existing_edge_ids.add(edge_id)

    node_id_map = {
        node.node_key: _derived_id("node", block, insertion_id, node.node_key)
        for node in block.nodes
    }
    edge_id_map = {
        edge.edge_key: _derived_id("edge", block, insertion_id, edge.edge_key)
        for edge in block.edges
    }
    if existing_node_ids.intersection(node_id_map.values()):
        raise ValidationError("insertion_id has already been used for a block node")
    if existing_edge_ids.intersection(edge_id_map.values()):
        raise ValidationError("insertion_id has already been used for a block edge")
    if len(set(node_id_map.values())) != len(node_id_map):
        raise ValidationError("generated block node IDs are not unique")
    if len(set(edge_id_map.values())) != len(edge_id_map):
        raise ValidationError("generated block edge IDs are not unique")

    for node in block.nodes:
        nodes.append(
            {
                "id": node_id_map[node.node_key],
                "agentId": node.agent_id,
                "label": node.label,
                "config": _thaw_json(node.config),
                "metadata": _thaw_json(node.metadata),
                "provenance": {
                    "kind": "insertion_block",
                    "sourceBlockId": block.block_id,
                    "sourceBlockVersion": block.version,
                    "sourceNodeKey": node.node_key,
                    "insertionId": insertion_id,
                },
            }
        )
    for edge in block.edges:
        item = {
            "id": edge_id_map[edge.edge_key],
            "source": node_id_map[edge.source_key],
            "target": node_id_map[edge.target_key],
            "metadata": _thaw_json(edge.metadata),
            "provenance": {
                "kind": "insertion_block",
                "sourceBlockId": block.block_id,
                "sourceBlockVersion": block.version,
                "sourceEdgeKey": edge.edge_key,
                "insertionId": insertion_id,
            },
        }
        if edge.source_port is not None:
            item["sourcePort"] = edge.source_port
        if edge.target_port is not None:
            item["targetPort"] = edge.target_port
        edges.append(item)

    return BlockExpansion(expanded, node_id_map, edge_id_map)


# ---------------------------------------------------------------------------
# Permission-filtered deterministic template finding


@dataclass(frozen=True)
class Principal:
    principal_id: str
    workspace_id: str
    roles: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", _required_text(self.principal_id, "principal_id"))
        object.__setattr__(self, "workspace_id", _required_text(self.workspace_id, "workspace_id"))
        object.__setattr__(self, "roles", _string_set(self.roles, "principal.roles"))


@dataclass(frozen=True)
class TemplateRecord:
    template_id: str
    published_version: int
    workspace_id: str
    name: str
    description: str = ""
    tags: tuple[str, ...] = ()
    lifecycle: str = "published"
    is_active: bool = True
    allowed_principal_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_roles: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "template_id", _required_text(self.template_id, "template_id"))
        object.__setattr__(self, "published_version", _positive_int(self.published_version, "published_version"))
        object.__setattr__(self, "workspace_id", _required_text(self.workspace_id, "workspace_id"))
        object.__setattr__(self, "name", _required_text(self.name, "template.name"))
        if not isinstance(self.description, str):
            raise ValidationError("template.description must be a string")
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "tags", _string_tuple(self.tags, "template.tags"))
        lifecycle = _required_text(self.lifecycle, "template.lifecycle").casefold()
        if lifecycle not in _LIFECYCLES:
            raise ValidationError(f"unsupported template lifecycle {lifecycle}")
        object.__setattr__(self, "lifecycle", lifecycle)
        if not isinstance(self.is_active, bool):
            raise ValidationError("template.is_active must be boolean")
        object.__setattr__(
            self,
            "allowed_principal_ids",
            _string_set(self.allowed_principal_ids, "template.allowed_principal_ids"),
        )
        object.__setattr__(self, "allowed_roles", _string_set(self.allowed_roles, "template.allowed_roles"))


@dataclass(frozen=True)
class KeywordContribution:
    keyword: str
    fields: tuple[str, ...]
    points: int


@dataclass(frozen=True)
class TemplateMatch:
    template_id: str
    published_version: int
    name: str
    score: int
    contributions: tuple[KeywordContribution, ...]

    @property
    def explanation(self) -> str:
        if not self.contributions:
            return "Eligible active published template; no search terms supplied."
        parts = [
            f"{item.keyword}: {', '.join(item.fields)} (+{item.points})"
            for item in self.contributions
        ]
        return "; ".join(parts)


def _may_start(principal: Principal, template: TemplateRecord) -> bool:
    if principal.workspace_id != template.workspace_id:
        return False
    return (
        principal.principal_id in template.allowed_principal_ids
        or bool(principal.roles.intersection(template.allowed_roles))
    )


def find_templates(
    templates: Iterable[TemplateRecord],
    principal: Principal,
    query: str,
    *,
    limit: int = 10,
) -> tuple[TemplateMatch, ...]:
    """Return only authorized active published templates with explainable scores."""

    if not isinstance(principal, Principal):
        raise ValidationError("principal must be a Principal")
    if not isinstance(query, str):
        raise ValidationError("query must be a string")
    limit = _positive_int(limit, "limit")
    try:
        records = tuple(templates)
    except TypeError:
        raise ValidationError("templates must be iterable") from None
    if any(not isinstance(item, TemplateRecord) for item in records):
        raise ValidationError("templates must contain only TemplateRecord values")

    active_ids: set[str] = set()
    for item in records:
        if item.lifecycle == "published" and item.is_active:
            if item.template_id in active_ids:
                raise ValidationError(f"multiple active published records for template {item.template_id}")
            active_ids.add(item.template_id)

    query_tokens = sorted(_tokens(query))
    matches: list[TemplateMatch] = []
    for item in records:
        if item.lifecycle != "published" or not item.is_active or not _may_start(principal, item):
            continue
        name_tokens = _tokens(item.name)
        description_tokens = _tokens(item.description)
        tag_tokens = frozenset().union(*(_tokens(tag) for tag in item.tags)) if item.tags else frozenset()
        contributions: list[KeywordContribution] = []
        score = 0
        for keyword in query_tokens:
            fields: list[str] = []
            points = 0
            if keyword in name_tokens:
                fields.append("name")
                points += 6
            if keyword in tag_tokens:
                fields.append("tag")
                points += 3
            if keyword in description_tokens:
                fields.append("description")
                points += 1
            if points:
                contributions.append(KeywordContribution(keyword, tuple(fields), points))
                score += points
        if query_tokens and score == 0:
            continue
        matches.append(
            TemplateMatch(
                template_id=item.template_id,
                published_version=item.published_version,
                name=item.name,
                score=score,
                contributions=tuple(contributions),
            )
        )
    matches.sort(key=lambda match: (-match.score, match.name.casefold(), match.template_id))
    return tuple(matches[:limit])


# ---------------------------------------------------------------------------
# Agent-version impact analysis


@dataclass(frozen=True)
class AgentUse:
    node_id: str
    agent_id: str
    agent_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _required_text(self.node_id, "node_id"))
        object.__setattr__(self, "agent_id", _required_text(self.agent_id, "agent_id"))
        object.__setattr__(self, "agent_version", _required_text(self.agent_version, "agent_version"))


@dataclass(frozen=True)
class WorkflowRelease:
    release_id: str
    template_id: str
    template_version: int
    lifecycle: str
    agent_uses: tuple[AgentUse, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", _required_text(self.release_id, "release_id"))
        object.__setattr__(self, "template_id", _required_text(self.template_id, "template_id"))
        object.__setattr__(self, "template_version", _positive_int(self.template_version, "template_version"))
        lifecycle = _required_text(self.lifecycle, "release.lifecycle").casefold()
        if lifecycle not in _LIFECYCLES:
            raise ValidationError(f"unsupported release lifecycle {lifecycle}")
        object.__setattr__(self, "lifecycle", lifecycle)
        try:
            uses = tuple(self.agent_uses)
        except TypeError:
            raise ValidationError("release.agent_uses must be iterable") from None
        if any(not isinstance(use, AgentUse) for use in uses):
            raise ValidationError("release.agent_uses must contain only AgentUse values")
        node_ids = [use.node_id for use in uses]
        if len(node_ids) != len(set(node_ids)):
            raise ValidationError(f"release {self.release_id} contains duplicate node IDs")
        object.__setattr__(self, "agent_uses", uses)


@dataclass(frozen=True)
class ReleaseImpact:
    release_id: str
    template_id: str
    template_version: int
    lifecycle: str
    node_ids: tuple[str, ...]
    current_versions: tuple[str, ...]
    target_version: str
    affects_future_starts: bool


@dataclass(frozen=True)
class AgentImpactAnalysis:
    agent_id: str
    from_version: Optional[str]
    target_version: str
    impacts: tuple[ReleaseImpact, ...]


def analyze_agent_version_impact(
    releases: Iterable[WorkflowRelease],
    agent_id: str,
    target_version: str,
    *,
    from_version: Optional[str] = None,
) -> AgentImpactAnalysis:
    """Find every supplied release that would change for an agent upgrade."""

    agent_id = _required_text(agent_id, "agent_id")
    target_version = _required_text(target_version, "target_version")
    if from_version is not None:
        from_version = _required_text(from_version, "from_version")
        if from_version == target_version:
            raise ValidationError("from_version and target_version must differ")
    try:
        records = tuple(releases)
    except TypeError:
        raise ValidationError("releases must be iterable") from None
    if any(not isinstance(item, WorkflowRelease) for item in records):
        raise ValidationError("releases must contain only WorkflowRelease values")
    release_ids = [item.release_id for item in records]
    if len(release_ids) != len(set(release_ids)):
        raise ValidationError("release IDs must be unique")

    impacts: list[ReleaseImpact] = []
    for release in records:
        uses = [
            use
            for use in release.agent_uses
            if use.agent_id == agent_id
            and use.agent_version != target_version
            and (from_version is None or use.agent_version == from_version)
        ]
        if not uses:
            continue
        uses.sort(key=lambda use: use.node_id)
        impacts.append(
            ReleaseImpact(
                release_id=release.release_id,
                template_id=release.template_id,
                template_version=release.template_version,
                lifecycle=release.lifecycle,
                node_ids=tuple(use.node_id for use in uses),
                current_versions=tuple(sorted({use.agent_version for use in uses})),
                target_version=target_version,
                affects_future_starts=release.lifecycle == "published",
            )
        )
    impacts.sort(key=lambda item: (item.template_id, item.template_version, item.release_id))
    return AgentImpactAnalysis(agent_id, from_version, target_version, tuple(impacts))


# ---------------------------------------------------------------------------
# Bounded team execution planning


@dataclass(frozen=True)
class ExecutionBudget:
    max_turns: int
    max_tokens: int
    max_time_seconds: int
    max_cost: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_turns", _positive_int(self.max_turns, "budget.max_turns"))
        object.__setattr__(self, "max_tokens", _positive_int(self.max_tokens, "budget.max_tokens"))
        object.__setattr__(
            self,
            "max_time_seconds",
            _positive_int(self.max_time_seconds, "budget.max_time_seconds"),
        )
        cost = _decimal(self.max_cost, "budget.max_cost")
        if cost < 0:
            raise ValidationError("budget.max_cost must be non-negative")
        object.__setattr__(self, "max_cost", cost)
        object.__setattr__(self, "currency", _required_text(self.currency, "budget.currency").upper())


@dataclass(frozen=True)
class TeamParticipant:
    participant_id: str
    role: str
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    can_commit: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "participant_id", _required_text(self.participant_id, "participant_id"))
        object.__setattr__(self, "role", _required_text(self.role, "participant.role"))
        object.__setattr__(self, "allowed_tools", _string_set(self.allowed_tools, "participant.allowed_tools"))
        if not isinstance(self.can_commit, bool):
            raise ValidationError("participant.can_commit must be boolean")


@dataclass(frozen=True)
class TeamRecipe:
    recipe_id: str
    version: int
    participants: tuple[TeamParticipant, ...]
    approved_roles: frozenset[str]
    approved_tools: frozenset[str]
    budget: ExecutionBudget
    commit_actor_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", _required_text(self.recipe_id, "recipe_id"))
        object.__setattr__(self, "version", _positive_int(self.version, "recipe.version"))
        try:
            participants = tuple(self.participants)
        except TypeError:
            raise ValidationError("recipe.participants must be iterable") from None
        if not participants or any(not isinstance(item, TeamParticipant) for item in participants):
            raise ValidationError("recipe must contain at least one TeamParticipant")
        participant_ids = [item.participant_id for item in participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValidationError("recipe participant IDs must be unique")
        object.__setattr__(self, "participants", participants)
        roles = _string_set(self.approved_roles, "recipe.approved_roles")
        tools = _string_set(self.approved_tools, "recipe.approved_tools")
        if not roles:
            raise ValidationError("recipe must approve at least one participant role")
        object.__setattr__(self, "approved_roles", roles)
        object.__setattr__(self, "approved_tools", tools)
        if not isinstance(self.budget, ExecutionBudget):
            raise ValidationError("recipe.budget must be an ExecutionBudget")
        commit_actor_id = _required_text(self.commit_actor_id, "recipe.commit_actor_id")
        object.__setattr__(self, "commit_actor_id", commit_actor_id)

        for participant in participants:
            if participant.role not in roles:
                raise ValidationError(
                    f"participant {participant.participant_id} uses unapproved role {participant.role}"
                )
            unapproved = participant.allowed_tools.difference(tools)
            if unapproved:
                raise ValidationError(
                    f"participant {participant.participant_id} uses unapproved tools {sorted(unapproved)}"
                )
        committers = [item.participant_id for item in participants if item.can_commit]
        if committers != [commit_actor_id]:
            raise ValidationError("recipe must have exactly one designated commit actor")


@dataclass(frozen=True)
class PlannedTeamTurn:
    participant_id: str
    token_reservation: int
    time_reservation_seconds: int
    cost_reservation: Decimal
    tool: Optional[str] = None
    commits_effect: bool = False
    action_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "participant_id", _required_text(self.participant_id, "turn.participant_id"))
        object.__setattr__(
            self,
            "token_reservation",
            _nonnegative_int(self.token_reservation, "turn.token_reservation"),
        )
        object.__setattr__(
            self,
            "time_reservation_seconds",
            _nonnegative_int(self.time_reservation_seconds, "turn.time_reservation_seconds"),
        )
        cost = _decimal(self.cost_reservation, "turn.cost_reservation")
        if cost < 0:
            raise ValidationError("turn.cost_reservation must be non-negative")
        object.__setattr__(self, "cost_reservation", cost)
        if self.tool is not None:
            object.__setattr__(self, "tool", _required_text(self.tool, "turn.tool"))
        if not isinstance(self.commits_effect, bool):
            raise ValidationError("turn.commits_effect must be boolean")
        if self.commits_effect:
            object.__setattr__(self, "action_id", _required_text(self.action_id, "turn.action_id"))
        elif self.action_id is not None:
            raise ValidationError("turn.action_id is only valid for an effect commit")


@dataclass(frozen=True)
class SingleAgentBaselineResult:
    agent_id: str
    budget: ExecutionBudget
    success: bool
    outcome: str
    turns_used: int
    tokens_used: int
    time_seconds: int
    cost: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _required_text(self.agent_id, "baseline.agent_id"))
        if not isinstance(self.budget, ExecutionBudget):
            raise ValidationError("baseline.budget must be an ExecutionBudget")
        if not isinstance(self.success, bool):
            raise ValidationError("baseline.success must be boolean")
        object.__setattr__(self, "outcome", _required_text(self.outcome, "baseline.outcome"))
        object.__setattr__(self, "turns_used", _nonnegative_int(self.turns_used, "baseline.turns_used"))
        object.__setattr__(self, "tokens_used", _nonnegative_int(self.tokens_used, "baseline.tokens_used"))
        object.__setattr__(self, "time_seconds", _nonnegative_int(self.time_seconds, "baseline.time_seconds"))
        cost = _decimal(self.cost, "baseline.cost")
        if cost < 0:
            raise ValidationError("baseline.cost must be non-negative")
        object.__setattr__(self, "cost", cost)
        if self.turns_used > self.budget.max_turns:
            raise ValidationError("baseline turns exceed its declared budget")
        if self.tokens_used > self.budget.max_tokens:
            raise ValidationError("baseline tokens exceed its declared budget")
        if self.time_seconds > self.budget.max_time_seconds:
            raise ValidationError("baseline time exceeds its declared budget")
        if self.cost > self.budget.max_cost:
            raise ValidationError("baseline cost exceeds its declared budget")


@dataclass(frozen=True)
class TeamExecutionPlan:
    recipe_id: str
    recipe_version: int
    commit_actor_id: str
    turns: tuple[PlannedTeamTurn, ...]
    turns_reserved: int
    tokens_reserved: int
    time_reserved_seconds: int
    cost_reserved: Decimal
    turns_remaining: int
    tokens_remaining: int
    time_remaining_seconds: int
    cost_remaining: Decimal
    baseline: SingleAgentBaselineResult

    @property
    def matched_budget(self) -> bool:
        return True


def plan_team_execution(
    recipe: TeamRecipe,
    turns: Iterable[PlannedTeamTurn],
    baseline: SingleAgentBaselineResult,
) -> TeamExecutionPlan:
    """Validate a bounded team plan and attach its matched-budget baseline."""

    if not isinstance(recipe, TeamRecipe):
        raise ValidationError("recipe must be a TeamRecipe")
    if not isinstance(baseline, SingleAgentBaselineResult):
        raise ValidationError("baseline must be a SingleAgentBaselineResult")
    if baseline.budget != recipe.budget:
        raise ValidationError("single-agent baseline must use exactly the team recipe budget")
    try:
        planned = tuple(turns)
    except TypeError:
        raise ValidationError("turns must be iterable") from None
    if not planned or any(not isinstance(item, PlannedTeamTurn) for item in planned):
        raise ValidationError("plan must contain at least one PlannedTeamTurn")

    participants = {item.participant_id: item for item in recipe.participants}
    committed_actions: set[str] = set()
    total_tokens = 0
    total_time = 0
    total_cost = Decimal("0")
    for index, turn in enumerate(planned):
        participant = participants.get(turn.participant_id)
        if participant is None:
            raise ValidationError(f"turn {index} references unapproved participant {turn.participant_id}")
        if participant.role not in recipe.approved_roles:
            raise ValidationError(f"turn {index} uses an unapproved participant role")
        if turn.tool is not None:
            if turn.tool not in recipe.approved_tools or turn.tool not in participant.allowed_tools:
                raise ValidationError(f"turn {index} uses unapproved tool {turn.tool}")
        if turn.commits_effect:
            if turn.participant_id != recipe.commit_actor_id or not participant.can_commit:
                raise ValidationError("only the designated commit actor may commit an effect")
            if turn.action_id in committed_actions:
                raise ValidationError(f"duplicate committed action ID {turn.action_id}")
            committed_actions.add(turn.action_id)  # type: ignore[arg-type]
        total_tokens += turn.token_reservation
        total_time += turn.time_reservation_seconds
        total_cost += turn.cost_reservation

    budget = recipe.budget
    if len(planned) > budget.max_turns:
        raise BudgetExceededError("team plan exceeds max turns")
    if total_tokens > budget.max_tokens:
        raise BudgetExceededError("team plan exceeds max tokens")
    if total_time > budget.max_time_seconds:
        raise BudgetExceededError("team plan exceeds max time")
    if total_cost > budget.max_cost:
        raise BudgetExceededError("team plan exceeds max cost")

    return TeamExecutionPlan(
        recipe_id=recipe.recipe_id,
        recipe_version=recipe.version,
        commit_actor_id=recipe.commit_actor_id,
        turns=planned,
        turns_reserved=len(planned),
        tokens_reserved=total_tokens,
        time_reserved_seconds=total_time,
        cost_reserved=total_cost,
        turns_remaining=budget.max_turns - len(planned),
        tokens_remaining=budget.max_tokens - total_tokens,
        time_remaining_seconds=budget.max_time_seconds - total_time,
        cost_remaining=budget.max_cost - total_cost,
        baseline=baseline,
    )


# ---------------------------------------------------------------------------
# Paired release experiments and future-version selection


@dataclass(frozen=True)
class ScenarioResult:
    case_id: str
    version_id: str
    passed: bool
    permission_violations: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()
    duplicate_effect_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _required_text(self.case_id, "case_id"))
        object.__setattr__(self, "version_id", _required_text(self.version_id, "version_id"))
        if not isinstance(self.passed, bool):
            raise ValidationError("scenario.passed must be boolean")
        object.__setattr__(
            self,
            "permission_violations",
            _string_tuple(self.permission_violations, "scenario.permission_violations"),
        )
        # Repeated effect IDs are deliberately retained so the evaluator can
        # diagnose and block them rather than rejecting the evidence itself.
        try:
            effect_ids = tuple(_required_text(item, "scenario.effect_ids") for item in self.effect_ids)
        except TypeError:
            raise ValidationError("scenario.effect_ids must be iterable") from None
        object.__setattr__(self, "effect_ids", effect_ids)
        object.__setattr__(
            self,
            "duplicate_effect_count",
            _nonnegative_int(self.duplicate_effect_count, "scenario.duplicate_effect_count"),
        )

    @property
    def duplicated_effect_ids(self) -> tuple[str, ...]:
        counts = Counter(self.effect_ids)
        return tuple(sorted(effect_id for effect_id, count in counts.items() if count > 1))


@dataclass(frozen=True)
class PairedScenarioEvaluation:
    case_id: str
    baseline_passed: bool
    candidate_passed: bool
    regressed: bool
    candidate_permission_violations: tuple[str, ...]
    candidate_duplicated_effect_ids: tuple[str, ...]
    candidate_duplicate_effect_count: int


@dataclass(frozen=True)
class ReleaseExperimentDecision:
    baseline_version: str
    candidate_version: str
    promoted: bool
    selected_future_version: str
    blockers: tuple[str, ...]
    paired_results: tuple[PairedScenarioEvaluation, ...]
    active_run_pins: tuple[tuple[str, str], ...]

    def active_run_pin_map(self) -> dict[str, str]:
        return dict(self.active_run_pins)


def _index_scenarios(
    results: Iterable[ScenarioResult], expected_version: str, label: str
) -> dict[str, ScenarioResult]:
    try:
        records = tuple(results)
    except TypeError:
        raise ValidationError(f"{label} results must be iterable") from None
    if not records or any(not isinstance(item, ScenarioResult) for item in records):
        raise ValidationError(f"{label} results must contain ScenarioResult values")
    indexed: dict[str, ScenarioResult] = {}
    for item in records:
        if item.version_id != expected_version:
            raise ValidationError(
                f"{label} case {item.case_id} is pinned to {item.version_id}, expected {expected_version}"
            )
        if item.case_id in indexed:
            raise ValidationError(f"duplicate {label} case ID {item.case_id}")
        indexed[item.case_id] = item
    return indexed


def evaluate_release_experiment(
    baseline_version: str,
    candidate_version: str,
    baseline_results: Iterable[ScenarioResult],
    candidate_results: Iterable[ScenarioResult],
    current_future_version: str,
    active_run_pins: Mapping[str, str],
) -> ReleaseExperimentDecision:
    """Evaluate paired cases and select a version only for future starts.

    Existing run pins are copied into the result and are never rewritten.
    Candidate permission violations, duplicate effects, or failed invariants
    always block promotion.
    """

    baseline_version = _required_text(baseline_version, "baseline_version")
    candidate_version = _required_text(candidate_version, "candidate_version")
    current_future_version = _required_text(current_future_version, "current_future_version")
    if baseline_version == candidate_version:
        raise ValidationError("baseline and candidate versions must differ")
    baseline = _index_scenarios(baseline_results, baseline_version, "baseline")
    candidate = _index_scenarios(candidate_results, candidate_version, "candidate")
    if set(baseline) != set(candidate):
        missing_candidate = sorted(set(baseline).difference(candidate))
        missing_baseline = sorted(set(candidate).difference(baseline))
        raise ValidationError(
            "paired experiments require identical case IDs; "
            f"missing candidate={missing_candidate}, missing baseline={missing_baseline}"
        )
    if not isinstance(active_run_pins, Mapping):
        raise ValidationError("active_run_pins must be an object")
    pin_snapshot: list[tuple[str, str]] = []
    for run_id, version_id in active_run_pins.items():
        pin_snapshot.append(
            (_required_text(run_id, "active_run_pins.run_id"), _required_text(version_id, "active_run_pins.version"))
        )
    if len({run_id for run_id, _ in pin_snapshot}) != len(pin_snapshot):
        raise ValidationError("active run IDs must be unique")
    pin_snapshot.sort()

    blockers: list[str] = []
    paired: list[PairedScenarioEvaluation] = []
    for case_id in sorted(baseline):
        base = baseline[case_id]
        cand = candidate[case_id]
        duplicated = cand.duplicated_effect_ids
        if cand.permission_violations:
            blockers.append(
                f"{case_id}: candidate permission violations: {', '.join(cand.permission_violations)}"
            )
        if duplicated:
            blockers.append(f"{case_id}: candidate repeated effect IDs: {', '.join(duplicated)}")
        if cand.duplicate_effect_count:
            blockers.append(
                f"{case_id}: candidate reported {cand.duplicate_effect_count} duplicate effect(s)"
            )
        if not cand.passed:
            blockers.append(f"{case_id}: candidate failed declared invariants")
        paired.append(
            PairedScenarioEvaluation(
                case_id=case_id,
                baseline_passed=base.passed,
                candidate_passed=cand.passed,
                regressed=base.passed and not cand.passed,
                candidate_permission_violations=cand.permission_violations,
                candidate_duplicated_effect_ids=duplicated,
                candidate_duplicate_effect_count=cand.duplicate_effect_count,
            )
        )

    promoted = not blockers
    return ReleaseExperimentDecision(
        baseline_version=baseline_version,
        candidate_version=candidate_version,
        promoted=promoted,
        selected_future_version=candidate_version if promoted else current_future_version,
        blockers=tuple(blockers),
        paired_results=tuple(paired),
        active_run_pins=tuple(pin_snapshot),
    )


__all__ = [
    "AgentImpactAnalysis",
    "AgentUse",
    "BlockEdge",
    "BlockExpansion",
    "BlockNode",
    "BudgetExceededError",
    "ExecutionBudget",
    "GovernanceError",
    "InsertionBlock",
    "KeywordContribution",
    "PairedScenarioEvaluation",
    "PlannedTeamTurn",
    "Principal",
    "ReleaseExperimentDecision",
    "ReleaseImpact",
    "ScenarioResult",
    "SingleAgentBaselineResult",
    "TeamExecutionPlan",
    "TeamParticipant",
    "TeamRecipe",
    "TemplateMatch",
    "TemplateRecord",
    "ValidationError",
    "WorkflowRelease",
    "analyze_agent_version_impact",
    "evaluate_release_experiment",
    "expand_insertion_block",
    "find_templates",
    "plan_team_execution",
]
