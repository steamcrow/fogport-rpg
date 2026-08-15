"""Publish one approved era onto an existing Fogport Kanka timeline.

This does NOT create new timelines — only Daniel's explicit call for a new
timeline gets a new bespoke script, the same way `publish_fogport_history.py`
was built for the one existing "Fogport History" timeline. Adding a new
ERA to a timeline that already exists, though, is exactly the kind of
repeatable, no-new-code-needed operation the rest of the menu already
handles for characters/creatures/locations/items/organizations. This file
extends that same pattern to eras.

To add a new era: drop an approved JSON file (see the shape below) into
kanka_librarian/approved_eras/, run scripts/refresh_publish_menu.py, and
publish it from the dropdown — no new script needed.

Approved file shape:
{
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
    "visibility": "all"
  },
  "approval": {
    "status": "approved",
    "approved_by": "Daniel Davis",
    "approved_at": "...",
    "document_sha256": "..."
  }
}
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .client import KankaClient
from .writer import KankaWriter

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


class EraPublishError(ValueError):
    """Raised before an unsafe or ambiguous era publication."""


def era_document_digest(document: dict[str, Any]) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def approve_era_document(document: dict[str, Any], *, approved_by: str, approved_at: str) -> dict[str, Any]:
    """Stamp a correct, matching approval block onto an era document."""
    approved = deepcopy(document)
    approved.pop("approval", None)
    digest = era_document_digest(approved)
    approved["approval"] = {
        "status": "approved",
        "approved_by": approved_by,
        "approved_at": approved_at,
        "document_sha256": digest,
    }
    return approved


def _validate(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 1:
        raise EraPublishError("Expected era schema version 1.")
    if document.get("mode") != "proposal-only":
        raise EraPublishError("Only proposal-only era documents can be approved.")
    if int(document.get("campaign_id", 0)) != CAMPAIGN_ID:
        raise EraPublishError("Era publisher is locked to Fogport 410879.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise EraPublishError("Campaign name must be Fogport.")
    if not str(document.get("timeline_name", "")).strip():
        raise EraPublishError("Approved era document needs timeline_name.")
    era = document.get("era")
    if not isinstance(era, dict) or not str(era.get("name", "")).strip():
        raise EraPublishError("Approved era document needs era.name.")
    if not str(era.get("abbreviation", "")).strip():
        raise EraPublishError("Approved era needs an abbreviation.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or approval.get("approved_by") != "Daniel Davis":
        raise EraPublishError("Daniel Davis approval is required.")
    if approval.get("document_sha256") != era_document_digest(document):
        raise EraPublishError("Era document changed after approval; approval is invalid.")


def _exact_match(records: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any] | None:
    matches = [
        item for item in records
        if str(item.get("name", "")).strip().casefold() == name.strip().casefold()
    ]
    if len(matches) > 1:
        raise EraPublishError(f"Multiple {kind} records named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def publish_era(proposal_path: Path, receipt_path: Path) -> None:
    document = json.loads(proposal_path.read_text(encoding="utf-8"))
    _validate(document)

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)

    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise EraPublishError("Kanka campaign identity lock failed.")

    timeline_name = str(document["timeline_name"]).strip()
    timelines = client._get_all_pages(f"campaigns/{CAMPAIGN_ID}/timelines")
    timeline = _exact_match(timelines, timeline_name, "timeline")
    if timeline is None:
        raise EraPublishError(
            f"Timeline {timeline_name!r} does not exist yet. This publisher only "
            "adds an era to an EXISTING timeline; creating a brand-new timeline "
            "still needs a dedicated script."
        )
    timeline_id = int(timeline["id"])

    era = document["era"]
    era_name = str(era["name"])
    path = f"campaigns/{CAMPAIGN_ID}/timelines/{timeline_id}/timeline_eras"
    existing_eras = client._get_all_pages(path)
    match = _exact_match(existing_eras, era_name, "timeline era")

    # Kanka's public docs call this input field "era", while the live API
    # currently validates "name". Send both with the same value, matching
    # the convention already used in publish_fogport_history.py.
    payload = {
        "name": era_name,
        "era": era_name,
        "abbreviation": str(era["abbreviation"]),
        "start_year": era.get("start_year"),
        "end_year": era.get("end_year"),
        "visibility": str(era.get("visibility", "all")),
    }

    if match:
        era_id = int(match["id"])
        writer._send("PATCH", f"{path}/{era_id}", payload)
        created = False
    else:
        era_id = int(writer._send("POST", path, payload)["id"])
        created = True

    direct = client._get(f"{path}/{era_id}").get("data", {})
    if str(direct.get("name")) != era_name:
        raise EraPublishError(f"Timeline era read-back failed for {era_name!r}.")

    receipt = {
        "published": True,
        "created": created,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "timeline_id": timeline_id,
        "timeline_name": timeline_name,
        "era_id": era_id,
        "era_name": era_name,
        "start_year": direct.get("start_year"),
        "end_year": direct.get("end_year"),
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/timelines/{timeline_id}",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Fogport timeline era verified\n\n")
            stream.write(f"- Era: **{era_name}** on timeline **{timeline_name}**\n")
            stream.write(f"- [Open Kanka Timeline]({receipt['overview_url']})\n")
