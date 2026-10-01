"""Deterministic, stateful enterprise simulation for the Atlas Checkout demo.

This module deliberately has no network, database, server, or wall-clock
dependency.  A caller owns persistence and passes one mutable ``world``
dictionary to every operation.  The simulator provides provider-shaped tool
contracts and receipts, but every result is explicitly marked as isolated and
simulated.

The generic adaptive-agent kernel is not modified here.  It can compile the
capability contracts and the Incident Commander specification, while a host
maps :class:`ToolOutcome` success and fault values to the kernel's existing
``record_tool_result`` and ``record_tool_error`` functions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json
import re
from typing import Any, Mapping


WORLD_SCHEMA_VERSION = "axiom.simulation-world.v1"
PROFILE_SCHEMA_VERSION = "axiom.simulation-profile.v1"
CAPABILITY_VERSION = "1.0.0"
ADAPTER_VERSION = "1.0.0"
INCIDENT_COMMANDER_ID = "atlas-incident-commander"
OUTCOME_VALIDATOR_ID = "simulation.atlas-incident-outcome.v1"

_START_TIME = "2026-09-30T09:00:00Z"
_WORLD_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
_OPERATION_KEY = re.compile(r"^[A-Za-z0-9_.:/-]{1,300}$")
_ZERO_HASH = "0" * 64


class SimulationError(ValueError):
    """Raised for invalid simulator contracts or corrupted world state."""

    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class ToolOutcome:
    """One provider-like result without performing external I/O."""

    ok: bool
    output: dict[str, Any] | None
    receipt: dict[str, Any]
    fault: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output": copy.deepcopy(self.output),
            "receipt": copy.deepcopy(self.receipt),
            "fault": copy.deepcopy(self.fault),
        }


def _json(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        encoded.encode("utf-8", "strict")
        return encoded
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SimulationError(
            "INVALID_JSON", "Simulation data must be finite UTF-8 JSON."
        ) from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _iso(start: str, elapsed_seconds: int) -> str:
    parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=elapsed_seconds)).astimezone(
        timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _obj(properties: Mapping[str, Any], required: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    return {
        "type": "object", "properties": copy.deepcopy(dict(properties)),
        "required": list(required), "additionalProperties": False,
    }


def _str(description: str, maximum: int = 1000, *, values: tuple[str, ...] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "string", "maxLength": maximum, "description": description,
    }
    if values:
        result["enum"] = list(values)
    return result


def _int(description: str, minimum: int = 0, maximum: int = 1_000_000) -> dict[str, Any]:
    return {
        "type": "integer", "minimum": minimum, "maximum": maximum,
        "description": description,
    }


def _num(description: str, minimum: float = 0, maximum: float = 1_000_000) -> dict[str, Any]:
    return {
        "type": "number", "minimum": minimum, "maximum": maximum,
        "description": description,
    }


def _bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _array(items: Mapping[str, Any], maximum: int = 100) -> dict[str, Any]:
    return {"type": "array", "items": copy.deepcopy(dict(items)), "maxItems": maximum}


_PROFILE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "fresh-incident": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "fresh-incident",
        "name": "Fresh checkout regression",
        "description": "A new checkout regression has no existing incident and all simulated providers are available.",
        "variation": {},
    },
    "existing-incident": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "existing-incident",
        "name": "Existing incident reuse",
        "description": "Jira already contains the active incident, so the agent must reuse it rather than create a duplicate.",
        "variation": {"existingIncident": True},
    },
    "missing-owner": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "missing-owner",
        "name": "Missing service ownership",
        "description": "The service catalog lacks an owner and incident channel, requiring scoped clarification.",
        "variation": {"missingOwner": True},
    },
    "confluence-unavailable": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "confluence-unavailable",
        "name": "Runbook service unavailable",
        "description": "The Confluence sandbox returns a controlled service-unavailable fault.",
        "variation": {"confluenceUnavailable": True},
    },
    "slack-rate-limit": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "slack-rate-limit",
        "name": "Slack rate limit and retry",
        "description": "The first message write receives a deterministic 429 and the next bounded attempt succeeds.",
        "variation": {"slackRateLimitCount": 1},
    },
    "jira-lost-ack": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "jira-lost-ack",
        "name": "Jira acknowledgement lost",
        "description": "Jira commits the incident but the response is lost, requiring reconciliation by operation key.",
        "variation": {"jiraLostAckCount": 1},
    },
    "changed-flag-version": {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "id": "changed-flag-version",
        "name": "Feature flag changes during approval",
        "description": "The feature flag revision changes on the virtual clock, invalidating a stale prepared update.",
        "variation": {"scheduleFlagChange": True},
    },
}

_PROFILE_ALIASES = {"changed-flag": "changed-flag-version"}


def scenario_profiles() -> list[dict[str, Any]]:
    """Return the seven immutable, presentation-ready simulation profiles."""

    result = []
    for profile in _PROFILE_DEFINITIONS.values():
        public = {key: copy.deepcopy(value) for key, value in profile.items() if key != "variation"}
        public["definitionHash"] = _hash(profile)
        result.append(public)
    return result


def _base_records() -> dict[str, Any]:
    return {
        "alerts": {
            "ALT-CHECKOUT-9001": {
                "id": "ALT-CHECKOUT-9001", "serviceId": "atlas-checkout",
                "title": "Checkout error rate above SLO", "severity": "critical",
                "triggeredAt": "2026-09-30T08:57:00Z", "status": "firing",
                "thresholdPercent": 5.0, "revision": 3,
            }
        },
        "metrics": {
            "atlas-checkout": {
                "serviceId": "atlas-checkout", "state": "degraded",
                "errorRatePercent": 18.7, "p95LatencyMs": 4800,
                "affectedSessions": 147, "consecutiveHealthyWindows": 0,
                "windowStart": "2026-09-30T08:55:00Z",
                "windowEnd": "2026-09-30T09:00:00Z", "revision": 12,
            }
        },
        "services": {
            "atlas-checkout": {
                "serviceId": "atlas-checkout", "displayName": "Atlas Checkout API",
                "criticality": "tier-1", "ownerTeam": "Commerce Reliability",
                "onCallUser": "U-ONCALL-42", "slackChannelId": "C-INCIDENTS",
                "runbookPageId": "CONF-RUNBOOK-77", "repository": "commerce/atlas-checkout",
                "revision": 8,
            }
        },
        "deployments": {
            "DEP-8842": {
                "deploymentId": "DEP-8842", "serviceId": "atlas-checkout",
                "version": "2026.09.30.417", "commitSha": "9f21b4a7c65e",
                "status": "succeeded", "startedAt": "2026-09-30T08:10:00Z",
                "completedAt": "2026-09-30T08:17:00Z",
                "changeSummary": "Enable checkout-v2 tax and pricing path.",
                "featureFlagKey": "checkout-v2", "revision": 4,
            }
        },
        "jiraIssues": {},
        "jiraRevision": 1,
        "confluencePages": {
            "CONF-RUNBOOK-77": {
                "pageId": "CONF-RUNBOOK-77", "title": "Atlas Checkout incident runbook",
                "spaceKey": "SRE", "version": 19,
                "summary": "Check the most recent deployment and disable checkout-v2 before a full rollback when the flag is enabled.",
                "preferredMitigation": "disable_feature_flag",
                "fallbackMitigation": "rollback_deployment",
                "lastReviewedAt": "2026-09-12T10:30:00Z",
            }
        },
        "slackChannels": {
            "C-INCIDENTS": {
                "channelId": "C-INCIDENTS", "name": "inc-checkout",
                "revision": 2, "messages": [
                    {
                        "messageId": "1701.0001", "authorId": "U-ONCALL-42",
                        "text": "Automated alert received; investigation has not started.",
                        "createdAt": "2026-09-30T08:58:00Z",
                    }
                ],
            }
        },
        "featureFlags": {
            "checkout-v2": {
                "flagKey": "checkout-v2", "serviceId": "atlas-checkout",
                "enabled": True, "rolloutPercentage": 100,
                "environment": "production", "revision": 7,
                "updatedBy": "deploy-bot", "updatedAt": "2026-09-30T08:15:00Z",
            }
        },
    }


def create_world(
    profile_id: str, world_id: str | None = None, generation: int = 1,
) -> dict[str, Any]:
    """Create one independent Atlas Checkout world from a versioned profile.

    ``changed-flag`` remains accepted as a hidden compatibility alias, while
    the catalog exposes only ``changed-flag-version``.
    """

    profile_id = _PROFILE_ALIASES.get(profile_id, profile_id)
    profile = _PROFILE_DEFINITIONS.get(profile_id)
    if profile is None:
        raise SimulationError("PROFILE_UNKNOWN", "The requested simulation profile is unavailable.")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise SimulationError(
            "WORLD_GENERATION_INVALID", "World generation must be a positive integer."
        )
    ident = world_id or (
        "atlas-" + profile_id + (f"-g{generation}" if generation > 1 else "")
    )
    if not isinstance(ident, str) or not _WORLD_ID.fullmatch(ident):
        raise SimulationError("WORLD_ID_INVALID", "World IDs must contain 1-120 safe characters.")

    records = _base_records()
    variation = profile["variation"]
    if variation.get("existingIncident"):
        records["jiraIssues"]["OPS-4312"] = {
            "key": "OPS-4312", "serviceId": "atlas-checkout",
            "summary": "Atlas Checkout errors after 2026.09.30.417",
            "severity": "SEV-1", "status": "Investigating",
            "createdAt": "2026-09-30T08:59:00Z", "revision": 2,
        }
        records["jiraRevision"] = 2
    if variation.get("missingOwner"):
        service = records["services"]["atlas-checkout"]
        service.update(ownerTeam="", onCallUser="", slackChannelId="", revision=9)

    world: dict[str, Any] = {
        "schemaVersion": WORLD_SCHEMA_VERSION,
        "id": ident,
        "profileId": profile_id,
        "profileVersion": 1,
        "generation": generation,
        "profileHash": _hash(profile),
        "sandbox": {"isolated": True, "externalNetwork": False, "externalEffects": False},
        "clock": {"startedAt": _START_TIME, "elapsedSeconds": 0, "now": _iso(_START_TIME, 0)},
        "revision": 1,
        "records": records,
        "scheduled": [],
        "operations": {},
        "events": [],
        "requestCounter": 0,
        "nextJiraNumber": 4313,
        "nextSlackSequence": 2,
        "faults": {
            "confluenceUnavailable": bool(variation.get("confluenceUnavailable")),
            "slackRateLimitRemaining": int(variation.get("slackRateLimitCount", 0)),
            "jiraLostAckRemaining": int(variation.get("jiraLostAckCount", 0)),
        },
    }
    if variation.get("scheduleFlagChange"):
        world["scheduled"].append({
            "id": "scheduled-external-flag-change",
            "dueSeconds": 60,
            "kind": "feature_flag.external_change",
            "payload": {"flagKey": "checkout-v2", "rolloutPercentage": 75},
        })
    _append_event(
        world, "world.created", "simulation-lab", None,
        {
            "profileId": profile_id,
            "profileHash": world["profileHash"],
            "generation": generation,
        },
        _business_hash(world), _business_hash(world),
    )
    validate_world(world)
    return world


def _business_hash(world: Mapping[str, Any]) -> str:
    return _hash({
        "clock": world.get("clock"), "revision": world.get("revision"),
        "records": world.get("records"), "scheduled": world.get("scheduled"),
        "faults": world.get("faults"),
        "nextJiraNumber": world.get("nextJiraNumber"),
        "nextSlackSequence": world.get("nextSlackSequence"),
    })


def _append_event(
    world: dict[str, Any], kind: str, provider: str, tool_id: str | None,
    details: Mapping[str, Any], before_hash: str, after_hash: str,
    *, operation_key: str | None = None, request_id: str | None = None,
) -> dict[str, Any]:
    sequence = len(world["events"]) + 1
    event = {
        "sequence": sequence,
        "eventId": f"sim_evt_{sequence:05d}",
        "at": world["clock"]["now"],
        "kind": kind,
        "provider": provider,
        "toolId": tool_id,
        "operationKey": operation_key,
        "requestId": request_id,
        "details": copy.deepcopy(dict(details)),
        "beforeStateHash": before_hash,
        "afterStateHash": after_hash,
        "previousEventHash": world["events"][-1]["eventHash"] if world["events"] else _ZERO_HASH,
    }
    event["eventHash"] = _hash(event)
    world["events"].append(event)
    return copy.deepcopy(event)


def validate_world(world: Any) -> None:
    """Fail closed when world identity, profile pins, or event history changed."""

    if not isinstance(world, dict) or world.get("schemaVersion") != WORLD_SCHEMA_VERSION:
        raise SimulationError("WORLD_INVALID", "Simulation world schema is missing or unsupported.")
    if not isinstance(world.get("id"), str) or not _WORLD_ID.fullmatch(world["id"]):
        raise SimulationError("WORLD_INVALID", "Simulation world identity is invalid.")
    profile = _PROFILE_DEFINITIONS.get(world.get("profileId"))
    if profile is None or world.get("profileVersion") != 1 or world.get("profileHash") != _hash(profile):
        raise SimulationError("WORLD_PROFILE_CHANGED", "The pinned simulation profile failed its integrity check.")
    if (isinstance(world.get("generation"), bool)
            or not isinstance(world.get("generation"), int)
            or world["generation"] < 1):
        raise SimulationError("WORLD_GENERATION_INVALID", "The world generation is invalid.")
    if world.get("sandbox") != {"isolated": True, "externalNetwork": False, "externalEffects": False}:
        raise SimulationError("WORLD_BOUNDARY_CHANGED", "The simulation isolation boundary changed.")
    clock = world.get("clock")
    if (not isinstance(clock, dict) or clock.get("startedAt") != _START_TIME
            or isinstance(clock.get("elapsedSeconds"), bool)
            or not isinstance(clock.get("elapsedSeconds"), int)
            or clock["elapsedSeconds"] < 0
            or clock.get("now") != _iso(_START_TIME, clock["elapsedSeconds"])):
        raise SimulationError("WORLD_CLOCK_INVALID", "The deterministic virtual clock is invalid.")
    for field, expected in (
        ("records", dict), ("scheduled", list), ("operations", dict),
        ("events", list), ("faults", dict),
    ):
        if not isinstance(world.get(field), expected):
            raise SimulationError("WORLD_INVALID", f"Simulation world field {field} is invalid.")
    for field, minimum in (
        ("revision", 1), ("requestCounter", 0),
        ("nextJiraNumber", 1), ("nextSlackSequence", 1),
    ):
        value = world.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise SimulationError(
                "WORLD_INVALID", f"Simulation world counter {field} is invalid."
            )
    expected_faults = {
        "confluenceUnavailable": bool,
        "slackRateLimitRemaining": int,
        "jiraLostAckRemaining": int,
    }
    if set(world["faults"]) != set(expected_faults):
        raise SimulationError("WORLD_INVALID", "Simulation fault state is invalid.")
    for field, expected in expected_faults.items():
        value = world["faults"][field]
        if (expected is bool and not isinstance(value, bool)) or (
            expected is int
            and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
        ):
            raise SimulationError("WORLD_INVALID", "Simulation fault state is invalid.")
    scheduled_ids: set[str] = set()
    for item in world["scheduled"]:
        if (not isinstance(item, dict)
                or set(item) != {"id", "dueSeconds", "kind", "payload"}
                or not isinstance(item["id"], str)
                or not item["id"]
                or item["id"] in scheduled_ids
                or isinstance(item["dueSeconds"], bool)
                or not isinstance(item["dueSeconds"], int)
                or item["dueSeconds"] < clock["elapsedSeconds"]
                or item["kind"] not in {
                    "feature_flag.external_change", "metrics.recovering",
                    "metrics.recovered", "deployment.rollback_completed",
                }
                or not isinstance(item["payload"], dict)):
            raise SimulationError("WORLD_INVALID", "A scheduled simulation event is invalid.")
        scheduled_ids.add(item["id"])
    previous = _ZERO_HASH
    for index, event in enumerate(world["events"], start=1):
        if (not isinstance(event, dict) or event.get("sequence") != index
                or event.get("eventId") != f"sim_evt_{index:05d}"
                or event.get("previousEventHash") != previous):
            raise SimulationError("EVENT_HISTORY_CHANGED", "Simulation events are not an append-only sequence.")
        claimed = event.get("eventHash")
        expected = _hash({key: value for key, value in event.items() if key != "eventHash"})
        if claimed != expected:
            raise SimulationError("EVENT_HISTORY_CHANGED", "A simulation event failed its integrity hash.")
        previous = claimed
    for operation_key, record in world["operations"].items():
        if (not isinstance(operation_key, str) or not _OPERATION_KEY.fullmatch(operation_key)
                or not isinstance(record, dict)
                or record.get("operationKey") != operation_key):
            raise SimulationError("OPERATION_LEDGER_CHANGED", "A simulation operation identity is invalid.")
        expected = _hash({key: value for key, value in record.items() if key != "recordHash"})
        if record.get("recordHash") != expected:
            raise SimulationError("OPERATION_LEDGER_CHANGED", "A simulation operation failed its integrity hash.")
    if not world["events"] or world["events"][-1].get("afterStateHash") != _business_hash(world):
        raise SimulationError(
            "WORLD_STATE_CHANGED",
            "Authoritative simulation state changed outside its append-only event history.",
        )
    _json(world)


def public_world(world: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep, credential-free view suitable for a run inspector."""

    validate_world(world)
    records = copy.deepcopy(world["records"])
    return {
        "schemaVersion": world["schemaVersion"], "id": world["id"],
        "profileId": world["profileId"], "profileVersion": world["profileVersion"],
        "profileHash": world["profileHash"], "generation": world["generation"],
        "sandbox": copy.deepcopy(world["sandbox"]),
        "clock": copy.deepcopy(world["clock"]), "revision": world["revision"],
        "records": records, "faults": copy.deepcopy(world["faults"]),
        "scheduledEventCount": len(world["scheduled"]),
        "operationCount": len(world["operations"]), "events": copy.deepcopy(world["events"]),
    }


