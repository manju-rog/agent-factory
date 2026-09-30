import json
from pathlib import Path
import tempfile
import unittest

from agent_sdk import (
    AgentImplementation,
    AgentManifest,
    ExecutionContext,
    ManifestError,
    RestrictedConnector,
    scaffold_agent,
)


def manifest(**updates):
    value = {
        "manifestVersion": "axiom.agent-manifest.v1",
        "implementationKey": "supplier.lookup",
        "version": "1.0.0",
        "description": "Look up one supplier through an approved connector.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
        "outputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
        "configSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "capabilities": ["supplier.read"],
        "sideEffectClass": "read",
        "retrySafety": "idempotent",
        "evidenceKinds": ["source"],
        "fixtureScenarios": ["known-answer"],
        "resourceLimits": {"timeoutSeconds": 5},
        "authentication": "secret_reference",
    }
    value.update(updates)
    return value


class AgentSdkTests(unittest.TestCase):
    def test_manifest_is_versioned_and_hashed(self):
        parsed = AgentManifest.from_dict(manifest())
        self.assertEqual("supplier.lookup", parsed.implementation_key)
        self.assertEqual(64, len(parsed.content_hash))
        self.assertEqual(parsed.content_hash, AgentManifest.from_dict(parsed.to_dict()).content_hash)

    def test_manifest_fails_closed_for_unknown_schema_and_unsafe_write_claim(self):
        bad = manifest(sideEffectClass="write", retrySafety="safe")
        bad["inputSchema"]["pattern"] = ".*"
        with self.assertRaises(ManifestError) as failure:
            AgentManifest.from_dict(bad)
        self.assertEqual({"inputSchema", "retrySafety"}, {issue["field"].split(".")[0] for issue in failure.exception.issues})

    def test_execution_validates_both_boundaries_and_connector_scope(self):
        parsed = AgentManifest.from_dict(manifest())
        connector = RestrictedConnector({"supplier.get": lambda payload: {"name": "Northstar"}})
        context = ExecutionContext("w", "run", "node", "op", "2099-01-01T00:00:00Z", lambda: False, connector)
        implementation = AgentImplementation(parsed, lambda ctx, inputs, config: ctx.connector.call("supplier.get", inputs))
        self.assertEqual({"name": "Northstar"}, implementation.execute(context, {"id": "S-1"}, {}))
        with self.assertRaises(ValueError):
            implementation.execute(context, {}, {})
        with self.assertRaises(PermissionError):
            connector.call("ticket.create", {})
        broken = AgentImplementation(parsed, lambda *_: {"unexpected": True})
        with self.assertRaises(ValueError):
            broken.execute(context, {"id": "S-1"}, {})

    def test_scaffolder_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            package = scaffold_agent(Path(directory), "example.capability")
            self.assertEqual("example.capability", json.loads((package / "manifest.json").read_text())["implementationKey"])
            self.assertTrue((package / "implementation.py").is_file())
            with self.assertRaises(FileExistsError):
                scaffold_agent(Path(directory), "example.capability")
            with self.assertRaises(ValueError):
                scaffold_agent(Path(directory), "../escape")


if __name__ == "__main__":
    unittest.main()
