from __future__ import annotations

import unittest
from unittest.mock import MagicMock
import sys

sys.modules.setdefault("requests", MagicMock())
from scripts import publish_approved_gallery as gallery


class GalleryVerificationTests(unittest.TestCase):
    def test_same_name_accepts_filename_or_stem(self):
        self.assertTrue(gallery._same_name({"name": "kitchen-maid.jpg"}, "kitchen-maid.jpg"))
        self.assertTrue(gallery._same_name({"name": "kitchen-maid"}, "kitchen-maid.jpg"))
        self.assertFalse(gallery._same_name({"name": "kitchen-porter"}, "kitchen-maid.jpg"))

    def test_processed_size_is_not_part_of_remote_identity(self):
        remote = {
            "id": "gallery-image-1",
            "name": "kitchen-maid",
            "path": "https://images.kanka.io/processed/kitchen-maid.jpg",
            "size": 12345,
        }
        expected_filename = "kitchen-maid.jpg"

        self.assertEqual(remote["id"], "gallery-image-1")
        self.assertTrue(gallery._same_name(remote, expected_filename))
        self.assertTrue(remote["path"])


if __name__ == "__main__":
    unittest.main()
