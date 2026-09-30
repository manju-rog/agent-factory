"""Deterministic domain primitives shared by Axiom's API and runtime.

The project intentionally supports a bounded JSON-Schema and rule subset.  A
small, explicit language is easier to validate, migrate, and execute safely
than silently accepting keywords that the runtime does not understand.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any, Iterable


SCHEMA_VERSION = "axiom.schema.v1"
RULE_VERSION = "axiom.rule.v1"

_SCHEMA_KEYS = {
    "$id", "$schema", "title", "description", "type", "properties",
    "required", "additionalProperties", "items", "enum", "const",
    "minLength", "maxLength", "minimum", "maximum", "minItems",
    "maxItems", "format",
}
_ANNOTATION_KEYS = {"$id", "$schema", "title", "description"}
_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_FORMATS = {"date", "date-time"}
_SAFE_PROPERTY_NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_DANGEROUS_PROPERTY_NAMES = {"__proto__", "constructor", "prototype"}


@dataclass(frozen=True)
class DomainIssue:
    code: str
    message: str
    path: str = "$"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}


class SchemaDefinitionError(ValueError):
    """Raised when a schema uses syntax outside Axiom's supported subset."""

    def __init__(self, issues: Iterable[DomainIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{i.path}: {i.message}" for i in self.issues))


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _schema_types(schema: dict[str, Any]) -> set[str]:
    declared = schema.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return set(declared)
    if "const" in schema:
        return {_value_type(schema["const"])}
    if "enum" in schema:
        return {_value_type(value) for value in schema["enum"]}
    return set(_TYPES)


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unsupported"


def schema_definition_issues(schema: Any, path: str = "$") -> list[DomainIssue]:
    """Return every unsupported or malformed schema construct."""
    issues: list[DomainIssue] = []
    if not isinstance(schema, dict):
        return [DomainIssue("SCHEMA_OBJECT", "Schema must be an object.", path)]
    unknown = sorted(set(schema) - _SCHEMA_KEYS)
    for keyword in unknown:
        issues.append(DomainIssue(
            "SCHEMA_KEYWORD_UNSUPPORTED",
            f"Keyword {keyword!r} is not supported by {SCHEMA_VERSION}.",
            path,
        ))
    declared = schema.get("type")
    if declared is not None:
        type_values = [declared] if isinstance(declared, str) else declared
        if (not isinstance(type_values, list) or not type_values
                or any(not isinstance(item, str) or item not in _TYPES for item in type_values)
                or len(type_values) != len(set(type_values))):
            issues.append(DomainIssue(
                "SCHEMA_TYPE", "type must be a supported type or a unique non-empty type array.",
                path + ".type",
            ))
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not enum:
            issues.append(DomainIssue("SCHEMA_ENUM", "enum must be a non-empty array.", path + ".enum"))
        elif any(_json_equal(left, right)
                 for index, left in enumerate(enum)
                 for right in enum[index + 1:]):
            issues.append(DomainIssue("SCHEMA_ENUM", "enum values must be unique.", path + ".enum"))
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            issues.append(DomainIssue("SCHEMA_PROPERTIES", "properties must be an object.", path + ".properties"))
        else:
            for key, child in properties.items():
                if (not isinstance(key, str)
                        or not _SAFE_PROPERTY_NAME.fullmatch(key)
                        or key in _DANGEROUS_PROPERTY_NAMES):
                    issues.append(DomainIssue(
                        "SCHEMA_PROPERTY_NAME",
                        "Property names must use 1–80 letters, numbers, underscores, or hyphens and cannot alter object prototypes.",
                        path + ".properties",
                    ))
                else:
                    issues.extend(schema_definition_issues(child, f"{path}.properties.{key}"))
    required = schema.get("required")
    if required is not None:
        if (not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required)
                or len(required) != len(set(required))):
            issues.append(DomainIssue("SCHEMA_REQUIRED", "required must contain unique property names.", path + ".required"))
        elif isinstance(schema.get("properties"), dict):
            for item in required:
                if item not in schema["properties"]:
                    issues.append(DomainIssue("SCHEMA_REQUIRED_UNKNOWN", f"Required property {item!r} is not declared.", path + ".required"))
    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, (bool, dict)):
        issues.append(DomainIssue("SCHEMA_ADDITIONAL_PROPERTIES", "additionalProperties must be boolean or a schema.", path + ".additionalProperties"))
    elif isinstance(additional, dict):
        issues.extend(schema_definition_issues(additional, path + ".additionalProperties"))
    if "items" in schema:
        issues.extend(schema_definition_issues(schema["items"], path + ".items"))
    if "format" in schema:
        if schema["format"] not in _FORMATS:
            issues.append(DomainIssue("SCHEMA_FORMAT", "format must be date or date-time.", path + ".format"))
        format_types = _schema_types(schema)
        if "string" not in format_types or not format_types <= {"string", "null"}:
            issues.append(DomainIssue("SCHEMA_FORMAT_TYPE", "format is supported only for string or nullable string values.", path + ".format"))
    for low, high in (("minLength", "maxLength"), ("minItems", "maxItems")):
        for key in (low, high):
            if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], int) or schema[key] < 0):
                issues.append(DomainIssue("SCHEMA_BOUND", f"{key} must be a non-negative integer.", path + "." + key))
        if low in schema and high in schema and isinstance(schema[low], int) and isinstance(schema[high], int) and schema[low] > schema[high]:
            issues.append(DomainIssue("SCHEMA_BOUND", f"{low} cannot exceed {high}.", path))
    for key in ("minimum", "maximum"):
        value = schema.get(key)
        if key in schema and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or (isinstance(value, float) and not math.isfinite(value))):
            issues.append(DomainIssue("SCHEMA_BOUND", f"{key} must be a finite number.", path + "." + key))
    if ("minimum" in schema and "maximum" in schema
            and isinstance(schema["minimum"], (int, float)) and isinstance(schema["maximum"], (int, float))
            and not isinstance(schema["minimum"], bool) and not isinstance(schema["maximum"], bool)
            and schema["minimum"] > schema["maximum"]):
        issues.append(DomainIssue("SCHEMA_BOUND", "minimum cannot exceed maximum.", path))
    return issues


