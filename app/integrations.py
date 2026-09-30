"""Provider-neutral external integration contracts for Axiom.

This module is intentionally independent from the HTTP server and performs no
network access by itself.  It turns administrator-reviewed connection records
into strict, redacted public state and exact adapter call plans.  A host may
inject a credential resolver and transport implementation at dispatch time.

Security invariants:

* connection records contain credential *references*, never credential values;
* the model selects a registered operation, never an arbitrary URL or header;
* outbound destinations are pinned to an administrator allowlist and checked
  again after DNS resolution immediately before dispatch;
* redirects are disabled and response sizes are bounded;
* writes always require an exact approval and uncertain writes reconcile before
  any retry; and
* public records, errors and representations never disclose secret references
  or resolved credentials.

Slack, Jira, Confluence, REST, webhook and MCP entries below are descriptors and
normalised operation templates.  They do not claim that a tenant is connected.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import ipaddress
import json
import math
import re
import socket
import threading
import time
import urllib.parse
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


class IntegrationError(ValueError):
    """A bounded, user-safe integration error."""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = copy.deepcopy(dict(details)) if details else None


CONNECTION_SCHEMA_VERSION = "axiom.connection.v1"
ADAPTER_API_VERSION = "axiom.integration-adapter.v1"
CAPABILITY_SCHEMA_VERSION = "axiom.capability.v1"

_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_OPERATION_IDENT = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
_SECRET_REF = re.compile(
    r"^(?:(?:secret|vault|keychain)://[A-Za-z0-9][A-Za-z0-9._/@:#-]{0,510}"
    r"|env:[A-Za-z_][A-Za-z0-9_]{0,126})$"
)
_OPERATION_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,79}$")
_PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_-]+)\}")
_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum",
    "description", "title", "format",
}
_AUTH_SLOTS = {
    "none": frozenset(),
    "bearer": frozenset({"token"}),
    "api_key_header": frozenset({"apiKey"}),
    "basic": frozenset({"username", "password"}),
    "oauth2": frozenset({"credential"}),
    "hmac_sha256": frozenset({"key"}),
}
_FORBIDDEN_AUTH_HEADERS = {
    "host", "content-length", "transfer-encoding", "connection", "cookie", "set-cookie",
    "proxy-authorization", "proxy-authenticate", "x-forwarded-for", "forwarded",
}
_CONNECTION_STATUSES = {"draft", "ready", "disabled", "revoked", "error"}
_TRANSPORTS = {"https-json", "webhook", "mcp-streamable-http"}
_EFFECTS = {"read", "write"}
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_NATIVE_CODECS = {
    "identity.v1",
    "slack.auth_test.v1", "slack.conversations_history.v1", "slack.chat_post_message.v1",
    "jira.myself.v1", "jira.issue.v1", "jira.search.v1", "jira.create_issue.v1",
    "confluence.spaces_health.v1", "confluence.page.v1", "confluence.pages.v1",
    "confluence.create_page.v1",
}
_RETRY_CODES = {408, 425, 429, 500, 502, 503, 504}
_DENIED_HOSTS = {
    "localhost", "localhost.localdomain", "metadata.google.internal",
    "metadata.google", "instance-data", "169.254.169.254",
}


def _json(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise IntegrationError("INVALID_JSON", "Integration data must be finite UTF-8 JSON.") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _size(value: Any) -> int:
    return len(_json(value).encode("utf-8"))


def _text(value: Any, label: str, maximum: int = 1000, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise IntegrationError("CONNECTION_SCHEMA", f"{label} must be bounded nonempty text.")
    if pattern is not None and not pattern.fullmatch(value):
        raise IntegrationError("CONNECTION_SCHEMA", f"{label} has an invalid stable identifier.")
    return value


def _strict_keys(value: Any, allowed: set[str], required: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise IntegrationError(
            "CONNECTION_SCHEMA", f"{label} has missing required or unsupported fields."
        )
    return value


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise IntegrationError("CONNECTION_SCHEMA", f"{label} must be between {minimum} and {maximum}.")
    return value


def _validate_schema(schema: Any, depth: int = 0) -> None:
    if not isinstance(schema, dict) or depth > 10 or set(schema) - _SCHEMA_KEYS:
        raise IntegrationError("OPERATION_SCHEMA", "Use the supported finite JSON-schema subset.")
    kind = schema.get("type")
    if kind not in {"object", "array", "string", "integer", "number", "boolean", "null"}:
        raise IntegrationError("OPERATION_SCHEMA", "Every schema node must declare one supported type.")
    if kind == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        if (
            not isinstance(props, dict) or len(props) > 100
            or any(not isinstance(key, str) or not _IDENT.fullmatch(key) for key in props)
            or not isinstance(required, list) or len(required) != len(set(required))
            or any(key not in props for key in required)
            or schema.get("additionalProperties", False) is not False
        ):
            raise IntegrationError("OPERATION_SCHEMA", "Object schemas must be strict and bounded.")
        for child in props.values():
            _validate_schema(child, depth + 1)
    elif any(key in schema for key in ("properties", "required", "additionalProperties")):
        raise IntegrationError("OPERATION_SCHEMA", "Object constraints require object type.")
    if kind == "array":
        if "items" not in schema:
            raise IntegrationError("OPERATION_SCHEMA", "Array schemas require an item schema.")
        _validate_schema(schema["items"], depth + 1)
    elif "items" in schema:
        raise IntegrationError("OPERATION_SCHEMA", "Only arrays may declare items.")
    if "enum" in schema:
        choices = schema["enum"]
        if not isinstance(choices, list) or not choices or len(choices) > 100:
            raise IntegrationError("OPERATION_SCHEMA", "Schema enums must be nonempty bounded arrays.")
        for choice in choices:
            _json(choice)
    for low, high, owner in (
        ("minLength", "maxLength", "string"),
        ("minItems", "maxItems", "array"),
        ("minimum", "maximum", "number"),
    ):
        for key in (low, high):
            if key not in schema:
                continue
            number = schema[key]
            valid_owner = kind in ({"number", "integer"} if owner == "number" else {owner})
            if (
                not valid_owner or isinstance(number, bool)
                or not isinstance(number, (int, float)) or not math.isfinite(number)
                or owner != "number" and (not isinstance(number, int) or number < 0)
            ):
                raise IntegrationError("OPERATION_SCHEMA", "Schema bounds must match their type.")
        if low in schema and high in schema and schema[low] > schema[high]:
            raise IntegrationError("OPERATION_SCHEMA", "Schema minimum cannot exceed maximum.")
    if "format" in schema and (kind != "string" or schema["format"] not in {"email"}):
        raise IntegrationError("OPERATION_SCHEMA", "Only the plain email string format is supported.")
    _json(schema)


def validate_value(value: Any, schema: Mapping[str, Any], path: str = "value", depth: int = 0) -> Any:
    """Validate a value against the strict schema subset used by capabilities."""

    if depth > 12:
        raise IntegrationError("SCHEMA_VALUE", "Integration data exceeds supported nesting depth.")
    kind = schema["type"]
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[kind]
    if not valid:
        raise IntegrationError("SCHEMA_VALUE", f"{path} must be {kind}.")
    if "enum" in schema and _json(value) not in {_json(item) for item in schema["enum"]}:
        raise IntegrationError("SCHEMA_VALUE", f"{path} is outside the allowed values.")
    if kind == "object":
        properties = schema.get("properties", {})
        if set(value) - set(properties) or set(schema.get("required", [])) - set(value):
            raise IntegrationError("SCHEMA_VALUE", f"{path} has missing required or undeclared fields.")
        for key, child in value.items():
            validate_value(child, properties[key], f"{path}.{key}", depth + 1)
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000):
            raise IntegrationError("SCHEMA_VALUE", f"{path} has invalid array length.")
        for child in value:
            validate_value(child, schema["items"], f"{path}[]", depth + 1)
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 32000):
            raise IntegrationError("SCHEMA_VALUE", f"{path} has invalid text length.")
        if schema.get("format") == "email" and not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",
            value,
        ):
            raise IntegrationError("SCHEMA_VALUE", f"{path} must be a plain email address.")
    elif kind in {"number", "integer"}:
        if (
            not math.isfinite(value)
            or value < schema.get("minimum", -math.inf)
            or value > schema.get("maximum", math.inf)
        ):
            raise IntegrationError("SCHEMA_VALUE", f"{path} is outside numeric bounds.")
    _json(value)
    return value


def _normalise_base_url(raw: Any, allow_private: bool) -> str:
    value = _text(raw, "base URL", 2048)
    if any(ord(char) < 32 for char in value) or "\\" in value:
        raise IntegrationError("DESTINATION_DENIED", "The connection base URL is malformed.")
    parsed = urllib.parse.urlsplit(value)
    allowed_schemes = {"https"} | ({"http"} if allow_private else set())
    if (
        parsed.scheme.lower() not in allowed_schemes or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
    ):
        raise IntegrationError(
            "DESTINATION_DENIED",
            "Base URLs need an approved HTTPS origin without credentials, query or fragment.",
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise IntegrationError("DESTINATION_DENIED", "The connection base URL has an invalid port.") from exc
    hostname = parsed.hostname.rstrip(".").lower()
    if not allow_private and _hostname_is_obviously_private(hostname):
        raise IntegrationError("DESTINATION_DENIED", "Private and metadata destinations are disabled.")
    netloc = hostname
    if ":" in hostname:
        netloc = f"[{hostname}]"
    if port is not None and not (parsed.scheme.lower() == "https" and port == 443):
        netloc += f":{port}"
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _hostname_is_obviously_private(hostname: str) -> bool:
    if (
        hostname in _DENIED_HOSTS or hostname.endswith((".localhost", ".local", ".internal", ".lan", ".home"))
    ):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return not address.is_global


def _default_resolver(hostname: str, port: int) -> Sequence[str]:
    try:
        return sorted({entry[4][0] for entry in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise IntegrationError("DESTINATION_UNRESOLVED", "The approved destination could not be resolved.") from exc


def validate_outbound_url(
    url: str,
    allowed_base_urls: Sequence[str],
    *,
    allow_private_network: bool = False,
    resolver: Any | None = None,
) -> tuple[str, ...]:
    """Validate allowlist membership and return the dispatch-time IP pin set.

    The transport must connect only to one of the returned addresses while
    retaining the validated hostname for Host/SNI.  Redirects must stay off.
    """

    if not isinstance(url, str) or len(url) > 4096 or any(ord(char) < 32 for char in url) or "\\" in url:
        raise IntegrationError("DESTINATION_DENIED", "The prepared destination is malformed.")
    parsed = urllib.parse.urlsplit(url)
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise IntegrationError("DESTINATION_DENIED", "The prepared destination contains forbidden URL fields.")
    matched = False
    for base in allowed_base_urls:
        allowed = urllib.parse.urlsplit(_normalise_base_url(base, allow_private_network))
        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        allowed_port = allowed.port or (443 if allowed.scheme == "https" else 80)
        prefix = allowed.path
        if (
            parsed.scheme.lower() == allowed.scheme.lower()
            and (parsed.hostname or "").rstrip(".").lower() == (allowed.hostname or "").rstrip(".").lower()
            and target_port == allowed_port
            and (parsed.path == prefix.rstrip("/") or parsed.path.startswith(prefix))
        ):
            matched = True
            break
    if not matched:
        raise IntegrationError("DESTINATION_DENIED", "The prepared destination is outside this connection's allowlist.")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not allow_private_network and _hostname_is_obviously_private(hostname):
        raise IntegrationError("DESTINATION_DENIED", "Private and metadata destinations are disabled.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    lookup = resolver or _default_resolver
    try:
        addresses = tuple(dict.fromkeys(str(item) for item in lookup(hostname, port)))
    except IntegrationError:
        raise
    except Exception as exc:
        raise IntegrationError("DESTINATION_UNRESOLVED", "The approved destination could not be resolved.") from exc
    if not addresses:
        raise IntegrationError("DESTINATION_UNRESOLVED", "The approved destination resolved to no addresses.")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise IntegrationError("DESTINATION_UNRESOLVED", "The resolver returned an invalid address.") from exc
        if not allow_private_network and not address.is_global:
            raise IntegrationError("DESTINATION_DENIED", "DNS resolved the destination to a private or reserved address.")
    return addresses


def _normalise_auth(auth: Any, provider: str) -> dict[str, Any]:
    record = _strict_keys(
        auth,
        {"mode", "secretRefs", "scopes", "headerName", "scheme"},
        {"mode", "secretRefs", "scopes"},
        "authentication",
    )
    mode = record["mode"]
    if mode not in _AUTH_SLOTS:
        raise IntegrationError("AUTH_MODE", "The selected authentication mode is unsupported.")
    descriptor = _PROVIDER_INDEX.get(provider)
    if descriptor is not None and mode not in descriptor["authModes"]:
        raise IntegrationError("AUTH_MODE", "This provider descriptor does not permit that authentication mode.")
    refs = record["secretRefs"]
    if not isinstance(refs, dict) or set(refs) != set(_AUTH_SLOTS[mode]):
        raise IntegrationError("SECRET_REFERENCE", "Authentication needs exactly its declared credential slots.")
    for reference in refs.values():
        if not isinstance(reference, str) or not _SECRET_REF.fullmatch(reference):
            raise IntegrationError("SECRET_REFERENCE", "Credentials must be server-side secret references, never values.")
    scopes = record["scopes"]
    if (
        not isinstance(scopes, list) or len(scopes) > 100
        or any(not isinstance(scope, str) or not scope or len(scope) > 200 for scope in scopes)
        or len(scopes) != len(set(scopes))
    ):
        raise IntegrationError("AUTH_SCOPE", "Authentication scopes must be unique bounded strings.")
    if mode == "api_key_header":
        header = record.get("headerName")
        if (
            not isinstance(header, str) or not _HEADER_NAME.fullmatch(header)
            or header.lower() in _FORBIDDEN_AUTH_HEADERS
        ):
            raise IntegrationError("AUTH_MODE", "API-key authentication needs one safe fixed header name.")
    elif "headerName" in record:
        raise IntegrationError("AUTH_MODE", "Only API-key authentication may choose a header name.")
    if mode == "bearer":
        scheme = record.get("scheme", "Bearer")
        if scheme not in {"Bearer", "Token"}:
            raise IntegrationError("AUTH_MODE", "Bearer authentication has an unsupported scheme.")
    elif "scheme" in record:
        raise IntegrationError("AUTH_MODE", "Only bearer authentication may declare a scheme.")
    return copy.deepcopy(record)


def _validate_native_provider_destinations(
    provider: str, auth: Mapping[str, Any], base_urls: Sequence[str]
) -> None:
    """Keep native-provider credentials on their documented API hosts.

    Generic REST, webhook, and MCP connections intentionally use an explicit
    administrator allowlist. Native presets are stricter: selecting "Slack" or
    "Atlassian Cloud" must never turn into a credential-bearing call to an
    unrelated HTTPS host because of a typo or a tampered connection record.
    """

    if provider not in {"slack", "jira-cloud", "confluence-cloud"}:
        return
    if len(base_urls) != 1:
        raise IntegrationError(
            "DESTINATION_DENIED", "Native provider connections require one exact official API base URL."
        )
    parsed = urllib.parse.urlsplit(base_urls[0])
    hostname = (parsed.hostname or "").rstrip(".").lower()
    port = parsed.port or 443
    if parsed.scheme != "https" or port != 443:
        raise IntegrationError(
            "DESTINATION_DENIED", "Native provider credentials require the official HTTPS API origin."
        )
    if provider == "slack":
        valid = hostname == "slack.com" and parsed.path == "/api/"
    else:
        product = "jira" if provider == "jira-cloud" else "confluence"
        direct_path = "/rest/api/3/" if provider == "jira-cloud" else "/wiki/api/v2/"
        oauth_path = re.compile(
            rf"^/ex/{product}/[A-Za-z0-9][A-Za-z0-9._-]{{0,199}}"
            + (r"/rest/api/3/$" if provider == "jira-cloud" else r"/wiki/api/v2/$")
        )
        if auth["mode"] == "oauth2":
            valid = hostname == "api.atlassian.com" and bool(oauth_path.fullmatch(parsed.path))
        else:
            valid = (
                hostname.endswith(".atlassian.net")
                and hostname != "atlassian.net"
                and parsed.path == direct_path
            )
    if not valid:
        raise IntegrationError(
            "DESTINATION_DENIED",
            "The native provider base URL does not match its official API host and path contract.",
        )


def _normalise_operation(raw: Any, transport: str) -> dict[str, Any]:
    allowed = {
        "id", "version", "description", "effect", "inputSchema", "outputSchema",
        "requiredScopes", "approvalRequired", "binding", "idempotency", "maxResponseBytes",
    }
    operation = _strict_keys(raw, allowed, allowed, "operation")
    ident = _text(operation["id"], "operation ID", 150, _OPERATION_IDENT)
    _text(str(operation["version"]), "operation version", 50, _VERSION)
    _text(operation["description"], "operation description", 2000)
    effect = operation["effect"]
    if effect not in _EFFECTS:
        raise IntegrationError("OPERATION_SCHEMA", "Operations must classify read or write effects.")
    _validate_schema(operation["inputSchema"])
    _validate_schema(operation["outputSchema"])
    if operation["inputSchema"].get("type") != "object" or operation["outputSchema"].get("type") != "object":
        raise IntegrationError("OPERATION_SCHEMA", "Operation input and output schemas must be objects.")
    scopes = operation["requiredScopes"]
    if (
        not isinstance(scopes, list) or len(scopes) > 100
        or any(not isinstance(scope, str) or not scope or len(scope) > 200 for scope in scopes)
        or len(scopes) != len(set(scopes))
    ):
        raise IntegrationError("AUTH_SCOPE", "Operation scopes must be unique bounded strings.")
    approval = operation["approvalRequired"]
    if not isinstance(approval, bool) or effect == "write" and approval is not True:
        raise IntegrationError("APPROVAL_POLICY", "Every external write must require exact-action approval.")
    if effect == "read" and approval:
        raise IntegrationError("APPROVAL_POLICY", "Read operation templates do not use write approval.")
    max_bytes = _bounded_int(operation["maxResponseBytes"], "maximum response bytes", 256, 10_000_000)
    binding = operation["binding"]
    if transport in {"https-json", "webhook"}:
        binding_allowed = {
            "kind", "method", "pathTemplate", "pathParameters", "queryParameters",
            "bodyParameters", "baseUrlIndex", "fixedHeaders", "fixedQuery", "codec",
        }
        binding = _strict_keys(
            binding,
            binding_allowed,
            {"kind", "method", "pathTemplate", "pathParameters", "queryParameters", "bodyParameters", "codec"},
            "HTTP operation binding",
        )
        if binding["kind"] != "http" or binding["method"] not in _METHODS:
            raise IntegrationError("OPERATION_BINDING", "HTTP operations need a supported fixed method.")
        if binding["codec"] not in _NATIVE_CODECS:
            raise IntegrationError("OPERATION_BINDING", "The operation names an unregistered trusted provider codec.")
        path = binding["pathTemplate"]
        if (
            not isinstance(path, str) or len(path) > 2000 or path.startswith(("/", "//"))
            or urllib.parse.urlsplit(path).scheme or "?" in path or "#" in path or "\\" in path
            or re.search(r"%(?:2f|5c|2e)", path, re.IGNORECASE)
            or any(segment in {".", ".."} for segment in path.split("/"))
        ):
            raise IntegrationError("OPERATION_BINDING", "Operation paths must be safe relative templates.")
        properties = set(operation["inputSchema"].get("properties", {}))
        locations: list[str] = []
        for key in ("pathParameters", "queryParameters", "bodyParameters"):
            values = binding[key]
            if not isinstance(values, list) or len(values) != len(set(values)) or any(value not in properties for value in values):
                raise IntegrationError("OPERATION_BINDING", "Operation parameter locations must name unique inputs.")
            locations.extend(values)
        if set(locations) != properties or len(locations) != len(set(locations)):
            raise IntegrationError("OPERATION_BINDING", "Every operation input needs exactly one request location.")
        if set(_PLACEHOLDER.findall(path)) != set(binding["pathParameters"]):
            raise IntegrationError("OPERATION_BINDING", "Path placeholders must exactly match path parameters.")
        index = binding.get("baseUrlIndex", 0)
        _bounded_int(index, "base URL index", 0, 20)
        headers = binding.get("fixedHeaders", {})
        if not isinstance(headers, dict) or len(headers) > 20:
            raise IntegrationError("OPERATION_BINDING", "Fixed headers must be a bounded object.")
        for name, value in headers.items():
            if (
                not isinstance(name, str) or not _HEADER_NAME.fullmatch(name)
                or name.lower() in _FORBIDDEN_AUTH_HEADERS | {"authorization"}
                or not isinstance(value, str) or len(value) > 1000 or "\r" in value or "\n" in value
            ):
                raise IntegrationError("OPERATION_BINDING", "Fixed headers contain an unsafe field.")
        fixed_query = binding.get("fixedQuery", {})
        if not isinstance(fixed_query, dict) or len(fixed_query) > 20 or set(fixed_query) & set(binding["queryParameters"]):
            raise IntegrationError("OPERATION_BINDING", "Fixed query values must be bounded and cannot overlap inputs.")
        for name, value in fixed_query.items():
            if (
                not isinstance(name, str) or not _IDENT.fullmatch(name)
                or isinstance(value, (dict, list)) or value is None
                or not isinstance(value, (str, int, float, bool)) or len(str(value)) > 1000
            ):
                raise IntegrationError("OPERATION_BINDING", "Fixed query values contain an unsafe field.")
    else:
        binding = _strict_keys(binding, {"kind", "toolName"}, {"kind"}, "MCP binding")
        if binding["kind"] == "mcp-list-tools":
            if "toolName" in binding or effect != "read" or operation["inputSchema"].get("properties"):
                raise IntegrationError("OPERATION_BINDING", "MCP tools/list is a zero-input read protocol operation.")
        elif binding["kind"] == "mcp-tool":
            if not _OPERATION_IDENT.fullmatch(str(binding.get("toolName", ""))):
                raise IntegrationError("OPERATION_BINDING", "MCP calls need one pre-registered stable tool name.")
        else:
            raise IntegrationError("OPERATION_BINDING", "The MCP protocol operation is unsupported.")
    durability = _strict_keys(
        operation["idempotency"],
        {"classification", "retry", "reconciliation", "operationKey", "reconciliationOperation"},
        {"classification", "retry", "reconciliation"} | ({"operationKey"} if effect == "write" else set()),
        "idempotency policy",
    )
    if durability["classification"] not in {"read_only", "provider_keyed", "non_idempotent"}:
        raise IntegrationError("IDEMPOTENCY_POLICY", "The idempotency classification is unsupported.")
    if durability["retry"] not in {"safe", "reconcile_before_retry", "never"}:
        raise IntegrationError("IDEMPOTENCY_POLICY", "The write retry policy is unsupported.")
    if durability["reconciliation"] not in {"not_applicable", "provider_status", "read_after_write", "manual"}:
        raise IntegrationError("IDEMPOTENCY_POLICY", "The reconciliation mode is unsupported.")
    if effect == "read":
        if durability != {"classification": "read_only", "retry": "safe", "reconciliation": "not_applicable"}:
            raise IntegrationError("IDEMPOTENCY_POLICY", "Read operations use the standard safe retry policy.")
    else:
        operation_key = durability.get("operationKey")
        if not isinstance(operation_key, str) or not operation_key or len(operation_key) > 200:
            raise IntegrationError("IDEMPOTENCY_POLICY", "Writes must bind a stable operation identity.")
        if durability["retry"] == "safe" and durability["classification"] != "provider_keyed":
            raise IntegrationError("IDEMPOTENCY_POLICY", "Only provider-keyed writes can be safely retried.")
        if durability["classification"] == "non_idempotent" and durability["retry"] == "safe":
            raise IntegrationError("IDEMPOTENCY_POLICY", "Non-idempotent writes cannot be blindly retried.")
        reconciliation_operation = durability.get("reconciliationOperation")
        if reconciliation_operation is not None and not _OPERATION_IDENT.fullmatch(str(reconciliation_operation)):
            raise IntegrationError("IDEMPOTENCY_POLICY", "Reconciliation must name one registered operation.")
    normalised = copy.deepcopy(operation)
    normalised["binding"] = copy.deepcopy(binding)
    normalised["maxResponseBytes"] = max_bytes
    normalised["version"] = str(operation["version"])
    normalised["id"] = ident
    return normalised


def normalize_connection_spec(document: Any) -> dict[str, Any]:
    """Validate and canonicalise a trusted administrator connection record."""

    allowed = {
        "schemaVersion", "id", "version", "generation", "name", "description", "provider",
        "status", "transport", "baseUrls", "allowPrivateNetwork", "auth", "timeouts",
        "rateLimit", "retryPolicy", "operations", "createdAt", "updatedAt", "updatedBy",
    }
    required = allowed - {"createdAt", "updatedAt", "updatedBy"}
    record = _strict_keys(document, allowed, required, "connection")
    if record["schemaVersion"] != CONNECTION_SCHEMA_VERSION:
        raise IntegrationError("CONNECTION_SCHEMA", "The connection schema version is unsupported.")
    ident = _text(record["id"], "connection ID", 128, _IDENT)
    version = _bounded_int(record["version"], "connection version", 1, 1_000_000)
    generation = _bounded_int(record["generation"], "connection generation", 1, 1_000_000_000)
    _text(record["name"], "connection name", 200)
    _text(record["description"], "connection description", 2000)
    provider = _text(record["provider"], "provider ID", 128, _IDENT)
    if provider not in _PROVIDER_INDEX:
        raise IntegrationError("PROVIDER_UNKNOWN", "Select a registered provider descriptor.")
    if record["status"] not in _CONNECTION_STATUSES:
        raise IntegrationError("CONNECTION_STATUS", "The connection status is unsupported.")
    transport = record["transport"]
    if transport not in _TRANSPORTS or transport != _PROVIDER_INDEX[provider]["transport"]:
        raise IntegrationError("CONNECTION_TRANSPORT", "The transport does not match the provider descriptor.")
    allow_private = record["allowPrivateNetwork"]
    if not isinstance(allow_private, bool):
        raise IntegrationError("NETWORK_POLICY", "Private-network access must be an explicit boolean policy.")
    base_urls = record["baseUrls"]
    if not isinstance(base_urls, list) or not 1 <= len(base_urls) <= 20:
        raise IntegrationError("DESTINATION_DENIED", "A connection needs one to twenty allowed base URLs.")
    base_urls = [_normalise_base_url(item, allow_private) for item in base_urls]
    if len(base_urls) != len(set(base_urls)):
        raise IntegrationError("DESTINATION_DENIED", "Allowed base URLs must be unique.")
    auth = _normalise_auth(record["auth"], provider)
    _validate_native_provider_destinations(provider, auth, base_urls)
    timeout = _strict_keys(
        record["timeouts"], {"connectMs", "readMs", "totalMs"}, {"connectMs", "readMs", "totalMs"}, "timeouts"
    )
    connect_ms = _bounded_int(timeout["connectMs"], "connect timeout", 100, 60_000)
    read_ms = _bounded_int(timeout["readMs"], "read timeout", 100, 120_000)
    total_ms = _bounded_int(timeout["totalMs"], "total timeout", 100, 180_000)
    if total_ms < max(connect_ms, read_ms):
        raise IntegrationError("TIMEOUT_POLICY", "Total timeout cannot be shorter than a component timeout.")
    rate = _strict_keys(
        record["rateLimit"],
        {"maxRequests", "windowSeconds", "maxConcurrent"},
        {"maxRequests", "windowSeconds", "maxConcurrent"},
        "rate limit",
    )
    normalised_rate = {
        "maxRequests": _bounded_int(rate["maxRequests"], "rate-limit requests", 1, 100_000),
        "windowSeconds": _bounded_int(rate["windowSeconds"], "rate-limit window", 1, 86_400),
        "maxConcurrent": _bounded_int(rate["maxConcurrent"], "concurrency limit", 1, 1000),
    }
    retry = _strict_keys(
        record["retryPolicy"],
        {"maxAttempts", "baseDelayMs", "maxDelayMs", "retryStatusCodes"},
        {"maxAttempts", "baseDelayMs", "maxDelayMs", "retryStatusCodes"},
        "retry policy",
    )
    retry_codes = retry["retryStatusCodes"]
    if (
        not isinstance(retry_codes, list) or len(retry_codes) > 20
        or len(retry_codes) != len(set(retry_codes))
        or any(code not in _RETRY_CODES for code in retry_codes)
    ):
        raise IntegrationError("RETRY_POLICY", "Retry status codes must use the approved transient set.")
    normalised_retry = {
        "maxAttempts": _bounded_int(retry["maxAttempts"], "retry attempts", 1, 8),
        "baseDelayMs": _bounded_int(retry["baseDelayMs"], "retry base delay", 0, 60_000),
        "maxDelayMs": _bounded_int(retry["maxDelayMs"], "retry maximum delay", 0, 300_000),
        "retryStatusCodes": list(retry_codes),
    }
    if normalised_retry["maxDelayMs"] < normalised_retry["baseDelayMs"]:
        raise IntegrationError("RETRY_POLICY", "Maximum retry delay cannot be shorter than the base delay.")
    operations_raw = record["operations"]
    if not isinstance(operations_raw, list) or not 1 <= len(operations_raw) <= 200:
        raise IntegrationError("OPERATION_SCHEMA", "A connection needs one to two hundred registered operations.")
    operations = [_normalise_operation(item, transport) for item in operations_raw]
    operation_ids = [item["id"] for item in operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise IntegrationError("OPERATION_SCHEMA", "Operation IDs must be unique within a connection.")
    granted = set(auth["scopes"])
    for operation in operations:
        if set(operation["requiredScopes"]) - granted:
            raise IntegrationError(
                "AUTH_SCOPE", "An operation requests scopes outside the reviewed connection grant.",
                {"operationId": operation["id"]},
            )
        binding_index = operation["binding"].get("baseUrlIndex", 0)
        if binding_index >= len(base_urls):
            raise IntegrationError("OPERATION_BINDING", "An operation selects an unavailable base URL.")
        reconciliation = operation["idempotency"].get("reconciliationOperation")
        if reconciliation and reconciliation not in operation_ids:
            raise IntegrationError("IDEMPOTENCY_POLICY", "Reconciliation names an unregistered operation.")
    normalised = copy.deepcopy(record)
    normalised.update(
        id=ident,
        version=version,
        generation=generation,
        provider=provider,
        baseUrls=base_urls,
        auth=auth,
        timeouts={"connectMs": connect_ms, "readMs": read_ms, "totalMs": total_ms},
        rateLimit=normalised_rate,
        retryPolicy=normalised_retry,
        operations=operations,
    )
    if _size(normalised) > 2_000_000:
        raise IntegrationError("CONNECTION_SCHEMA", "The connection definition is too large.")
    return normalised


def public_connection(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return state safe for bootstrap/API responses.

    Secret references themselves are intentionally omitted because vault paths,
    environment names and tenant identifiers can also be sensitive.
    """

    connection = normalize_connection_spec(document)
    public = copy.deepcopy(connection)
    slots = sorted(public["auth"].pop("secretRefs"))
    public["auth"].update(
        credentialReferencesConfigured=len(slots) == len(_AUTH_SLOTS[public["auth"]["mode"]]),
        credentialSlotCount=len(slots),
    )
    public["connectionHash"] = _hash(public)
    return public