_DEPLOYMENT_SCHEMA = _obj({
    "deploymentId": _str("Stable deployment ID", 120),
    "serviceId": _str("Service ID", 120),
    "version": _str("Released version", 120),
    "commitSha": _str("Source commit", 120),
    "status": _str("Deployment state", 100),
    "startedAt": _str("Provider timestamp", 100),
    "completedAt": _str("Provider timestamp", 100),
    "changeSummary": _str("Change summary", 1000),
    "featureFlagKey": _str("Related feature flag", 120),
    "revision": _int("Record revision", 1),
}, ("deploymentId", "serviceId", "version", "commitSha", "status", "startedAt",
    "completedAt", "changeSummary", "featureFlagKey", "revision"))

_ISSUE_SCHEMA = _obj({
    "key": _str("Stable issue key", 100),
    "serviceId": _str("Affected service", 120),
    "summary": _str("Issue summary", 1000),
    "severity": _str("Incident severity", 50),
    "status": _str("Issue status", 100),
    "createdAt": _str("Provider timestamp", 100),
    "revision": _int("Issue revision", 1),
}, ("key", "serviceId", "summary", "severity", "status", "createdAt", "revision"))

_MESSAGE_SCHEMA = _obj({
    "messageId": _str("Stable Slack message ID", 120),
    "authorId": _str("Message author", 120),
    "text": _str("Message text", 40000),
    "createdAt": _str("Provider timestamp", 100),
}, ("messageId", "authorId", "text", "createdAt"))


