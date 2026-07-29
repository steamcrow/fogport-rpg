"""Finish the Fogport Calendar and attach approved annual observances.

The publisher is deliberately narrow: it may only touch the Fogport campaign,
one exact calendar name, and the twenty already-approved observance entities.
Every calendar field and reminder is read back before the receipt is written.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from kanka_librarian.client import KankaClient
from kanka_librarian.writer import KankaWriter


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
CALENDAR_NAME = "Fogport Calendar"


class CalendarError(ValueError):
    """Raised before a calendar write would be unsafe or incomplete."""


def document_digest(document: dict[str, Any]) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    return hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_calendar_document(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 1 or document.get("mode") != "fogport-calendar":
        raise CalendarError("Expected the approved fogport-calendar document.")
    if int(document.get("campaign_id", 0)) != CAMPAIGN_ID:
        raise CalendarError("Calendar publisher is locked to Fogport campaign 410879.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise CalendarError("Calendar campaign name must be Fogport.")
    if str(document.get("calendar_name", "")).casefold() != CALENDAR_NAME.casefold():
        raise CalendarError("Calendar publisher may only use Fogport Calendar.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise CalendarError("The calendar document is not explicitly approved.")
    if approval.get("document_sha256") != document_digest(document):
        raise CalendarError("The calendar document changed after approval.")
    months = document.get("months")
    if not isinstance(months, list) or len(months) != 12:
        raise CalendarError("Fogport Calendar must have exactly twelve provisional months.")
    if any(not isinstance(item, list) or len(item) != 2 or int(item[1]) < 28 for item in months):
        raise CalendarError("Each calendar month needs a name and a valid length.")
    if document.get("weekdays") != ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        raise CalendarError("The provisional calendar must retain the ordinary seven weekdays.")
    date = document.get("current_date")
    if date != {"year": 43, "month": 1, "day": 1}:
        raise CalendarError("The provisional calendar date must be January 1, 43 A.Cat.")


def calendar_payload(document: dict[str, Any]) -> dict[str, Any]:
    months = document["months"]
    date = document["current_date"]
    return {
        "name": CALENDAR_NAME,
        "entry": "<p>The provisional working calendar of Fogport. Its familiar month and weekday names may be replaced once the city’s final calendar is established.</p>",
        "type": "Primary",
        "current_year": int(date["year"]),
        "current_month": int(date["month"]),
        "current_day": int(date["day"]),
        "month_name": [str(month[0]) for month in months],
        "month_length": [int(month[1]) for month in months],
        "month_type": ["standard"] * len(months),
        "weekday": list(document["weekdays"]),
        "format": str(document["format"]),
        "skip_year_zero": bool(document["skip_year_zero"]),
        "is_private": False,
    }


def find_exact(records: list[dict[str, Any]], name: str, *, kind: str) -> dict[str, Any] | None:
    matches = [item for item in records if str(item.get("name", "")).strip().casefold() == name.casefold()]
    if len(matches) > 1:
        raise CalendarError(f"Multiple {kind} records named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def calendar_matches(actual: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Compare Kanka's calendar read-back with our approved shape.

    The calendar collection/read endpoints expose the same values using the
    API payload names (``current_year``, ``month_name``, ``weekday``, etc.),
    while older test fixtures and some related endpoints use a normalized
    shape (``date``, ``months``, ``weekdays``).  Normalize both forms here so
    verification remains strict about every approved value without assuming
    that Kanka's response serializer matches our internal fixture.
    """
    actual = normalize_calendar_readback(actual)
    expected_months = [
        {"name": name, "length": length, "type": "standard"}
        for name, length in zip(payload["month_name"], payload["month_length"], strict=True)
    ]
    return (
        str(actual.get("name", "")).casefold() == CALENDAR_NAME.casefold()
        and actual.get("date") == "43-1-1"
        and actual.get("months") == expected_months
        and actual.get("weekdays") == payload["weekday"]
        and actual.get("format") == payload["format"]
        and bool(actual.get("skip_year_zero")) is True
    )


