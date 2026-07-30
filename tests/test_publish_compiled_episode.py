from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.publish_compiled_episode import (
    EpisodeError,
    compose_entry,
    find_match,
    normalize_kanka_html,
    read_back_matches,
    read_location_parent_entity_id,
    resolve_location_parent_entity_id,
    resolve_gallery_image,
    validate_document,
)
from scripts.publish_fogport_calendar import (
    CalendarError,
    calendar_matches,
    calendar_payload,
    document_digest as calendar_document_digest,
    normalize_calendar_readback,
    parse_date,
    prepare_observances,
    RECURRENCE_PERIODICITY,
    reminder_matches,
    reminder_payload,
    validate_observance_entity,
    validate_calendar_document,
)
from kanka_librarian.writer import KankaWriter


class CompiledEpisodeTests(unittest.TestCase):
    def test_reminder_writer_uses_kanka_reminders_routes(self):
        writer = KankaWriter(token="test-token", expected_campaign_id=410879)
        with patch.object(writer, "_send", return_value={"id": 7}) as send:
            writer.create_entity_reminder(410879, 1234, {"name": "The First Fog"})
            writer.update_entity_reminder(410879, 1234, 7, {"name": "The First Fog"})

        self.assertEqual(send.call_args_list[0].args[:2], ("POST", "campaigns/410879/entities/1234/reminders"))
        self.assertEqual(send.call_args_list[1].args[:2], ("PATCH", "campaigns/410879/entities/1234/reminders/7"))

    def test_explicit_alias_matches_existing_record(self):
        records = [
            {"id": 1, "entity_id": 11, "name": "Byl Blacksaft"},
            {"id": 2, "entity_id": 12, "name": "Lott"},
        ]
        change = {
            "name": "Byl Hasbaine",
            "match_names": ["Byl Blacksaft"],
        }
        self.assertEqual(find_match(records, change)["id"], 1)

    def test_ambiguous_former_and_current_name_stops(self):
        records = [
            {"id": 1, "entity_id": 11, "name": "Byl Blacksaft"},
            {"id": 2, "entity_id": 12, "name": "Byl Hasbaine"},
        ]
        change = {
            "name": "Byl Hasbaine",
            "match_names": ["Byl Blacksaft"],
        }
        with self.assertRaises(EpisodeError):
            find_match(records, change)

    def test_append_is_idempotent(self):
        change = {
            "append_entry": "<h2>Episode: One Door Remaining</h2><p>Changed.</p>",
            "append_marker": "<h2>Episode: One Door Remaining</h2>",
        }
        first = compose_entry("<p>Byl Hasbaine</p>", change)
        second = compose_entry(first, change)
        self.assertIn("Byl Hasbaine", second)
        self.assertEqual(second.count("<h2>Episode: One Door Remaining</h2>"), 1)

    def test_read_back_normalizes_only_kanka_formatting(self):
        cases = [
            ("block whitespace", "<p>First.</p>\n\n<p>Second.</p>", "<p>First.</p><p>Second.</p>", True),
            ("HTML entities", "<p>G. Bramble & Sons</p>", "<p>G. Bramble &amp; Sons</p>", True),
            ("text whitespace", "<p>Grand Key</p>", "<p>Grand  Key</p>", False),
            ("inline spacing", "<p><strong>Grand</strong> Key</p>", "<p><strong>Grand</strong>Key</p>", False),
        ]
        for label, expected, actual, matches in cases:
            with self.subTest(label):
                self.assertEqual(read_back_matches("entry", expected, actual), matches)
        self.assertEqual(
            normalize_kanka_html("<p>First.</p>\n\n<p>Second.</p>"),
            "<p>First.</p><p>Second.</p>",
        )

    def test_gallery_image_resolution_requires_one_exact_name(self):
        class FakeClient:
            def _get(self, path, params=None):
                self.path = path
                self.params = params
                return {
                    "data": [
                        {"id": "one", "name": "Gutterkin", "is_folder": False},
                        {
                            "id": "two",
                            "name": "Gutterkin Concepts",
                            "is_folder": False,
                        },
                    ],
                    "meta": {"last_page": 1},
                }

        client = FakeClient()
        image = resolve_gallery_image(client, "gutterkin")
        self.assertEqual(image["id"], "one")
        self.assertEqual(client.path, "campaigns/410879/images")
        class AmbiguousClient:
            def _get(self, path, params=None):
                return {
                    "data": [
                        {"id": "one", "name": "Gutterkin Pair", "is_folder": False},
                        {"id": "two", "name": "Gutterkin Group", "is_folder": False},
                    ],
                    "meta": {"last_page": 1},
                }

        with self.assertRaises(EpisodeError):
            resolve_gallery_image(AmbiguousClient(), "gutterkin")

    def test_location_parent_resolution_uses_generic_entity_id_and_rejects_missing(self):
        registry = {
            ("locations", "fogport"): [
                {"id": 41, "entity_id": 941, "name": "Fogport"}
            ]
        }
        self.assertEqual(
            resolve_location_parent_entity_id("Fogport", registry),
            941,
        )
        with self.assertRaises(EpisodeError):
            resolve_location_parent_entity_id("Fogport", {})


    def test_location_parent_is_read_from_generic_entity_endpoint(self):
        class FakeClient:
            def __init__(self):
                self.paths = []

            def _get(self, path):
                self.paths.append(path)
                return {"data": {"id": 123, "parent_id": 941}}

        client = FakeClient()
        self.assertEqual(read_location_parent_entity_id(client, 123), 941)
        self.assertEqual(
            client.paths,
            ["campaigns/410879/entities/123"],
        )

    def test_annual_observances_are_a_valid_fifty_event_batch(self):
        document = json.loads(
            Path("kanka_librarian/approved/fogport-annual-observances.json").read_text(
                encoding="utf-8"
            )
        )
        changes = validate_document(document)
        self.assertEqual(len(changes), 50)
        self.assertTrue(all(change["section"] == "events" for change in changes))
        self.assertTrue(all(change.get("date") for change in changes))

    def test_fogport_calendar_document_is_approved_and_provisional(self):
        document = json.loads(
            Path("kanka_librarian/approved/fogport-calendar.json").read_text(
                encoding="utf-8"
            )
        )
        validate_calendar_document(document)
        self.assertEqual(document["approval"]["document_sha256"], calendar_document_digest(document))
        payload = calendar_payload(document)
        self.assertEqual(payload["month_name"][0], "January")
        self.assertEqual(payload["month_name"][-1], "December")
        self.assertEqual(payload["weekday"], ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])

    def test_calendar_readback_requires_the_full_provisional_shape(self):
        document = json.loads(Path("kanka_librarian/approved/fogport-calendar.json").read_text())
        payload = calendar_payload(document)
        actual = {
            "name": "Fogport Calendar",
            "date": "43-1-1",
            "months": [
                {"name": name, "length": length, "type": "standard"}
                for name, length in zip(payload["month_name"], payload["month_length"])
            ],
            "weekdays": payload["weekday"],
            "format": payload["format"],
            "skip_year_zero": True,
        }
        self.assertTrue(calendar_matches(actual, payload))
        actual["months"] = actual["months"][:-1]
        self.assertFalse(calendar_matches(actual, payload))

    def test_calendar_readback_accepts_kanka_api_field_names(self):
        document = json.loads(Path("kanka_librarian/approved/fogport-calendar.json").read_text())
        payload = calendar_payload(document)
        actual = {
            "name": "Fogport Calendar",
            "current_year": 43,
            "current_month": 1,
            "current_day": 1,
            "month_name": payload["month_name"],
            "month_length": payload["month_length"],
            "month_type": payload["month_type"],
            "weekday": payload["weekday"],
            "format": payload["format"],
            "skip_year_zero": 1,
        }
        self.assertTrue(calendar_matches(actual, payload))
        actual["month_length"] = actual["month_length"][:-1]
        self.assertFalse(calendar_matches(actual, payload))

    def test_calendar_readback_accepts_mixed_kanka_serialization(self):
        document = json.loads(Path("kanka_librarian/approved/fogport-calendar.json").read_text())
        payload = calendar_payload(document)
        actual = {
            "name": "Fogport Calendar",
            "date": {"year": "43", "month": 1, "day": 1},
            "months": [
                {"month_name": name, "month_length": str(length), "month_type": "standard"}
                for name, length in zip(payload["month_name"], payload["month_length"])
            ],
            "weekday": {str(index): name for index, name in enumerate(payload["weekday"])},
            "date_format": payload["format"],
            "skip_year_zero": 1,
        }
        self.assertTrue(calendar_matches(actual, payload))

    def test_observance_dates_and_reminders_are_yearly(self):
        self.assertEqual(RECURRENCE_PERIODICITY, "year")
        self.assertLessEqual(len(RECURRENCE_PERIODICITY), 5)
        self.assertEqual(parse_date("October 31"), (10, 31))
        with self.assertRaises(CalendarError):
            parse_date("Fogmonth 1")
        expected = reminder_payload(17, 10, 31, "Long Night of Lanterns")
        actual = {
            "calendar_id": 17, "year": 43, "month": 10, "day": 31,
            "length": 1, "recurring_periodicity": "year", "entity_id": 99,
        }
        self.assertTrue(reminder_matches(actual, expected, 99))
        actual["recurring_periodicity"] = "monthly"
        self.assertFalse(reminder_matches(actual, expected, 99))

    def test_observance_entity_validation_requires_exact_generic_id(self):
        class Client:
            def __init__(self, response):
                self.response = response
                self.paths = []

            def _get(self, path):
                self.paths.append(path)
                return self.response

        client = Client({"data": {"id": 1234, "name": "The First Fog"}})
        self.assertEqual(
            validate_observance_entity(client, name="The First Fog", entity_id=1234)["id"],
            1234,
        )
        self.assertEqual(client.paths, ["campaigns/410879/entities/1234"])

        with self.assertRaises(ValueError):
            validate_observance_entity(
                Client({"data": {"id": 99}}), name="The First Fog", entity_id=1234
            )

    def test_calendar_preflight_validates_all_observances_before_writes(self):
        class Client:
            def __init__(self):
                self.paths = []

            def _get(self, path):
                self.paths.append(path)
                if path.endswith("/1234"):
                    return {"data": {"id": 1234}}
                return {"data": {"id": 9999}}

        changes = [
            {"name": "The First Fog", "date": "January 7"},
            {"name": "Missing Holiday", "date": "February 2"},
        ]
        events = [{"name": "The First Fog", "entity_id": 1234}]
        with self.assertRaisesRegex(CalendarError, "Missing Holiday"):
            prepare_observances(Client(), changes, events)

    def test_calendar_preflight_rejects_invalid_date_before_any_calendar_write(self):
        class Client:
            def _get(self, path):
                return {"data": {"id": 1234}}

        changes = [{"name": "The First Fog", "date": "Fogmonth 1"}]
        events = [{"name": "The First Fog", "entity_id": 1234}]
        with self.assertRaisesRegex(CalendarError, "Unsupported observance month"):
            prepare_observances(Client(), changes, events)

if __name__ == "__main__":
    unittest.main()
