from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.cleanup_misplaced_gm_journals import MISPLACED, inventory
from scripts.publish_exact_gamemaster_guide import (
    CAMPAIGN_ID,
    ENTITY_ID,
    NOTE_ID,
    POST_ID,
    digest,
    verify_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "kanka_librarian/approved_notes/gamemaster-guide-v2.json"


class ExactGamemasterGuideFixTests(unittest.TestCase):
    def test_manifest_is_approved_and_exactly_locked(self) -> None:
        document = json.loads(MANIFEST.read_text())
        verify_manifest(document)
        self.assertEqual((CAMPAIGN_ID, NOTE_ID, ENTITY_ID, POST_ID), (410879, 332976, 9626686, 1413484))
        self.assertEqual(document["approval"]["document_sha256"], digest(document))

    def test_cleanup_is_locked_to_nine_exact_journals(self) -> None:
        self.assertEqual(len(MISPLACED), 9)
        records = [
            {"name": name, "id": ids[0], "entity_id": ids[1]}
            for name, ids in MISPLACED.items()
        ]
        self.assertEqual(inventory(records), MISPLACED)
        records[0]["entity_id"] += 1
        self.assertNotEqual(inventory(records), MISPLACED)


if __name__ == "__main__":
    unittest.main()