def _operation(document: Mapping[str, Any], operation_id: str) -> dict[str, Any]:
    return next((item for item in document["operations"] if item["id"] == operation_id), None) or (_raise(
        "OPERATION_NOT_FOUND", "The requested operation is not registered on this connection."
    ))


def _raise(code: str, message: str) -> Any:
    raise IntegrationError(code, message)


@dataclass(frozen=True)
class PreparedIntegrationCall:
    """An exact, credential-free operation prepared for policy and approval."""

    connection_id: str
    connection_version: int
    connection_generation: int
    provider: str
    transport: str
    operation_id: str
    operation_version: str
    effect: str
    approval_required: bool
    operation_key: str
    arguments: Mapping[str, Any]
    target_url: str
    method: str | None
    remote_operation: str | None
    headers: Mapping[str, str]
    query: Mapping[str, Any]
    body: Mapping[str, Any] | None
    timeout_ms: int
    max_response_bytes: int
    auth_binding_hash: str
    plan_hash: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "connectionIdentity": {
                "connectionId": self.connection_id,
                "version": self.connection_version,
                "generation": self.connection_generation,
            },
            "provider": self.provider,
            "transport": self.transport,
            "operationId": self.operation_id,
            "operationVersion": self.operation_version,
            "effect": self.effect,
            "approvalRequired": self.approval_required,
            "operationKey": self.operation_key,
            "arguments": copy.deepcopy(dict(self.arguments)),
            "targetUrl": self.target_url,
            "method": self.method,
            "remoteOperation": self.remote_operation,
            "headers": copy.deepcopy(dict(self.headers)),
            "query": copy.deepcopy(dict(self.query)),
            "body": copy.deepcopy(self.body),
            "timeoutMs": self.timeout_ms,
            "maxResponseBytes": self.max_response_bytes,
            "planHash": self.plan_hash,
        }

    def storage_dict(self) -> dict[str, Any]:
        """Return the durable host-only plan, including its private auth binding."""
        return {**self.public_dict(), "authBindingHash": self.auth_binding_hash}

    def __repr__(self) -> str:
        return (
            f"PreparedIntegrationCall(connection_id={self.connection_id!r}, "
            f"operation_id={self.operation_id!r}, effect={self.effect!r}, plan_hash={self.plan_hash!r})"
        )


