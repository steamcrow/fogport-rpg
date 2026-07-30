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
# Kanka validates this as a short periodicity token; "yearly" is rejected
# because it is six characters. The API's annual recurrence token is "year".
RECURRENCE_PERIODICITY = "year"


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
    """Return one strict shape from Kanka's several calendar serializers.

    Kanka has returned combinations of API field names (``month_name``),
    normalized fixture names (``months``), and nested date objects over time.
    Normalize each field independently instead of selecting one whole shape;
    that keeps verification strict while tolerating harmless serialization
    differences.
    """
    if not isinstance(actual, dict):
        return {}
    if isinstance(actual.get("calendar"), dict):
        actual = actual["calendar"]

    def number(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    date_value = actual.get("date", actual.get("current_date"))
    if isinstance(date_value, dict):
        year = date_value.get("year", date_value.get("current_year"))
        month = date_value.get("month", date_value.get("current_month"))
        day = date_value.get("day", date_value.get("current_day"))
    else:
        year = actual.get("current_year")
        month = actual.get("current_month")
        day = actual.get("current_day")
        if isinstance(date_value, str):
            parts = date_value.replace("/", "-").split("-")
            if len(parts) == 3:
                year, month, day = parts
    date = None
    if all(value is not None for value in (number(year), number(month), number(day))):
        date = f"{number(year)}-{number(month)}-{number(day)}"

    months = actual.get("months")
    if not isinstance(months, list):
        names = actual.get("month_name")
        lengths = actual.get("month_length")
        types = actual.get("month_type")
        if all(isinstance(value, list) for value in (names, lengths, types)):
            months = [
                {"name": name, "length": length, "type": month_type}
                for name, length, month_type in zip(names, lengths, types)
            ]
    if isinstance(months, list):
        normalized_months = []
        for item in months:
            if not isinstance(item, dict):
                normalized_months = []
                break
            normalized_months.append(
                {
                    "name": str(item.get("name", item.get("month_name", ""))),
                    "length": number(item.get("length", item.get("month_length"))),
                    "type": str(item.get("type", item.get("month_type", ""))),
                }
            )
        months = normalized_months

    weekdays = actual.get("weekdays", actual.get("weekday"))
    if isinstance(weekdays, dict):
        weekdays = list(weekdays.values())

    return {
        "name": actual.get("name", ""),
        "date": date,
        "months": months,
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
        "recurring_periodicity": RECURRENCE_PERIODICITY,
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
        and actual.get("recurring_periodicity") == RECURRENCE_PERIODICITY
        and int(actual.get("entity_id", actual.get("remindable_id", 0)) or 0) == entity_id
    )


def validate_observance_entity(
    client: KankaClient, *, name: str, entity_id: int,
) -> dict[str, Any]:
    """Confirm an event's generic entity id before any reminder write.

    Kanka event records expose both the event-table ``id`` and the generic
    entity ``entity_id``. Reminder routes use the latter. A stale or
    accidentally substituted event id produces an opaque 404 on POST, so
    resolve the generic entity first and require an exact identity match.
    """
    path = f"campaigns/{CAMPAIGN_ID}/entities/{int(entity_id)}"
    response = client._get(path)
    entity = response.get("data", {})
    if not isinstance(entity, dict):
        raise CalendarError(
            f"Observance {name!r} returned no generic entity for {path}; "
            "no reminder writes were attempted."
        )
    returned_id = entity.get("id", entity.get("entity_id"))
    try:
        returned_id = int(returned_id)
    except (TypeError, ValueError):
        returned_id = None
    if returned_id != int(entity_id):
        raise CalendarError(
            f"Observance {name!r} entity validation failed for {path}; "
            f"Kanka returned id {returned_id!r}. No reminder writes were attempted."
        )
    return entity


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
        validate_observance_entity(client, name=name, entity_id=entity_id)
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
        try:
            if candidates:
                reminder = writer.update_entity_reminder(CAMPAIGN_ID, entity_id, int(candidates[0]["id"]), expected)
            else:
                reminder = writer.create_entity_reminder(CAMPAIGN_ID, entity_id, expected)
        except Exception as exc:
            raise CalendarError(
                f"Reminder write failed for {name!r} at "
                f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/reminders: {exc}"
            ) from exc
        direct = client._get(
            f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/reminders/{int(reminder['id'])}"
        ).get("data", {})
        if not reminder_matches(direct, expected, entity_id):
            raise CalendarError(f"Reminder read-back failed for {name!r}.")
        receipts.append({"name": name, "entity_id": entity_id, "reminder_id": int(reminder["id"]), "created": created, "date": f"{month}-{day}", "recurring": RECURRENCE_PERIODICITY})

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "calendar": {"id": calendar_id, "name": CALENDAR_NAME, "created": created_calendar, "date": "43-1-1"},
        "reminders_verified": len(receipts),
        "reminders": receipts,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
