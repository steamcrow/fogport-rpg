"""Safety tests for kanka_librarian.era_publish (the new timeline-era publisher)."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from kanka_librarian.era_publish import approve_era_document, publish_era


def _approved_document(**overrides: object) -> dict:
    document = {
        "schema_version": 1,
        "mode": "proposal-only",
        "campaign_id": 410879,
        "campaign_name": "Fogport",
        "timeline_name": "Fogport History",
        "era": {
            "name": "The Drowned Years",
            "abbreviation": "DY",
            "start_year": -40,
            "end_year": 0,
            "visibility": "all",
        },
    }
    document.update(overrides)
    return approve_era_document(
        document,
        approved_by="Daniel Davis",
        approved_at=datetime.now(timezone.utc).isoformat(),
    )


class EraPublishGuardrailTests(unittest.TestCase):
    """These checks all happen before any Kanka API call, so a wrong or
    tampered era document is refused before it ever reaches Kanka."""

    def _write(self, tmp: str, document: dict) -> Path:
        path = Path(tmp) / "era.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_wrong_campaign_is_refused(self) -> None:
        document = _approved_document(campaign_id=29474, campaign_name="MAELSTROS")
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(ValueError) as caught:
                publish_era(manifest, Path(tmp) / "r.json")
            self.assertIn("locked to Fogport", str(caught.exception))

    def test_missing_timeline_name_is_refused(self) -> None:
        document = _approved_document()
        document["timeline_name"] = ""
        document.pop("approval")
        document = approve_era_document(
            document, approved_by="Daniel Davis",
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(ValueError) as caught:
                publish_era(manifest, Path(tmp) / "r.json")
            self.assertIn("timeline_name", str(caught.exception))

    def test_missing_abbreviation_is_refused(self) -> None:
        document = _approved_document()
        document["era"] = {"name": "The Drowned Years"}
        document.pop("approval")
        document = approve_era_document(
            document, approved_by="Daniel Davis",
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(ValueError) as caught:
                publish_era(manifest, Path(tmp) / "r.json")
            self.assertIn("abbreviation", str(caught.exception))

    def test_edited_after_approval_is_refused(self) -> None:
        document = _approved_document()
        document["era"]["name"] = "Tampered Era Name"
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(ValueError) as caught:
                publish_era(manifest, Path(tmp) / "r.json")
            self.assertIn("changed after approval", str(caught.exception))

    def test_unapproved_document_is_refused(self) -> None:
        document = _approved_document()
        document["approval"]["status"] = "pending"
        with TemporaryDirectory() as tmp:
            manifest = self._write(tmp, document)
            with self.assertRaises(ValueError) as caught:
                publish_era(manifest, Path(tmp) / "r.json")
            self.assertIn("approval is required", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
