"""Template duplication, archive/restore, and portable package contracts."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import APIError, Store, USERS


AUTHOR, REVIEWER, OPERATOR, CONTRIBUTOR = USERS


class TemplateLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "templates.sqlite3", latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def test_duplicate_is_an_independent_unpublished_draft(self):
        source = self.store.get("templates", "customer-resolution")
        duplicate = self.call("duplicate_template", source["id"], AUTHOR)
        self.assertNotEqual(source["id"], duplicate["id"])
        self.assertEqual("draft", duplicate["status"])
        self.assertIsNone(duplicate["publishedVersion"])
        self.assertEqual([], duplicate["versions"])
        self.assertEqual(source["nodes"], duplicate["nodes"])
        duplicate["nodes"][0]["label"] = "Changed only in memory"
        self.assertNotEqual(source["nodes"][0]["label"], duplicate["nodes"][0]["label"])

    def test_archive_blocks_new_starts_and_restore_preserves_release(self):
        run = self.call("create_run", {
            "templateId": "customer-resolution", "mode": "fixture", "scenario": "happy",
        }, CONTRIBUTOR)
        archived = self.call("archive_template", "customer-resolution", AUTHOR)
        self.assertEqual("archived", archived["status"])
        self.assertEqual([], self.store.find_startable_templates(CONTRIBUTOR, "service"))
        with self.assertRaises(APIError) as blocked:
            self.call("create_run", {
                "templateId": "customer-resolution", "mode": "fixture", "scenario": "happy",
            }, CONTRIBUTOR)
        self.assertEqual("TEMPLATE_ARCHIVED", blocked.exception.code)
        self.assertEqual("queued", self.store.get("runs", run["id"])["status"])

        restored = self.call("restore_template", "customer-resolution", AUTHOR)
        self.assertEqual("draft", restored["status"])
        self.assertEqual(1, restored["publishedVersion"])
        self.assertEqual(["customer-resolution"], [
            item["template_id"] for item in self.store.find_startable_templates(CONTRIBUTOR, "service")
        ])

    def test_export_import_verifies_hash_and_current_validation(self):
        package = self.store.export_template("customer-resolution")
        imported = self.call("import_template", package, AUTHOR)
        self.assertEqual("draft", imported["status"])
        self.assertIsNone(imported["publishedVersion"])
        self.assertEqual(package["sha256"], imported["importedHash"])
        self.assertTrue(self.store.validate(imported)["valid"])

        tampered = copy.deepcopy(package)
        tampered["template"]["name"] = "Tampered after hashing"
        with self.assertRaises(APIError) as denied:
            self.call("import_template", tampered, AUTHOR)
        self.assertEqual("TEMPLATE_IMPORT_HASH", denied.exception.code)

    def test_only_admin_can_mutate_template_lifecycle(self):
        for method in ("duplicate_template", "archive_template", "restore_template"):
            with self.subTest(method=method):
                with self.assertRaises(APIError) as denied:
                    self.call(method, "customer-resolution", CONTRIBUTOR)
                self.assertEqual("ROLE_DENIED", denied.exception.code)
        package = self.store.export_template("customer-resolution")
        with self.assertRaises(APIError) as denied:
            self.call("import_template", package, CONTRIBUTOR)
        self.assertEqual("ROLE_DENIED", denied.exception.code)


if __name__ == "__main__":
    unittest.main()
