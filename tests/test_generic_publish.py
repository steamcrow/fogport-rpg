"""Safety tests for kanka_librarian.generic_publish (the new item/organization publisher)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kanka_librarian.generic_publish import publish_simple_entity
from kanka_librarian.publisher import approve_proposal


def _approved_document(**overrides: object) -> dict:
    proposal = {
        "mode": "proposal-only",
        "campaign_id": 410879,
        "campaign_name": "Fogport",
        "create_order": ["test-item"],
        "approval_questions": [],
        "proposals": [
            {
                "temp_id": "test-item",
                "action": "create",
                "section": "items",
                "name": "Test Item",
                "type": "Trinket",
                "is_private": False,
                "entry": "<p>A test item.</p>",
            }
        ],
    }
    proposal.update(overrides)
    return approve_proposal(proposal, approved_by="Daniel Davis")


class GenericPublishGuardrailTests(unittest.TestCase):
    """These checks all happen before any Kanka API call, so no network or
    token is needed to exercise them — a wrong or tampered manifest must
    be refused before it ever reaches Kanka."""

    def _write(self, tmp: str, document: dict) -> Path:
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_wrong_campaign_is_refused(self) -> None:
        document = _approved_document(campaign_id=29474, campaign_name="MAELSTROS")
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(SystemExit) as caught:
                publish_simple_entity(
                    manifest, Path(tmp) / "r.json",
                    section="items", subject_label="item",
                    list_method="list_items", id_field_name="item_id",
                )
            self.assertIn("refuses campaign", str(caught.exception))

    def test_wrong_section_is_refused(self) -> None:
        document = _approved_document()
        document["proposals"][0]["section"] = "organizations"
        # Re-approve so the digest matches the edited content.
        document.pop("approval")
        document = approve_proposal(document, approved_by="Daniel Davis")
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(SystemExit) as caught:
                publish_simple_entity(
                    manifest, Path(tmp) / "r.json",
                    section="items", subject_label="item",
                    list_method="list_items", id_field_name="item_id",
                )
            self.assertIn("refuses non-items changes", str(caught.exception))

    def test_more_than_one_change_is_refused(self) -> None:
        document = _approved_document()
        second = dict(document["proposals"][0])
        second["temp_id"] = "test-item-2"
        document["proposals"].append(second)
        document["create_order"] = ["test-item", "test-item-2"]
        document.pop("approval")
        document = approve_proposal(document, approved_by="Daniel Davis")
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(SystemExit) as caught:
                publish_simple_entity(
                    manifest, Path(tmp) / "r.json",
                    section="items", subject_label="item",
                    list_method="list_items", id_field_name="item_id",
                )
            self.assertIn("exactly one approved change", str(caught.exception))

    def test_edited_after_approval_is_refused(self) -> None:
        document = _approved_document()
        document["proposals"][0]["name"] = "Tampered Name"
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises((SystemExit, ValueError)):
                publish_simple_entity(
                    manifest, Path(tmp) / "r.json",
                    section="items", subject_label="item",
                    list_method="list_items", id_field_name="item_id",
                )


if __name__ == "__main__":
    unittest.main()