def _tool(
    identifier: str, provider_id: str, provider_name: str, description: str,
    effect: str, inputs: Mapping[str, Any], output_schema: Mapping[str, Any],
) -> dict[str, Any]:
    input_schema = _obj(inputs, tuple(inputs))

    def example_value(schema: Mapping[str, Any]) -> Any:
        if "enum" in schema:
            return copy.deepcopy(schema["enum"][0])
        kind = schema["type"]
        return {
            "string": "example", "integer": int(schema.get("minimum", 0)),
            "number": schema.get("minimum", 0), "boolean": False,
            "array": [], "object": {},
        }[kind]

    durability = (
        {"classification": "safe_read", "retry": "bounded", "reconciliation": "not_required"}
        if effect == "read" else
        {"classification": "idempotent_simulation", "operationKey": "required",
         "retry": "only_after_ledger_check", "reconciliation": "simulation_operation_lookup"}
    )
    return {
        "schemaVersion": "axiom.capability-contract.v1",
        "id": identifier, "version": CAPABILITY_VERSION,
        "description": description, "effect": effect,
        "inputSchema": input_schema, "outputSchema": copy.deepcopy(dict(output_schema)),
        "semanticFields": {
            name: schema.get("description", "Declared simulation argument.")
            for name, schema in inputs.items()
        },
        "authorization": {
            "scope": f"simulation:{provider_id}", "principal": "isolated-atlas-world",
            "credentials": "none", "environment": "sandbox",
        },
        "adapterBinding": {
            "adapterId": f"axiom.simulation.{provider_id}",
            "adapterVersion": ADAPTER_VERSION, "operation": identifier,
            "transport": "in-process",
        },
        "idempotency": durability,
        "boundArguments": {"worldId": "input.worldId"},
        "examples": [{
            "label": provider_name + " sandbox contract example",
            "input": {name: example_value(schema) for name, schema in inputs.items()},
        }],
        "verification": {
            "status": "deterministic-simulation", "environment": "isolated-local",
            "externalIntegration": False, "providerLabel": provider_name + " (Simulated)",
        },
    }


_CAPABILITIES = [
    _tool(
        "simulation.metrics.query", "metrics", "Pulse Metrics",
        "Read the Atlas Checkout alert and one bounded aggregate metrics window. advanceSeconds moves only the deterministic virtual clock.",
        "read",
        {
            "worldId": _str("Host-bound simulation world ID", 120),
            "alertId": _str("Alert identifier", 120),
            "advanceSeconds": _int("Virtual seconds to advance before observing", 0, 300),
        },
        _obj({
            "alertId": _str("Alert identifier", 120), "serviceId": _str("Service ID", 120),
            "state": _str("Observed health state", 50, values=("degraded", "recovering", "healthy")),
            "errorRatePercent": _num("Request error percentage", 0, 100),
            "p95LatencyMs": _int("P95 latency in milliseconds", 0, 120000),
            "affectedSessions": _int("Estimated affected sessions", 0, 1_000_000),
            "thresholdPercent": _num("Alert threshold percentage", 0, 100),
            "consecutiveHealthyWindows": _int("Consecutive healthy windows", 0, 100),
            "alertStatus": _str("Alert state", 50),
            "windowStart": _str("Window start", 100), "windowEnd": _str("Window end", 100),
            "revision": _int("Metrics record revision", 1),
        }, ("alertId", "serviceId", "state", "errorRatePercent", "p95LatencyMs",
            "affectedSessions", "thresholdPercent", "consecutiveHealthyWindows",
            "alertStatus", "windowStart", "windowEnd", "revision")),
    ),
    _tool(
        "simulation.catalog.get_service", "catalog", "Atlas Service Catalog",
        "Read service ownership, runbook, repository, and incident-channel metadata.", "read",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "serviceId": _str("Service identifier", 120)},
        _obj({
            "serviceId": _str("Service ID", 120), "displayName": _str("Service name", 200),
            "criticality": _str("Business criticality", 50), "ownerTeam": _str("Owning team", 200),
            "onCallUser": _str("On-call user ID", 120), "slackChannelId": _str("Incident channel", 120),
            "runbookPageId": _str("Runbook page", 120), "repository": _str("Repository", 300),
            "revision": _int("Catalog revision", 1),
        }, ("serviceId", "displayName", "criticality", "ownerTeam", "onCallUser",
            "slackChannelId", "runbookPageId", "repository", "revision")),
    ),
    _tool(
        "simulation.deployments.list_recent", "deployments", "Atlas Deploy",
        "List the bounded recent deployment history for one service.", "read",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "serviceId": _str("Service identifier", 120),
         "limit": _int("Maximum deployments", 1, 10)},
        _obj({
            "serviceId": _str("Service ID", 120),
            "deployments": _array(_DEPLOYMENT_SCHEMA, 10),
            "revision": _int("Collection revision", 1),
        }, ("serviceId", "deployments", "revision")),
    ),
    _tool(
        "simulation.deployments.rollback", "deployments", "Atlas Deploy",
        "Start one idempotent rollback when the exact deployment revision still matches.", "write",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "deploymentId": _str("Deployment identifier", 120),
         "expectedRevision": _int("Reviewed deployment revision", 1),
         "reason": _str("Operational rollback reason", 2000)},
        _obj({
            "deploymentId": _str("Deployment identifier", 120),
            "status": _str("Rollback state", 100), "revision": _int("New deployment revision", 1),
            "scheduledCompletionAt": _str("Virtual completion time", 100),
        }, ("deploymentId", "status", "revision", "scheduledCompletionAt")),
    ),
    _tool(
        "simulation.jira.search_incidents", "jira", "Jira Cloud",
        "Search active simulated Jira incidents for one service.", "read",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "serviceId": _str("Affected service", 120),
         "status": _str("Requested issue state", 100)},
        _obj({
            "issues": _array(_ISSUE_SCHEMA, 20), "count": _int("Matching issue count", 0, 20),
            "revision": _int("Issue collection revision", 1),
        }, ("issues", "count", "revision")),
    ),
    _tool(
        "simulation.jira.create_incident", "jira", "Jira Cloud",
        "Create one exact simulated incident. A controlled lost acknowledgement may require operation-key reconciliation.",
        "write",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "projectKey": _str("Jira project key", 30),
         "serviceId": _str("Affected service", 120),
         "summary": _str("Incident summary", 1000),
         "severity": _str("Incident severity", 50)},
        _ISSUE_SCHEMA,
    ),
    _tool(
        "simulation.confluence.get_page", "confluence", "Confluence Cloud",
        "Read the versioned Atlas Checkout incident runbook.", "read",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "pageId": _str("Confluence page identifier", 120)},
        _obj({
            "pageId": _str("Page identifier", 120), "title": _str("Page title", 1000),
            "spaceKey": _str("Confluence space", 100), "version": _int("Page version", 1),
            "summary": _str("Runbook summary", 5000),
            "preferredMitigation": _str("Preferred mitigation", 120),
            "fallbackMitigation": _str("Fallback mitigation", 120),
            "lastReviewedAt": _str("Review timestamp", 100),
        }, ("pageId", "title", "spaceKey", "version", "summary",
            "preferredMitigation", "fallbackMitigation", "lastReviewedAt")),
    ),
    _tool(
        "simulation.slack.get_history", "slack", "Slack",
        "Read a bounded simulated incident-channel history.", "read",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "channelId": _str("Slack channel ID", 120),
         "limit": _int("Maximum messages", 1, 50)},
        _obj({
            "channelId": _str("Channel ID", 120), "messages": _array(_MESSAGE_SCHEMA, 50),
            "hasMore": _bool("More messages exist"), "revision": _int("Channel revision", 1),
        }, ("channelId", "messages", "hasMore", "revision")),
    ),
    _tool(
        "simulation.slack.post_message", "slack", "Slack",
        "Post one exact incident update to the simulated channel. The first call can be deterministically rate-limited.",
        "write",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "channelId": _str("Slack channel ID", 120),
         "text": _str("Reviewed incident message", 40000)},
        _MESSAGE_SCHEMA,
    ),
    _tool(
        "simulation.feature_flags.get", "feature-flags", "LaunchDarkly",
        "Read one production feature flag and its concurrency revision.", "read",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "flagKey": _str("Feature flag key", 120)},
        _obj({
            "flagKey": _str("Feature flag key", 120), "serviceId": _str("Owning service", 120),
            "enabled": _bool("Current flag state"), "rolloutPercentage": _int("Rollout percent", 0, 100),
            "environment": _str("Flag environment", 100), "revision": _int("Flag revision", 1),
            "updatedBy": _str("Last actor", 120), "updatedAt": _str("Last update", 100),
        }, ("flagKey", "serviceId", "enabled", "rolloutPercentage", "environment",
            "revision", "updatedBy", "updatedAt")),
    ),
    _tool(
        "simulation.feature_flags.update", "feature-flags", "LaunchDarkly",
        "Update one simulated feature flag only when the exact reviewed revision still matches.", "write",
        {"worldId": _str("Host-bound simulation world ID", 120),
         "flagKey": _str("Feature flag key", 120),
         "enabled": _bool("Requested flag state"),
         "expectedRevision": _int("Reviewed flag revision", 1),
         "reason": _str("Operational change reason", 2000)},
        _obj({
            "flagKey": _str("Feature flag key", 120), "enabled": _bool("Current flag state"),
            "rolloutPercentage": _int("Rollout percent", 0, 100),
            "revision": _int("New flag revision", 1), "updatedAt": _str("Update timestamp", 100),
        }, ("flagKey", "enabled", "rolloutPercentage", "revision", "updatedAt")),
    ),
]

_CAPABILITY_INDEX = {item["id"]: item for item in _CAPABILITIES}


