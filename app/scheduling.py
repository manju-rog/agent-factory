"""Validated, timezone-aware recurrence helpers for durable workflow schedules.

This module is deliberately independent of HTTP and persistence.  The server
stores the returned UTC instants and occurrence index, so a restart never has
to infer whether an occurrence was already consumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


FREQUENCIES = frozenset({"once", "hourly", "daily", "weekly"})
OVERLAP_POLICIES = frozenset({"skip"})
SCENARIOS = frozenset({"happy", "lost_acknowledgement"})
LOCAL_START_PATTERN = re.compile(
    r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2})"
)
TIMEZONE_PATTERN = re.compile(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*")


class ScheduleValidationError(ValueError):
    """A stable validation failure suitable for conversion into an API error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DueWindow:
    """The single occurrence to dispatch and the durable recurrence advance."""

    occurrence_index: int
    scheduled_for: str
    next_index: int
    next_run_at: str | None
    due_count: int

    @property
    def coalesced_count(self) -> int:
        return max(0, self.due_count - 1)


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("UTC serialization requires an aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("UTC timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must include an offset")
    return parsed.astimezone(timezone.utc)


def parse_current_time(value=None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        return parse_utc(value)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    raise ValueError("current_time must be an aware datetime or an ISO timestamp")


def load_timezone(name: str) -> ZoneInfo:
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 100
        or not TIMEZONE_PATTERN.fullmatch(name)
        or name in {"localtime", ".", ".."}
    ):
        raise ScheduleValidationError(
            "SCHEDULE_TIMEZONE_INVALID", "Choose a valid IANA timezone."
        )
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScheduleValidationError(
            "SCHEDULE_TIMEZONE_INVALID", "Choose a valid IANA timezone."
        ) from exc


def parse_local_start(value: str) -> datetime:
    if not isinstance(value, str) or not LOCAL_START_PATTERN.fullmatch(value):
        raise ScheduleValidationError(
            "SCHEDULE_START_INVALID",
            "Use a local start in YYYY-MM-DDTHH:mm format.",
        )
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ScheduleValidationError(
            "SCHEDULE_START_INVALID", "Choose a real local date and time."
        ) from exc
    if result.strftime("%Y-%m-%dT%H:%M") != value:
        raise ScheduleValidationError(
            "SCHEDULE_START_INVALID", "Choose a real local date and time."
        )
    return result


def _resolve_local(naive: datetime, zone: ZoneInfo, *, reject_ambiguous: bool):
    """Resolve a wall time, returning None when a recurrence hits a DST gap."""

    candidates = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        round_trip = aware.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive:
            candidates.append(aware)
    if not candidates:
        if reject_ambiguous:
            raise ScheduleValidationError(
                "SCHEDULE_START_NONEXISTENT",
                "That local time does not exist because the timezone clock moves forward. Choose another time.",
            )
        return None
    unique = {candidate.utcoffset() for candidate in candidates}
    if len(unique) > 1 and reject_ambiguous:
        raise ScheduleValidationError(
            "SCHEDULE_START_AMBIGUOUS",
            "That local time occurs twice because the timezone clock moves backward. Choose another time.",
        )
    # The earlier instant is the deterministic policy for a future overlap.
    return min(candidates, key=lambda item: item.astimezone(timezone.utc))


def validate_definition(definition: dict) -> dict:
    """Return a normalized schedule definition without accepting extra fields."""

    if not isinstance(definition, dict):
        raise ScheduleValidationError(
            "SCHEDULE_BODY_INVALID", "A schedule must be a JSON object."
        )
    name = definition.get("name")
    if (
        not isinstance(name, str)
        or not 1 <= len(name.strip()) <= 120
        or any(ord(character) < 32 for character in name)
    ):
        raise ScheduleValidationError(
            "SCHEDULE_NAME_INVALID", "Enter a schedule name using 1–120 characters."
        )
    template_id = definition.get("templateId")
    if not isinstance(template_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,128}", template_id
    ):
        raise ScheduleValidationError(
            "SCHEDULE_TEMPLATE_INVALID", "Choose a published workflow."
        )
    frequency = definition.get("frequency")
    if frequency not in FREQUENCIES:
        raise ScheduleValidationError(
            "SCHEDULE_FREQUENCY_INVALID",
            "Choose once, hourly, daily, or weekly.",
        )
    local_start = definition.get("localStart")
    naive = parse_local_start(local_start)
    timezone_name = definition.get("timezone")
    zone = load_timezone(timezone_name)
    aware = _resolve_local(naive, zone, reject_ambiguous=True)
    scenario = definition.get("scenario", "happy")
    if scenario not in SCENARIOS:
        raise ScheduleValidationError(
            "SCHEDULE_SCENARIO_INVALID",
            "Scheduled runs support happy or lost_acknowledgement scenarios.",
        )
    overlap = definition.get("overlapPolicy", "skip")
    if overlap not in OVERLAP_POLICIES:
        raise ScheduleValidationError(
            "SCHEDULE_OVERLAP_INVALID",
            "The supported overlap policy is skip.",
        )
    schedule_input = definition.get("input", {})
    if not isinstance(schedule_input, dict):
        raise ScheduleValidationError(
            "SCHEDULE_INPUT_INVALID", "Scheduled workflow input must be a JSON object."
        )
    return {
        "name": name.strip(),
        "templateId": template_id,
        "frequency": frequency,
        "localStart": local_start,
        "timezone": timezone_name,
        "scenario": scenario,
        "input": schedule_input,
        "overlapPolicy": overlap,
        "firstRunAt": utc_iso(aware),
    }


