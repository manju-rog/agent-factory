"""Durable workflow scheduling contracts.

These tests deliberately exercise the scheduler through its public Store API
and through HTTP.  They verify business behavior (version pinning, recurrence,
recovery, overlap protection, and authorization), not implementation helpers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import APIError, Store, USERS, create_server


ADMIN, REVIEWER, OPERATOR, CONTRIBUTOR = USERS
TEMPLATE_ID = "customer-resolution"


def instant(value: str) -> datetime:
    """Parse an API UTC instant while keeping comparisons representation-free."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def task_input(label: str = "scheduled") -> dict:
    return {
        "requestId": f"REQ-{label}",
        "customerId": "CUS-1042",
        "subject": f"Resolve {label} service request",
        "amount": 12500,
        "priority": "normal",
    }


def schedule_request(**overrides) -> dict:
    value = {
        "name": "Daily customer resolution",
        "templateId": TEMPLATE_ID,
        "frequency": "daily",
        "localStart": "2030-03-09T09:15",
        "timezone": "America/New_York",
        "scenario": "happy",
        "input": task_input(),
        "overlapPolicy": "skip",
    }
    value.update(overrides)
    return value


class SchedulingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axiom-schedules-")
        self.path = Path(self.temp.name) / "schedules.sqlite3"
        self.store = Store(self.path, latency=0)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, method: str, *args):
        return self.store.atomic(getattr(self.store, method), *args)

    def dispatch(self, at: str):
        return self.store.dispatch_due_schedules(at)

    def test_one_time_schedule_dispatches_exactly_once(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                name="One-time review",
                frequency="once",
                localStart="2030-05-04T10:30",
                timezone="Asia/Kolkata",
            ),
            ADMIN,
        )
        self.assertEqual("active", schedule["status"])
        self.assertEqual(1, schedule["templateVersion"])
        self.assertRegex(schedule["templateHash"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            datetime(2030, 5, 4, 5, 0, tzinfo=timezone.utc),
            instant(schedule["nextRunAt"]),
        )

        self.dispatch("2030-05-04T05:00:00Z")
        first = self.call("get_schedule", schedule["id"], ADMIN)
        self.dispatch("2030-05-04T05:00:00Z")
        second = self.call("get_schedule", schedule["id"], ADMIN)

        self.assertEqual("completed", second["status"])
        self.assertIsNone(second["nextRunAt"])
        self.assertEqual(1, second["runCount"])
        self.assertEqual(first["runIds"], second["runIds"])
        self.assertEqual(1, len(second["runIds"]))
        run = self.store.get("runs", second["runIds"][0])
        self.assertEqual(schedule["templateVersion"], run["version"])
        self.assertEqual(schedule["id"], run["trigger"]["scheduleId"])
        self.assertFalse(run["trigger"]["manual"])

    def test_daily_recurrence_preserves_local_wall_time_across_dst(self):
        schedule = self.call("create_schedule", schedule_request(), ADMIN)
        spring_gap = self.call(
            "create_schedule",
            schedule_request(
                name="Daily clock-gap review",
                localStart="2030-03-09T02:30",
            ),
            ADMIN,
        )
        # New York is UTC-5 on March 9 and UTC-4 after the March 10 DST jump.
        self.assertEqual(
            datetime(2030, 3, 9, 14, 15, tzinfo=timezone.utc),
            instant(schedule["nextRunAt"]),
        )

        self.dispatch("2030-03-09T14:15:00Z")
        advanced = self.call("get_schedule", schedule["id"], ADMIN)
        self.assertEqual("active", advanced["status"])
        self.assertEqual(1, advanced["runCount"])
        self.assertEqual(
            datetime(2030, 3, 10, 13, 15, tzinfo=timezone.utc),
            instant(advanced["nextRunAt"]),
        )
        gap_advanced = self.call("get_schedule", spring_gap["id"], ADMIN)
        # 02:30 does not exist on March 10, so the next real wall-clock
        # occurrence is March 11 at 02:30 EDT (06:30 UTC).
        self.assertEqual(
            datetime(2030, 3, 11, 6, 30, tzinfo=timezone.utc),
            instant(gap_advanced["nextRunAt"]),
        )

        fall_overlap = self.call(
            "create_schedule",
            schedule_request(
                name="Daily repeated-clock review",
                localStart="2030-11-02T01:30",
            ),
            ADMIN,
        )
        self.dispatch("2030-11-02T05:30:00Z")
        overlap_advanced = self.call("get_schedule", fall_overlap["id"], ADMIN)
        # 01:30 happens twice on November 3. The recurrence policy chooses
        # the earlier real instant deterministically (still EDT, 05:30 UTC).
        self.assertEqual(
            datetime(2030, 11, 3, 5, 30, tzinfo=timezone.utc),
            instant(overlap_advanced["nextRunAt"]),
        )

    def test_pause_resume_and_manual_run_are_independent_of_due_time(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="hourly",
                localStart="2030-06-01T10:00",
                timezone="UTC",
            ),
            ADMIN,
        )
        original_due = schedule["nextRunAt"]
        paused = self.call(
            "schedule_action", schedule["id"], "pause",
            {"expectedRevision": schedule["revision"]}, OPERATOR,
        )
        self.assertEqual("paused", paused["status"])
        self.assertEqual(original_due, paused["nextRunAt"])

        self.dispatch("2030-06-01T12:30:00Z")
        still_paused = self.call("get_schedule", schedule["id"], CONTRIBUTOR)
        self.assertEqual([], still_paused["runIds"])

        resumed = self.call(
            "schedule_action", schedule["id"], "resume",
            {"expectedRevision": paused["revision"]}, OPERATOR,
        )
        self.assertEqual("active", resumed["status"])
        self.assertEqual(original_due, resumed["nextRunAt"])

        result = self.call(
            "schedule_action", schedule["id"], "run",
            {"expectedRevision": resumed["revision"],
             "idempotencyKey": "operator-demo-click-1"}, OPERATOR,
        )
        self.assertEqual(schedule["id"], result["schedule"]["id"])
        self.assertEqual(original_due, result["schedule"]["nextRunAt"])
        self.assertEqual("active", result["schedule"]["status"])
        self.assertEqual(1, result["schedule"]["runCount"])
        self.assertTrue(result["run"]["trigger"]["manual"])
        self.assertEqual(schedule["id"], result["run"]["trigger"]["scheduleId"])
        replay = self.call(
            "schedule_action", schedule["id"], "run",
            {"expectedRevision": resumed["revision"],
             "idempotencyKey": "operator-demo-click-1"}, OPERATOR,
        )
        self.assertEqual(result["run"]["id"], replay["run"]["id"])
        self.assertEqual(1, replay["schedule"]["runCount"])

    def test_dispatch_pins_release_even_after_new_workflow_publication(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="once",
                localStart="2031-01-02T10:00",
                timezone="UTC",
            ),
            ADMIN,
        )
        pinned_hash = schedule["templateHash"]
        self.assertEqual(1, schedule["templateVersion"])

        self.call("submit_template", TEMPLATE_ID, ADMIN)
        published = self.call("publish_template", TEMPLATE_ID, REVIEWER)
        self.assertEqual(2, published["publishedVersion"])

        self.dispatch("2031-01-02T10:00:00Z")
        current = self.call("get_schedule", schedule["id"], ADMIN)
        run = self.store.get("runs", current["runIds"][0])
        self.assertEqual(1, run["version"])
        self.assertEqual(pinned_hash, current["templateHash"])
        self.assertEqual(pinned_hash, run["_snapshotHash"])
        self.assertEqual(schedule["id"], run["trigger"]["scheduleId"])

    def test_due_dispatch_is_recovered_after_restart_without_duplication(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="once",
                localStart="2032-02-03T04:05",
                timezone="UTC",
            ),
            ADMIN,
        )
        self.store.close()
        self.store = Store(self.path, latency=0)

        self.dispatch("2032-02-03T04:06:00Z")
        self.dispatch("2032-02-03T04:07:00Z")
        recovered = self.call("get_schedule", schedule["id"], ADMIN)
        self.assertEqual("completed", recovered["status"])
        self.assertEqual(1, recovered["runCount"])
        self.assertEqual(1, len(recovered["runIds"]))

    def test_overlap_skip_coalesces_due_slots_without_a_second_run(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="hourly",
                localStart="2033-03-04T10:00",
                timezone="UTC",
            ),
            ADMIN,
        )
        self.dispatch("2033-03-04T10:00:00Z")
        first = self.call("get_schedule", schedule["id"], ADMIN)
        self.assertEqual(1, first["runCount"])
        self.assertEqual("queued", self.store.get("runs", first["runIds"][0])["status"])

        # The 11:00 and 12:00 slots are both overdue while the 10:00 run is active.
        self.dispatch("2033-03-04T12:30:00Z")
        skipped = self.call("get_schedule", schedule["id"], ADMIN)
        self.assertEqual(1, skipped["runCount"])
        self.assertEqual(1, len(skipped["runIds"]))
        self.assertEqual(2, skipped["missedCount"])
        self.assertEqual(
            datetime(2033, 3, 4, 13, 0, tzinfo=timezone.utc),
            instant(skipped["nextRunAt"]),
        )

    def test_archive_is_durable_and_prevents_dispatch(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="once",
                localStart="2034-04-05T06:07",
                timezone="UTC",
            ),
            ADMIN,
        )
        archived = self.call(
            "archive_schedule", schedule["id"],
            {"expectedRevision": schedule["revision"]}, ADMIN,
        )
        self.assertEqual("archived", archived["status"])
        self.assertIsNone(archived["nextRunAt"])

        self.dispatch("2034-04-05T06:08:00Z")
        persisted = self.call("get_schedule", schedule["id"], CONTRIBUTOR)
        self.assertEqual("archived", persisted["status"])
        self.assertEqual([], persisted["runIds"])
        self.store.close()
        self.store = Store(self.path, latency=0)
        self.assertEqual(
            "archived",
            self.call("get_schedule", schedule["id"], ADMIN)["status"],
        )

    def test_validation_rejects_invalid_time_contract_and_workflow_input(self):
        invalid_cases = (
            ({"frequency": "monthly"}, "SCHEDULE_FREQUENCY_INVALID"),
            ({"timezone": "Mars/Olympus_Mons"}, "SCHEDULE_TIMEZONE_INVALID"),
            ({"localStart": "2030-01-02T03:04:05Z"}, "SCHEDULE_START_INVALID"),
            ({"localStart": "2030-03-10T02:30"}, "SCHEDULE_START_NONEXISTENT"),
            ({"localStart": "2030-11-03T01:30"}, "SCHEDULE_START_AMBIGUOUS"),
            ({"overlapPolicy": "parallel"}, "SCHEDULE_OVERLAP_INVALID"),
            ({"input": {"requestId": "missing-required-fields"}}, "INPUT_SCHEMA_INVALID"),
        )
        for changes, expected_code in invalid_cases:
            with self.subTest(changes=changes):
                with self.assertRaises(APIError) as failure:
                    self.call("create_schedule", schedule_request(**changes), ADMIN)
                self.assertEqual(expected_code, failure.exception.code)

    def test_role_checks_and_optimistic_update_prevent_unauthorized_edits(self):
        with self.assertRaises(APIError) as denied:
            self.call("create_schedule", schedule_request(), CONTRIBUTOR)
        self.assertEqual("ROLE_DENIED", denied.exception.code)

        schedule = self.call("create_schedule", schedule_request(), ADMIN)
        update_body = {
            **schedule_request(name="Reviewed daily run"),
            "expectedRevision": schedule["revision"],
        }
        with self.assertRaises(APIError) as denied:
            self.call(
                "update_schedule",
                schedule["id"],
                {**update_body, "name": "Unauthorized"},
                OPERATOR,
            )
        self.assertEqual("ROLE_DENIED", denied.exception.code)

        updated = self.call(
            "update_schedule",
            schedule["id"],
            update_body,
            ADMIN,
        )
        self.assertEqual("Reviewed daily run", updated["name"])
        self.assertGreater(updated["revision"], schedule["revision"])
        with self.assertRaises(APIError) as stale:
            self.call(
                "update_schedule",
                schedule["id"],
                {**update_body, "name": "Stale edit"},
                ADMIN,
            )
        self.assertEqual("REVISION_CONFLICT", stale.exception.code)

    def test_material_edit_uses_a_new_definition_generation_and_run_identity(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="once", localStart="2036-01-02T03:04", timezone="UTC",
            ),
            ADMIN,
        )
        self.dispatch("2036-01-02T03:04:00Z")
        first = self.call("get_schedule", schedule["id"], ADMIN)
        first_run = self.store.get("runs", first["lastRunId"])
        first_run["status"] = "completed"
        self.store.put("runs", first_run)

        changed_input = task_input("edited-generation")
        edited = self.call(
            "update_schedule", schedule["id"],
            {
                **schedule_request(
                    name="Edited one-time review", frequency="once",
                    localStart="2036-01-02T03:04", timezone="UTC",
                    input=changed_input,
                ),
                "expectedRevision": first["revision"],
            },
            ADMIN,
        )
        self.assertEqual(2, edited["definitionGeneration"])
        self.dispatch("2036-01-02T03:05:00Z")
        current = self.call("get_schedule", schedule["id"], ADMIN)

        self.assertEqual(2, current["runCount"])
        self.assertEqual(2, len(current["runIds"]))
        self.assertNotEqual(current["runIds"][0], current["runIds"][1])
        second_run = self.store.get("runs", current["runIds"][1])
        self.assertEqual(changed_input, second_run["input"])
        self.assertEqual(2, second_run["trigger"]["definitionGeneration"])
        self.assertNotEqual(
            first_run["trigger"]["occurrenceKey"],
            second_run["trigger"]["occurrenceKey"],
        )

    def test_run_now_replay_precedes_revision_conflict_and_changed_reuse_is_denied(self):
        schedule = self.call("create_schedule", schedule_request(), ADMIN)
        request = {
            "expectedRevision": schedule["revision"],
            "idempotencyKey": "lost-response-1",
        }
        first = self.call(
            "schedule_action", schedule["id"], "run", request, OPERATOR,
        )
        self.assertGreater(first["schedule"]["revision"], request["expectedRevision"])

        replay = self.call(
            "schedule_action", schedule["id"], "run", request, OPERATOR,
        )
        self.assertEqual(first["run"]["id"], replay["run"]["id"])
        self.assertEqual(1, replay["schedule"]["runCount"])

        with self.assertRaises(APIError) as changed:
            self.call(
                "schedule_action", schedule["id"], "run",
                {
                    "expectedRevision": first["schedule"]["revision"],
                    "idempotencyKey": "lost-response-1",
                },
                OPERATOR,
            )
        self.assertEqual("IDEMPOTENCY_KEY_REUSED", changed.exception.code)
        with self.assertRaises(APIError) as different_actor:
            self.call(
                "schedule_action", schedule["id"], "run", request, ADMIN,
            )
        self.assertEqual("IDEMPOTENCY_KEY_REUSED", different_actor.exception.code)

    def test_archive_requires_current_revision_and_rejects_a_racing_request(self):
        schedule = self.call("create_schedule", schedule_request(), ADMIN)
        with self.assertRaises(APIError) as missing:
            self.call("archive_schedule", schedule["id"], {}, ADMIN)
        self.assertEqual("SCHEDULE_REVISION_REQUIRED", missing.exception.code)

        archived = self.call(
            "archive_schedule", schedule["id"],
            {"expectedRevision": schedule["revision"]}, ADMIN,
        )
        self.assertEqual("archived", archived["status"])
        with self.assertRaises(APIError) as stale:
            self.call(
                "archive_schedule", schedule["id"],
                {"expectedRevision": schedule["revision"]}, ADMIN,
            )
        self.assertEqual("REVISION_CONFLICT", stale.exception.code)

    def test_pause_resume_and_new_run_require_the_current_revision(self):
        schedule = self.call("create_schedule", schedule_request(), ADMIN)
        with self.assertRaises(APIError) as missing:
            self.call("schedule_action", schedule["id"], "pause", {}, OPERATOR)
        self.assertEqual("SCHEDULE_REVISION_REQUIRED", missing.exception.code)
        with self.assertRaises(APIError) as stale:
            self.call(
                "schedule_action", schedule["id"], "pause",
                {"expectedRevision": schedule["revision"] + 1}, OPERATOR,
            )
        self.assertEqual("REVISION_CONFLICT", stale.exception.code)

        paused = self.call(
            "schedule_action", schedule["id"], "pause",
            {"expectedRevision": schedule["revision"]}, OPERATOR,
        )
        with self.assertRaises(APIError) as stale_resume:
            self.call(
                "schedule_action", schedule["id"], "resume",
                {"expectedRevision": schedule["revision"]}, OPERATOR,
            )
        self.assertEqual("REVISION_CONFLICT", stale_resume.exception.code)
        resumed = self.call(
            "schedule_action", schedule["id"], "resume",
            {"expectedRevision": paused["revision"]}, OPERATOR,
        )
        with self.assertRaises(APIError) as missing_key:
            self.call(
                "schedule_action", schedule["id"], "run",
                {"expectedRevision": resumed["revision"]}, OPERATOR,
            )
        self.assertEqual("IDEMPOTENCY_KEY_REQUIRED", missing_key.exception.code)
        with self.assertRaises(APIError) as missing_run:
            self.call(
                "schedule_action", schedule["id"], "run",
                {"idempotencyKey": "missing-revision"}, OPERATOR,
            )
        self.assertEqual("SCHEDULE_REVISION_REQUIRED", missing_run.exception.code)
        with self.assertRaises(APIError) as stale_run:
            self.call(
                "schedule_action", schedule["id"], "run",
                {"expectedRevision": paused["revision"],
                 "idempotencyKey": "stale-revision"}, OPERATOR,
            )
        self.assertEqual("REVISION_CONFLICT", stale_run.exception.code)
        self.assertEqual("active", resumed["status"])

    def test_archived_template_does_not_invalidate_an_existing_release_pin(self):
        schedule = self.call(
            "create_schedule",
            schedule_request(
                frequency="once", localStart="2037-02-03T04:05", timezone="UTC",
            ),
            ADMIN,
        )
        self.call("archive_template", TEMPLATE_ID, ADMIN)

        self.dispatch("2037-02-03T04:05:00Z")
        current = self.call("get_schedule", schedule["id"], ADMIN)
        self.assertEqual(1, current["runCount"])
        run = self.store.get("runs", current["lastRunId"])
        self.assertEqual(schedule["templateVersion"], run["version"])
        self.assertEqual(schedule["templateHash"], run["trigger"]["releaseHash"])

        with self.assertRaises(APIError) as blocked:
            self.call("create_schedule", schedule_request(name="New blocked schedule"), ADMIN)
        self.assertEqual("TEMPLATE_ARCHIVED", blocked.exception.code)

    def test_redacted_input_can_be_omitted_without_overwriting_stored_values(self):
        protected_input = {**task_input("protected"), "apiToken": "server-only-value"}
        schedule = self.call(
            "create_schedule", schedule_request(input=protected_input), ADMIN,
        )
        self.assertTrue(schedule["inputRedacted"])
        self.assertEqual("[REDACTED]", schedule["input"]["apiToken"])

        with self.assertRaises(APIError) as naive_round_trip:
            self.call(
                "update_schedule", schedule["id"],
                {
                    **schedule_request(
                        name="Naive masked round trip", input=schedule["input"],
                    ),
                    "expectedRevision": schedule["revision"],
                },
                ADMIN,
            )
        self.assertEqual(
            "SCHEDULE_INPUT_MODE_REQUIRED", naive_round_trip.exception.code
        )

        update = schedule_request(name="Renamed without resubmitting input")
        update.pop("input")
        updated = self.call(
            "update_schedule", schedule["id"],
            {**update, "expectedRevision": schedule["revision"],
             "inputMode": "preserve"}, ADMIN,
        )
        stored = self.store.get("schedules", schedule["id"])
        self.assertEqual("server-only-value", stored["input"]["apiToken"])
        self.assertTrue(updated["inputRedacted"])
        self.assertEqual("[REDACTED]", updated["input"]["apiToken"])

        changed_template = schedule_request(
            name="Unsafe hidden-input rebind", templateId="vendor-risk-onboarding"
        )
        changed_template.pop("input")
        with self.assertRaises(APIError) as hidden_rebind:
            self.call(
                "update_schedule", schedule["id"],
                {**changed_template, "expectedRevision": updated["revision"],
                 "inputMode": "preserve"}, ADMIN,
            )
        self.assertEqual(
            "SCHEDULE_INPUT_REQUIRED_FOR_TEMPLATE_CHANGE",
            hidden_rebind.exception.code,
        )

        replacement = {**protected_input, "apiToken": "[REDACTED]"}
        replaced = self.call(
            "update_schedule", schedule["id"],
            {
                **schedule_request(
                    name="Literal replacement", input=replacement,
                ),
                "expectedRevision": updated["revision"],
                "inputMode": "replace",
            },
            ADMIN,
        )
        self.assertEqual(
            "[REDACTED]",
            self.store.get("schedules", schedule["id"])["input"]["apiToken"],
        )
        self.assertTrue(replaced["inputRedacted"])


class SchedulingHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axiom-schedule-http-")
        self.store = Store(Path(self.temp.name) / "http.sqlite3", latency=0)
        self.server = create_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        self.csrf = None
        status, bootstrap = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status)
        self.bootstrap = bootstrap
        self.csrf = bootstrap["csrf"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.store.close()
        self.temp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None):
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(
            self.base + path, data=payload, headers=headers, method=method
        )
        try:
            response = self.client.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def switch(self, role: str):
        target = next(user for user in self.bootstrap["users"] if user["role"] == role)
        status, session = self.request("POST", "/api/session", {"userId": target["id"]})
        self.assertEqual(200, status, session)
        self.csrf = session["csrf"]

    def test_crud_actions_and_role_denial_are_reachable_over_http(self):
        status, created = self.request(
            "POST",
            "/api/schedules",
            schedule_request(
                frequency="once",
                localStart="2035-05-06T07:08",
                timezone="UTC",
            ),
        )
        self.assertEqual(200, status, created)

        status, listed = self.request("GET", "/api/schedules")
        self.assertEqual(200, status, listed)
        self.assertIn(created["id"], {item["id"] for item in listed})

        status, paused = self.request(
            "POST", f"/api/schedules/{created['id']}/pause",
            {"expectedRevision": created["revision"]},
        )
        self.assertEqual(200, status, paused)
        self.assertEqual("paused", paused["status"])
        status, resumed = self.request(
            "POST", f"/api/schedules/{created['id']}/resume",
            {"expectedRevision": paused["revision"]},
        )
        self.assertEqual(200, status, resumed)
        self.assertEqual("active", resumed["status"])

        status, missing_key = self.request(
            "POST", f"/api/schedules/{created['id']}/run",
            {"expectedRevision": resumed["revision"]},
        )
        self.assertEqual(400, status, missing_key)
        self.assertEqual("IDEMPOTENCY_KEY_REQUIRED", missing_key["error"]["code"])
        status, manual = self.request(
            "POST", f"/api/schedules/{created['id']}/run",
            {"expectedRevision": resumed["revision"],
             "idempotencyKey": "http-run-now-1"},
        )
        self.assertEqual(200, status, manual)
        self.assertEqual(created["id"], manual["run"]["trigger"]["scheduleId"])
        self.assertTrue(manual["run"]["trigger"]["manual"])

        self.switch("contributor")
        status, denied = self.request("POST", "/api/schedules", schedule_request())
        self.assertEqual(403, status, denied)
        self.assertEqual("ROLE_DENIED", denied["error"]["code"])

        self.switch("admin")
        status, archived = self.request(
            "DELETE", f"/api/schedules/{created['id']}",
            {"expectedRevision": manual["schedule"]["revision"]},
        )
        self.assertEqual(200, status, archived)
        self.assertEqual("archived", archived["status"])


if __name__ == "__main__":
    unittest.main()
