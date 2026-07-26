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
    resolve_location_parent_id,
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

    def test_location_parent_uses_location_resource_id(self):
        registry = {
            ("locations", "fogport"): [
                {"id": 41, "entity_id": 941, "name": "Fogport"}
            ]
        }
        self.assertEqual(resolve_location_parent_id("Fogport", registry), 41)

    def test_missing_location_parent_stops(self):
        with self.assertRaises(EpisodeError):
            resolve_location_parent_id("Fogport", {})


if __name__ == "__main__":
    unittest.main()
