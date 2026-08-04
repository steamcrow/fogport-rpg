"""Read the exact Fogport Gamemaster Note without changing Kanka."""

from __future__ import annotations

import json
import os
from pathlib import Path

from kanka_librarian.client import KankaClient


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
TARGET_ENTITY_ID = 9626686


def select_target(notes: list[dict]) -> dict:
    matches = [
        note for note in notes
        if int(note.get("entity_id", 0)) == TARGET_ENTITY_ID
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly one Note with entity ID {TARGET_ENTITY_ID}; "
            f"found {len(matches)}. Nothing was changed."
        )
    return matches[0]


def main() -> None:
    token = os.environ["KANKA_API_TOKEN"]
    output = Path(
        os.environ.get(
            "REPORT_PATH", "receipts/fogport-gm-note-inspection.json"
        )
    )
    client = KankaClient(token)

    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Campaign identity mismatch; nothing was read or changed.")

    note = select_target(client.list_notes(CAMPAIGN_ID, related=True))
    entity = client._get(
        f"campaigns/{CAMPAIGN_ID}/entities/{TARGET_ENTITY_ID}"
    ).get("data", {})
    posts = client.list_entity_posts(CAMPAIGN_ID, TARGET_ENTITY_ID)

    report = {
        "schema_version": 1,
        "mode": "read-only-exact-entity-inspection",
        "campaign_id": CAMPAIGN_ID,
        "campaign_name": CAMPAIGN_NAME,
        "target_entity_id": TARGET_ENTITY_ID,
        "overview_url": (
            f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{TARGET_ENTITY_ID}"
        ),
        "note": note,
        "entity": entity,
        "posts": posts,
        "writes_attempted": 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
