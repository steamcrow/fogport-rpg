import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.publish_approved_batch import BatchError, batch_digest, validate_batch


def approved_batch(items):
    document = {
        "schema_version": 1,
        "mode": "approved-batch",
        "campaign_id": 410879,
        "campaign_name": "Fogport",
        "items": items,
    }
    document["approval"] = {
        "status": "approved",
        "approved_by": "Daniel Davis",
        "batch_sha256": batch_digest(document),
    }
    return document


class BatchPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "kanka_librarian/approved").mkdir(parents=True)
        (self.root / "kanka_librarian/approved_characters").mkdir(parents=True)
        (self.root / "kanka_librarian/approved_creatures").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / "kanka_librarian/approved/room.json").write_text("{}")
        (self.root / "kanka_librarian/approved_characters/person.json").write_text("{}")
        (self.root / "kanka_librarian/approved_creatures/grig.json").write_text("{}")

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_mixed_approved_batch_in_order(self):
        document = approved_batch(
            [
                {"kind": "location", "proposal": "kanka_librarian/approved/room.json"},
                {
                    "kind": "character",
                    "proposal": "kanka_librarian/approved_characters/person.json",
                },
                {
                    "kind": "creature",
                    "proposal": "kanka_librarian/approved_creatures/grig.json",
                },
            ]
        )
        result = validate_batch(document, self.root)
        self.assertEqual(
            [item[0] for item in result],
            ["location", "character", "creature"],
        )

    def test_rejects_edit_after_approval(self):
        document = approved_batch(
            [{"kind": "location", "proposal": "kanka_librarian/approved/room.json"}]
        )
        document["items"][0]["proposal"] = "kanka_librarian/approved/missing.json"
        with self.assertRaisesRegex(BatchError, "changed after approval"):
            validate_batch(document, self.root)

    def test_rejects_path_traversal(self):
        outside = self.root / "outside.json"
        outside.write_text("{}")
        document = approved_batch(
            [{"kind": "location", "proposal": "kanka_librarian/approved/../../outside.json"}]
        )
        with self.assertRaisesRegex(BatchError, "must be inside"):
            validate_batch(document, self.root)

    def test_rejects_duplicate_items(self):
        item = {"kind": "location", "proposal": "kanka_librarian/approved/room.json"}
        document = approved_batch([item, dict(item)])
        with self.assertRaisesRegex(BatchError, "Duplicate proposal"):
            validate_batch(document, self.root)


if __name__ == "__main__":
    unittest.main()
