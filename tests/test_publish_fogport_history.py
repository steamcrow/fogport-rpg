from __future__ import annotations

import json
from pathlib import Path
import sys
from types import ModuleType
import unittest

client_module = ModuleType("kanka_librarian.client")
client_module.KankaClient = object
writer_module = ModuleType("kanka_librarian.writer")
writer_module.KankaWriter = object
sys.modules.setdefault("kanka_librarian.client", client_module)
sys.modules.setdefault("kanka_librarian.writer", writer_module)

from scripts.publish_fogport_history import (
    HistoryError,
    document_digest,
    exact_match,
    render_references,
    validate,
)


class FogportHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(
            Path("fogport_history.json").read_text(encoding="utf-8")
        )

    def test_approval_digest(self):
        validate(self.document)

    def test_catastrophe_is_public_and_linked_to_timeline(self):
        catastrophe = next(
            item for item in self.document["entities"] if item["key"] == "catastrophe"
        )
        self.assertFalse(catastrophe["is_private"])
        self.assertIn("11:17", catastrophe["entry"])
        self.assertIn("Gutterkin", catastrophe["entry"])
        element = next(
            item for item in self.document["elements"]
            if item["entity_key"] == "catastrophe"
        )
        self.assertEqual(element["era_key"], "after")
        self.assertEqual(element["visibility_id"], 1)

    def test_catastrophe_truth_is_gm_only(self):
        catastrophe = next(
            item for item in self.document["entities"] if item["key"] == "catastrophe"
        )
        secret = catastrophe["posts"][0]
        self.assertEqual(secret["visibility_id"], 3)
        self.assertIn("Continuance Engine", secret["entry"])
        self.assertNotIn("Continuance Engine", catastrophe["entry"])

    def test_gutterkin_origin_is_now_definite(self):
        gutterkin = next(
            item for item in self.document["entities"] if item["key"] == "gutterkin"
        )
        self.assertIn("ordinary children once", gutterkin["entry"])
        self.assertNotIn("true origin has not been established", gutterkin["posts"][0]["entry"])

    def test_exact_match_rejects_ambiguity(self):
        with self.assertRaises(HistoryError):
            exact_match(
                [{"name": "The Catastrophe"}, {"name": "the catastrophe"}],
                "The Catastrophe",
                "event",
            )

    def test_references_use_generic_entity_id(self):
        rendered = render_references(
            "<p>The Catastrophe changed Fogport.</p>",
            [{"phrase": "Catastrophe", "key": "catastrophe"}],
            {},
            {
                "catastrophe": {
                    "id": 10,
                    "entity_id": 999,
                    "name": "The Catastrophe",
                    "_section": "events",
                }
            },
        )
        self.assertIn("[entity:999|Catastrophe]", rendered)


if __name__ == "__main__":
    unittest.main()