def capability_catalog() -> list[dict[str, Any]]:
    """Return independent trusted capability-contract copies."""

    return copy.deepcopy(_CAPABILITIES)


def _validate_value(value: Any, schema: Mapping[str, Any], path: str = "arguments") -> None:
    kind = schema.get("type")
    okay = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }.get(kind, False)
    if not okay:
        raise SimulationError("ARGUMENT_INVALID", f"{path} must be {kind}.")
    if "enum" in schema and value not in schema["enum"]:
        raise SimulationError("ARGUMENT_INVALID", f"{path} is outside the supported values.")
    if kind == "object":
        properties = schema.get("properties", {})
        if set(value) - set(properties) or set(schema.get("required", [])) - set(value):
            raise SimulationError("ARGUMENT_INVALID", f"{path} has missing or undeclared fields.")
        for key, child in value.items():
            _validate_value(child, properties[key], path + "." + key)
    elif kind == "array":
        if len(value) > schema.get("maxItems", 1000):
            raise SimulationError("ARGUMENT_INVALID", f"{path} contains too many items.")
        for index, child in enumerate(value):
            _validate_value(child, schema["items"], f"{path}[{index}]")
    elif kind == "string" and len(value) > schema.get("maxLength", 32000):
        raise SimulationError("ARGUMENT_INVALID", f"{path} is too long.")
    elif kind in {"integer", "number"} and (
        value < schema.get("minimum", float("-inf"))
        or value > schema.get("maximum", float("inf"))
    ):
        raise SimulationError("ARGUMENT_INVALID", f"{path} is outside the allowed range.")


def _request_receipt(world: dict[str, Any], tool: Mapping[str, Any], status_code: int) -> dict[str, Any]:
    world["requestCounter"] += 1
    request_id = f"simreq-{world['id'][-20:]}-{world['requestCounter']:05d}"
    provider = tool["verification"]["providerLabel"]
    return {
        "requestId": request_id, "provider": provider,
        "toolId": tool["id"], "statusCode": status_code,
        "virtualTime": world["clock"]["now"],
        "latencyMs": 35 + (world["requestCounter"] * 17) % 83,
        "simulated": True, "externalEffect": False,
        "worldId": world["id"],
    }


def _fault_outcome(
    world: dict[str, Any], tool: Mapping[str, Any], status_code: int,
    code: str, message: str, *, retryable: bool, condition: str | None,
    outcome_unknown: bool = False, retry_after_seconds: int | None = None,
    operation_key: str | None = None,
) -> ToolOutcome:
    receipt = _request_receipt(world, tool, status_code)
    fault = {
        "code": code, "message": message, "retryable": retryable,
        "condition": condition, "outcomeUnknown": outcome_unknown,
    }
    if retry_after_seconds is not None:
        fault["retryAfterSeconds"] = retry_after_seconds
    before = _business_hash(world)
    event = _append_event(
        world, "capability.failed", receipt["provider"], tool["id"],
        {"code": code, "statusCode": status_code, "retryable": retryable,
         "outcomeUnknown": outcome_unknown},
        before, _business_hash(world), operation_key=operation_key,
        request_id=receipt["requestId"],
    )
    receipt["eventId"] = event["eventId"]
    validate_world(world)
    return ToolOutcome(False, None, receipt, fault)


def _schedule(world: dict[str, Any], ident: str, delay_seconds: int, kind: str, payload: Mapping[str, Any]) -> None:
    if any(item.get("id") == ident for item in world["scheduled"]):
        return
    world["scheduled"].append({
        "id": ident, "dueSeconds": world["clock"]["elapsedSeconds"] + delay_seconds,
        "kind": kind, "payload": copy.deepcopy(dict(payload)),
    })
    world["scheduled"].sort(key=lambda item: (item["dueSeconds"], item["id"]))


def _apply_scheduled(world: dict[str, Any], item: Mapping[str, Any]) -> None:
    before = _business_hash(world)
    kind, payload = item["kind"], item["payload"]
    details: dict[str, Any]
    if kind == "feature_flag.external_change":
        flag = world["records"]["featureFlags"].get(payload["flagKey"])
        if flag is None:
            raise SimulationError("SCHEDULE_INVALID", "Scheduled flag change references an unknown flag.")
        flag.update(
            rolloutPercentage=payload["rolloutPercentage"], revision=flag["revision"] + 1,
            updatedBy="release-manager", updatedAt=world["clock"]["now"],
        )
        details = {"flagKey": flag["flagKey"], "revision": flag["revision"],
                   "rolloutPercentage": flag["rolloutPercentage"]}
    elif kind == "metrics.recovering":
        metrics = world["records"]["metrics"][payload["serviceId"]]
        metrics.update(
            state="recovering", errorRatePercent=3.4, p95LatencyMs=780,
            affectedSessions=18, consecutiveHealthyWindows=1,
            windowStart=_iso(_START_TIME, max(0, world["clock"]["elapsedSeconds"] - 300)),
            windowEnd=world["clock"]["now"], revision=metrics["revision"] + 1,
        )
        details = {"serviceId": payload["serviceId"], "state": "recovering",
                   "revision": metrics["revision"]}
    elif kind == "metrics.recovered":
        metrics = world["records"]["metrics"][payload["serviceId"]]
        metrics.update(
            state="healthy", errorRatePercent=0.7, p95LatencyMs=245,
            affectedSessions=0, consecutiveHealthyWindows=2,
            windowStart=_iso(_START_TIME, max(0, world["clock"]["elapsedSeconds"] - 300)),
            windowEnd=world["clock"]["now"], revision=metrics["revision"] + 1,
        )
        for alert in world["records"]["alerts"].values():
            if alert["serviceId"] == payload["serviceId"]:
                alert.update(status="resolved", revision=alert["revision"] + 1)
        details = {"serviceId": payload["serviceId"], "state": "healthy",
                   "revision": metrics["revision"]}
    elif kind == "deployment.rollback_completed":
        deployment = world["records"]["deployments"][payload["deploymentId"]]
        deployment.update(status="rolled_back", revision=deployment["revision"] + 1)
        details = {"deploymentId": deployment["deploymentId"], "status": deployment["status"],
                   "revision": deployment["revision"]}
    else:
        raise SimulationError("SCHEDULE_INVALID", "Scheduled simulation event kind is unsupported.")
    world["revision"] += 1
    _append_event(
        world, kind, "simulation-clock", None, details,
        before, _business_hash(world),
    )


def advance_clock(world: dict[str, Any], seconds: int) -> dict[str, Any]:
    """Advance deterministic virtual time and apply due scheduled events."""

    validate_world(world)
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 <= seconds <= 86400:
        raise SimulationError("CLOCK_ADVANCE_INVALID", "Advance the virtual clock by 0-86400 whole seconds.")
    start = world["clock"]["elapsedSeconds"]
    target = start + seconds
    due = [item for item in world["scheduled"] if item["dueSeconds"] <= target]
    for item in due:
        world["clock"]["elapsedSeconds"] = item["dueSeconds"]
        world["clock"]["now"] = _iso(_START_TIME, item["dueSeconds"])
        world["scheduled"].remove(item)
        _apply_scheduled(world, item)
    world["clock"]["elapsedSeconds"] = target
    world["clock"]["now"] = _iso(_START_TIME, target)
    if seconds:
        before = _business_hash(world)
        _append_event(
            world, "clock.advanced", "simulation-clock", None,
            {"fromSeconds": start, "toSeconds": target, "advancedSeconds": seconds},
            before, _business_hash(world),
        )
    validate_world(world)
    return copy.deepcopy(world["clock"])


