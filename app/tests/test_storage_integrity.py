import copy
import json
import math
import os
import sqlite3
import tempfile
import unittest

from domain import template_hashes
from server import APIError, SCHEMA_VERSION, Store, USERS, digest


AUTHOR = USERS[0]


class StorageIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "axiom.db")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_store_rejects_non_finite_run_input_atomically_and_recovers(self):
        store = Store(self.db_path)
        try:
            baseline = store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            for value in (math.nan, math.inf, -math.inf, "\ud800"):
                with self.subTest(value=repr(value)):
                    with self.assertRaises(APIError) as raised:
                        store.atomic(
                            store.create_run,
                            {
                                "templateId": "customer-resolution",
                                "mode": "simulation",
                                "input": {"invalidNumber": value},
                            },
                            AUTHOR,
                        )
                    self.assertEqual(raised.exception.status, 400)
                    self.assertEqual(raised.exception.code, "INVALID_JSON_VALUE")
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                        baseline,
                    )

            healthy = store.atomic(
                store.create_run,
                {
                    "templateId": "customer-resolution",
                    "mode": "simulation",
                    "input": {"customerId": "C-STRICT-JSON"},
                },
                AUTHOR,
            )
            self.assertEqual(healthy["status"], "queued")
            self.assertEqual(
                store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                baseline + 1,
            )
        finally:
            store.close()

    def test_legacy_non_strict_json_is_refused_before_schema_changes(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO runs(id,data) VALUES (?,?)",
            ("run-bad-json", '{"id":"run-bad-json","value":NaN}'),
        )
        connection.execute("PRAGMA user_version=7")
        connection.commit()
        before = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "runs record 1"):
            Store(self.db_path)

        check = sqlite3.connect(self.db_path)
        try:
            after = {
                row[0] for row in check.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertEqual(before, after)
            self.assertEqual(7, check.execute("PRAGMA user_version").fetchone()[0])
        finally:
            check.close()

    def test_strict_custom_input_schema_receives_no_hidden_default_fields(self):
        store = Store(self.db_path)
        try:
            template = store.get("templates", "customer-resolution")
            template["inputSchema"] = {
                "type": "object",
                "properties": {"foo": {"type": "string"}},
                "required": ["foo"],
                "additionalProperties": False,
            }
            store.put("templates", template)
            run = store.atomic(
                store.create_run,
                {
                    "templateId": template["id"],
                    "mode": "simulation",
                    "input": {"foo": "ok"},
                },
                AUTHOR,
            )
            persisted = store.get("runs", run["id"])
            self.assertEqual({"foo": "ok"}, persisted["input"])
        finally:
            store.close()

    def test_legacy_effects_table_is_physically_rebuilt_and_remains_writable(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """
            CREATE TABLE effects (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """
        )
        legacy = {
            "id": "effect-legacy",
            "runId": "run-legacy",
            "nodeId": "ticket",
            "operationKey": "op-legacy",
            "state": "prepared",
            "transitions": [],
        }
        connection.execute(
            "INSERT INTO effects(id, data) VALUES (?, ?)",
            (legacy["id"], json.dumps(legacy)),
        )
        connection.commit()
        connection.close()

        store = Store(self.db_path)
        try:
            columns = {
                row["name"]: row
                for row in store.db.execute("PRAGMA table_info(effects)").fetchall()
            }
            self.assertTrue(
                {
                    "operation_generation",
                    "action_fingerprint",
                }.issubset(columns)
            )
            self.assertEqual(columns["operation_generation"]["notnull"], 1)
            self.assertEqual(columns["action_fingerprint"]["notnull"], 1)
            table_sql = store.db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='effects'"
            ).fetchone()["sql"]
            self.assertIn("reconciled", table_sql)
            indexes = {
                row["name"]: row["unique"]
                for row in store.db.execute("PRAGMA index_list(effects)").fetchall()
            }
            self.assertEqual(1, indexes["effects_operation_key"])

            migrated = json.loads(
                store.db.execute(
                    "SELECT data FROM effects WHERE id=?", ("effect-legacy",)
                ).fetchone()["data"]
            )
            self.assertEqual(migrated["operationGeneration"], 1)
            self.assertEqual(len(migrated["actionFingerprint"]), 64)

            second = {
                "id": "effect-new",
                "runId": "run-new",
                "nodeId": "ticket",
                "operationKey": "op-new",
                "operationGeneration": 3,
                "actionFingerprint": "a" * 64,
                "state": "prepared",
                "transitions": [],
            }
            store.atomic(store._save_effect, second)
            saved = json.loads(
                store.db.execute(
                    "SELECT data FROM effects WHERE id=?", ("effect-new",)
                ).fetchone()["data"]
            )
            self.assertEqual(saved, second)
        finally:
            store.close()

    def test_future_database_versions_are_refused_without_downgrade(self):
        cases = ("pragma", "migration-record")
        for case in cases:
            with self.subTest(case=case):
                path = os.path.join(self.tempdir.name, f"future-{case}.db")
                connection = sqlite3.connect(path)
                if case == "pragma":
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
                else:
                    connection.execute(
                        """
                        CREATE TABLE schema_migrations (
                            version INTEGER PRIMARY KEY,
                            name TEXT NOT NULL,
                            applied_at TEXT NOT NULL
                        )
                        """
                    )
                    connection.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                        (SCHEMA_VERSION + 1, "future", "2099-01-01T00:00:00Z"),
                    )
                connection.commit()
                before_tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                connection.close()

                with self.assertRaisesRegex(RuntimeError, "newer|future|version"):
                    Store(path)

                check = sqlite3.connect(path)
                try:
                    after_tables = {
                        row[0]
                        for row in check.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                    self.assertEqual(before_tables, after_tables)
                    if case == "pragma":
                        actual = check.execute("PRAGMA user_version").fetchone()[0]
                        self.assertEqual(actual, SCHEMA_VERSION + 1)
                    else:
                        actual = check.execute(
                            "SELECT MAX(version) FROM schema_migrations"
                        ).fetchone()[0]
                        self.assertEqual(actual, SCHEMA_VERSION + 1)
                finally:
                    check.close()

    def test_legacy_release_input_schema_is_rehashed_and_migration_is_idempotent(self):
        store = Store(self.db_path)
        try:
            template = store.get("templates", "customer-resolution")
            template.pop("inputSchema", None)
            release = template["versions"][0]
            snapshot = release["snapshot"]
            snapshot.pop("inputSchema", None)
            snapshot.pop("agentManifests", None)
            snapshot["agentVersions"] = {
                node["id"]: "1.1.0" for node in snapshot["nodes"]
            }

            legacy_hashes = template_hashes(Store._release_hash_basis(snapshot))
            snapshot.update(legacy_hashes)
            release.update(legacy_hashes)
            release["hash"] = digest(snapshot)
            immutable_release = copy.deepcopy(release)
            store.put("templates", template)
            for agent in store.all("agents"):
                agent["version"] = "1.1.0"
                store.put("agents", agent)
        finally:
            store.close()

        migrated_store = Store(self.db_path)
        try:
            migrated = migrated_store.get("templates", "customer-resolution")
            migrated_release = migrated["versions"][0]
            migrated_snapshot = migrated_release["snapshot"]
            compatibility = migrated["releaseCompatibility"]["1"]
            execution_snapshot = compatibility["snapshot"]
            expected_hashes = template_hashes(
                Store._release_hash_basis(execution_snapshot)
            )

            self.assertIn("inputSchema", migrated)
            self.assertEqual(immutable_release, migrated_release)
            self.assertNotIn("inputSchema", migrated_snapshot)
            self.assertIn("inputSchema", execution_snapshot)
            self.assertEqual(compatibility["sourceHash"], migrated_release["hash"])
            self.assertEqual(compatibility["hash"], digest(execution_snapshot))
            self.assertEqual(
                execution_snapshot["semanticHash"], expected_hashes["semanticHash"]
            )
            self.assertEqual(
                execution_snapshot["layoutHash"], expected_hashes["layoutHash"]
            )
            self.assertEqual(set(execution_snapshot["agentManifests"]), {
                node["id"] for node in execution_snapshot["nodes"]
            })
            verified = migrated_store._verified_release(migrated)
            self.assertEqual(execution_snapshot, verified["snapshot"])
            self.assertIn(
                "inputSchema",
                {item.get("label") for item in migrated_store.diff_template(migrated["id"])["changes"]},
            )
            first_pass = copy.deepcopy(migrated)
        finally:
            migrated_store.close()

        reopened = Store(self.db_path)
        try:
            second_pass = reopened.get("templates", "customer-resolution")
            self.assertEqual(second_pass, first_pass)
            reopened._verified_release(
                second_pass
            )
        finally:
            reopened.close()

    def test_legacy_release_migration_refuses_to_bless_a_tampered_snapshot(self):
        store = Store(self.db_path)
        try:
            template = store.get("templates", "customer-resolution")
            template.pop("inputSchema", None)
            release = template["versions"][0]
            snapshot = release["snapshot"]
            snapshot.pop("inputSchema", None)
            legacy_hashes = template_hashes(Store._release_hash_basis(snapshot))
            snapshot.update(legacy_hashes)
            release.update(legacy_hashes)
            release["hash"] = digest(snapshot)

            snapshot["description"] += " modified after legacy publication"
            store.put("templates", template)
        finally:
            store.close()

        with self.assertRaisesRegex(RuntimeError, "failed its stored hash check"):
            Store(self.db_path)

        check = sqlite3.connect(self.db_path)
        try:
            stored = json.loads(
                check.execute(
                    "SELECT data FROM templates WHERE id=?",
                    ("customer-resolution",),
                ).fetchone()[0]
            )
            self.assertNotIn("inputSchema", stored)
            self.assertIn(
                "modified after legacy publication",
                stored["versions"][0]["snapshot"]["description"],
            )
        finally:
            check.close()

    def test_fixture_run_rejects_a_tampered_release_without_partial_write(self):
        store = Store(self.db_path)
        try:
            template = store.get("templates", "customer-resolution")
            template["versions"][0]["snapshot"]["description"] += " tampered"
            store.put("templates", template)
            baseline = store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

            with self.assertRaises(APIError) as raised:
                store.atomic(
                    store.create_run,
                    {
                        "templateId": "customer-resolution",
                        "mode": "fixture",
                        "input": {"customerId": "C-TAMPER"},
                    },
                    AUTHOR,
                )
            self.assertEqual(raised.exception.status, 409)
            self.assertEqual(raised.exception.code, "RELEASE_INTEGRITY_FAILED")
            self.assertEqual(
                store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                baseline,
            )
        finally:
            store.close()

    def test_fixture_release_is_bound_to_its_template_and_version(self):
        store = Store(self.db_path)
        try:
            source = store.get("templates", "customer-resolution")
            foreign = copy.deepcopy(source)
            foreign["id"] = "foreign-template"
            store.put("templates", foreign)
            baseline = store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

            with self.assertRaises(APIError) as raised:
                store.atomic(
                    store.create_run,
                    {
                        "templateId": foreign["id"],
                        "mode": "fixture",
                        "input": {"customerId": "C-CROSS-BIND"},
                    },
                    AUTHOR,
                )
            self.assertEqual(raised.exception.code, "RELEASE_INTEGRITY_FAILED")
            self.assertEqual(
                store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                baseline,
            )
        finally:
            store.close()

    def test_run_resolves_its_embedded_agent_manifest_not_the_live_registry(self):
        store = Store(self.db_path)
        try:
            template = store.get("templates", "customer-resolution")
            pinned = copy.deepcopy(
                template["versions"][0]["snapshot"]["agentManifests"]["ticket"]
            )
            live = store.get("agents", "ticket")
            live["version"] = "99.0.0"
            live["inputSchema"] = {
                "type": "object",
                "properties": {"impossible": {"type": "string"}},
                "required": ["impossible"],
                "additionalProperties": False,
            }
            store.put("agents", live)

            public = store.atomic(
                store.create_run,
                {"templateId": "customer-resolution", "mode": "fixture"},
                AUTHOR,
            )
            run = store.get("runs", public["id"])

            _, _, resolved = store._definition(run, "ticket")
            self.assertEqual(pinned, resolved)
            self.assertNotEqual(live["version"], resolved["version"])
        finally:
            store.close()

    def test_historical_run_without_resolvable_manifest_fails_closed(self):
        store = Store(self.db_path)
        try:
            public = store.atomic(
                store.create_run,
                {"templateId": "customer-resolution", "mode": "fixture"},
                AUTHOR,
            )
            run = store.get("runs", public["id"])
            run["_snapshot"].pop("agentManifests")
            run["_snapshot"]["agentVersions"]["intake"] = "0.0.0"
            store.put("runs", run)
        finally:
            store.close()

        reopened = Store(self.db_path)
        try:
            historical = reopened.get("runs", public["id"])
            with self.assertRaises(APIError) as raised:
                reopened._definition(historical, "intake")
            self.assertEqual("RUN_SNAPSHOT_INTEGRITY_FAILED", raised.exception.code)
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
