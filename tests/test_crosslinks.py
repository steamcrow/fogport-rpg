import json
from pathlib import Path
import tempfile
import unittest

from kanka_librarian.crosslinks import build_registry, link_entry, load_aliases


REGISTRY = {
    "schema_version": 1,
    "campaign_id": 410879,
    "entities": [
        {
            "canonical_name": "Mercy Vale",
            "aliases": ["Mercy"],
            "section": "characters",
            "endpoint": "characters",
            "kanka_id": 10,
            "entity_id": 110,
            "is_private": False,
            "entry": "",
        },
        {
            "canonical_name": "The Twisted Eel Pawnshop",
            "aliases": ["Twisted Eel", "the Eel"],
            "section": "locations",
            "endpoint": "locations",
            "kanka_id": 20,
            "entity_id": 120,
            "is_private": False,
            "entry": "",
        },
        {
            "canonical_name": "Secret Door",
            "aliases": [],
            "section": "locations",
            "endpoint": "locations",
            "kanka_id": 30,
            "entity_id": 130,
            "is_private": True,
            "entry": "",
        },
    ],
}


class FakeClient:
    def list_locations(self, campaign_id):
        return [{"id": 20, "entity_id": 120, "name": "The Twisted Eel Pawnshop"}]

    def list_characters(self, campaign_id):
        return [{"id": 10, "entity_id": 110, "name": "Mercy Vale", "entry": "x"}]


class CrosslinkTests(unittest.TestCase):
    def test_links_first_occurrence_only_and_longest_alias_first(self):
        linked, report = link_entry(
            "Mercy owns the Twisted Eel. Mercy likes the Eel.",
            REGISTRY,
        )
        self.assertEqual(linked.count("[entity:110|Mercy]"), 1)
        self.assertIn("[entity:120|Twisted Eel]", linked)
        self.assertEqual(len(report["links_added"]), 2)

    def test_preserves_html_tags_and_existing_links(self):
        linked, report = link_entry(
            '<a title="Mercy">Mercy</a> [entity:120|the Eel] Mercy',
            REGISTRY,
        )
        self.assertIn('title="Mercy"', linked)
        self.assertEqual(linked.count("[entity:110|Mercy]"), 1)
        self.assertEqual(linked.count("[entity:120|the Eel]"), 1)
        self.assertEqual(len(report["links_added"]), 1)

    def test_skips_self_links_and_private_targets_in_public_text(self):
        linked, _ = link_entry(
            "Mercy found the Secret Door.",
            REGISTRY,
            source_entity_id=110,
            source_private=False,
        )
        self.assertEqual(linked, "Mercy found the Secret Door.")

    def test_private_text_can_link_private_targets(self):
        linked, _ = link_entry(
            "Mercy found the Secret Door.",
            REGISTRY,
            source_private=True,
        )
        self.assertIn("[entity:130|Secret Door]", linked)

    def test_ambiguous_alias_is_never_linked(self):
        registry = json.loads(json.dumps(REGISTRY))
        registry["entities"].append(
            {
                **registry["entities"][0],
                "canonical_name": "Mercy Island",
                "entity_id": 999,
                "aliases": ["Mercy"],
            }
        )
        linked, report = link_entry("Mercy waits.", registry)
        self.assertEqual(linked, "Mercy waits.")
        self.assertIn("mercy", report["ambiguous_phrases"])

    def test_registry_contains_both_ids(self):
        registry = build_registry(
            FakeClient(),
            410879,
            {"Mercy Vale": ["Mercy"]},
            sections=["locations", "characters"],
        )
        mercy = next(item for item in registry["entities"] if item["canonical_name"] == "Mercy Vale")
        self.assertEqual((mercy["kanka_id"], mercy["entity_id"]), (10, 110))
        self.assertEqual(mercy["aliases"], ["Mercy"])

    def test_alias_file_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aliases.json"
            path.write_text('{"schema_version":1,"aliases":{"Mercy Vale":["Mercy"]}}')
            self.assertEqual(load_aliases(path), {"Mercy Vale": ["Mercy"]})


if __name__ == "__main__":
    unittest.main()

