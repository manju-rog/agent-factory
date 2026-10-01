import pathlib
import sys
import unittest

APP = pathlib.Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from capability_runtime import (  # noqa: E402
    CapabilityAdapterError,
    CapabilityExecution,
    CapabilityRuntime,
)


class _Adapter:
    def execute(self, action, context):
        return CapabilityExecution({"tool": action["toolId"]}, {"purpose": context.get("purpose")})

    def reconcile(self, action, context):
        return CapabilityExecution({"reconciled": True}, {"operationKey": action["operationKey"]})


def action(adapter_id="sandbox-mirror.atlas"):
    return {
        "toolId": "demo.read", "toolVersion": "1.0.0",
        "effect": "read", "arguments": {}, "operationKey": "op-1",
        "actionTarget": {
            "toolId": "demo.read", "toolVersion": "1.0.0",
            "adapterBinding": {
                "adapterId": adapter_id, "adapterVersion": "1.0.0",
                "operation": "demo.read", "transport": "in-process",
            },
        },
    }


class CapabilityRuntimeTests(unittest.TestCase):
    def test_exact_registration_executes(self):
        runtime = CapabilityRuntime()
        runtime.register("sandbox-mirror.atlas", _Adapter(), "1.0.0")
        result = runtime.execute(action(), {"purpose": "normal"})
        self.assertEqual({"tool": "demo.read"}, result.output)
        self.assertEqual("normal", result.receipt["purpose"])

    def test_named_namespace_registration_executes(self):
        runtime = CapabilityRuntime()
        runtime.register("sandbox-mirror.*", _Adapter(), "1.0.0")
        self.assertEqual("demo.read", runtime.execute(action()).output["tool"])

    def test_unknown_or_non_in_process_binding_fails_closed(self):
        runtime = CapabilityRuntime()
        runtime.register("sandbox-mirror.atlas", _Adapter(), "1.0.0")
        with self.assertRaises(CapabilityAdapterError) as caught:
            runtime.execute(action("invented.adapter"))
        self.assertEqual("ADAPTER_NOT_REGISTERED", caught.exception.code)
        candidate = action()
        candidate["actionTarget"]["adapterBinding"]["transport"] = "shell"
        with self.assertRaises(CapabilityAdapterError):
            runtime.execute(candidate)

    def test_reconciliation_is_explicit(self):
        runtime = CapabilityRuntime()
        runtime.register("sandbox-mirror.atlas", _Adapter(), "1.0.0")
        candidate = action()
        candidate.update(effect="write")
        self.assertTrue(runtime.is_reconcilable(candidate))
        self.assertEqual({"reconciled": True}, runtime.reconcile(candidate).output)

    def test_duplicate_registration_is_rejected(self):
        runtime = CapabilityRuntime()
        runtime.register("sandbox-mirror.atlas", _Adapter(), "1.0.0")
        with self.assertRaises(ValueError):
            runtime.register("sandbox-mirror.atlas", _Adapter(), "1.0.0")

    def test_operation_and_versions_must_match_the_frozen_registered_target(self):
        runtime = CapabilityRuntime()
        runtime.register("sandbox-mirror.atlas", _Adapter(), "1.0.0")
        cases = {
            "operation": lambda candidate: candidate["actionTarget"][
                "adapterBinding"
            ].update(operation="demo.write"),
            "target tool id": lambda candidate: candidate["actionTarget"].update(
                toolId="demo.write"
            ),
            "target tool version": lambda candidate: candidate[
                "actionTarget"
            ].update(toolVersion="2.0.0"),
            "registered adapter version": lambda candidate: candidate[
                "actionTarget"
            ]["adapterBinding"].update(adapterVersion="2.0.0"),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                candidate = action()
                mutate(candidate)
                with self.assertRaises(CapabilityAdapterError) as caught:
                    runtime.execute(candidate)
                self.assertEqual("ADAPTER_BINDING_INVALID", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
