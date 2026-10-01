"""Trusted in-process capability adapter registry for Axiom.

The adaptive planning kernel deliberately knows nothing about business domains.
This module provides the small host-side seam that maps a capability's frozen
``adapterBinding.adapterId`` to reviewed executable code.  It never evaluates
model-produced source code, URLs, module names, or shell commands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy


class CapabilityAdapterError(RuntimeError):
    """A bounded adapter failure that the agent runtime may safely record."""

    def __init__(self, code, message, *, retryable=False, outcome_unknown=False,
                 condition=None, receipt=None):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.retryable = bool(retryable)
        self.outcome_unknown = bool(outcome_unknown)
        self.condition = condition
        self.receipt = copy.deepcopy(receipt) if isinstance(receipt, dict) else {}


@dataclass(frozen=True)
class CapabilityExecution:
    """Schema-valid business output plus host-only execution evidence."""

    output: dict
    receipt: dict = field(default_factory=dict)
    provider: str = "in-process-adapter"
    external_effect: bool = False

    def __post_init__(self):
        if not isinstance(self.output, dict):
            raise TypeError("Capability output must be a JSON object.")
        if not isinstance(self.receipt, dict):
            raise TypeError("Capability receipt must be a JSON object.")


class CapabilityRuntime:
    """Resolve only explicitly registered in-process adapter bindings.

    Registrations may be exact (``sandbox-mirror.atlas``) or an explicit
    namespace prefix ending in ``*`` (``local-fixture.*``).  Duplicate and
    ambiguous registrations fail closed.
    """

    def __init__(self):
        self._registrations = []

    def register(self, adapter_id, adapter, version="1.0.0"):
        if not isinstance(adapter_id, str) or not adapter_id:
            raise ValueError("Adapter registrations need a stable non-empty ID.")
        if not isinstance(version, str) or not version:
            raise ValueError("Adapter registrations need a stable non-empty version.")
        if adapter_id == "*" or ("*" in adapter_id and not adapter_id.endswith(".*")):
            raise ValueError("Only a named namespace suffix wildcard is supported.")
        if any(item[0] == adapter_id for item in self._registrations):
            raise ValueError("The adapter ID is already registered: " + adapter_id)
        if not callable(getattr(adapter, "execute", None)):
            raise TypeError("Registered capability adapters must implement execute(action, context).")
        self._registrations.append((adapter_id, version, adapter))

    @staticmethod
    def binding(action):
        target = action.get("actionTarget", {}) if isinstance(action, dict) else {}
        binding = target.get("adapterBinding", {}) if isinstance(target, dict) else {}
        tool_id = action.get("toolId") if isinstance(action, dict) else None
        tool_version = action.get("toolVersion") if isinstance(action, dict) else None
        if (not isinstance(binding, dict)
                or binding.get("transport") != "in-process"
                or not isinstance(binding.get("adapterId"), str)
                or not isinstance(binding.get("adapterVersion"), str)
                or not isinstance(tool_id, str)
                or not isinstance(tool_version, str)
                or target.get("toolId") != tool_id
                or target.get("toolVersion") != tool_version
                or binding.get("operation") != tool_id):
            raise CapabilityAdapterError(
                "ADAPTER_BINDING_INVALID",
                "The frozen capability target, operation, version, and in-process adapter binding must match exactly.",
            )
        return binding

    def resolve(self, action):
        binding = self.binding(action)
        adapter_id = binding["adapterId"]
        matches = []
        for registered_id, registered_version, adapter in self._registrations:
            if registered_id.endswith(".*"):
                prefix = registered_id[:-1]
                if adapter_id.startswith(prefix):
                    matches.append((len(prefix), registered_version, adapter))
            elif registered_id == adapter_id:
                matches.append((10_000 + len(registered_id), registered_version, adapter))
        if not matches:
            raise CapabilityAdapterError(
                "ADAPTER_NOT_REGISTERED",
                "No trusted in-process adapter is registered for this frozen capability.",
            )
        matches.sort(key=lambda item: item[0], reverse=True)
        if len(matches) > 1 and matches[0][0] == matches[1][0]:
            raise CapabilityAdapterError(
                "ADAPTER_REGISTRATION_AMBIGUOUS",
                "More than one trusted adapter matches this capability binding.",
            )
        if matches[0][1] != binding["adapterVersion"]:
            raise CapabilityAdapterError(
                "ADAPTER_BINDING_INVALID",
                "The frozen capability adapter version is not registered by this runtime.",
            )
        return matches[0][2]

    def execute(self, action, context=None):
        result = self.resolve(action).execute(copy.deepcopy(action), context or {})
        if not isinstance(result, CapabilityExecution):
            raise TypeError("Capability adapters must return CapabilityExecution.")
        return result

    def recheck(self, action, context=None):
        adapter = self.resolve(action)
        method = getattr(adapter, "recheck", None)
        result = method(copy.deepcopy(action), context or {}) if callable(method) else adapter.execute(
            copy.deepcopy(action), {**(context or {}), "purpose": "precondition-recheck"}
        )
        if not isinstance(result, CapabilityExecution):
            raise TypeError("Capability rechecks must return CapabilityExecution.")
        return result

    def reconcile(self, action, context=None):
        adapter = self.resolve(action)
        method = getattr(adapter, "reconcile", None)
        if not callable(method):
            raise CapabilityAdapterError(
                "EFFECT_RECONCILIATION_REQUIRED",
                "This adapter has no trusted reconciliation operation.",
            )
        result = method(copy.deepcopy(action), context or {})
        if not isinstance(result, CapabilityExecution):
            raise TypeError("Capability reconciliation must return CapabilityExecution.")
        return result

    def is_reconcilable(self, action):
        try:
            return callable(getattr(self.resolve(action), "reconcile", None))
        except CapabilityAdapterError:
            return False


class LocalFixtureAdapter:
    """Adapter wrapper for the original deterministic demonstration fixtures."""

    def __init__(self, fixture_module):
        self.fixtures = fixture_module

    def execute(self, action, context=None):
        tool_id = action.get("toolId")
        arguments = copy.deepcopy(action.get("arguments", {}))
        if action.get("effect") == "write":
            output = self.fixtures.prepare_write_result(
                tool_id, arguments, action.get("operationKey")
            )
        else:
            output = self.fixtures.execute_read(tool_id, arguments)
        return CapabilityExecution(
            output=output,
            receipt={"provider": "local-fixture", "externalEffect": False},
            provider="local-fixture",
            external_effect=False,
        )

    def recheck(self, action, context=None):
        if action.get("effect") != "read":
            raise CapabilityAdapterError(
                "BUSINESS_PRECONDITION_UNAVAILABLE",
                "Only registered read capabilities can be rechecked.",
            )
        return self.execute(action, context)

    def reconcile(self, action, context=None):
        if action.get("effect") != "write":
            raise CapabilityAdapterError(
                "EFFECT_RECONCILIATION_REQUIRED",
                "Only a stable write operation can be reconciled.",
            )
        return self.execute(action, {**(context or {}), "purpose": "reconciliation"})
