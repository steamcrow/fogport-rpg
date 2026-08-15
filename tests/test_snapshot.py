"""Safety tests for kanka_librarian.snapshot (the read-only campaign index)."""

from __future__ import annotations

import unittest
from typing import Any

from kanka_librarian.snapshot import build_snapshot


class FakeClient:
    """A minimal stand-in for KankaClient -- no network, fixed data."""

    def __init__(self) -> None:
        self._pages: dict[str, list[dict[str, Any]]] = {}

    def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return {"id": campaign_id, "name": "Fogport"}

    def list_characters(self, campaign_id: int) -> list[dict[str, Any]]:
        return [
            {"id": 2, "entity_id": 20, "name": "Zed", "type": "Rogue", "is_private": False, "entry": "<p>secret bio</p>"},
            {"id": 1, "entity_id": 10, "name": "Anna", "type": "Guard", "is_private": True, "entry": "<p>secret bio</p>"},
        ]

    def list_creatures(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_locations(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_organizations(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_items(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_notes(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_journals(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_events(self, campaign_id: int) -> list[dict[str, Any]]:
        return [{"id": 5, "entity_id": 50, "name": "The Catastrophe", "type": "Disaster", "is_private": False, "date": "0-1-1"}]

    def list_quests(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_races(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def list_families(self, campaign_id: int) -> list[dict[str, Any]]:
        return []

    def _get_all_pages(self, path: str) -> list[dict[str, Any]]:
        if path.endswith("/timelines"):
            return [{"id": 7, "name": "Fogport History"}]
        if "timeline_eras" in path:
            return [{"id": 70, "name": "Before", "abbreviation": "B", "start_year": -100, "end_year": 0}]
        return []


class SnapshotTests(unittest.TestCase):
    def test_campaign_identity_is_checked(self) -> None:
        client = FakeClient()
        with self.assertRaises(ValueError):
            build_snapshot(client, campaign_id=410879, campaign_name="Not Fogport")

    def test_entities_are_slimmed_and_sorted_by_name(self) -> None:
        client = FakeClient()
        snapshot = build_snapshot(client, campaign_id=410879, campaign_name="Fogport")
        characters = snapshot["entities"]["characters"]
        self.assertEqual([c["name"] for c in characters], ["Anna", "Zed"])
        # No description/body text should leak into the snapshot.
        for character in characters:
            self.assertNotIn("entry", character)

    def test_private_flag_is_preserved_not_hidden(self) -> None:
        # Privacy is about what Kanka itself shows publicly, not about
        # hiding structure from this repo -- the repo already contains
        # GM-only post bodies in the approved_*/ manifests. Dropping the
        # is_private flag here would make the snapshot actively misleading.
        client = FakeClient()
        snapshot = build_snapshot(client, campaign_id=410879, campaign_name="Fogport")
        anna = next(c for c in snapshot["entities"]["characters"] if c["name"] == "Anna")
        self.assertTrue(anna["is_private"])

    def test_events_keep_their_date(self) -> None:
        client = FakeClient()
        snapshot = build_snapshot(client, campaign_id=410879, campaign_name="Fogport")
        event = snapshot["entities"]["events"][0]
        self.assertEqual(event["date"], "0-1-1")

    def test_timelines_and_eras_are_included(self) -> None:
        client = FakeClient()
        snapshot = build_snapshot(client, campaign_id=410879, campaign_name="Fogport")
        self.assertEqual(len(snapshot["timelines"]), 1)
        self.assertEqual(snapshot["timelines"][0]["name"], "Fogport History")
        self.assertEqual(snapshot["timelines"][0]["eras"][0]["name"], "Before")

    def test_snapshot_states_it_is_not_authoritative(self) -> None:
        client = FakeClient()
        snapshot = build_snapshot(client, campaign_id=410879, campaign_name="Fogport")
        self.assertIn("not authoritative for publishing", snapshot["note"].lower())


if __name__ == "__main__":
    unittest.main()