def _read_output(world: Mapping[str, Any], tool_id: str, arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    records = world["records"]
    if tool_id == "simulation.metrics.query":
        alert = records["alerts"].get(arguments["alertId"])
        if alert is None:
            return None
        metrics = records["metrics"][alert["serviceId"]]
        return {
            "alertId": alert["id"], "serviceId": alert["serviceId"],
            "state": metrics["state"], "errorRatePercent": metrics["errorRatePercent"],
            "p95LatencyMs": metrics["p95LatencyMs"], "affectedSessions": metrics["affectedSessions"],
            "thresholdPercent": alert["thresholdPercent"],
            "consecutiveHealthyWindows": metrics["consecutiveHealthyWindows"],
            "alertStatus": alert["status"], "windowStart": metrics["windowStart"],
            "windowEnd": metrics["windowEnd"], "revision": metrics["revision"],
        }
    if tool_id == "simulation.catalog.get_service":
        return copy.deepcopy(records["services"].get(arguments["serviceId"]))
    if tool_id == "simulation.deployments.list_recent":
        items = [copy.deepcopy(item) for item in records["deployments"].values()
                 if item["serviceId"] == arguments["serviceId"]]
        items.sort(key=lambda item: (item["startedAt"], item["deploymentId"]), reverse=True)
        items = items[:arguments["limit"]]
        return {
            "serviceId": arguments["serviceId"], "deployments": items,
            "revision": max((item["revision"] for item in items), default=1),
        }
    if tool_id == "simulation.jira.search_incidents":
        requested = arguments["status"].casefold()
        items = [copy.deepcopy(item) for item in records["jiraIssues"].values()
                 if item["serviceId"] == arguments["serviceId"]
                 and (requested == "any" or item["status"].casefold() == requested)]
        items.sort(key=lambda item: item["key"])
        return {"issues": items, "count": len(items), "revision": records["jiraRevision"]}
    if tool_id == "simulation.confluence.get_page":
        return copy.deepcopy(records["confluencePages"].get(arguments["pageId"]))
    if tool_id == "simulation.slack.get_history":
        channel = records["slackChannels"].get(arguments["channelId"])
        if channel is None:
            return None
        messages = copy.deepcopy(channel["messages"][-arguments["limit"]:])
        return {"channelId": channel["channelId"], "messages": messages,
                "hasMore": len(channel["messages"]) > len(messages), "revision": channel["revision"]}
    if tool_id == "simulation.feature_flags.get":
        return copy.deepcopy(records["featureFlags"].get(arguments["flagKey"]))
    raise SimulationError("CAPABILITY_NOT_READ", "The selected capability is not a registered read.")


def _commit_write(
    world: dict[str, Any], tool: Mapping[str, Any], arguments: Mapping[str, Any],
    operation_key: str, receipt: dict[str, Any], output: Mapping[str, Any], before_hash: str,
) -> dict[str, Any]:
    world["revision"] += 1
    event = _append_event(
        world, "operation.committed", receipt["provider"], tool["id"],
        {"resultHash": _hash(output), "worldRevision": world["revision"]},
        before_hash, _business_hash(world), operation_key=operation_key,
        request_id=receipt["requestId"],
    )
    canonical_receipt = {
        **receipt, "statusCode": 201, "operationKey": operation_key,
        "providerReceiptId": "simop-" + _hash(operation_key)[:16],
        "eventId": event["eventId"], "committedAt": world["clock"]["now"],
        "worldRevision": world["revision"], "resultHash": _hash(output),
        "replayed": False,
    }
    record = {
        "operationKey": operation_key, "toolId": tool["id"],
        "actionHash": _hash({"toolId": tool["id"], "arguments": arguments}),
        "argumentsHash": _hash(arguments), "state": "committed",
        "output": copy.deepcopy(dict(output)), "receipt": copy.deepcopy(canonical_receipt),
    }
    record["recordHash"] = _hash(record)
    world["operations"][operation_key] = record
    return canonical_receipt


def _write_output(
    world: dict[str, Any], tool_id: str, arguments: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, tuple[int, str, str, str | None] | None]:
    records = world["records"]
    if tool_id == "simulation.jira.create_incident":
        duplicates = [item for item in records["jiraIssues"].values()
                      if item["serviceId"] == arguments["serviceId"]
                      and item["status"] in {"Investigating", "Mitigating"}]
        if duplicates:
            return None, (409, "INCIDENT_ALREADY_EXISTS",
                          "An active incident already exists for this service.", "conflictingEvidence")
        key = f"{arguments['projectKey']}-{world['nextJiraNumber']}"
        world["nextJiraNumber"] += 1
        issue = {
            "key": key, "serviceId": arguments["serviceId"],
            "summary": arguments["summary"], "severity": arguments["severity"],
            "status": "Investigating", "createdAt": world["clock"]["now"], "revision": 1,
        }
        records["jiraIssues"][key] = issue
        records["jiraRevision"] += 1
        return copy.deepcopy(issue), None
    if tool_id == "simulation.slack.post_message":
        channel = records["slackChannels"].get(arguments["channelId"])
        if channel is None:
            return None, (404, "CHANNEL_NOT_FOUND", "The simulated Slack channel does not exist.", "missingCapability")
        message = {
            "messageId": f"1701.{world['nextSlackSequence']:04d}",
            "authorId": "AXIOM-INCIDENT-BOT", "text": arguments["text"],
            "createdAt": world["clock"]["now"],
        }
        world["nextSlackSequence"] += 1
        channel["messages"].append(message)
        channel["revision"] += 1
        return copy.deepcopy(message), None
    if tool_id == "simulation.feature_flags.update":
        flag = records["featureFlags"].get(arguments["flagKey"])
        if flag is None:
            return None, (404, "FLAG_NOT_FOUND", "The simulated feature flag does not exist.", "missingCapability")
        if flag["revision"] != arguments["expectedRevision"]:
            return None, (412, "FEATURE_FLAG_VERSION_CHANGED",
                          "The feature flag revision changed after review.", "changedBusinessState")
        flag.update(
            enabled=arguments["enabled"],
            rolloutPercentage=100 if arguments["enabled"] else 0,
            revision=flag["revision"] + 1, updatedBy="AXIOM-INCIDENT-BOT",
            updatedAt=world["clock"]["now"],
        )
        if not flag["enabled"]:
            suffix = _hash({"flag": flag["flagKey"], "revision": flag["revision"]})[:10]
            _schedule(world, "flag-recovering-" + suffix, 60, "metrics.recovering",
                      {"serviceId": flag["serviceId"]})
            _schedule(world, "flag-recovered-" + suffix, 180, "metrics.recovered",
                      {"serviceId": flag["serviceId"]})
        return {
            "flagKey": flag["flagKey"], "enabled": flag["enabled"],
            "rolloutPercentage": flag["rolloutPercentage"], "revision": flag["revision"],
            "updatedAt": flag["updatedAt"],
        }, None
    if tool_id == "simulation.deployments.rollback":
        deployment = records["deployments"].get(arguments["deploymentId"])
        if deployment is None:
            return None, (404, "DEPLOYMENT_NOT_FOUND", "The simulated deployment does not exist.", "missingCapability")
        if deployment["revision"] != arguments["expectedRevision"]:
            return None, (412, "DEPLOYMENT_VERSION_CHANGED",
                          "The deployment revision changed after review.", "changedBusinessState")
        deployment.update(status="rolling_back", revision=deployment["revision"] + 1)
        suffix = _hash({"deployment": deployment["deploymentId"], "revision": deployment["revision"]})[:10]
        _schedule(world, "rollback-complete-" + suffix, 120, "deployment.rollback_completed",
                  {"deploymentId": deployment["deploymentId"]})
        _schedule(world, "rollback-recovering-" + suffix, 60, "metrics.recovering",
                  {"serviceId": deployment["serviceId"]})
        _schedule(world, "rollback-recovered-" + suffix, 180, "metrics.recovered",
                  {"serviceId": deployment["serviceId"]})
        return {
            "deploymentId": deployment["deploymentId"], "status": deployment["status"],
            "revision": deployment["revision"],
            "scheduledCompletionAt": _iso(_START_TIME, world["clock"]["elapsedSeconds"] + 120),
        }, None
    raise SimulationError("CAPABILITY_NOT_WRITE", "The selected capability is not a registered write.")


def operation_receipt(world: Mapping[str, Any], operation_key: str) -> dict[str, Any] | None:
    """Return the immutable committed operation record, if any."""

    validate_world(world)
    record = world["operations"].get(operation_key)
    return copy.deepcopy(record) if record else None


def reconcile_operation(world: dict[str, Any], operation_key: str) -> ToolOutcome:
    """Resolve an uncertain simulated write by its stable operation identity."""

    validate_world(world)
    if not isinstance(operation_key, str) or not _OPERATION_KEY.fullmatch(operation_key):
        raise SimulationError("OPERATION_KEY_INVALID", "A bounded stable operation key is required.")
    record = world["operations"].get(operation_key)
    if record is None:
        pseudo_tool = {
            "id": "simulation.operation.reconcile",
            "verification": {"providerLabel": "Simulation Operation Ledger"},
        }
        return _fault_outcome(
            world, pseudo_tool, 404, "OPERATION_NOT_FOUND",
            "No committed simulated operation matches this identity.",
            retryable=False, condition="missingCapability", operation_key=operation_key,
        )
    tool = _CAPABILITY_INDEX[record["toolId"]]
    request_receipt = _request_receipt(world, tool, 200)
    before = _business_hash(world)
    event = _append_event(
        world, "operation.reconciled", request_receipt["provider"], tool["id"],
        {"providerReceiptId": record["receipt"]["providerReceiptId"],
         "resultHash": record["receipt"]["resultHash"]},
        before, _business_hash(world), operation_key=operation_key,
        request_id=request_receipt["requestId"],
    )
    receipt = {
        **copy.deepcopy(record["receipt"]),
        "requestId": request_receipt["requestId"], "statusCode": 200,
        "latencyMs": request_receipt["latencyMs"], "replayed": True,
        "reconciled": True, "recovered": True,
        "reconciliationEventId": event["eventId"],
    }
    validate_world(world)
    return ToolOutcome(True, copy.deepcopy(record["output"]), receipt, None)


def execute_tool(
    world: dict[str, Any], tool_id: str, arguments: Mapping[str, Any],
    *, operation_key: str | None = None,
) -> ToolOutcome:
    """Execute one simulated provider call against the supplied mutable world."""

    validate_world(world)
    tool = _CAPABILITY_INDEX.get(tool_id)
    if tool is None:
        raise SimulationError("CAPABILITY_UNKNOWN", "The simulation capability is not registered.")
    if not isinstance(arguments, Mapping):
        raise SimulationError("ARGUMENT_INVALID", "Capability arguments must be an object.")
    arguments = copy.deepcopy(dict(arguments))
    _validate_value(arguments, tool["inputSchema"])
    if arguments["worldId"] != world["id"]:
        raise SimulationError("WORLD_BINDING_CHANGED", "The capability cannot cross the host-bound simulation world.")

    is_write = tool["effect"] == "write"
    if is_write:
        if not isinstance(operation_key, str) or not _OPERATION_KEY.fullmatch(operation_key):
            raise SimulationError("OPERATION_KEY_REQUIRED", "Simulated writes require a bounded stable operation key.")
        existing = world["operations"].get(operation_key)
        action_hash = _hash({"toolId": tool_id, "arguments": arguments})
        if existing:
            if existing["actionHash"] != action_hash:
                return _fault_outcome(
                    world, tool, 409, "IDEMPOTENCY_KEY_CONFLICT",
                    "The operation key is already bound to a different exact action.",
                    retryable=False, condition="conflictingEvidence", operation_key=operation_key,
                )
            request_receipt = _request_receipt(world, tool, 200)
            before = _business_hash(world)
            event = _append_event(
                world, "operation.replayed", request_receipt["provider"], tool_id,
                {"providerReceiptId": existing["receipt"]["providerReceiptId"],
                 "resultHash": existing["receipt"]["resultHash"]},
                before, _business_hash(world), operation_key=operation_key,
                request_id=request_receipt["requestId"],
            )
            receipt = {
                **copy.deepcopy(existing["receipt"]),
                "requestId": request_receipt["requestId"], "statusCode": 200,
                "latencyMs": request_receipt["latencyMs"], "replayed": True,
                "replayEventId": event["eventId"],
            }
            validate_world(world)
            return ToolOutcome(True, copy.deepcopy(existing["output"]), receipt, None)

    if tool_id == "simulation.metrics.query" and arguments["advanceSeconds"]:
        advance_clock(world, arguments["advanceSeconds"])

    if tool_id == "simulation.confluence.get_page" and world["faults"]["confluenceUnavailable"]:
        return _fault_outcome(
            world, tool, 503, "CONFLUENCE_SERVICE_UNAVAILABLE",
            "The simulated Confluence provider is unavailable.", retryable=True,
            condition="unavailableService",
        )
    if tool_id == "simulation.slack.post_message" and world["faults"]["slackRateLimitRemaining"] > 0:
        world["faults"]["slackRateLimitRemaining"] -= 1
        return _fault_outcome(
            world, tool, 429, "SLACK_RATE_LIMITED",
            "The simulated Slack rate limit was reached; retry after 30 virtual seconds.",
            retryable=True, condition="unavailableService", retry_after_seconds=30,
            operation_key=operation_key,
        )

    before = _business_hash(world)
    receipt = _request_receipt(world, tool, 200)
    if not is_write:
        output = _read_output(world, tool_id, arguments)
        if output is None:
            return _fault_outcome(
                world, tool, 404, "SIMULATED_RECORD_NOT_FOUND",
                "No simulated provider record matches the supplied identifier.",
                retryable=False, condition="missingCapability",
            )
        _validate_value(output, tool["outputSchema"], "output")
        event = _append_event(
            world, "capability.observed", receipt["provider"], tool_id,
            {"resultHash": _hash(output), "recordRevision": output.get("revision")},
            before, _business_hash(world), request_id=receipt["requestId"],
        )
        receipt.update(eventId=event["eventId"], resultHash=_hash(output))
        validate_world(world)
        return ToolOutcome(True, copy.deepcopy(output), receipt, None)

    output, provider_fault = _write_output(world, tool_id, arguments)
    if provider_fault:
        status, code, message, condition = provider_fault
        return _fault_outcome(
            world, tool, status, code, message, retryable=False,
            condition=condition, operation_key=operation_key,
        )
    assert output is not None
    _validate_value(output, tool["outputSchema"], "output")
    canonical_receipt = _commit_write(
        world, tool, arguments, operation_key, receipt, output, before,
    )
    if tool_id == "simulation.jira.create_incident" and world["faults"]["jiraLostAckRemaining"] > 0:
        world["faults"]["jiraLostAckRemaining"] -= 1
        lost_receipt = _request_receipt(world, tool, 504)
        event = _append_event(
            world, "delivery.acknowledgement_lost", lost_receipt["provider"], tool_id,
            {"operationKey": operation_key, "outcome": "unknown-to-caller"},
            _business_hash(world), _business_hash(world), operation_key=operation_key,
            request_id=lost_receipt["requestId"],
        )
        lost_receipt.update(eventId=event["eventId"], operationKey=operation_key,
                            providerReceiptId=None, outcome="unknown")
        validate_world(world)
        return ToolOutcome(False, None, lost_receipt, {
            "code": "JIRA_ACKNOWLEDGEMENT_LOST",
            "message": "The simulated Jira response was lost after the provider committed the operation.",
            "retryable": False, "condition": "unavailableService", "outcomeUnknown": True,
        })
    validate_world(world)
    return ToolOutcome(True, copy.deepcopy(output), canonical_receipt, None)


def incident_commander_spec() -> dict[str, Any]:
    """Return the registered, reusable Goal Agent specification."""

    result_schema = _obj({
        "status": _str("Business status", 50, values=("resolved", "mitigated", "investigating", "needs_human")),
        "incidentKey": _str("Jira incident key, or empty when unavailable", 100),
        "serviceId": _str("Affected service", 120),
        "summary": _str("Evidence-based incident summary", 3000),
        "mitigation": _str("Applied mitigation or none", 120),
        "communicationState": _str("Stakeholder communication state", 120),
        "recoveryVerified": _bool("Whether authoritative metrics verify recovery"),
        "unresolvedRisks": _array(_str("Unresolved risk", 1000), 20),
    }, ("status", "incidentKey", "serviceId", "summary", "mitigation",
        "communicationState", "recoveryVerified", "unresolvedRisks"))
    input_schema = _obj({
        "worldId": _str("Host-bound isolated simulation world", 120),
        "alertId": _str("Metrics alert to investigate", 120),
        "ownerTeam": _str("Clarified owner when the catalog is incomplete", 200),
        "slackChannelId": _str("Clarified incident channel when the catalog is incomplete", 120),
    }, ("worldId",))
    cases = []
    for profile in scenario_profiles():
        cases.append({
            "id": profile["id"], "description": profile["description"],
            "input": {"worldId": "atlas-" + profile["id"], "alertId": "ALT-CHECKOUT-9001"},
            "expectedState": {"observationConditioned": True, "profileId": profile["id"]},
        })
    return {
        "id": INCIDENT_COMMANDER_ID, "version": 1,
        "name": "Atlas Incident Commander",
        "mission": "Investigate an Atlas Checkout production alert, reuse an existing incident when present, prepare the safest evidence-backed mitigation and communicate the verified result without claiming external effects.",
        "instructions": (
            "Start from authoritative simulated metrics and service ownership. Inspect the recent deployment, active Jira incidents, the versioned runbook, and the related feature flag. "
            "Reuse an active incident rather than creating another. Prefer the runbook's feature-flag mitigation when its reviewed revision still matches; otherwise use the declared rollback fallback. "
            "Every write is an isolated simulation and still requires exact approval. Treat provider faults as observations, retry Slack at most once after a rate limit, and never call an unregistered capability. "
            "Verify recovery using two healthy metrics windows before reporting resolved."
        ),
        "inputSchema": input_schema, "outputSchema": result_schema,
        "contextFields": ["input.worldId", "input.alertId", "input.ownerTeam", "input.slackChannelId"],
        "allowedTools": [item["id"] for item in _CAPABILITIES],
        "requiredEvidenceTools": ["simulation.metrics.query", "simulation.catalog.get_service"],
        "stopRules": {
            "missingCapability": "return_partial", "deniedCapability": "escalate",
            "unavailableService": "return_partial", "conflictingEvidence": "escalate",
            "budgetExhausted": "stop", "changedBusinessState": "escalate",
        },
        "policyRefs": ["simulation-policy:atlas-incident-v1"],
        "evaluationCases": cases,
        "limits": {
            "maxTurns": 28, "maxToolCalls": 20, "maxWriteCalls": 5,
            "maxContextBytes": 96000, "maxOutputBytes": 32000,
            "maxModelTokens": 128000, "maxEstimatedCostMicros": 5_000_000,
            "timeoutSeconds": 1800,
        },
    }


def _observations(state: Mapping[str, Any], tool_id: str) -> list[tuple[str, dict[str, Any]]]:
    values: list[tuple[str, dict[str, Any]]] = []
    facts = state.get("facts", {})
    for event in state.get("events", []):
        if event.get("type") != "tool.observed" or event.get("toolId") != tool_id:
            continue
        call_id = event.get("callId")
        value = facts.get(call_id)
        if isinstance(call_id, str) and isinstance(value, dict):
            values.append((call_id, value))
    return values


def _failures(state: Mapping[str, Any], tool_id: str) -> list[tuple[str, dict[str, Any]]]:
    values: list[tuple[str, dict[str, Any]]] = []
    facts = state.get("facts", {})
    for event in state.get("events", []):
        if event.get("type") != "tool.failed" or event.get("toolId") != tool_id:
            continue
        call_id = event.get("callId")
        value = facts.get(call_id, {})
        error = value.get("error") if isinstance(value, dict) else None
        if isinstance(call_id, str) and isinstance(error, dict):
            values.append((call_id, error))
    return values


def _ref(call_id: str, field: str) -> dict[str, str]:
    return {"$ref": f"facts.{call_id}.{field}"}


def _call(tool_id: str, arguments: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {"kind": "call", "toolId": tool_id, "arguments": copy.deepcopy(dict(arguments)), "reason": reason}


def incident_commander_decision(compiled: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Return one observation-driven scripted decision for offline demos.

    The function never reads ``profileId`` or any scenario selector.  Different
    paths arise only from recorded tool outputs, recorded tool faults, and
    explicitly supplied clarification fields.
    """

    spec_id = compiled.get("spec", {}).get("id") if isinstance(compiled, Mapping) else None
    if spec_id != INCIDENT_COMMANDER_ID:
        raise SimulationError("FIXTURE_AGENT_UNSUPPORTED", "The simulation fixture supports only Atlas Incident Commander.")
    task_input = state.get("input", {})
    if not isinstance(task_input.get("alertId"), str) or not task_input["alertId"].strip():
        return {
            "kind": "ask", "question": "Which Atlas alert should I investigate?",
            "fields": ["input.alertId"],
            "reason": "An alert identifier is required before retrieving scoped metrics.",
        }

    metrics_observations = _observations(state, "simulation.metrics.query")
    if not metrics_observations:
        return _call(
            "simulation.metrics.query",
            {"alertId": {"$ref": "input.alertId"}, "advanceSeconds": 0},
            "Observe the alert and current customer-impact metrics before choosing an action.",
        )
    baseline_call, baseline = metrics_observations[0]

    catalog_observations = _observations(state, "simulation.catalog.get_service")
    if not catalog_observations:
        return _call(
            "simulation.catalog.get_service", {"serviceId": _ref(baseline_call, "serviceId")},
            "Resolve the service owner, runbook, and approved incident channel.",
        )
    catalog_call, catalog = catalog_observations[-1]
    missing_fields = []
    if not catalog.get("ownerTeam") and not task_input.get("ownerTeam"):
        missing_fields.append("input.ownerTeam")
    if not catalog.get("slackChannelId") and not task_input.get("slackChannelId"):
        missing_fields.append("input.slackChannelId")
    if missing_fields:
        return {
            "kind": "ask",
            "question": "The service catalog is incomplete. Who owns Atlas Checkout, and which incident channel is approved?",
            "fields": missing_fields,
            "reason": "The agent cannot invent ownership or a communication destination.",
        }

    deployments = _observations(state, "simulation.deployments.list_recent")
    if not deployments:
        return _call(
            "simulation.deployments.list_recent",
            {"serviceId": _ref(baseline_call, "serviceId"), "limit": 3},
            "Compare the alert with recent production changes.",
        )
    deployment_call, deployment_result = deployments[-1]
    recent = deployment_result.get("deployments", [])
    if not recent:
        return _finish_decision(
            state, baseline_call, catalog_call, "", "none", "not_posted", False,
            ["No recent deployment was available for an evidence-backed mitigation."],
        )
    deployment = recent[0]

    jira_searches = _observations(state, "simulation.jira.search_incidents")
    jira_failures = _failures(state, "simulation.jira.create_incident")
    if not jira_searches or (jira_failures and jira_failures[-1][1].get("code") == "JIRA_ACKNOWLEDGEMENT_LOST" and len(jira_searches) == 1):
        return _call(
            "simulation.jira.search_incidents",
            {"serviceId": _ref(baseline_call, "serviceId"), "status": "Investigating"},
            "Search for an active incident before creating or reconciling one.",
        )
    jira_call, jira = jira_searches[-1]

    runbooks = _observations(state, "simulation.confluence.get_page")
    runbook_failures = _failures(state, "simulation.confluence.get_page")
    if not runbooks and not runbook_failures:
        return _call(
            "simulation.confluence.get_page", {"pageId": _ref(catalog_call, "runbookPageId")},
            "Retrieve the versioned incident runbook before choosing a mitigation.",
        )

    flags = _observations(state, "simulation.feature_flags.get")
    if runbooks and deployment.get("featureFlagKey") and not flags:
        return _call(
            "simulation.feature_flags.get", {"flagKey": deployment["featureFlagKey"]},
            "Inspect the runbook-linked feature flag and its exact revision.",
        )

    issue_creates = _observations(state, "simulation.jira.create_incident")
    issue_key = jira.get("issues", [{}])[0].get("key", "") if jira.get("issues") else ""
    if not issue_key and issue_creates:
        issue_key = issue_creates[-1][1].get("key", "")
    if not issue_key and not jira_failures:
        severity = "SEV-1" if baseline.get("severity") == "critical" or baseline["errorRatePercent"] >= 10 else "SEV-2"
        return _call(
            "simulation.jira.create_incident",
            {
                "projectKey": "OPS", "serviceId": _ref(baseline_call, "serviceId"),
                "summary": "Atlas Checkout errors after " + str(deployment.get("version", "recent deployment")),
                "severity": severity,
            },
            "No active incident was observed; prepare one exact Jira record for approval.",
        )

    flag_updates = _observations(state, "simulation.feature_flags.update")
    flag_failures = _failures(state, "simulation.feature_flags.update")
    rollbacks = _observations(state, "simulation.deployments.rollback")
    rollback_failures = _failures(state, "simulation.deployments.rollback")
    mitigation = "none"
    mitigation_done = False
    if flag_updates:
        mitigation, mitigation_done = "feature_flag_disabled", True
    elif rollbacks:
        mitigation, mitigation_done = "deployment_rollback_started", True
    elif runbooks and flags and not flag_failures and not rollback_failures:
        flag_call, flag = flags[-1]
        if flag.get("enabled"):
            return _call(
                "simulation.feature_flags.update",
                {
                    "flagKey": _ref(flag_call, "flagKey"), "enabled": False,
                    "expectedRevision": _ref(flag_call, "revision"),
                    "reason": "Disable the runbook-linked checkout-v2 path while the incident is active.",
                },
                "Prepare the runbook's least-disruptive mitigation using the exact observed flag revision.",
            )
        return _call(
            "simulation.deployments.rollback",
            {
                "deploymentId": deployment["deploymentId"],
                "expectedRevision": deployment["revision"],
                "reason": "The runbook-linked flag is already disabled; roll back the correlated deployment.",
            },
            "Prepare the runbook fallback using the exact observed deployment revision.",
        )

    if mitigation_done and len(metrics_observations) < 2:
        return _call(
            "simulation.metrics.query",
            {"alertId": {"$ref": "input.alertId"}, "advanceSeconds": 180},
            "Advance only the virtual clock and verify two post-mitigation metrics windows.",
        )
    latest_metrics_call, latest_metrics = metrics_observations[-1]
    recovery_verified = bool(
        latest_metrics.get("state") == "healthy"
        and latest_metrics.get("consecutiveHealthyWindows", 0) >= 2
        and latest_metrics.get("errorRatePercent", 100) < latest_metrics.get("thresholdPercent", 0)
    )

    channel_id = catalog.get("slackChannelId") or task_input.get("slackChannelId", "")
    slack_posts = _observations(state, "simulation.slack.post_message")
    slack_failures = _failures(state, "simulation.slack.post_message")
    if channel_id and not slack_posts:
        retryable_rate_limits = [error for _, error in slack_failures
                                 if error.get("code") == "SLACK_RATE_LIMITED" and error.get("retryable")]
        if not slack_failures or len(retryable_rate_limits) < 2:
            text = (
                f"{issue_key or 'Incident pending'} | Atlas Checkout | "
                f"mitigation={mitigation} | recovery={'verified' if recovery_verified else 'not yet verified'}"
            )
            return _call(
                "simulation.slack.post_message", {"channelId": channel_id, "text": text},
                "Post the exact evidence-backed incident state to the approved simulated channel."
                + (" This is the single bounded retry after the observed 429." if slack_failures else ""),
            )

    communication = "posted" if slack_posts else (
        "rate_limited" if slack_failures else "not_configured"
    )
    unresolved = []
    if runbook_failures:
        unresolved.append("The Confluence runbook was unavailable; no mitigation was invented.")
    if flag_failures or rollback_failures:
        unresolved.append("The prepared mitigation could not be applied because authoritative state changed.")
    if not recovery_verified:
        unresolved.append("Two healthy post-mitigation metrics windows have not been verified.")
    if communication != "posted":
        unresolved.append("The incident update was not accepted by the simulated Slack provider.")
    return _finish_decision(
        state, latest_metrics_call, catalog_call, issue_key, mitigation,
        communication, recovery_verified, unresolved,
    )


def _finish_decision(
    state: Mapping[str, Any], metrics_call: str, catalog_call: str,
    incident_key: str, mitigation: str, communication: str,
    recovery_verified: bool, unresolved: list[str],
) -> dict[str, Any]:
    service = state["facts"][metrics_call]["serviceId"]
    status = "resolved" if recovery_verified else ("mitigated" if mitigation != "none" else "investigating")
    summary = (
        "Authoritative simulated metrics verify recovery after the approved mitigation."
        if recovery_verified else
        "The incident remains under investigation; unresolved conditions are reported without claiming recovery."
    )
    evidence = [
        f"facts.{metrics_call}.serviceId", f"facts.{metrics_call}.errorRatePercent",
        f"facts.{metrics_call}.consecutiveHealthyWindows",
        f"facts.{catalog_call}.criticality",
    ]
    for event in state.get("events", []):
        if event.get("type") != "tool.observed":
            continue
        call_id, tool_id = event.get("callId"), event.get("toolId")
        if tool_id == "simulation.jira.create_incident" and f"facts.{call_id}.key" not in evidence:
            evidence.append(f"facts.{call_id}.key")
        elif tool_id == "simulation.jira.search_incidents" and f"facts.{call_id}.count" not in evidence:
            evidence.append(f"facts.{call_id}.count")
        elif tool_id in {"simulation.feature_flags.update", "simulation.deployments.rollback"}:
            field = "flagKey" if tool_id.endswith("update") else "deploymentId"
            evidence.append(f"facts.{call_id}.{field}")
        elif tool_id == "simulation.slack.post_message":
            evidence.append(f"facts.{call_id}.messageId")
    return {
        "kind": "finish",
        "output": {
            "status": status, "incidentKey": incident_key, "serviceId": service,
            "summary": summary, "mitigation": mitigation,
            "communicationState": communication, "recoveryVerified": recovery_verified,
            "unresolvedRisks": unresolved,
        },
        "evidence": list(dict.fromkeys(evidence)),
        "reason": "Conclude only from recorded provider observations and explicitly retain unresolved risk.",
    }


def validate_incident_outcome(world: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an Incident Commander result against authoritative world state."""

    validate_world(world)
    base = {
        "validatorId": OUTCOME_VALIDATOR_ID, "agentId": INCIDENT_COMMANDER_ID,
        "businessOutcomeVerified": False, "status": "unknown", "checks": [],
    }
    if not isinstance(state, Mapping) or state.get("status") != "completed" or not isinstance(state.get("output"), Mapping):
        return {**base, "reason": "A completed typed Incident Commander result is required."}
    output = state["output"]
    records = world["records"]
    metrics = records["metrics"]["atlas-checkout"]
    incidents = [item for item in records["jiraIssues"].values()
                 if item["serviceId"] == "atlas-checkout" and item["status"] in {"Investigating", "Mitigating"}]
    flag = records["featureFlags"]["checkout-v2"]
    deployments = list(records["deployments"].values())
    slack_messages = [message for channel in records["slackChannels"].values()
                      for message in channel["messages"] if message["authorId"] == "AXIOM-INCIDENT-BOT"]
    authoritative_recovery = (
        metrics["state"] == "healthy" and metrics["consecutiveHealthyWindows"] >= 2
        and metrics["errorRatePercent"] < records["alerts"]["ALT-CHECKOUT-9001"]["thresholdPercent"]
    )
    authoritative_mitigation = (
        "feature_flag_disabled" if not flag["enabled"] else
        "deployment_rollback_started" if any(item["status"] in {"rolling_back", "rolled_back"} for item in deployments)
        else "none"
    )

    checks: list[dict[str, Any]] = []

    def check(identifier: str, passed: bool, statement: str, evidence: list[str]) -> None:
        checks.append({
            "id": identifier, "status": "satisfied" if passed else "contradicted",
            "statement": statement, "evidence": evidence,
            "kind": "authoritative-simulation-state",
        })

    check(
        "recovery-claim", output.get("recoveryVerified") is authoritative_recovery,
        "The recovery claim matches two authoritative healthy metrics windows.",
        ["world.records.metrics.atlas-checkout"],
    )
    check(
        "service-identity", output.get("serviceId") == "atlas-checkout",
        "The result identifies the service represented by the authoritative alert.",
        ["world.records.alerts.ALT-CHECKOUT-9001.serviceId"],
    )
    check(
        "incident-identity",
        (not output.get("incidentKey") and not incidents)
        or any(item["key"] == output.get("incidentKey") for item in incidents),
        "The returned incident key names an authoritative active Jira record.",
        ["world.records.jiraIssues"],
    )
    check(
        "no-duplicate-incident", len(incidents) <= 1,
        "The sandbox contains at most one active incident for Atlas Checkout.",
        ["world.records.jiraIssues"],
    )
    check(
        "mitigation-claim", output.get("mitigation") == authoritative_mitigation,
        "The reported mitigation matches the authoritative flag or deployment state.",
        ["world.records.featureFlags.checkout-v2", "world.records.deployments"],
    )
    slack_rate_limited = any(
        event.get("toolId") == "simulation.slack.post_message"
        and event.get("kind") == "capability.failed"
        and event.get("details", {}).get("code") == "SLACK_RATE_LIMITED"
        for event in world["events"]
    )
    expected_communication = (
        "posted" if slack_messages else
        "rate_limited" if slack_rate_limited else
        "not_configured"
    )
    check(
        "communication-receipt", output.get("communicationState") == expected_communication,
        "A claimed posted update has an authoritative simulated Slack message.",
        ["world.records.slackChannels"],
    )
    check(
        "isolated-effects",
        world["sandbox"]["externalEffects"] is False
        and all(record["receipt"].get("externalEffect") is False for record in world["operations"].values()),
        "Every committed effect remained inside the isolated simulation world.",
        ["world.sandbox", "world.operations"],
    )
    expected_status = "resolved" if authoritative_recovery else (
        "mitigated" if authoritative_mitigation != "none" else "investigating"
    )
    check(
        "status-claim", output.get("status") == expected_status,
        "The business status matches authoritative recovery and mitigation state.",
        ["world.records.metrics.atlas-checkout", "world.records.featureFlags.checkout-v2"],
    )
    verified = all(item["status"] == "satisfied" for item in checks)
    return {
        **base, "businessOutcomeVerified": verified,
        "status": "satisfied" if verified else "contradicted",
        "checks": checks,
        "reason": "All authoritative simulation checks passed." if verified
        else "One or more authoritative simulation checks contradicted the result.",
    }


# Stable host-integration surface.  The more descriptive functions above stay
# public as well, but these short names let the HTTP/storage layer depend on a
# deliberately small contract.


def profiles() -> list[dict[str, Any]]:
    """Return the canonical profile catalog (aliases are intentionally hidden)."""

    return scenario_profiles()


def tool_catalog() -> list[dict[str, Any]]:
    """Return trusted in-process capability contracts for the simulation host."""

    return capability_catalog()


def agent_specs() -> list[dict[str, Any]]:
    """Return agent specifications registered by this simulation package."""

    return [incident_commander_spec()]


def scenarios() -> list[dict[str, Any]]:
    """Return launch descriptors without allocating or mutating a world."""

    return [
        {
            "id": profile["id"],
            "name": profile["name"],
            "description": profile["description"],
            "profileVersion": 1,
            "definitionHash": profile["definitionHash"],
            "agentId": INCIDENT_COMMANDER_ID,
            "input": {"alertId": "ALT-CHECKOUT-9001"},
        }
        for profile in scenario_profiles()
    ]


_FAULT_FIELDS = {
    "confluence-unavailable": "confluenceUnavailable",
    "confluenceUnavailable": "confluenceUnavailable",
    "slack-rate-limit": "slackRateLimitRemaining",
    "slackRateLimitRemaining": "slackRateLimitRemaining",
    "jira-lost-ack": "jiraLostAckRemaining",
    "jiraLostAckRemaining": "jiraLostAckRemaining",
}


def set_fault(world: dict[str, Any], fault_id: str, enabled: bool) -> dict[str, Any]:
    """Enable or disable one declared deterministic fault and audit the change."""

    validate_world(world)
    field = _FAULT_FIELDS.get(fault_id)
    if field is None:
        raise SimulationError("FAULT_UNKNOWN", "The simulation fault is not registered.")
    if not isinstance(enabled, bool):
        raise SimulationError("FAULT_VALUE_INVALID", "Fault state must be a boolean.")
    before = _business_hash(world)
    if field.endswith("Remaining"):
        world["faults"][field] = 1 if enabled else 0
    else:
        world["faults"][field] = enabled
    world["revision"] += 1
    _append_event(
        world, "fault.changed", "simulation-lab", None,
        {"faultId": fault_id, "enabled": enabled},
        before, _business_hash(world),
    )
    validate_world(world)
    return {
        "faultId": fault_id,
        "enabled": enabled,
        "worldRevision": world["revision"],
        "faults": copy.deepcopy(world["faults"]),
    }


def execute(
    world: dict[str, Any], tool_id: str, arguments: Mapping[str, Any],
    operation_key: str | None = None, action_hash: str | None = None,
    purpose: str = "execute",
) -> dict[str, Any]:
    """Run or reconcile one call and return a persistence-ready result envelope.

    Provider faults are values (``ok`` is false); malformed requests and broken
    integrity boundaries raise :class:`SimulationError`.  ``action_hash`` is a
    host approval identity, while the operation ledger independently binds the
    exact tool and argument hash.
    """

    validate_world(world)
    if purpose not in {"execute", "reconcile"}:
        raise SimulationError(
            "EXECUTION_PURPOSE_INVALID", "Purpose must be execute or reconcile."
        )
    if action_hash is not None and (
        not isinstance(action_hash, str) or not 1 <= len(action_hash) <= 300
    ):
        raise SimulationError(
            "ACTION_HASH_INVALID", "Action hashes must be bounded non-empty strings."
        )
    existing = world["operations"].get(operation_key) if operation_key else None
    if (existing is not None and action_hash is not None
            and existing.get("approvedActionHash") not in {None, action_hash}):
        raise SimulationError(
            "ACTION_HASH_CHANGED",
            "The operation is already bound to a different approved action.",
        )
    first_event = len(world["events"])
    if purpose == "reconcile":
        if operation_key is None:
            raise SimulationError(
                "OPERATION_KEY_REQUIRED", "Reconciliation requires an operation key."
            )
        outcome = reconcile_operation(world, operation_key)
    else:
        outcome = execute_tool(
            world, tool_id, arguments, operation_key=operation_key,
        )

    operation = world["operations"].get(operation_key) if operation_key else None
    if operation is not None and action_hash is not None and operation.get("approvedActionHash") is None:
        operation["approvedActionHash"] = action_hash
        operation["recordHash"] = _hash(
            {key: value for key, value in operation.items() if key != "recordHash"}
        )
        before = _business_hash(world)
        _append_event(
            world, "operation.approval_bound", "simulation-lab", operation["toolId"],
            {"actionHash": action_hash}, before, _business_hash(world),
            operation_key=operation_key,
        )
    validate_world(world)
    return {
        "ok": outcome.ok,
        "purpose": purpose,
        "world": copy.deepcopy(world),
        "worldRevision": world["revision"],
        "output": copy.deepcopy(outcome.output),
        "receipt": copy.deepcopy(outcome.receipt),
        "fault": copy.deepcopy(outcome.fault),
        "events": copy.deepcopy(world["events"][first_event:]),
        "operation": copy.deepcopy(operation) if operation else None,
    }


def fixture_decision(
    compiled: Mapping[str, Any], state: Mapping[str, Any], scenario: Any = None,
) -> dict[str, Any]:
    """Compatibility entrypoint; scenario is never used to select behaviour."""

    del scenario
    return incident_commander_decision(compiled, state)


def validate_outcome(
    world: Mapping[str, Any], state: Mapping[str, Any],
) -> dict[str, Any]:
    """Stable host entrypoint for authoritative final-state validation."""

    return validate_incident_outcome(world, state)


__all__ = [
    "ADAPTER_VERSION", "CAPABILITY_VERSION", "INCIDENT_COMMANDER_ID",
    "OUTCOME_VALIDATOR_ID", "PROFILE_SCHEMA_VERSION", "WORLD_SCHEMA_VERSION",
    "SimulationError", "ToolOutcome", "advance_clock", "agent_specs",
    "capability_catalog", "create_world", "execute", "execute_tool",
    "fixture_decision", "incident_commander_decision", "incident_commander_spec",
    "operation_receipt", "profiles", "public_world", "reconcile_operation",
    "scenario_profiles", "scenarios", "set_fault", "tool_catalog",
    "validate_incident_outcome", "validate_outcome", "validate_world",
]