def occurrence_at(record: dict, index: int) -> datetime | None:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("occurrence index must be a non-negative integer")
    naive = parse_local_start(record["localStart"])
    zone = load_timezone(record["timezone"])
    first = _resolve_local(naive, zone, reject_ambiguous=True)
    frequency = record["frequency"]
    if frequency == "once":
        return first.astimezone(timezone.utc) if index == 0 else None
    if frequency == "hourly":
        return first.astimezone(timezone.utc) + timedelta(hours=index)
    days = index if frequency == "daily" else index * 7
    candidate = _resolve_local(naive + timedelta(days=days), zone, reject_ambiguous=False)
    return candidate.astimezone(timezone.utc) if candidate is not None else None


def _estimated_index(record: dict, instant: datetime) -> int:
    first = occurrence_at(record, 0)
    if first is None or instant < first:
        return -1
    frequency = record["frequency"]
    if frequency == "once":
        return 0
    if frequency == "hourly":
        return int((instant - first).total_seconds() // 3600)
    zone = load_timezone(record["timezone"])
    anchor = parse_local_start(record["localStart"])
    local_now = instant.astimezone(zone).replace(tzinfo=None)
    elapsed_days = (local_now.date() - anchor.date()).days
    estimate = elapsed_days if frequency == "daily" else elapsed_days // 7
    return max(-1, estimate)


def next_valid_occurrence(record: dict, index: int):
    """Return the next representable recurrence, skipping bounded DST gaps."""

    current = index
    # Timezone discontinuities are short in the IANA database.  The generous
    # bound also protects corrupted records from an unbounded worker loop.
    for _ in range(32):
        occurrence = occurrence_at(record, current)
        if occurrence is not None:
            return current, occurrence
        current += 1
    raise ValueError("timezone recurrence did not produce a valid occurrence")


def due_window(record: dict, current_time=None) -> DueWindow | None:
    """Coalesce all due slots into at most one dispatch decision."""

    instant = parse_current_time(current_time)
    next_index = record.get("_nextIndex", 0)
    if isinstance(next_index, bool) or not isinstance(next_index, int) or next_index < 0:
        raise ValueError("stored schedule occurrence index is invalid")
    first_pending_index, first_pending = next_valid_occurrence(record, next_index)
    if first_pending_index > next_index:
        next_index = first_pending_index
    if first_pending > instant:
        return None
    latest_index = max(next_index, _estimated_index(record, instant))
    # Estimates use local calendar units and can land on the next not-yet-due
    # wall time or on a DST gap.  Walk only around that boundary.
    while latest_index >= next_index:
        candidate = occurrence_at(record, latest_index)
        if candidate is not None and candidate <= instant:
            break
        latest_index -= 1
    if latest_index < next_index:
        return None
    chosen = occurrence_at(record, latest_index)
    if chosen is None:
        # A DST gap can only cover a small number of calendar occurrences.
        for _ in range(32):
            latest_index -= 1
            if latest_index < next_index:
                return None
            chosen = occurrence_at(record, latest_index)
            if chosen is not None and chosen <= instant:
                break
        else:
            raise ValueError("timezone recurrence did not produce a due occurrence")
    if record["frequency"] == "once":
        next_index_value, next_run_at = 1, None
    else:
        next_index_value, next_occurrence = next_valid_occurrence(record, latest_index + 1)
        next_run_at = utc_iso(next_occurrence)
    return DueWindow(
        occurrence_index=latest_index,
        scheduled_for=utc_iso(chosen),
        next_index=next_index_value,
        next_run_at=next_run_at,
        due_count=latest_index - next_index + 1,
    )
