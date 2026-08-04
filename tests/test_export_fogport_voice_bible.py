from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.export_fogport_voice_bible import (
    FOGPORT_CAMPAIGN_ID,
    export,
    html_to_markdown,
)


class FakeReadOnlyClient:
    def __init__(self) -> None:
        self.post_reads: list[tuple[int, int]] = []

    def get_campaign(self, campaign_id: int):
        return {"id": campaign_id, "name": "Fogport", "visibility": "private"}

    def list_entities(self, campaign_id: int, *, related: bool = False):
        self.related = related
        return [{
            "id": 9626686,
            "name": "Gamemaster Guide",
            "type": "Ai Guide",
            "entry": "<p>People are <strong>messy</strong>.</p>",
            "is_private": False,
            "updated_at": "2026-08-04T00:00:00Z",
            "attributes": [{"name": "Aspect", "value": "Fogport remembers", "is_private": True}],
            "relations": [{"relation": "guides", "target_id": 7, "visibility_id": 1}],
            "tags": [],
        }]

    def list_entity_posts(self, campaign_id: int, entity_id: int):
        self.post_reads.append((campaign_id, entity_id))
        return [{
            "id": 1413484,
            "name": "GM Style Guide",
            "entry": "<h1>First Rule</h1><p>Fogport is discovered.</p>",
            "visibility_id": 3,
            "is_private": True,
            "position": 1,
        }]


class FogportVoiceBibleTests(unittest.TestCase):
    def test_html_conversion_preserves_structure(self) -> None:
        rendered = html_to_markdown("<h2>Rule</h2><ul><li>One</li><li><b>Two</b></li></ul>")
        self.assertIn("## Rule", rendered)
        self.assertIn("- One", rendered)
        self.assertIn("- **Two**", rendered)

    def test_complete_export_reads_exact_campaign_and_every_entity_post(self) -> None:
        client = FakeReadOnlyClient()
        with tempfile.TemporaryDirectory() as temporary:
            markdown_path, snapshot_path, instructions_path = export(client, Path(temporary))
            markdown = markdown_path.read_text(encoding="utf-8")
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertTrue(client.related)
        self.assertEqual(client.post_reads, [(FOGPORT_CAMPAIGN_ID, 9626686)])
        self.assertIn("Gamemaster Guide", markdown)
        self.assertIn("People are **messy**.", markdown)
        self.assertIn("GM CONFIDENTIAL", markdown)
        self.assertIn("PRIVATE / GM-RESTRICTED", markdown)
        self.assertIn("Fogport is discovered.", markdown)
        self.assertEqual(snapshot["campaign"]["id"], FOGPORT_CAMPAIGN_ID)
        self.assertEqual(snapshot["counts"], {"entities": 1, "private_entities": 0, "posts": 1})
        self.assertTrue(instructions_path.name == "START_HERE.txt")

    def test_campaign_identity_mismatch_stops_before_entity_reads(self) -> None:
        class WrongCampaignClient(FakeReadOnlyClient):
            def get_campaign(self, campaign_id: int):
                return {"id": campaign_id, "name": "MAELSTROS"}

            def list_entities(self, campaign_id: int, *, related: bool = False):
                self.fail("must not read wrong campaign")

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(Exception):
                export(WrongCampaignClient(), Path(temporary))


if __name__ == "__main__":
    unittest.main()
