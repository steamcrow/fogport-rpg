import json
from pathlib import Path
import tempfile
import unittest

from scripts.crosslink_cleanup import CleanupError, cleanup_digest, validate_manifest


def approved_manifest(alias_path="kanka_librarian/crosslink_aliases.json"):
    document = {
        "schema_version": 1,
        "mode": "approved-crosslink-cleanup",
        "campaign_id": 410879,
        "campaign_name": "Fogport",
        "sections": ["locations", "characters"],
        "include_posts": True,
        "aliases": alias_path,
        "link_policy": "first-meaningful-occurrence",
        "preserve_prose": True,
    }
    document["approval"] = {
        "status": "approved",
        "approved_by": "Daniel Davis",
        "cleanup_sha256": cleanup_digest(document),
    }
    return document


class CleanupManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "kanka_librarian").mkdir()
        (self.root / "kanka_librarian/crosslink_aliases.json").write_text(
            json.dumps({"schema_version": 1, "aliases": {}}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_locked_link_only_cleanup(self):
        sections, aliases = validate_manifest(approved_manifest(), self.root)
        self.assertEqual(sections, ["locations", "characters"])
        self.assertEqual(aliases.name, "crosslink_aliases.json")

    def test_rejects_edit_after_approval(self):
        document = approved_manifest()
        document["include_posts"] = False
        with self.assertRaisesRegex(CleanupError, "changed after approval"):
            validate_manifest(document, self.root)

    def test_rejects_alias_path_traversal(self):
        outside = self.root / "aliases.json"
        outside.write_text("{}", encoding="utf-8")
        document = approved_manifest("../aliases.json")
        with self.assertRaisesRegex(CleanupError, "inside kanka_librarian"):
            validate_manifest(document, self.root)

    def test_rejects_non_link_only_policy(self):
        document = approved_manifest()
        document["preserve_prose"] = False
        document["approval"]["cleanup_sha256"] = cleanup_digest(document)
        with self.assertRaisesRegex(CleanupError, "prose preservation"):
            validate_manifest(document, self.root)


if __name__ == "__main__":
    unittest.main()
