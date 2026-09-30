"""Small, provider-neutral SDK contract for executable Axiom capabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from domain import SchemaDefinitionError, assert_supported_schema, content_hash, validate_instance


MANIFEST_VERSION = "axiom.agent-manifest.v1"
_KEY = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?\Z")


class ManifestError(ValueError):
    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("; ".join(issue["message"] for issue in issues))


@dataclass(frozen=True)
class AgentManifest:
    implementation_key: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any]
    capabilities: tuple[str, ...]
    side_effect_class: str
    retry_safety: str
    evidence_kinds: tuple[str, ...] = ()
    fixture_scenarios: tuple[str, ...] = ()
    resource_limits: Mapping[str, int | float] = field(default_factory=dict)
    authentication: str = "none"
    manifest_version: str = MANIFEST_VERSION

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentManifest":
        if not isinstance(raw, Mapping):
            raise ManifestError([{"field": "$", "message": "Manifest must be an object."}])
        known = {
            "manifestVersion", "implementationKey", "version", "description",
            "inputSchema", "outputSchema", "configSchema", "capabilities",
            "sideEffectClass", "retrySafety", "evidenceKinds", "fixtureScenarios",
            "resourceLimits", "authentication",
        }
        issues: list[dict[str, str]] = []
        for key in sorted(set(raw) - known):
            issues.append({"field": key, "message": f"Unknown manifest field {key!r}."})
        key = raw.get("implementationKey")
        version = raw.get("version")
        description = raw.get("description")
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            issues.append({"field": "implementationKey", "message": "implementationKey must be a lowercase stable identifier."})
        if not isinstance(version, str) or not _SEMVER.fullmatch(version):
            issues.append({"field": "version", "message": "version must use semantic version form, for example 1.0.0."})
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1000:
            issues.append({"field": "description", "message": "description must contain 1–1000 characters."})
        schemas = {}
        for json_name, attr_name in (("inputSchema", "input_schema"), ("outputSchema", "output_schema"), ("configSchema", "config_schema")):
            schema = raw.get(json_name)
            try:
                assert_supported_schema(schema)
                schemas[attr_name] = schema
            except SchemaDefinitionError as exc:
                issues.extend({"field": json_name + issue.path[1:], "message": issue.message} for issue in exc.issues)
        def string_tuple(name: str) -> tuple[str, ...]:
            value = raw.get(name, [])
            if (not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value)
                    or len(value) != len(set(value))):
                issues.append({"field": name, "message": f"{name} must contain unique non-empty strings."})
                return ()
            return tuple(value)
        capabilities = string_tuple("capabilities")
        evidence = string_tuple("evidenceKinds")
        fixtures = string_tuple("fixtureScenarios")
        side_effect = raw.get("sideEffectClass")
        retry = raw.get("retrySafety")
        auth = raw.get("authentication", "none")
        if side_effect not in {"none", "read", "write"}:
            issues.append({"field": "sideEffectClass", "message": "sideEffectClass must be none, read, or write."})
        if retry not in {"safe", "idempotent", "reconcile", "unsafe"}:
            issues.append({"field": "retrySafety", "message": "retrySafety must describe the supported recovery contract."})
        if side_effect == "write" and retry == "safe":
            issues.append({"field": "retrySafety", "message": "A write cannot claim unconditional safe retry; use idempotent, reconcile, or unsafe."})
        if auth not in {"none", "secret_reference", "oauth2", "workload_identity"}:
            issues.append({"field": "authentication", "message": "authentication uses an unsupported strategy."})
        limits = raw.get("resourceLimits", {})
        if not isinstance(limits, Mapping):
            issues.append({"field": "resourceLimits", "message": "resourceLimits must be an object."})
            limits = {}
        else:
            permitted = {"timeoutSeconds", "maxInputBytes", "maxOutputBytes", "maxModelTokens"}
            for name, value in limits.items():
                if name not in permitted or isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    issues.append({"field": f"resourceLimits.{name}", "message": "Resource limit is unsupported or must be positive."})
        if raw.get("manifestVersion", MANIFEST_VERSION) != MANIFEST_VERSION:
            issues.append({"field": "manifestVersion", "message": f"Only {MANIFEST_VERSION} is supported."})
        if issues:
            raise ManifestError(issues)
        return cls(
            implementation_key=key,
            version=version,
            description=description.strip(),
            capabilities=capabilities,
            side_effect_class=side_effect,
            retry_safety=retry,
            evidence_kinds=evidence,
            fixture_scenarios=fixtures,
            resource_limits=dict(limits),
            authentication=auth,
            **schemas,
        )

    @property
    def content_hash(self) -> str:
        return content_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestVersion": self.manifest_version,
            "implementationKey": self.implementation_key,
            "version": self.version,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "configSchema": self.config_schema,
            "capabilities": list(self.capabilities),
            "sideEffectClass": self.side_effect_class,
            "retrySafety": self.retry_safety,
            "evidenceKinds": list(self.evidence_kinds),
            "fixtureScenarios": list(self.fixture_scenarios),
            "resourceLimits": dict(self.resource_limits),
            "authentication": self.authentication,
        }


@dataclass(frozen=True)
class ExecutionContext:
    workspace_id: str
    run_id: str
    node_id: str
    operation_key: str
    deadline: str
    cancellation_requested: Callable[[], bool]
    connector: "RestrictedConnector"

    def log(self, event: str, fields: Mapping[str, Any] | None = None) -> dict[str, Any]:
        fields = dict(fields or {})
        redacted = {key: ("[REDACTED]" if re.search(r"secret|token|password|key", key, re.I) else value)
                    for key, value in fields.items()}
        return {"time": datetime.now(timezone.utc).isoformat(), "event": event, "fields": redacted,
                "runId": self.run_id, "nodeId": self.node_id}


class RestrictedConnector:
    """Connector boundary that exposes only pre-approved named operations."""

    def __init__(self, operations: Mapping[str, Callable[[dict[str, Any]], dict[str, Any]]]):
        self._operations = dict(operations)

    @property
    def allowed_operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation not in self._operations:
            raise PermissionError(f"Connector operation {operation!r} is not approved for this capability.")
        if not isinstance(payload, dict):
            raise TypeError("Connector payload must be an object.")
        result = self._operations[operation](payload)
        if not isinstance(result, dict):
            raise TypeError("Connector result must be an object.")
        return result


class AgentImplementation:
    """Validated wrapper around a developer-supplied execute function."""

    def __init__(self, manifest: AgentManifest, execute: Callable[[ExecutionContext, dict[str, Any], dict[str, Any]], dict[str, Any]]):
        self.manifest = manifest
        self._execute = execute

    def execute(self, context: ExecutionContext, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        input_issues = validate_instance(self.manifest.input_schema, inputs)
        config_issues = validate_instance(self.manifest.config_schema, config)
        if input_issues or config_issues:
            raise ValueError({"input": [issue.as_dict() for issue in input_issues],
                              "config": [issue.as_dict() for issue in config_issues]})
        if context.cancellation_requested():
            raise InterruptedError("Execution was cancelled before dispatch.")
        output = self._execute(context, inputs, config)
        output_issues = validate_instance(self.manifest.output_schema, output)
        if output_issues:
            raise ValueError({"output": [issue.as_dict() for issue in output_issues]})
        return output


def scaffold_agent(target_root: Path, implementation_key: str, *, description: str = "New Axiom capability") -> Path:
    """Create a minimal owned capability package below an explicit root."""
    if not _KEY.fullmatch(implementation_key):
        raise ValueError("implementation_key must be a lowercase stable identifier")
    root = target_root.resolve()
    package = (root / implementation_key).resolve()
    if root not in package.parents or package.exists():
        raise FileExistsError("Refusing to overwrite an existing or out-of-root capability")
    package.mkdir(parents=True)
    manifest = {
        "manifestVersion": MANIFEST_VERSION,
        "implementationKey": implementation_key,
        "version": "0.1.0",
        "description": description,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "outputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "configSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "capabilities": [],
        "sideEffectClass": "none",
        "retrySafety": "safe",
        "evidenceKinds": [],
        "fixtureScenarios": ["known-answer"],
        "resourceLimits": {"timeoutSeconds": 30, "maxInputBytes": 65536, "maxOutputBytes": 65536},
        "authentication": "none",
    }
    AgentManifest.from_dict(manifest)
    (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (package / "implementation.py").write_text(
        '"""Implement this capability without widening its declared authority."""\n\n'
        "def execute(context, inputs, config):\n"
        "    return {}\n",
        encoding="utf-8",
    )
    (package / "known_answer.json").write_text(json.dumps({"inputs": {}, "config": {}, "expectedOutput": {}}, indent=2) + "\n", encoding="utf-8")
    (package / "README.md").write_text(
        f"# {implementation_key}\n\nValidate inputs and outputs against `manifest.json`; add deterministic known-answer fixtures before registration.\n",
        encoding="utf-8",
    )
    return package
