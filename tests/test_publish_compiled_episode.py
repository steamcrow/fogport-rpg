from __future__ import annotations

import json
from pathlib import Path
import unittest

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


class CompiledEpisodeTests(unittest.TestCase):
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

    def test_annual_observances_are_a_valid_twenty_event_batch(self):
        document = json.loads(
            Path("kanka_librarian/approved/fogport-annual-observances.json").read_text(
                encoding="utf-8"
            )
        )
        changes = validate_document(document)
        self.assertEqual(len(changes), 20)
        self.assertTrue(all(change["section"] == "events" for change in changes))
        self.assertTrue(all(change.get("date") for change in changes))

if __name__ == "__main__":
    unittest.main()
