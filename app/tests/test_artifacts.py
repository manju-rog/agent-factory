"""Bounded local task attachment ingestion and redaction contracts."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import APIError, Store, USERS, encode


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


class TaskArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "artifacts.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    @staticmethod
    def attachment(name, mime_type, content):
        return {"name": name, "mimeType": mime_type,
                "contentBase64": base64.b64encode(content).decode("ascii")}

    def create(self, artifacts):
        return self.call("create_run", {
            "templateId": "customer-resolution", "mode": "fixture", "scenario": "happy",
            "artifacts": artifacts,
        }, CONTRIBUTOR)

    def test_attachment_is_hashed_persisted_and_redacted_from_views(self):
        content = b'{"case":"A-42","note":"untrusted task content"}'
        run = self.create([self.attachment("case.json", "application/json", content)])
        self.assertEqual(1, len(run["artifacts"]))
        metadata = run["artifacts"][0]
        self.assertEqual(hashlib.sha256(content).hexdigest(), metadata["sha256"])
        self.assertNotIn("contentBase64", metadata)
        self.assertNotIn(base64.b64encode(content).decode("ascii"), encode(run))

        self.store.close()
        self.store = Store(self.path, latency=0)
        restarted = self.store.public_run(self.store.get("runs", run["id"]), CONTRIBUTOR)
        self.assertEqual(metadata["sha256"], restarted["artifacts"][0]["sha256"])
        self.assertNotIn("contentBase64", restarted["artifacts"][0])

        for _ in range(5):
            self.store.tick()
        evidence = self.store.evidence(run["id"])
        self.assertEqual(metadata["sha256"], evidence["artifacts"][0]["sha256"])
        self.assertNotIn("contentBase64", encode(evidence))
        self.assertNotIn("untrusted task content", encode(evidence))

    def test_unsafe_or_malformed_attachments_fail_atomically(self):
        cases = (
            ([self.attachment("../escape.txt", "text/plain", b"x")], "ARTIFACT_NAME_INVALID"),
            ([self.attachment("script.html", "text/html", b"<script>x</script>")], "ARTIFACT_TYPE_UNSUPPORTED"),
            ([{"name": "bad.txt", "mimeType": "text/plain", "contentBase64": "%%%"}], "ARTIFACT_BASE64_INVALID"),
            ([self.attachment("bad.json", "application/json", b"{not-json")], "ARTIFACT_JSON_INVALID"),
            ([self.attachment("nan.json", "application/json", b'{"value":NaN}')], "ARTIFACT_JSON_INVALID"),
            ([self.attachment("infinity.json", "application/json", b'{"value":Infinity}')], "ARTIFACT_JSON_INVALID"),
            ([self.attachment("duplicate.json", "application/json", b'{"value":1,"value":2}')], "ARTIFACT_JSON_INVALID"),
            ([self.attachment("too-deep.json", "application/json", (b"[" * 1100) + b"0" + (b"]" * 1100))], "ARTIFACT_JSON_INVALID"),
            ([self.attachment("binary.txt", "text/plain", b"\xff")], "ARTIFACT_ENCODING_INVALID"),
            ([self.attachment("large.txt", "text/plain", b"a" * (256 * 1024 + 1))], "ARTIFACT_TOO_LARGE"),
        )
        initial_runs = self.store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        initial_artifacts = self.store.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        for artifacts, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(APIError) as denied:
                    self.create(artifacts)
                self.assertEqual(code, denied.exception.code)
                self.assertEqual(initial_runs, self.store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
                self.assertEqual(initial_artifacts, self.store.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])

    def test_duplicate_names_and_file_count_are_bounded(self):
        duplicate = [self.attachment("note.txt", "text/plain", b"a"),
                     self.attachment("NOTE.TXT", "text/plain", b"b")]
        with self.assertRaises(APIError) as denied:
            self.create(duplicate)
        self.assertEqual("ARTIFACT_NAME_DUPLICATE", denied.exception.code)

        six = [self.attachment(f"{index}.txt", "text/plain", b"x") for index in range(6)]
        with self.assertRaises(APIError) as denied:
            self.create(six)
        self.assertEqual("ARTIFACT_LIMIT", denied.exception.code)

    def test_task_start_idempotency_deduplicates_run_and_artifact_ingestion(self):
        body = {
            "templateId": "customer-resolution", "mode": "fixture", "scenario": "happy",
            "idempotencyKey": "task-start:case-42",
            "input": {"subject": "Idempotent task"},
            "artifacts": [self.attachment("note.txt", "text/plain", b"only once")],
        }
        first = self.call("create_run", body, CONTRIBUTOR)
        second = self.call("create_run", body, CONTRIBUTOR)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM run_requests").fetchone()[0])

        changed = {**body, "input": {"subject": "Different task"}}
        with self.assertRaises(APIError) as denied:
            self.call("create_run", changed, CONTRIBUTOR)
        self.assertEqual("IDEMPOTENCY_KEY_REUSED", denied.exception.code)

    def test_default_run_export_redacts_secret_like_and_raw_external_content(self):
        secrets = {
            "apiKey": "API-KEY-DO-NOT-EXPORT",
            "token": "TOKEN-DO-NOT-EXPORT",
            "credential": "CREDENTIAL-DO-NOT-EXPORT",
            "bearer": "BEARER-DO-NOT-EXPORT",
            "jwt": "JWT-DO-NOT-EXPORT",
        }
        run = self.call("create_run", {
            "templateId": "customer-resolution", "mode": "simulation", "scenario": "happy",
            "input": {
                **secrets,
                "externalContent": "private camel-case raw upload text",
                "external_content": {
                    "raw": "private snake-case raw upload text",
                    "instructions": ["do not export this object"],
                },
            },
        }, CONTRIBUTOR)
        for key in secrets:
            self.assertEqual("[REDACTED]", run["input"][key])

        restarted = self.store.public_run(
            self.store.get("runs", run["id"]), CONTRIBUTOR
        )
        for key in secrets:
            self.assertEqual("[REDACTED]", restarted["input"][key])

        exported = self.store.export_run(run["id"], CONTRIBUTOR)
        self.assertEqual("axiom.run-export.v1", exported["schemaVersion"])
        self.assertEqual(64, len(exported["manifestHash"]))
        encoded = encode(exported)
        for secret in secrets.values():
            self.assertNotIn(secret, encoded)
        self.assertNotIn("private camel-case raw upload text", encoded)
        self.assertNotIn("private snake-case raw upload text", encoded)
        for key in secrets:
            self.assertEqual("[REDACTED]", exported["run"]["input"][key])
        self.assertTrue(exported["run"]["input"]["externalContent"]["redacted"])
        self.assertTrue(exported["run"]["input"]["external_content"]["redacted"])
        evidence_hash_basis = {
            key: value for key, value in exported["evidence"].items()
            if key not in {"artifactHash", "hashAlgorithm"}
        }
        self.assertEqual(
            exported["evidence"]["artifactHash"],
            hashlib.sha256(encode(evidence_hash_basis).encode()).hexdigest(),
        )
        self.assertIn("Sensitive-looking values", exported["reportMarkdown"])


if __name__ == "__main__":
    unittest.main()