def normalize_calendar_readback(actual: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical calendar shape from either Kanka response form."""
    if "months" in actual or "weekdays" in actual or "date" in actual:
        return actual

    month_names = actual.get("month_name")
    month_lengths = actual.get("month_length")
    month_types = actual.get("month_type")
    weekdays = actual.get("weekday")
    if not all(isinstance(value, list) for value in (month_names, month_lengths, month_types, weekdays)):
        return actual
    if not (len(month_names) == len(month_lengths) == len(month_types)):
        return actual

    return {
        "name": actual.get("name", ""),
        "date": "-".join(
            str(actual.get(field, ""))
            for field in ("current_year", "current_month", "current_day")
        ),
        "months": [
            {"name": str(name), "length": int(length), "type": str(month_type)}
            for name, length, month_type in zip(month_names, month_lengths, month_types, strict=True)
        ],
        "weekdays": weekdays,
        "format": actual.get("format", actual.get("date_format")),
        "skip_year_zero": bool(actual.get("skip_year_zero")),
    }


def parse_date(value: str) -> tuple[int, int]:
    names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    month_name, day = value.rsplit(" ", 1)
    if month_name not in names:
        raise CalendarError(f"Unsupported observance month: {month_name!r}.")
    return names.index(month_name) + 1, int(day)


def reminder_payload(calendar_id: int, month: int, day: int, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "calendar_id": int(calendar_id),
        "year": 43,
        "month": month,
        "day": day,
        "length": 1,
        "recurring_periodicity": "yearly",
        "recurring_until": None,
        "comment": "Fogport annual observance",
        "colour": "#9a7b3f",
        "is_private": False,
        "visibility_id": 1,
    }


def reminder_matches(actual: dict[str, Any], expected: dict[str, Any], entity_id: int) -> bool:
    return (
        int(actual.get("calendar_id", 0)) == int(expected["calendar_id"])
        and int(actual.get("year", 0)) == int(expected["year"])
        and int(actual.get("month", 0)) == int(expected["month"])
        and int(actual.get("day", 0)) == int(expected["day"])
        and int(actual.get("length", 0)) == 1
        and actual.get("recurring_periodicity") == "yearly"
        and int(actual.get("entity_id", actual.get("remindable_id", 0)) or 0) == entity_id
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.document.read_text(encoding="utf-8"))
    validate_calendar_document(document)
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise CalendarError("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise CalendarError("Kanka campaign identity lock failed.")

    payload = calendar_payload(document)
    calendar = find_exact(client.list_calendars(CAMPAIGN_ID), CALENDAR_NAME, kind="calendar")
    created_calendar = calendar is None
    if calendar is None:
        calendar = writer.create_calendar(CAMPAIGN_ID, payload)
    else:
        calendar = writer.update_calendar(CAMPAIGN_ID, int(calendar["id"]), payload)
    calendar_id = int(calendar["id"])
    direct_calendar = client._get(f"campaigns/{CAMPAIGN_ID}/calendars/{calendar_id}").get("data", {})
    if not calendar_matches(direct_calendar, payload):
        raise CalendarError("Fogport Calendar read-back failed; no reminder writes were attempted.")

    observances_path = args.document.parent.parent.parent / document["annual_observances_document"]
    observances = json.loads(observances_path.read_text(encoding="utf-8"))
    changes = observances.get("changes", [])
    if len(changes) != 20 or any(change.get("section") != "events" for change in changes):
        raise CalendarError("The approved annual-observances batch must contain exactly twenty events.")
    events = client.list_events(CAMPAIGN_ID)
    reminders = client.list_calendar_reminders(CAMPAIGN_ID, calendar_id)
    receipts: list[dict[str, Any]] = []
    for change in changes:
        name = str(change["name"])
        event = find_exact(events, name, kind="event")
        if event is None or not event.get("entity_id"):
            raise CalendarError(f"Existing annual observance event {name!r} is missing.")
        entity_id = int(event["entity_id"])
        month, day = parse_date(str(change["date"]))
        expected = reminder_payload(calendar_id, month, day, name)
        candidates = [
            item for item in reminders
            if int(item.get("entity_id", item.get("remindable_id", 0)) or 0) == entity_id
            and int(item.get("calendar_id", 0)) == calendar_id
        ]
        if len(candidates) > 1:
            raise CalendarError(f"Multiple Fogport Calendar reminders found for {name!r}.")
        created = not candidates
        if candidates:
