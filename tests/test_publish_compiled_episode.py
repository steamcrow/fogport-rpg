from __future__ import annotations

import sys
from types import ModuleType
import unittest

client_module = ModuleType("kanka_librarian.client")
client_module.KankaClient = object
writer_module = ModuleType("kanka_librarian.writer")
writer_module.KankaWriter = object
sys.modules.setdefault("kanka_librarian.client", client_module)
sys.modules.setdefault("kanka_librarian.writer", writer_module)

from scripts.publish_compiled_episode import (
    EpisodeError,
    compose_entry,
    find_match,
    normalize_kanka_html,
    read_back_matches,
    resolve_location_parent_entity_id,
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

    def test_kanka_block_tag_whitespace_is_equivalent(self):
        expected = "<p>First.</p>\n\n<p>Second.</p>"
        actual = "<p>First.</p><p>Second.</p>"
        self.assertEqual(normalize_kanka_html(expected), actual)
        self.assertTrue(read_back_matches("entry", expected, actual))

    def test_kanka_html_entities_are_equivalent(self):
        expected = (
            "<p>A key made by "
            "[entity:9618502|G. Bramble & Sons].</p>"
        )
        actual = (
            "<p>A key made by "
            "[entity:9618502|G. Bramble &amp; Sons].</p>"
        )
        self.assertTrue(read_back_matches("entry", expected, actual))

    def test_text_whitespace_remains_strict(self):
        self.assertFalse(
            read_back_matches(
                "entry",
                "<p>Grand Key</p>",
                "<p>Grand  Key</p>",
            )
        )

    def test_inline_tag_spacing_remains_strict(self):
        self.assertFalse(
            read_back_matches(
                "entry",
                "<p><strong>Grand</strong> Key</p>",
                "<p><strong>Grand</strong>Key</p>",
            )
        )

    def test_location_parent_uses_generic_entity_id(self):
        registry = {
            ("locations", "fogport"): [
                {"id": 41, "entity_id": 941, "name": "Fogport"}
            ]
        }
        self.assertEqual(
            resolve_location_parent_entity_id("Fogport", registry),
            941,
        )

    def test_missing_location_parent_stops(self):
        with self.assertRaises(EpisodeError):
            resolve_location_parent_entity_id("Fogport", {})


if __name__ == "__main__":
    unittest.main()