def assert_supported_schema(schema: Any) -> None:
    issues = schema_definition_issues(schema)
    if issues:
        raise SchemaDefinitionError(issues)


def validate_instance(schema: dict[str, Any], value: Any, path: str = "$") -> list[DomainIssue]:
    """Validate a value against the complete supported subset."""
    assert_supported_schema(schema)
    issues: list[DomainIssue] = []
    value_type = _value_type(value)
    accepted = _schema_types(schema)
    # JSON Schema treats integers as numbers.
    if value_type not in accepted and not (value_type == "integer" and "number" in accepted):
        return [DomainIssue("VALUE_TYPE", f"Expected {' or '.join(sorted(accepted))}; received {value_type}.", path)]
    if "const" in schema and not _json_equal(value, schema["const"]):
        issues.append(DomainIssue("VALUE_CONST", "Value does not match the required constant.", path))
    if "enum" in schema and not any(_json_equal(value, candidate) for candidate in schema["enum"]):
        issues.append(DomainIssue("VALUE_ENUM", "Value is not in the allowed set.", path))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            issues.append(DomainIssue("VALUE_MIN_LENGTH", "String is shorter than minLength.", path))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            issues.append(DomainIssue("VALUE_MAX_LENGTH", "String is longer than maxLength.", path))
        if schema.get("format") == "date":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                issues.append(DomainIssue("VALUE_FORMAT", "String must be a valid ISO 8601 calendar date.", path))
        if schema.get("format") == "date-time":
            try:
                if "T" not in value and "t" not in value:
                    raise ValueError
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
            except ValueError:
                issues.append(DomainIssue("VALUE_FORMAT", "String must be an ISO 8601 date-time with a timezone.", path))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            issues.append(DomainIssue("VALUE_NUMBER", "Number must be finite.", path))
        if "minimum" in schema and value < schema["minimum"]:
            issues.append(DomainIssue("VALUE_MINIMUM", "Number is below minimum.", path))
        if "maximum" in schema and value > schema["maximum"]:
            issues.append(DomainIssue("VALUE_MAXIMUM", "Number is above maximum.", path))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            issues.append(DomainIssue("VALUE_MIN_ITEMS", "Array has fewer than minItems entries.", path))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            issues.append(DomainIssue("VALUE_MAX_ITEMS", "Array has more than maxItems entries.", path))
        if "items" in schema:
            for index, item in enumerate(value):
                issues.extend(validate_instance(schema["items"], item, f"{path}[{index}]"))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                issues.append(DomainIssue("VALUE_REQUIRED", f"Required property {key!r} is missing.", path))
        for key, item in value.items():
            if key in properties:
                issues.extend(validate_instance(properties[key], item, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                issues.append(DomainIssue("VALUE_ADDITIONAL_PROPERTY", f"Property {key!r} is not allowed.", f"{path}.{key}"))
            elif isinstance(schema.get("additionalProperties"), dict):
                issues.extend(validate_instance(schema["additionalProperties"], item, f"{path}.{key}"))
    return issues


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool/int equality shortcut."""
    left_type = _value_type(left)
    right_type = _value_type(right)
    if left_type in {"integer", "number"} and right_type in {"integer", "number"}:
        return left == right
    if left_type != right_type:
        return False
    if left_type == "array":
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    if left_type == "object":
        return (left.keys() == right.keys()
                and all(_json_equal(left[key], right[key]) for key in left))
    return left == right


def _prefixed_issues(issues: Iterable[DomainIssue], prefix: str) -> list[DomainIssue]:
    return [DomainIssue(issue.code, issue.message, prefix + issue.path[1:]) for issue in issues]


def _additional_schema(schema: dict[str, Any]) -> dict[str, Any] | None:
    additional = schema.get("additionalProperties", True)
    if additional is False:
        return None
    if additional is True:
        return {}
    return additional


def _check_lower_bound(
    source: dict[str, Any],
    target: dict[str, Any],
    keyword: str,
    code: str,
    label: str,
    *,
    integral: bool = False,
) -> DomainIssue | None:
    if keyword not in target:
        return None
    if keyword not in source:
        return DomainIssue(code, f"Source {label} is not bounded by target {keyword}.")
    source_bound = source[keyword]
    if integral:
        source_bound = math.ceil(source_bound)
    if source_bound < target[keyword]:
        return DomainIssue(code, f"Source {keyword} is less restrictive than the target.")
    return None


def _check_upper_bound(
    source: dict[str, Any],
    target: dict[str, Any],
    keyword: str,
    code: str,
    label: str,
    *,
    integral: bool = False,
) -> DomainIssue | None:
    if keyword not in target:
        return None
    if keyword not in source:
        return DomainIssue(code, f"Source {label} is not bounded by target {keyword}.")
    source_bound = source[keyword]
    if integral:
        source_bound = math.floor(source_bound)
    if source_bound > target[keyword]:
        return DomainIssue(code, f"Source {keyword} is less restrictive than the target.")
    return None


def schema_assignable(source: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[DomainIssue]]:
    """Conservatively decide whether every supported source value fits target.

    Returning false for an uncertain relationship is intentional: publication
    should ask for an explicit mapping rather than promise unsafe compatibility.
    """
    assert_supported_schema(source)
    assert_supported_schema(target)
    if not (set(target) - _ANNOTATION_KEYS):
        return True, []
    issues: list[DomainIssue] = []

    # An enum or constant makes the source finite.  Checking its actually valid
    # values is both exact and avoids false negatives from unused union members.
    candidates: list[Any] | None = None
    if "const" in source:
        candidates = [source["const"]]
    elif "enum" in source:
        candidates = source["enum"]
    if candidates is not None:
        valid_candidates = [candidate for candidate in candidates if not validate_instance(source, candidate)]
        if any(validate_instance(target, candidate) for candidate in valid_candidates):
            issues.append(DomainIssue(
                "SCHEMA_ENUM_NOT_ASSIGNABLE",
                "A value permitted by the finite source is rejected by the target.",
            ))
        return not issues, issues

    source_types = _schema_types(source)
    target_types = _schema_types(target)
    expanded_target = set(target_types)
    if "number" in target_types:
        expanded_target.add("integer")
    if not source_types <= expanded_target:
        issues.append(DomainIssue("SCHEMA_NOT_ASSIGNABLE", "Source types are not a subset of target types."))
    if "enum" in target or "const" in target:
        issues.append(DomainIssue("SCHEMA_CONSTRAINT_NOT_ASSIGNABLE", "An unconstrained source cannot satisfy a constrained target."))

    if "string" in source_types and "string" in target_types:
        if target.get("format") and source.get("format") != target.get("format"):
            issues.append(DomainIssue("SCHEMA_FORMAT_NOT_ASSIGNABLE", "Source string format is not constrained to the target format."))
        for keyword, code, checker in (
            ("minLength", "SCHEMA_MIN_LENGTH_NOT_ASSIGNABLE", _check_lower_bound),
            ("maxLength", "SCHEMA_MAX_LENGTH_NOT_ASSIGNABLE", _check_upper_bound),
        ):
            issue = checker(source, target, keyword, code, "string length")
            if issue:
                issues.append(issue)

    source_has_numeric = bool(source_types & {"integer", "number"})
    target_accepts_numeric = "number" in target_types or "integer" in target_types
    if source_has_numeric and target_accepts_numeric:
        integral = "number" not in source_types
        for keyword, code, checker in (
            ("minimum", "SCHEMA_MINIMUM_NOT_ASSIGNABLE", _check_lower_bound),
            ("maximum", "SCHEMA_MAXIMUM_NOT_ASSIGNABLE", _check_upper_bound),
        ):
            issue = checker(source, target, keyword, code, "number", integral=integral)
            if issue:
                issues.append(issue)

    if "object" in source_types and "object" in target_types:
        source_props = source.get("properties", {})
        target_props = target.get("properties", {})
        source_required = set(source.get("required", []))
        target_required = set(target.get("required", []))
        source_additional = _additional_schema(source)
        target_additional = _additional_schema(target)

        for key in target_required:
            if key not in source_required:
                issues.append(DomainIssue("SCHEMA_REQUIRED_NOT_ASSIGNABLE", f"Source does not always provide required target property {key!r}.", f"$.properties.{key}"))

        # A target property schema constrains the value whenever that key is
        # present, even when the property itself is optional.
        for key in set(target_props) | target_required:
            source_child = source_props.get(key, source_additional)
            target_child = target_props.get(key, target_additional)
            if source_child is None:
                continue
            if target_child is None:
                issues.append(DomainIssue(
                    "SCHEMA_PROPERTY_NOT_ASSIGNABLE",
                    f"Source permits target-forbidden property {key!r}.",
                    f"$.properties.{key}",
                ))
                continue
            ok, child = schema_assignable(source_child, target_child)
            if not ok:
                issues.extend(_prefixed_issues(child, f"$.properties.{key}"))

        # Declared source fields unknown to the target are governed by the
        # target's additionalProperties contract.
        for key, source_child in source_props.items():
            if key in target_props or key in target_required:
                continue
            if target_additional is None:
                issues.append(DomainIssue(
                    "SCHEMA_ADDITIONAL_PROPERTY_NOT_ASSIGNABLE",
                    f"Source permits property {key!r}, which the target forbids.",
                    f"$.properties.{key}",
                ))
            else:
                ok, child = schema_assignable(source_child, target_additional)
                if not ok:
                    issues.extend(_prefixed_issues(child, f"$.properties.{key}"))

        # Compare the contracts for arbitrary, undeclared field names.
        if source_additional is not None:
            if target_additional is None:
                issues.append(DomainIssue(
                    "SCHEMA_ADDITIONAL_PROPERTIES_NOT_ASSIGNABLE",
                    "Source permits undeclared properties that the target forbids.",
                ))
            else:
                ok, child = schema_assignable(source_additional, target_additional)
                if not ok:
                    issues.extend(_prefixed_issues(child, "$.additionalProperties"))

    if "array" in source_types and "array" in target_types:
        for keyword, code, checker in (
            ("minItems", "SCHEMA_MIN_ITEMS_NOT_ASSIGNABLE", _check_lower_bound),
            ("maxItems", "SCHEMA_MAX_ITEMS_NOT_ASSIGNABLE", _check_upper_bound),
        ):
            issue = checker(source, target, keyword, code, "array length")
            if issue:
                issues.append(issue)
        if "items" in target and source.get("maxItems") != 0:
            if "items" not in source:
                issues.append(DomainIssue("SCHEMA_ITEMS_NOT_ASSIGNABLE", "Source array item type is unconstrained."))
            else:
                ok, child = schema_assignable(source["items"], target["items"])
                if not ok:
                    issues.extend(_prefixed_issues(child, "$.items"))
    return not issues, issues


class RuleError(ValueError):
    pass


def _resolve_path(context: Any, path: str) -> tuple[bool, Any]:
    if not isinstance(path, str) or not path or path.startswith(".") or path.endswith("."):
        raise RuleError("Rule paths must be non-empty dotted field names.")
    value = context
    for part in path.split("."):
        if not part or not all(char.isalnum() or char in "_-" for char in part):
            raise RuleError("Rule paths may contain letters, digits, underscores, and hyphens.")
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def evaluate_rule(rule: Any, context: dict[str, Any], *, max_depth: int = 8, max_nodes: int = 64) -> bool:
    """Evaluate the versioned, side-effect-free Axiom rule AST."""
    remaining = [max_nodes]

    def visit(node: Any, depth: int) -> bool:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise RuleError(f"Rule exceeds the {max_nodes}-node limit.")
        if depth > max_depth:
            raise RuleError(f"Rule exceeds the {max_depth}-level depth limit.")
        if not isinstance(node, dict) or set(node) - {"op", "path", "value", "rules", "rule"}:
            raise RuleError("Each rule must be an object containing only supported fields.")
        op = node.get("op")
        if op == "and" or op == "or":
            rules = node.get("rules")
            if not isinstance(rules, list) or not rules:
                raise RuleError(f"{op} requires a non-empty rules array.")
            values = [visit(item, depth + 1) for item in rules]
            return all(values) if op == "and" else any(values)
        if op == "not":
            if "rule" not in node:
                raise RuleError("not requires one nested rule.")
            return not visit(node["rule"], depth + 1)
        if op == "exists":
            found, _ = _resolve_path(context, node.get("path"))
            return found
        if op not in {"eq", "ne", "gt", "gte", "lt", "lte"}:
            raise RuleError(f"Unsupported rule operation {op!r} for {RULE_VERSION}.")
        if "value" not in node:
            raise RuleError(f"{op} requires a comparison value.")
        found, actual = _resolve_path(context, node.get("path"))
        if not found:
            return False
        expected = node["value"]
        if op == "eq":
            return _json_equal(actual, expected)
        if op == "ne":
            return not _json_equal(actual, expected)
        numeric = (isinstance(actual, (int, float)) and not isinstance(actual, bool)
                   and isinstance(expected, (int, float)) and not isinstance(expected, bool))
        textual = isinstance(actual, str) and isinstance(expected, str)
        if not numeric and not textual:
            raise RuleError(f"{op} compares two strings or two numeric values.")
        return {"gt": actual > expected, "gte": actual >= expected,
                "lt": actual < expected, "lte": actual <= expected}[op]

    if not isinstance(context, dict):
        raise RuleError("Rule context must be an object.")
    return visit(rule, 1)


def split_template(template: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return canonical behavior and layout documents for independent diffs."""
    behavior = {key: value for key, value in template.items() if key not in {"updatedAt", "createdAt", "draftRevision", "versions"}}
    nodes = []
    layout_nodes = []
    for node in behavior.get("nodes", []):
        nodes.append({key: value for key, value in node.items() if key not in {"x", "y"}})
        layout_nodes.append({"id": node.get("id"), "x": node.get("x"), "y": node.get("y")})
    behavior["nodes"] = nodes
    layout = {"schemaVersion": "axiom.layout.v1", "nodes": sorted(layout_nodes, key=lambda item: str(item["id"]))}
    return behavior, layout


def template_hashes(template: dict[str, Any]) -> dict[str, str]:
    behavior, layout = split_template(template)
    return {"semanticHash": content_hash(behavior), "layoutHash": content_hash(layout)}