def _append_query(url: str, query: Mapping[str, Any]) -> str:
    if not query:
        return url
    pairs: list[tuple[str, str]] = []
    for key, raw in query.items():
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if isinstance(value, (dict, list)):
                encoded = _json(value)
            elif isinstance(value, bool):
                encoded = "true" if value else "false"
            else:
                encoded = str(value)
            pairs.append((key, encoded))
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(pairs)


def _require_provider_success(raw: Any, provider: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise IntegrationError("PROVIDER_RESPONSE", "The provider returned an unexpected JSON shape.")
    if provider == "slack" and raw.get("ok") is not True:
        # Slack commonly reports application errors with HTTP 200.  Keep only
        # its bounded public error code; response metadata and tokens are not
        # copied into errors or receipts.
        provider_code = raw.get("error")
        details = {"providerCode": provider_code[:200]} if isinstance(provider_code, str) else None
        raise IntegrationError("PROVIDER_RESPONSE", "Slack rejected the operation.", details)
    return raw


def _page_from_confluence(raw: Mapping[str, Any]) -> dict[str, Any]:
    version = raw.get("version")
    links = raw.get("_links")
    version_number = version.get("number") if isinstance(version, Mapping) else None
    url = ""
    if isinstance(links, Mapping):
        base = links.get("base") if isinstance(links.get("base"), str) else ""
        web = links.get("webui") if isinstance(links.get("webui"), str) else ""
        url = base.rstrip("/") + "/" + web.lstrip("/") if base and web else web or base
    return {"id": raw.get("id"), "title": raw.get("title"), "version": version_number, "url": url}


def _encode_native_body(codec: str, arguments: Mapping[str, Any], ordinary_body: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Project normalized arguments into a trusted provider-native request body."""

    if codec == "jira.create_issue.v1":
        description = arguments["description"]
        return {
            "fields": {
                "project": {"key": arguments["projectKey"]},
                "issuetype": {"name": arguments["issueType"]},
                "summary": arguments["summary"],
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }],
                },
            }
        }
    if codec == "confluence.create_page.v1":
        return {
            "spaceId": arguments["spaceId"], "status": "current", "title": arguments["title"],
            "body": {"representation": "storage", "value": arguments["body"]},
        }
    return copy.deepcopy(ordinary_body)


def _decode_native_response(codec: str, raw_value: Any, provider: str) -> dict[str, Any]:
    """Project a bounded provider envelope into the operation's stable schema."""

    raw = _require_provider_success(raw_value, provider)
    if codec == "identity.v1":
        return copy.deepcopy(dict(raw))
    if codec == "slack.auth_test.v1":
        return {"teamId": raw.get("team_id"), "userId": raw.get("user_id"), "url": raw.get("url")}
    if codec == "slack.conversations_history.v1":
        messages = raw.get("messages")
        if not isinstance(messages, list):
            raise IntegrationError("PROVIDER_RESPONSE", "Slack returned invalid message data.")
        projected = []
        for message in messages:
            if not isinstance(message, Mapping):
                raise IntegrationError("PROVIDER_RESPONSE", "Slack returned invalid message data.")
            projected.append({
                "id": message.get("ts"), "text": message.get("text", ""),
                "authorId": message.get("user") or message.get("bot_id") or "unknown",
                "createdAt": message.get("ts"),
            })
        metadata = raw.get("response_metadata")
        cursor = metadata.get("next_cursor") if isinstance(metadata, Mapping) else ""
        return {"messages": projected, "hasMore": bool(raw.get("has_more") or cursor)}
    if codec == "slack.chat_post_message.v1":
        return {"messageId": raw.get("ts"), "channelId": raw.get("channel"), "accepted": True}
    if codec == "jira.myself.v1":
        return {
            "accountId": raw.get("accountId"), "displayName": raw.get("displayName"),
            "active": raw.get("active"),
        }
    if codec == "jira.issue.v1":
        fields = raw.get("fields")
        fields = fields if isinstance(fields, Mapping) else {}
        status = fields.get("status")
        return {
            "key": raw.get("key"), "summary": fields.get("summary"),
            "status": status.get("name") if isinstance(status, Mapping) else None,
        }
    if codec == "jira.search.v1":
        issues = raw.get("issues")
        if not isinstance(issues, list):
            raise IntegrationError("PROVIDER_RESPONSE", "Jira returned invalid issue data.")
        projected = [_decode_native_response("jira.issue.v1", issue, provider) for issue in issues]
        has_more = bool(raw.get("nextPageToken")) or raw.get("isLast") is False
        return {"issues": projected, "hasMore": has_more}
    if codec == "jira.create_issue.v1":
        return {"key": raw.get("key"), "id": raw.get("id"), "url": raw.get("self")}
    if codec == "confluence.spaces_health.v1":
        results = raw.get("results")
        return {"accessible": isinstance(results, list), "spaceCount": len(results) if isinstance(results, list) else 0}
    if codec in {"confluence.page.v1", "confluence.create_page.v1"}:
        return _page_from_confluence(raw)
    if codec == "confluence.pages.v1":
        results = raw.get("results")
        if not isinstance(results, list):
            raise IntegrationError("PROVIDER_RESPONSE", "Confluence returned invalid page data.")
        return {"pages": [_page_from_confluence(item) if isinstance(item, Mapping) else {} for item in results]}
    raise IntegrationError("OPERATION_BINDING", "The trusted provider codec is unavailable.")


def prepare_call(
    document: Mapping[str, Any], operation_id: str, arguments: Mapping[str, Any], operation_key: str
) -> PreparedIntegrationCall:
    """Prepare one exact call without resolving credentials or touching a network."""

    connection = normalize_connection_spec(document)
    if connection["status"] != "ready":
        raise IntegrationError("CONNECTION_NOT_READY", "The selected connection is not ready for dispatch.")
    if not isinstance(operation_id, str):
        raise IntegrationError("OPERATION_NOT_FOUND", "A registered operation ID is required.")
    operation = _operation(connection, operation_id)
    if not isinstance(arguments, dict):
        raise IntegrationError("SCHEMA_VALUE", "Operation arguments must be one object.")
    validate_value(arguments, operation["inputSchema"], "arguments")
    if not isinstance(operation_key, str) or not _OPERATION_KEY.fullmatch(operation_key):
        raise IntegrationError("OPERATION_KEY", "A stable bounded operation key is required.")
    binding = operation["binding"]
    base_url = connection["baseUrls"][binding.get("baseUrlIndex", 0)]
    method: str | None = None
    remote_operation: str | None = None
    headers: dict[str, str] = {}
    query: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    if binding["kind"] == "http":
        method = binding["method"]
        # Resolve only the trusted, reviewed template against the allowlisted
        # base. Substituting model-supplied values first would let an exact
        # "." or ".." value be normalized by urljoin into another endpoint.
        target_url = urllib.parse.urljoin(base_url, binding["pathTemplate"])
        for name in binding["pathParameters"]:
            scalar = arguments[name]
            if isinstance(scalar, (dict, list)) or scalar is None:
                raise IntegrationError("SCHEMA_VALUE", "Path arguments must be non-null scalars.")
            raw_segment = str(scalar)
            if raw_segment in {".", ".."}:
                raise IntegrationError("SCHEMA_VALUE", "Path arguments cannot be dot segments.")
            target_url = target_url.replace(
                "{" + name + "}", urllib.parse.quote(raw_segment, safe="")
            )
        query = copy.deepcopy(binding.get("fixedQuery", {}))
        query.update({name: copy.deepcopy(arguments[name]) for name in binding["queryParameters"] if name in arguments})
        target_url = _append_query(target_url, query)
        body_values = {name: copy.deepcopy(arguments[name]) for name in binding["bodyParameters"] if name in arguments}
        body = _encode_native_body(binding["codec"], arguments, body_values or None)
        headers = {"Accept": "application/json", **copy.deepcopy(binding.get("fixedHeaders", {}))}
        if body is not None:
            headers.setdefault("Content-Type", "application/json")
        durability = operation["idempotency"]
        location = durability.get("operationKey", "")
        if operation["effect"] == "write" and location.startswith("header:"):
            header = location.split(":", 1)[1]
            if not _HEADER_NAME.fullmatch(header) or header.lower() in _FORBIDDEN_AUTH_HEADERS | {"authorization"}:
                raise IntegrationError("IDEMPOTENCY_POLICY", "The operation-key header is unsafe.")
            headers[header] = operation_key
        target_url = urllib.parse.urlunsplit(urllib.parse.urlsplit(target_url))
    else:
        target_url = base_url
        remote_operation = "tools/list" if binding["kind"] == "mcp-list-tools" else binding["toolName"]
        body = copy.deepcopy(dict(arguments))
    public_auth = {key: value for key, value in connection["auth"].items() if key != "secretRefs"}
    # The opaque hash detects an unversioned credential-reference change while
    # keeping secret paths and environment variable names out of prepared state.
    auth_hash = _hash(connection["auth"])
    payload = {
        "connectionId": connection["id"], "connectionVersion": connection["version"],
        "connectionGeneration": connection["generation"], "provider": connection["provider"],
        "transport": connection["transport"], "operationId": operation["id"],
        "operationVersion": operation["version"], "effect": operation["effect"],
        "approvalRequired": operation["approvalRequired"], "operationKey": operation_key,
        "arguments": copy.deepcopy(arguments), "targetUrl": target_url, "method": method,
        "remoteOperation": remote_operation, "headers": headers, "query": query, "body": body,
        "timeoutMs": connection["timeouts"]["totalMs"],
        "maxResponseBytes": operation["maxResponseBytes"],
    }
    return PreparedIntegrationCall(
        connection_id=connection["id"], connection_version=connection["version"],
        connection_generation=connection["generation"], provider=connection["provider"],
        transport=connection["transport"], operation_id=operation["id"],
        operation_version=operation["version"], effect=operation["effect"],
        approval_required=operation["approvalRequired"], operation_key=operation_key,
        arguments=copy.deepcopy(arguments), target_url=target_url, method=method,
        remote_operation=remote_operation, headers=headers, query=query, body=body,
        timeout_ms=connection["timeouts"]["totalMs"], max_response_bytes=operation["maxResponseBytes"],
        auth_binding_hash=auth_hash, plan_hash=_hash(payload),
    )


def verify_prepared_call(document: Mapping[str, Any], prepared: PreparedIntegrationCall) -> dict[str, Any]:
    """Rebuild a plan and reject stale connection, payload or authority state."""

    connection = normalize_connection_spec(document)
    if (
        connection["id"] != prepared.connection_id
        or connection["version"] != prepared.connection_version
        or connection["generation"] != prepared.connection_generation
        or connection["status"] != "ready"
    ):
        raise IntegrationError("CONNECTION_CHANGED", "Connection authority changed after this action was prepared.")
    rebuilt = prepare_call(connection, prepared.operation_id, dict(prepared.arguments), prepared.operation_key)
    # The hash is an approval/audit identifier, not a substitute for checking
    # the exact object that will be dispatched. A persisted record must not be
    # able to retain an old valid hash while changing its URL, method, headers,
    # body, timeout, or remote operation.
    if rebuilt != prepared:
        raise IntegrationError("PREPARED_CALL_CHANGED", "The exact prepared integration call changed before dispatch.")
    return connection


@runtime_checkable
class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


@dataclass(frozen=True, repr=False)
class SensitiveHttpRequest:
    """Ephemeral request containing credentials; never persist or audit this object."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout_ms: int
    max_response_bytes: int
    approved_addresses: tuple[str, ...]
    follow_redirects: bool = False

    def __repr__(self) -> str:
        return (
            f"SensitiveHttpRequest(method={self.method!r}, url=<redacted>, "
            f"headers=<redacted:{len(self.headers)}>, body_bytes={len(self.body or b'')}, "
            f"approved_addresses={self.approved_addresses!r}, follow_redirects=False)"
        )


@dataclass(frozen=True, repr=False)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str

    def __repr__(self) -> str:
        return f"TransportResponse(status={self.status}, headers={len(self.headers)}, body_bytes={len(self.body)}, final_url=<redacted>)"


@runtime_checkable
class HttpExecutor(Protocol):
    """Transport must pin DNS, disable redirects and honour all request bounds."""

    def send(self, request: SensitiveHttpRequest) -> TransportResponse: ...


@runtime_checkable
class McpClient(Protocol):
    """An MCP host that executes only a pre-registered tool contract."""

    def list_tools(
        self, *, endpoint: str, timeout_ms: int, approved_addresses: tuple[str, ...],
        credential: str | None,
    ) -> Mapping[str, Any]: ...

    def call_tool(
        self, *, endpoint: str, tool_name: str, arguments: Mapping[str, Any],
        operation_key: str, timeout_ms: int, approved_addresses: tuple[str, ...],
        credential: str | None,
    ) -> Mapping[str, Any]: ...


def _resolve_secret(resolver: SecretResolver, reference: str) -> str:
    try:
        value = resolver.resolve(reference)
    except Exception as exc:
        raise IntegrationError("SECRET_UNAVAILABLE", "A required server-side credential is unavailable.") from exc
    if not isinstance(value, str) or not value or len(value) > 65_536 or "\r" in value or "\n" in value:
        raise IntegrationError("SECRET_UNAVAILABLE", "A required server-side credential is invalid.")
    return value


def _authenticated_headers(
    connection: Mapping[str, Any], prepared: PreparedIntegrationCall, resolver: SecretResolver
) -> dict[str, str]:
    headers = dict(prepared.headers)
    auth = connection["auth"]
    refs = auth["secretRefs"]
    if auth["mode"] == "none":
        return headers
    if auth["mode"] == "bearer":
        headers["Authorization"] = f"{auth.get('scheme', 'Bearer')} {_resolve_secret(resolver, refs['token'])}"
    elif auth["mode"] == "api_key_header":
        headers[auth["headerName"]] = _resolve_secret(resolver, refs["apiKey"])
    elif auth["mode"] == "basic":
        username = _resolve_secret(resolver, refs["username"])
        password = _resolve_secret(resolver, refs["password"])
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + encoded
    elif auth["mode"] == "oauth2":
        headers["Authorization"] = "Bearer " + _resolve_secret(resolver, refs["credential"])
    elif auth["mode"] == "hmac_sha256":
        key = _resolve_secret(resolver, refs["key"]).encode("utf-8")
        timestamp = str(int(time.time()))
        body = _json(prepared.body or {}).encode("utf-8")
        signature = hmac.new(key, timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
        headers.update({"X-Axiom-Timestamp": timestamp, "X-Axiom-Signature": "sha256=" + signature})
    return headers


@dataclass(frozen=True)
class AdapterResult:
    operation_id: str
    operation_key: str
    status: str
    output: Mapping[str, Any]
    receipt: Mapping[str, Any]


@dataclass(frozen=True)
class RetryAdvice:
    retry: bool
    delay_ms: int
    reconcile_first: bool
    reason: str


def retry_advice(
    document: Mapping[str, Any], operation_id: str, *, attempt: int,
    status_code: int | None = None, network_error: bool = False, outcome_unknown: bool = False,
) -> RetryAdvice:
    connection = normalize_connection_spec(document)
    operation = _operation(connection, operation_id)
    policy = connection["retryPolicy"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise IntegrationError("RETRY_POLICY", "Retry attempt must be a positive integer.")
    if attempt >= policy["maxAttempts"]:
        return RetryAdvice(False, 0, False, "attempt_limit")
    transient = network_error or status_code in policy["retryStatusCodes"]
    if not transient and not outcome_unknown:
        return RetryAdvice(False, 0, False, "not_transient")
    durability = operation["idempotency"]
    if operation["effect"] == "write" and (outcome_unknown or durability["retry"] != "safe"):
        return RetryAdvice(False, 0, True, "write_requires_reconciliation")
    delay = min(policy["maxDelayMs"], policy["baseDelayMs"] * (2 ** max(0, attempt - 1)))
    return RetryAdvice(True, delay, False, "transient_read" if operation["effect"] == "read" else "provider_keyed_write")


def reconciliation_directive(
    document: Mapping[str, Any], operation_id: str, operation_key: str
) -> dict[str, Any]:
    connection = normalize_connection_spec(document)
    operation = _operation(connection, operation_id)
    if operation["effect"] != "write":
        raise IntegrationError("RECONCILIATION_POLICY", "Only writes can have an uncertain remote outcome.")
    if not isinstance(operation_key, str) or not _OPERATION_KEY.fullmatch(operation_key):
        raise IntegrationError("OPERATION_KEY", "A stable operation key is required for reconciliation.")
    policy = operation["idempotency"]
    return {
        "connectionId": connection["id"], "generation": connection["generation"],
        "operationId": operation["id"], "operationKey": operation_key,
        "mode": policy["reconciliation"],
        "reconciliationOperation": policy.get("reconciliationOperation"),
        "automatic": policy["reconciliation"] in {"provider_status", "read_after_write"}
            and bool(policy.get("reconciliationOperation")),
        "retryPermittedOnlyAfterNotFound": policy["retry"] == "reconcile_before_retry",
    }


class RateLease:
    def __init__(self, limiter: "InMemoryRateLimiter", connection_id: str):
        self._limiter = limiter
        self._connection_id = connection_id
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._limiter._release(self._connection_id)

    def __enter__(self) -> "RateLease":
        return self

    def __exit__(self, *_: Any) -> None:
        self.release()


class InMemoryRateLimiter:
    """Single-process limiter; distributed deployments must inject a shared limiter."""

    def __init__(self, clock: Any = time.monotonic):
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def acquire(self, connection_id: str, policy: Mapping[str, int]) -> RateLease:
        now_value = float(self._clock())
        with self._lock:
            events = self._events[connection_id]
            cutoff = now_value - policy["windowSeconds"]
            while events and events[0] <= cutoff:
                events.popleft()
            if self._active[connection_id] >= policy["maxConcurrent"]:
                raise IntegrationError("RATE_LIMITED", "The connection concurrency limit is active.")
            if len(events) >= policy["maxRequests"]:
                retry_ms = max(1, math.ceil((events[0] + policy["windowSeconds"] - now_value) * 1000))
                raise IntegrationError("RATE_LIMITED", "The connection request limit is active.", {"retryAfterMs": retry_ms})
            events.append(now_value)
            self._active[connection_id] += 1
        return RateLease(self, connection_id)

    def _release(self, connection_id: str) -> None:
        with self._lock:
            self._active[connection_id] = max(0, self._active[connection_id] - 1)


@runtime_checkable
class IntegrationAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    transport: str

    def execute(
        self, connection: Mapping[str, Any], prepared: PreparedIntegrationCall, *,
        secret_resolver: SecretResolver, network_resolver: Any,
    ) -> AdapterResult: ...

    def reconcile(
        self, connection: Mapping[str, Any], prepared: PreparedIntegrationCall, *,
        secret_resolver: SecretResolver, network_resolver: Any,
    ) -> AdapterResult: ...


class StrictHttpAdapter:
    """HTTP adapter with injected transport; it never follows redirects."""

    adapter_id = "axiom.strict-http"
    adapter_version = "1.0.0"

    def __init__(self, executor: HttpExecutor, rate_limiter: InMemoryRateLimiter | None = None, *, transport: str = "https-json"):
        if transport not in {"https-json", "webhook"}:
            raise ValueError("StrictHttpAdapter supports HTTP transports only")
        self.transport = transport
        self._executor = executor
        self._rate_limiter = rate_limiter or InMemoryRateLimiter()

    def execute(
        self, document: Mapping[str, Any], prepared: PreparedIntegrationCall, *,
        secret_resolver: SecretResolver, network_resolver: Any,
    ) -> AdapterResult:
        connection = verify_prepared_call(document, prepared)
        if connection["transport"] != self.transport:
            raise IntegrationError("ADAPTER_MISMATCH", "The selected adapter does not own this transport.")
        addresses = validate_outbound_url(
            prepared.target_url, connection["baseUrls"],
            allow_private_network=connection["allowPrivateNetwork"], resolver=network_resolver,
        )
        headers = _authenticated_headers(connection, prepared, secret_resolver)
        body = _json(prepared.body).encode("utf-8") if prepared.body is not None else None
        request = SensitiveHttpRequest(
            method=prepared.method or "POST", url=prepared.target_url, headers=headers, body=body,
            timeout_ms=prepared.timeout_ms, max_response_bytes=prepared.max_response_bytes,
            approved_addresses=addresses, follow_redirects=False,
        )
        lease = self._rate_limiter.acquire(connection["id"], connection["rateLimit"])
        try:
            response = self._executor.send(request)
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError("ADAPTER_UNAVAILABLE", "The external adapter request failed.") from exc
        finally:
            lease.release()
        if not isinstance(response, TransportResponse):
            raise IntegrationError("ADAPTER_PROTOCOL", "The HTTP transport returned an invalid response envelope.")
        if 300 <= response.status < 400:
            raise IntegrationError("REDIRECT_DENIED", "External redirects are disabled for integration calls.")
        if response.final_url != prepared.target_url:
            raise IntegrationError("REDIRECT_DENIED", "The transport changed the approved destination.")
        if len(response.body) > prepared.max_response_bytes:
            raise IntegrationError("RESPONSE_TOO_LARGE", "The provider response exceeded its byte limit.")
        if not 200 <= response.status < 300:
            raise IntegrationError(
                "PROVIDER_RESPONSE", "The provider returned a non-success response.",
                {"status": response.status, "retryable": response.status in connection["retryPolicy"]["retryStatusCodes"]},
            )
        try:
            raw_output = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise IntegrationError("PROVIDER_RESPONSE", "The provider did not return valid JSON.") from exc
        operation = _operation(connection, prepared.operation_id)
        output = _decode_native_response(operation["binding"]["codec"], raw_output, connection["provider"])
        validate_value(output, operation["outputSchema"], "providerOutput")
        receipt = {
            "connectionId": connection["id"], "generation": connection["generation"],
            "operationId": prepared.operation_id, "operationKey": prepared.operation_key,
            "status": response.status, "resultHash": _hash(output), "verified": True,
        }
        return AdapterResult(prepared.operation_id, prepared.operation_key, "acknowledged", output, receipt)

    def reconcile(
        self, document: Mapping[str, Any], prepared: PreparedIntegrationCall, *,
        secret_resolver: SecretResolver, network_resolver: Any,
    ) -> AdapterResult:
        directive = reconciliation_directive(document, prepared.operation_id, prepared.operation_key)
        if not directive["automatic"]:
            raise IntegrationError("RECONCILIATION_REQUIRED", "This operation needs provider-specific or human reconciliation.")
        raise IntegrationError(
            "RECONCILIATION_ADAPTER_REQUIRED",
            "Dispatch the registered reconciliation operation; do not repeat the original write.",
            {"operationId": directive["reconciliationOperation"]},
        )


class StrictMcpAdapter:
    """MCP adapter that can call only tools pre-registered as operations."""

    adapter_id = "axiom.strict-mcp"
    adapter_version = "1.0.0"
    transport = "mcp-streamable-http"

    def __init__(self, client: McpClient, rate_limiter: InMemoryRateLimiter | None = None):
        self._client = client
        self._rate_limiter = rate_limiter or InMemoryRateLimiter()

    def execute(
        self, document: Mapping[str, Any], prepared: PreparedIntegrationCall, *,
        secret_resolver: SecretResolver, network_resolver: Any,
    ) -> AdapterResult:
        connection = verify_prepared_call(document, prepared)
        if connection["transport"] != self.transport or not prepared.remote_operation:
            raise IntegrationError("ADAPTER_MISMATCH", "The selected adapter does not own this transport.")
        addresses = validate_outbound_url(
            prepared.target_url, connection["baseUrls"],
            allow_private_network=connection["allowPrivateNetwork"], resolver=network_resolver,
        )
        credential = None
        if connection["auth"]["mode"] in {"bearer", "oauth2"}:
            slot = "token" if connection["auth"]["mode"] == "bearer" else "credential"
            credential = _resolve_secret(secret_resolver, connection["auth"]["secretRefs"][slot])
        lease = self._rate_limiter.acquire(connection["id"], connection["rateLimit"])
        try:
            operation = _operation(connection, prepared.operation_id)
            if operation["binding"]["kind"] == "mcp-list-tools":
                raw = self._client.list_tools(
                    endpoint=prepared.target_url, timeout_ms=prepared.timeout_ms,
                    approved_addresses=addresses, credential=credential,
                )
            else:
                raw = self._client.call_tool(
                    endpoint=prepared.target_url, tool_name=prepared.remote_operation,
                    arguments=copy.deepcopy(dict(prepared.arguments)), operation_key=prepared.operation_key,
                    timeout_ms=prepared.timeout_ms, approved_addresses=addresses, credential=credential,
                )
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError("ADAPTER_UNAVAILABLE", "The MCP tool call failed.") from exc
        finally:
            lease.release()
        if operation["binding"]["kind"] == "mcp-list-tools":
            tools = raw.get("tools") if isinstance(raw, Mapping) else None
            if not isinstance(tools, list):
                raise IntegrationError("PROVIDER_RESPONSE", "The MCP server returned invalid tools/list data.")
            projected_tools = []
            for tool in tools:
                if not isinstance(tool, Mapping) or not isinstance(tool.get("name"), str):
                    raise IntegrationError("PROVIDER_RESPONSE", "The MCP server returned invalid tool metadata.")
                description = tool.get("description")
                projected_tools.append({
                    "name": tool["name"],
                    "description": description if isinstance(description, str) and description else "No description supplied.",
                })
            output = {"tools": projected_tools}
        else:
            output = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else raw
        validate_value(output, operation["outputSchema"], "providerOutput")
        receipt = {
            "connectionId": connection["id"], "generation": connection["generation"],
            "operationId": prepared.operation_id, "operationKey": prepared.operation_key,
            "resultHash": _hash(output), "verified": True,
        }
        return AdapterResult(prepared.operation_id, prepared.operation_key, "acknowledged", output, receipt)

    def reconcile(
        self, document: Mapping[str, Any], prepared: PreparedIntegrationCall, *,
        secret_resolver: SecretResolver, network_resolver: Any,
    ) -> AdapterResult:
        directive = reconciliation_directive(document, prepared.operation_id, prepared.operation_key)
        if not directive["automatic"]:
            raise IntegrationError("RECONCILIATION_REQUIRED", "This MCP write needs explicit reconciliation.")
        raise IntegrationError(
            "RECONCILIATION_ADAPTER_REQUIRED",
            "Call the registered MCP reconciliation operation instead of repeating the original write.",
            {"operationId": directive["reconciliationOperation"]},
        )


class AdapterRegistry:
    """Trusted developer registry. Connection records cannot register code."""

    def __init__(self) -> None:
        self._adapters: dict[str, IntegrationAdapter] = {}

    def register(self, adapter: IntegrationAdapter) -> None:
        if not isinstance(adapter, IntegrationAdapter):
            raise IntegrationError("ADAPTER_CONTRACT", "Adapters must implement the integration contract.")
        if adapter.transport in self._adapters:
            raise IntegrationError("ADAPTER_CONTRACT", "Only one trusted adapter may own a transport.")
        self._adapters[adapter.transport] = adapter

    def resolve(self, document: Mapping[str, Any]) -> IntegrationAdapter:
        connection = normalize_connection_spec(document)
        adapter = self._adapters.get(connection["transport"])
        if adapter is None:
            raise IntegrationError("ADAPTER_NOT_CONFIGURED", "No trusted adapter is configured for this transport.")
        return adapter


def capability_contracts(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project connection operations into Agent Factory capability contracts."""

    connection = normalize_connection_spec(document)
    contracts = []
    for operation in connection["operations"]:
        projected_id = capability_id(connection["id"], connection["provider"], operation["id"])
        semantics = {
            name: operation["inputSchema"]["properties"][name].get("description", f"Input {name} for {operation['id']}.")
            for name in operation["inputSchema"].get("properties", {})
        }
        contracts.append({
            "schemaVersion": CAPABILITY_SCHEMA_VERSION,
            "id": projected_id, "version": operation["version"],
            "description": operation["description"], "effect": operation["effect"],
            "inputSchema": copy.deepcopy(operation["inputSchema"]),
            "outputSchema": copy.deepcopy(operation["outputSchema"]),
            "semanticFields": semantics,
            "authorization": {
                "scope": " ".join(operation["requiredScopes"]) or "connection-authorized",
                "connectionId": connection["id"], "connectionGeneration": connection["generation"],
                "approvalRequired": operation["approvalRequired"],
            },
            "adapterBinding": {
                "adapterId": _PROVIDER_INDEX[connection["provider"]]["adapterId"],
                "adapterVersion": "1.0.0", "operation": operation["id"],
                "transport": connection["transport"], "connectionId": connection["id"],
                "connectionVersion": connection["version"], "connectionGeneration": connection["generation"],
            },
            "idempotency": copy.deepcopy(operation["idempotency"]),
            "examples": [{"label": "Administrator-supplied contract example", "input": _example_value(operation["inputSchema"])}],
        })
    return contracts


def capability_id(connection_id: str, provider: str, operation_id: str) -> str:
    """Return a stable Agent Factory ID without cross-connection collisions."""

    _text(connection_id, "connection ID", 128, _IDENT)
    _text(provider, "provider ID", 128, _IDENT)
    _text(operation_id, "operation ID", 150, _OPERATION_IDENT)
    # Connection IDs are administrator-controlled and capability IDs are an
    # authority boundary. Keep a 128-bit namespace so deliberate collisions
    # are not a realistic aliasing path.
    namespace = _hash({"connectionId": connection_id})[:32]
    candidate = f"external.{namespace}.{provider}.{operation_id}"
    if len(candidate) <= 150:
        return candidate
    leaf = operation_id.rsplit(".", 1)[-1][:40]
    compact = f"external.{namespace}.{provider[:40]}.{leaf}.{_hash(operation_id)[:16]}"
    if len(compact) > 150 or not _OPERATION_IDENT.fullmatch(compact):
        raise IntegrationError("CAPABILITY_ID", "The connection operation cannot be projected to a stable capability ID.")
    return compact


def _example_value(schema: Mapping[str, Any]) -> Any:
    if "enum" in schema:
        return copy.deepcopy(schema["enum"][0])
    kind = schema["type"]
    if kind == "object":
        return {key: _example_value(value) for key, value in schema.get("properties", {}).items() if key in schema.get("required", [])}
    if kind == "array":
        return []
    if kind == "string":
        return "user@example.com" if schema.get("format") == "email" else "example"
    if kind == "integer":
        return max(0, int(schema.get("minimum", 0)))
    if kind == "number":
        return max(0, schema.get("minimum", 0))
    if kind == "boolean":
        return False
    return None


def provider_descriptors() -> list[dict[str, Any]]:
    """Return catalog metadata. Every entry is unconfigured descriptor-only state."""

    return copy.deepcopy(_PROVIDER_DESCRIPTORS)


def provider_descriptor(provider_id: str) -> dict[str, Any]:
    descriptor = _PROVIDER_INDEX.get(provider_id)
    if descriptor is None:
        raise IntegrationError("PROVIDER_UNKNOWN", "The requested provider descriptor is unavailable.")
    return copy.deepcopy(descriptor)


def connection_template(
    provider_id: str, *, connection_id: str, name: str, base_urls: Sequence[str],
    auth: Mapping[str, Any], allow_private_network: bool = False,
) -> dict[str, Any]:
    """Create a validated draft; only an administrator can later mark it ready."""

    descriptor = provider_descriptor(provider_id)
    record = {
        "schemaVersion": CONNECTION_SCHEMA_VERSION, "id": connection_id, "version": 1,
        "generation": 1, "name": name,
        "description": descriptor["description"], "provider": provider_id,
        "status": "draft", "transport": descriptor["transport"],
        "baseUrls": list(base_urls), "allowPrivateNetwork": allow_private_network,
        "auth": copy.deepcopy(dict(auth)),
        "timeouts": copy.deepcopy(descriptor["defaults"]["timeouts"]),
        "rateLimit": copy.deepcopy(descriptor["defaults"]["rateLimit"]),
        "retryPolicy": copy.deepcopy(descriptor["defaults"]["retryPolicy"]),
        "operations": copy.deepcopy(descriptor["operationTemplates"]),
    }
    return normalize_connection_spec(record)


def _walk_forbidden_refs(value: Any, depth: int = 0) -> None:
    if depth > 30:
        raise IntegrationError("OPENAPI_BOUNDS", "The OpenAPI document is nested too deeply.")
    if isinstance(value, dict):
        if "$ref" in value:
            raise IntegrationError(
                "OPENAPI_REF_UNSUPPORTED",
                "OpenAPI references are not resolved automatically; provide one fully inlined reviewed document.",
            )
        for child in value.values():
            _walk_forbidden_refs(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _walk_forbidden_refs(child, depth + 1)


def _openapi_security_schemes(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    components = document.get("components", {})
    if not isinstance(components, dict) or set(components) - {"securitySchemes", "schemas"}:
        raise IntegrationError("OPENAPI_UNSUPPORTED", "Only security schemes and inlined schemas are supported in components.")
    raw = components.get("securitySchemes", {})
    if not isinstance(raw, dict) or len(raw) > 50:
        raise IntegrationError("OPENAPI_SECURITY", "OpenAPI security schemes must be a bounded object.")
    result: dict[str, dict[str, Any]] = {}
    for name, scheme in raw.items():
        if not isinstance(name, str) or not _IDENT.fullmatch(name) or not isinstance(scheme, dict):
            raise IntegrationError("OPENAPI_SECURITY", "Security schemes need stable names and inline definitions.")
        kind = scheme.get("type")
        if kind == "http" and scheme.get("scheme") in {"bearer", "basic"}:
            result[name] = {"type": "http", "scheme": scheme["scheme"]}
        elif kind == "apiKey" and scheme.get("in") == "header":
            header = scheme.get("name")
            if (
                not isinstance(header, str) or not _HEADER_NAME.fullmatch(header)
                or header.lower() in _FORBIDDEN_AUTH_HEADERS | {"authorization"}
            ):
                raise IntegrationError("OPENAPI_SECURITY", "API-key security needs one safe header name.")
            result[name] = {"type": "apiKey", "in": "header", "name": header}
        elif kind == "oauth2" and isinstance(scheme.get("flows"), dict):
            # Flow URLs and token acquisition remain server-side setup; the
            # inspector records the scheme but performs no discovery or OAuth.
            if _size(scheme["flows"]) > 64_000:
                raise IntegrationError("OPENAPI_SECURITY", "OAuth flow metadata is too large.")
            result[name] = {"type": "oauth2"}
        else:
            raise IntegrationError("OPENAPI_SECURITY", "The OpenAPI security scheme is unsupported.")
    return result


def _openapi_parameters(path_parameters: Any, operation_parameters: Any) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    combined: list[Any] = []
    for value in (path_parameters or [], operation_parameters or []):
        if not isinstance(value, list):
            raise IntegrationError("OPENAPI_OPERATION", "OpenAPI parameters must be inline arrays.")
        combined.extend(value)
    properties: dict[str, Any] = {}
    required: list[str] = []
    path_names: list[str] = []
    query_names: list[str] = []
    for parameter in combined:
        if not isinstance(parameter, dict) or set(parameter) - {"name", "in", "required", "schema", "description", "deprecated", "style", "explode"}:
            raise IntegrationError("OPENAPI_OPERATION", "An OpenAPI parameter uses unsupported fields.")
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or not _IDENT.fullmatch(name) or name in properties or location not in {"path", "query"}:
            raise IntegrationError("OPENAPI_OPERATION", "Parameters must have unique safe path or query names.")
        schema = parameter.get("schema")
        _validate_schema(schema)
        properties[name] = copy.deepcopy(schema)
        if location == "path":
            if parameter.get("required") is not True:
                raise IntegrationError("OPENAPI_OPERATION", "Path parameters must be required.")
            path_names.append(name)
            required.append(name)
        else:
            query_names.append(name)
            if parameter.get("required") is True:
                required.append(name)
    return properties, required, path_names, query_names


def _openapi_json_schema(container: Any, label: str) -> dict[str, Any]:
    if not isinstance(container, dict) or set(container) - {"description", "required", "content"}:
        raise IntegrationError("OPENAPI_OPERATION", f"{label} uses unsupported fields.")
    content = container.get("content")
    if not isinstance(content, dict) or set(content) != {"application/json"}:
        raise IntegrationError("OPENAPI_OPERATION", f"{label} must use only application/json.")
    media = content["application/json"]
    if not isinstance(media, dict) or set(media) - {"schema", "example", "examples"} or "schema" not in media:
        raise IntegrationError("OPENAPI_OPERATION", f"{label} needs one inline JSON schema.")
    schema = media["schema"]
    _validate_schema(schema)
    if schema["type"] != "object":
        raise IntegrationError("OPENAPI_OPERATION", f"{label} schema must be an object.")
    return copy.deepcopy(schema)


def inspect_openapi(document: Any) -> dict[str, Any]:
    """Inspect a bounded, fully inlined OpenAPI 3.1 JSON document.

    The result contains *unclassified review candidates*.  It never creates a
    connection, capability or executable adapter operation, and it deliberately
    does not infer effect or retry safety from HTTP methods.
    """

    if not isinstance(document, dict) or _size(document) > 2_000_000:
        raise IntegrationError("OPENAPI_BOUNDS", "Provide one bounded in-memory OpenAPI JSON object.")
    _walk_forbidden_refs(document)
    version = document.get("openapi")
    if not isinstance(version, str) or not re.fullmatch(r"3\.1(?:\.\d+)?", version):
        raise IntegrationError("OPENAPI_VERSION", "Only OpenAPI 3.1 documents are supported.")
    info = document.get("info")
    if not isinstance(info, dict) or not isinstance(info.get("title"), str) or not isinstance(info.get("version"), str):
        raise IntegrationError("OPENAPI_SCHEMA", "OpenAPI info needs a title and version.")
    servers = document.get("servers")
    if not isinstance(servers, list) or len(servers) != 1 or not isinstance(servers[0], dict) or set(servers[0]) - {"url", "description"}:
        raise IntegrationError("OPENAPI_SERVER", "Provide exactly one fixed HTTPS server.")
    server_raw = servers[0].get("url")
    if not isinstance(server_raw, str) or "{" in server_raw or "}" in server_raw:
        raise IntegrationError("OPENAPI_SERVER", "OpenAPI server variables are unsupported.")
    server_url = _normalise_base_url(server_raw, False)
    security_schemes = _openapi_security_schemes(document)
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths or len(paths) > 200:
        raise IntegrationError("OPENAPI_BOUNDS", "OpenAPI paths must be a nonempty bounded object.")
    top_security = document.get("security", [])
    candidates: list[dict[str, Any]] = []
    operation_ids: set[str] = set()
    for raw_path, path_item in paths.items():
        if (
            not isinstance(raw_path, str) or not raw_path.startswith("/") or len(raw_path) > 2000
            or "?" in raw_path or "#" in raw_path or "\\" in raw_path
            or not isinstance(path_item, dict)
        ):
            raise IntegrationError("OPENAPI_OPERATION", "OpenAPI paths must be safe absolute templates.")
        unsupported_path_fields = set(path_item) - ({method.lower() for method in _METHODS} | {"summary", "description", "parameters"})
        if unsupported_path_fields:
            raise IntegrationError("OPENAPI_UNSUPPORTED", "The OpenAPI path item uses unsupported features.")
        for method_name, operation in path_item.items():
            method = method_name.upper()
            if method not in _METHODS:
                continue
            if not isinstance(operation, dict):
                raise IntegrationError("OPENAPI_OPERATION", "Each OpenAPI operation must be an object.")
            unsupported = set(operation) - {
                "operationId", "summary", "description", "parameters", "requestBody", "responses",
                "security", "deprecated", "tags",
            }
            if unsupported:
                raise IntegrationError("OPENAPI_UNSUPPORTED", "An OpenAPI operation uses unsupported features.")
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not _IDENT.fullmatch(operation_id) or operation_id in operation_ids:
                raise IntegrationError("OPENAPI_OPERATION", "Every operation needs a unique safe operationId.")
            operation_ids.add(operation_id)
            properties, required, path_names, query_names = _openapi_parameters(
                path_item.get("parameters"), operation.get("parameters")
            )
            body_names: list[str] = []
            if "requestBody" in operation:
                body_schema = _openapi_json_schema(operation["requestBody"], "OpenAPI request body")
                if set(properties) & set(body_schema.get("properties", {})):
                    raise IntegrationError("OPENAPI_OPERATION", "Request-body fields cannot collide with parameters.")
                body_names = list(body_schema.get("properties", {}))
                properties.update(copy.deepcopy(body_schema.get("properties", {})))
                if operation["requestBody"].get("required") is True:
                    required.extend(body_schema.get("required", []))
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                raise IntegrationError("OPENAPI_OPERATION", "Each operation needs a JSON success response.")
            success_key = next((key for key in ("200", "201", "202") if key in responses), None)
            if success_key is None:
                raise IntegrationError("OPENAPI_OPERATION", "A supported 200, 201 or 202 JSON response is required.")
            output_schema = _openapi_json_schema(responses[success_key], "OpenAPI success response")
            security = operation.get("security", top_security)
            if not isinstance(security, list) or len(security) > 20:
                raise IntegrationError("OPENAPI_SECURITY", "Operation security requirements must be bounded.")
            alternatives = []
            for alternative in security:
                if not isinstance(alternative, dict) or set(alternative) - set(security_schemes):
                    raise IntegrationError("OPENAPI_SECURITY", "Operation security names an unsupported scheme.")
                if any(not isinstance(scopes, list) or any(not isinstance(scope, str) for scope in scopes) for scopes in alternative.values()):
                    raise IntegrationError("OPENAPI_SECURITY", "Operation security scopes must be arrays of strings.")
                alternatives.append(copy.deepcopy(alternative))
            template = raw_path.lstrip("/")
            if set(_PLACEHOLDER.findall(template)) != set(path_names):
                raise IntegrationError("OPENAPI_OPERATION", "Path placeholders must exactly match declared parameters.")
            candidate = {
                "candidateId": f"rest.{operation_id}", "sourceOperationId": operation_id,
                "description": operation.get("description") or operation.get("summary") or f"Reviewed {operation_id} operation.",
                "method": method, "pathTemplate": template, "serverBaseUrl": server_url,
                "inputSchema": _obj(properties, list(dict.fromkeys(required))),
                "outputSchema": output_schema, "pathParameters": path_names,
                "queryParameters": query_names, "bodyParameters": body_names,
                "securityAlternatives": alternatives, "reviewState": "unclassified",
                "requiredReviewFields": ["effect", "requiredScopes", "approvalRequired", "idempotency", "maxResponseBytes"],
            }
            candidate["candidateHash"] = _hash(candidate)
            candidates.append(candidate)
    if not candidates:
        raise IntegrationError("OPENAPI_OPERATION", "The document contains no supported operations.")
    return {
        "status": "review_required", "openapiVersion": version,
        "title": info["title"], "sourceVersion": info["version"], "serverBaseUrl": server_url,
        "securitySchemes": security_schemes, "candidates": candidates,
        "activationWarning": "No candidate is executable until a trusted reviewer classifies effect, approval, scopes, idempotency and response limits.",
    }


def activate_openapi_candidate(candidate: Any, review: Any) -> dict[str, Any]:
    """Apply an explicit trusted review and return one normalised operation."""

    candidate_fields = {
        "candidateId", "sourceOperationId", "description", "method", "pathTemplate", "serverBaseUrl",
        "inputSchema", "outputSchema", "pathParameters", "queryParameters", "bodyParameters",
        "securityAlternatives", "reviewState", "requiredReviewFields", "candidateHash",
    }
    candidate = _strict_keys(candidate, candidate_fields, candidate_fields, "OpenAPI candidate")
    expected_hash = _hash({key: value for key, value in candidate.items() if key != "candidateHash"})
    if candidate["reviewState"] != "unclassified" or candidate["candidateHash"] != expected_hash:
        raise IntegrationError("OPENAPI_CANDIDATE_CHANGED", "The inspected OpenAPI candidate changed before review.")
    review = _strict_keys(
        review,
        {"effect", "requiredScopes", "approvalRequired", "idempotency", "maxResponseBytes"},
        {"effect", "requiredScopes", "approvalRequired", "idempotency", "maxResponseBytes"},
        "OpenAPI classification",
    )
    operation = {
        "id": candidate["candidateId"], "version": "1.0.0", "description": candidate["description"],
        "effect": review["effect"], "inputSchema": copy.deepcopy(candidate["inputSchema"]),
        "outputSchema": copy.deepcopy(candidate["outputSchema"]),
        "requiredScopes": copy.deepcopy(review["requiredScopes"]),
        "approvalRequired": review["approvalRequired"],
        "binding": {
            "kind": "http", "method": candidate["method"], "pathTemplate": candidate["pathTemplate"],
            "pathParameters": copy.deepcopy(candidate["pathParameters"]),
            "queryParameters": copy.deepcopy(candidate["queryParameters"]),
            "bodyParameters": copy.deepcopy(candidate["bodyParameters"]),
            "fixedHeaders": {}, "fixedQuery": {}, "codec": "identity.v1",
        },
        "idempotency": copy.deepcopy(review["idempotency"]),
        "maxResponseBytes": review["maxResponseBytes"],
    }
    return _normalise_operation(operation, "https-json")


def _obj(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(required), "additionalProperties": False}


def _string(description: str, maximum: int = 1000) -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": maximum, "description": description}


def _integer(description: str, minimum: int = 1, maximum: int = 1000) -> dict[str, Any]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum, "description": description}


def _array(items: Mapping[str, Any], maximum: int = 100) -> dict[str, Any]:
    return {"type": "array", "items": dict(items), "maxItems": maximum}


def _read_policy() -> dict[str, str]:
    return {"classification": "read_only", "retry": "safe", "reconciliation": "not_applicable"}


def _write_policy(*, keyed: bool = False, operation_key: str = "host-ledger-only") -> dict[str, str]:
    return {
        "classification": "provider_keyed" if keyed else "non_idempotent",
        "retry": "safe" if keyed else "reconcile_before_retry",
        "reconciliation": "provider_status" if keyed else "manual",
        "operationKey": operation_key,
    }


def _http_operation(
    ident: str, description: str, effect: str, method: str, path: str,
    input_schema: Mapping[str, Any], output_schema: Mapping[str, Any], scopes: Sequence[str],
    *, path_parameters: Sequence[str] = (), query_parameters: Sequence[str] = (),
    body_parameters: Sequence[str] = (), durability: Mapping[str, Any] | None = None,
    codec: str = "identity.v1", fixed_query: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": ident, "version": "1.0.0", "description": description, "effect": effect,
        "inputSchema": copy.deepcopy(dict(input_schema)), "outputSchema": copy.deepcopy(dict(output_schema)),
        "requiredScopes": list(scopes), "approvalRequired": effect == "write",
        "binding": {
            "kind": "http", "method": method, "pathTemplate": path,
            "pathParameters": list(path_parameters), "queryParameters": list(query_parameters),
            "bodyParameters": list(body_parameters), "fixedHeaders": {},
            "fixedQuery": copy.deepcopy(dict(fixed_query or {})), "codec": codec,
        },
        "idempotency": copy.deepcopy(dict(durability or (_read_policy() if effect == "read" else _write_policy()))),
        "maxResponseBytes": 1_000_000,
    }


_ISSUE = _obj({"key": _string("Stable issue key", 100), "summary": _string("Issue summary", 1000), "status": _string("Workflow status", 200)}, ["key", "summary", "status"])
_MESSAGE = _obj({"id": _string("Message ID", 200), "text": {"type": "string", "maxLength": 10000, "description": "Message text"}, "authorId": _string("Author ID", 200), "createdAt": _string("Provider timestamp", 200)}, ["id", "text", "authorId", "createdAt"])
_PAGE = _obj({"id": _string("Page ID", 200), "title": _string("Page title", 1000), "version": _integer("Page version", 1, 1_000_000), "url": _string("Canonical page URL", 2000)}, ["id", "title", "version", "url"])

_COMMON_DEFAULTS = {
    "timeouts": {"connectMs": 5_000, "readMs": 20_000, "totalMs": 30_000},
    "rateLimit": {"maxRequests": 60, "windowSeconds": 60, "maxConcurrent": 4},
    "retryPolicy": {"maxAttempts": 3, "baseDelayMs": 250, "maxDelayMs": 5_000, "retryStatusCodes": [429, 500, 502, 503, 504]},
}

_SLACK_OPERATIONS = [
    _http_operation(
        "slack.auth.test", "Verify the configured Slack identity without reading workspace content.",
        "read", "POST", "auth.test", _obj({}, []),
        _obj({"teamId": _string("Slack team ID", 200), "userId": _string("Authenticated Slack user ID", 200), "url": _string("Slack workspace URL", 2000)}, ["teamId", "userId", "url"]),
        [], codec="slack.auth_test.v1",
    ),
    _http_operation(
        "slack.conversations.history", "Read a bounded page of messages from one permitted Slack channel.",
        "read", "GET", "conversations.history",
        _obj({"channel": _string("Slack channel ID", 100), "limit": _integer("Maximum messages", 1, 200)}, ["channel", "limit"]),
        _obj({"messages": _array(_MESSAGE, 200), "hasMore": {"type": "boolean"}}, ["messages", "hasMore"]),
        ["channels:history"], query_parameters=["channel", "limit"], codec="slack.conversations_history.v1",
    ),
    _http_operation(
        "slack.chat.post_message", "Post one reviewed message to a permitted Slack channel.",
        "write", "POST", "chat.postMessage",
        _obj({"channel": _string("Slack channel ID", 100), "text": _string("Message text", 40000)}, ["channel", "text"]),
        _obj({"messageId": _string("Created message ID", 200), "channelId": _string("Destination channel ID", 100), "accepted": {"type": "boolean"}}, ["messageId", "channelId", "accepted"]),
        ["chat:write"], body_parameters=["channel", "text"], durability=_write_policy(), codec="slack.chat_post_message.v1",
    ),
]

_JIRA_OPERATIONS = [
    _http_operation(
        "jira.users.myself", "Verify the configured Jira principal without changing tenant state.",
        "read", "GET", "myself", _obj({}, []),
        _obj({"accountId": _string("Atlassian account ID", 200), "displayName": _string("Account display name", 500), "active": {"type": "boolean"}}, ["accountId", "displayName", "active"]),
        ["read:jira-user"], codec="jira.myself.v1",
    ),
    _http_operation(
        "jira.issues.search", "Search Jira issues with one administrator-authorized JQL query.",
        "read", "GET", "search/jql",
        _obj({"jql": _string("JQL query", 4000), "maxResults": _integer("Maximum issues", 1, 100)}, ["jql", "maxResults"]),
        _obj({"issues": _array(_ISSUE, 100), "hasMore": {"type": "boolean"}}, ["issues", "hasMore"]),
        ["read:jira-work"], query_parameters=["jql", "maxResults"], codec="jira.search.v1",
    ),
    _http_operation(
        "jira.issues.get", "Read one Jira issue by its stable key.", "read", "GET", "issue/{issueKey}",
        _obj({"issueKey": _string("Jira issue key", 100)}, ["issueKey"]), _ISSUE,
        ["read:jira-work"], path_parameters=["issueKey"], codec="jira.issue.v1",
    ),
    _http_operation(
        "jira.issues.create", "Create one reviewed Jira issue and capture its provider receipt.",
        "write", "POST", "issue",
        _obj({"projectKey": _string("Jira project key", 100), "issueType": _string("Issue type", 100), "summary": _string("Issue summary", 1000), "description": _string("Issue description", 30000)}, ["projectKey", "issueType", "summary", "description"]),
        _obj({"key": _string("Created issue key", 100), "id": _string("Provider issue ID", 100), "url": _string("Created issue URL", 2000)}, ["key", "id", "url"]),
        ["write:jira-work"], body_parameters=["projectKey", "issueType", "summary", "description"], durability=_write_policy(), codec="jira.create_issue.v1",
    ),
]

_CONFLUENCE_OPERATIONS = [
    _http_operation(
        "confluence.spaces.health", "Verify that the configured principal can read Confluence spaces.",
        "read", "GET", "spaces",
        _obj({}, []),
        _obj({"accessible": {"type": "boolean"}, "spaceCount": _integer("Visible spaces in the probe", 0, 1)}, ["accessible", "spaceCount"]),
        ["read:space:confluence"], codec="confluence.spaces_health.v1", fixed_query={"limit": 1},
    ),
    _http_operation(
        "confluence.pages.get", "Read one permitted Confluence page and its current version.",
        "read", "GET", "pages/{pageId}",
        _obj({"pageId": _string("Confluence page ID", 100)}, ["pageId"]), _PAGE,
        ["read:page:confluence"], path_parameters=["pageId"], codec="confluence.page.v1",
    ),
    _http_operation(
        "confluence.pages.list", "List a bounded set of pages in one permitted space.",
        "read", "GET", "pages",
        _obj({"spaceId": _string("Confluence space ID", 100), "limit": _integer("Maximum pages", 1, 100)}, ["spaceId", "limit"]),
        _obj({"pages": _array(_PAGE, 100)}, ["pages"]),
        ["read:page:confluence"], query_parameters=["spaceId", "limit"], codec="confluence.pages.v1",
    ),
    _http_operation(
        "confluence.pages.create", "Create one reviewed Confluence page in an authorized space.",
        "write", "POST", "pages",
        _obj({"spaceId": _string("Confluence space ID", 100), "title": _string("Page title", 1000), "body": _string("Storage-format page body", 100000)}, ["spaceId", "title", "body"]),
        _PAGE, ["write:page:confluence"], body_parameters=["spaceId", "title", "body"], durability=_write_policy(), codec="confluence.create_page.v1",
    ),
]

_WEBHOOK_OPERATIONS = [
    _http_operation(
        "webhook.events.deliver", "Deliver one exact reviewed JSON event to an allowlisted webhook.",
        "write", "POST", "events",
        _obj({"eventType": _string("Stable event type", 200), "subjectId": _string("Stable business object ID", 200), "payloadJson": _string("Canonical JSON event payload", 100000)}, ["eventType", "subjectId", "payloadJson"]),
        _obj({"accepted": {"type": "boolean"}, "receiptId": _string("Receiver receipt", 200)}, ["accepted", "receiptId"]),
        [], body_parameters=["eventType", "subjectId", "payloadJson"], durability=_write_policy(),
    ),
]

_MCP_OPERATIONS = [
    {
        "id": "mcp.catalog.list_tools", "version": "1.0.0",
        "description": "List MCP tool metadata for administrator review; discovered tools are not automatically authorized.",
        "effect": "read", "inputSchema": _obj({}, []),
        "outputSchema": _obj({"tools": _array(_obj({"name": _string("Tool name", 200), "description": _string("Tool description", 2000)}, ["name", "description"]), 200)}, ["tools"]),
        "requiredScopes": [], "approvalRequired": False,
        "binding": {"kind": "mcp-list-tools"},
        "idempotency": _read_policy(), "maxResponseBytes": 1_000_000,
    }
]

_PROVIDER_DESCRIPTORS = [
    {
        "id": "slack", "name": "Slack", "description": "Slack Web API descriptor with bounded channel reads and reviewed message writes.",
        "category": "collaboration", "docsUrl": "https://api.slack.com/web",
        "transport": "https-json", "adapterId": "axiom.strict-http", "authModes": ["bearer", "oauth2"],
        "authSlotLabels": {"token": "Bot or user token", "credential": "OAuth access-token reference"},
        "secretRefSchemes": ["env"], "setupFields": ["baseUrls", "auth.mode", "auth.secretRefs", "auth.scopes"],
        "healthOperationId": "slack.auth.test", "setupCapable": True,
        "baseUrlExamples": ["https://slack.com/api/"], "configurationState": "descriptor-only",
        "operationTemplates": _SLACK_OPERATIONS, "defaults": _COMMON_DEFAULTS,
    },
    {
        "id": "jira-cloud", "name": "Jira Cloud", "description": "Atlassian Jira Cloud descriptor; configure one exact tenant API base URL.",
        "category": "project-management", "docsUrl": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
        "transport": "https-json", "adapterId": "axiom.strict-http", "authModes": ["basic", "oauth2"],
        "authSlotLabels": {"username": "Atlassian account email reference", "password": "API token reference", "credential": "OAuth access-token reference"},
        "secretRefSchemes": ["env"], "setupFields": ["baseUrls", "auth.mode", "auth.secretRefs", "auth.scopes"],
        "healthOperationId": "jira.users.myself", "setupCapable": True,
        "baseUrlExamples": ["https://tenant.atlassian.net/rest/api/3/"], "configurationState": "descriptor-only",
        "operationTemplates": _JIRA_OPERATIONS, "defaults": _COMMON_DEFAULTS,
    },
    {
        "id": "confluence-cloud", "name": "Confluence Cloud", "description": "Atlassian Confluence Cloud descriptor; configure one exact tenant API base URL.",
        "category": "knowledge-management", "docsUrl": "https://developer.atlassian.com/cloud/confluence/rest/v2/",
        "transport": "https-json", "adapterId": "axiom.strict-http", "authModes": ["basic", "oauth2"],
        "authSlotLabels": {"username": "Atlassian account email reference", "password": "API token reference", "credential": "OAuth access-token reference"},
        "secretRefSchemes": ["env"], "setupFields": ["baseUrls", "auth.mode", "auth.secretRefs", "auth.scopes"],
        "healthOperationId": "confluence.spaces.health", "setupCapable": True,
        "baseUrlExamples": ["https://tenant.atlassian.net/wiki/api/v2/"], "configurationState": "descriptor-only",
        "operationTemplates": _CONFLUENCE_OPERATIONS, "defaults": _COMMON_DEFAULTS,
    },
    {
        "id": "generic-rest", "name": "REST / OpenAPI", "description": "Inspect OpenAPI 3.1 contracts and promote only developer-reviewed strict JSON operations under exact allowlisted base URLs.",
        "category": "developer", "docsUrl": "https://spec.openapis.org/oas/v3.1.0",
        "transport": "https-json", "adapterId": "axiom.strict-http", "authModes": ["none", "bearer", "api_key_header", "basic", "oauth2"],
        "authSlotLabels": {"token": "Bearer token reference", "apiKey": "API key reference", "username": "Username reference", "password": "Password reference", "credential": "OAuth access-token reference"},
        "secretRefSchemes": ["env"], "setupFields": ["baseUrls", "auth.mode", "auth.secretRefs", "auth.scopes", "operations"],
        "healthOperationId": None, "setupCapable": True,
        "baseUrlExamples": [], "configurationState": "descriptor-only",
        "operationTemplates": [
            _http_operation(
                "rest.resources.get", "Example normalized read operation; replace during developer review.",
                "read", "GET", "resources/{resourceId}",
                _obj({"resourceId": _string("Resource ID", 200)}, ["resourceId"]),
                _obj({"id": _string("Resource ID", 200), "state": _string("Resource state", 200)}, ["id", "state"]),
                [], path_parameters=["resourceId"],
            )
        ], "defaults": _COMMON_DEFAULTS,
    },
    {
        "id": "webhook", "name": "Outbound Webhook", "description": "Reviewed JSON event delivery to one exact allowlisted receiver.",
        "category": "event-delivery", "docsUrl": None,
        "transport": "webhook", "adapterId": "axiom.strict-http", "authModes": ["none", "bearer", "api_key_header", "hmac_sha256"],
        "authSlotLabels": {"token": "Bearer token reference", "apiKey": "API key reference", "key": "HMAC signing-key reference"},
        "secretRefSchemes": ["env"], "setupFields": ["baseUrls", "auth.mode", "auth.secretRefs", "operations"],
        "healthOperationId": None, "setupCapable": True,
        "baseUrlExamples": [], "configurationState": "descriptor-only",
        "operationTemplates": _WEBHOOK_OPERATIONS, "defaults": _COMMON_DEFAULTS,
    },
    {
        "id": "mcp", "name": "MCP server", "description": "Streamable HTTP MCP descriptor. Discovered tools require separate trusted effect and schema registration.",
        "category": "tool-protocol", "docsUrl": "https://modelcontextprotocol.io/specification/2026-07-28/basic/transports",
        "transport": "mcp-streamable-http", "adapterId": "axiom.strict-mcp", "authModes": ["none", "bearer", "oauth2"],
        "authSlotLabels": {"token": "Bearer token reference", "credential": "OAuth access-token reference"},
        "secretRefSchemes": ["env"], "setupFields": ["baseUrls", "auth.mode", "auth.secretRefs", "operations"],
        "healthOperationId": "mcp.catalog.list_tools", "setupCapable": True,
        "baseUrlExamples": [], "configurationState": "descriptor-only",
        "operationTemplates": _MCP_OPERATIONS, "defaults": _COMMON_DEFAULTS,
    },
]

_PROVIDER_INDEX = {item["id"]: item for item in _PROVIDER_DESCRIPTORS}


__all__ = [
    "ADAPTER_API_VERSION", "CAPABILITY_SCHEMA_VERSION", "CONNECTION_SCHEMA_VERSION",
    "AdapterRegistry", "AdapterResult", "HttpExecutor", "InMemoryRateLimiter",
    "IntegrationAdapter", "IntegrationError", "McpClient", "PreparedIntegrationCall",
    "RetryAdvice", "SecretResolver", "SensitiveHttpRequest", "StrictHttpAdapter",
    "StrictMcpAdapter", "TransportResponse", "capability_contracts", "capability_id", "connection_template",
    "activate_openapi_candidate", "inspect_openapi", "normalize_connection_spec", "prepare_call", "provider_descriptor", "provider_descriptors",
    "public_connection", "reconciliation_directive", "retry_advice", "validate_outbound_url",
    "validate_value", "verify_prepared_call",
]
