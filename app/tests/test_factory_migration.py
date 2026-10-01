"""Schema-9 to schema-11 preservation checks for the adaptive agent factory and gateway."""

import json
import os
import sqlite3
import tempfile
import unittest

from server import SCHEMA_VERSION, Store


class FactoryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "axiom-schema-9.db")

    def tearDown(self):
        self.tempdir.cleanup()

    def create_schema_nine_marker(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE outbox (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
                [
                    (version, f"schema-nine-marker-{version}", "2026-09-24T00:00:00Z")
                    for version in range(1, 10)
                ],
            )
            sentinel = {
                "id": "preserved-schema-nine-record",
                "kind": "migration-sentinel",
                "message": "This existing application record must survive the factory migration.",
            }
            connection.execute(
                "INSERT INTO outbox(id,data) VALUES (?,?)",
                (sentinel["id"], json.dumps(sentinel, separators=(",", ":"), sort_keys=True)),
            )
            connection.execute("PRAGMA user_version=9")
            connection.commit()
        finally:
            connection.close()

    def test_schema_nine_records_survive_factory_and_gateway_migrations_and_reopen(self):
        self.create_schema_nine_marker()
        self.assertEqual(12, SCHEMA_VERSION)

        store = Store(self.db_path, latency=0)
        try:
            self.assertEqual(
                12, store.db.execute("PRAGMA user_version").fetchone()[0]
            )
            migration = store.db.execute(
                "SELECT name FROM schema_migrations WHERE version=10"
            ).fetchone()
            self.assertIsNotNone(migration)
            gateway_migration = store.db.execute(
                "SELECT name FROM schema_migrations WHERE version=11"
            ).fetchone()
            self.assertIsNotNone(gateway_migration)
            simulation_migration = store.db.execute(
                "SELECT name FROM schema_migrations WHERE version=12"
            ).fetchone()
            self.assertIsNotNone(simulation_migration)
            tables = {
                row[0]
                for row in store.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertTrue({
                "agent_specs", "agent_runs", "simulation_worlds",
                "simulation_events", "simulation_operations",
            }.issubset(tables))
            preserved = json.loads(
                store.db.execute(
                    "SELECT data FROM outbox WHERE id=?",
                    ("preserved-schema-nine-record",),
                ).fetchone()[0]
            )
            self.assertEqual("migration-sentinel", preserved["kind"])
            specs_before = store.db.execute(
                "SELECT COUNT(*) FROM agent_specs"
            ).fetchone()[0]
            aliases_before = store.db.execute(
                "SELECT COUNT(*) FROM agents WHERE data LIKE '%\"implementationId\":\"goal-agent\"%'"
            ).fetchone()[0]
            self.assertGreaterEqual(specs_before, 3)
            self.assertGreaterEqual(aliases_before, 3)
        finally:
            store.close()

        reopened = Store(self.db_path, latency=0)
        try:
            self.assertEqual(
                specs_before,
                reopened.db.execute("SELECT COUNT(*) FROM agent_specs").fetchone()[0],
            )
            self.assertEqual(
                aliases_before,
                reopened.db.execute(
                    "SELECT COUNT(*) FROM agents WHERE data LIKE '%\"implementationId\":\"goal-agent\"%'"
                ).fetchone()[0],
            )
            self.assertIsNotNone(
                reopened.db.execute(
                    "SELECT 1 FROM outbox WHERE id=?",
                    ("preserved-schema-nine-record",),
                ).fetchone()
            )
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
