#!/usr/bin/env python3
"""Export a read-only, machine-readable snapshot of MAELSTROS."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kanka_librarian import KankaClient, KankaError  # noqa: E402

MAELSTROS_CAMPAIGN_ID = 29474
MAELSTROS_EXPECTED_NAME = "MAELSTROS"
FOGPORT_CAMPAIGN_ID = 410879
DEFAULT_OUTPUT = ROOT / "artifacts" / "maelstros-snapshot.json"


def selected_fields(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Keep only stable fields needed to compare a later proposal with Kanka."""
    return {field: item.get(field) for field in fields}


def build_snapshot(
    campaign: dict[str, Any],
    locations: list[dict[str, Any]],
    characters: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only",
        "campaign": selected_fields(
            campaign,
            ("id", "name", "visibility", "locale"),
        ),
        "protected_campaign": {
            "id": FOGPORT_CAMPAIGN_ID,
            "name": "Fogport",
            "accessed": False,
        },
        "locations": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "type",
                    "parent_id",
                    "is_private",
                    "entry",
                    "image",
                    "image_full",
                    "updated_at",
                ),
            )
            for item in sorted(
                locations,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "characters": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "type",
                    "title",
                    "location_id",
                    "is_private",
                    "is_dead",
                    "entry",
                    "image",
                    "image_full",
                    "updated_at",
                ),
            )
            for item in sorted(
                characters,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
    }


def main() -> int:
    load_dotenv(ROOT / ".env")

    if MAELSTROS_CAMPAIGN_ID == FOGPORT_CAMPAIGN_ID:
        print("SAFETY STOP: MAELSTROS and Fogport campaign IDs must never match.", file=sys.stderr)
        return 2

    token = os.getenv("KANKA_API_TOKEN", "")
    base_url = os.getenv("KANKA_API_BASE_URL", "https://api.kanka.io/1.0")
    output_path = Path(os.getenv("KANKA_SNAPSHOT_PATH", str(DEFAULT_OUTPUT)))

    try:
        client = KankaClient(token=token, base_url=base_url)
        campaign = client.get_campaign(MAELSTROS_CAMPAIGN_ID)
        actual_id = campaign.get("id")
        actual_name = str(campaign.get("name") or "")
        if actual_id != MAELSTROS_CAMPAIGN_ID or actual_name.casefold() != MAELSTROS_EXPECTED_NAME.casefold():
            raise KankaError(
                "SAFETY STOP: campaign identity mismatch. "
                f"Expected {MAELSTROS_EXPECTED_NAME} ({MAELSTROS_CAMPAIGN_ID}), "
                f"received {actual_name or 'Unnamed'} ({actual_id})."
            )

        locations = client.list_locations(MAELSTROS_CAMPAIGN_ID)
        characters = client.list_characters(MAELSTROS_CAMPAIGN_ID)
    except KankaError as exc:
        print(f"Kanka Librarian error: {exc}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(campaign, locations, characters)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("KANKA LIBRARIAN — READ-ONLY SNAPSHOT")
    print(f"Target campaign: {actual_name} (ID: {actual_id})")
    print(f"Protected campaign: Fogport (ID: {FOGPORT_CAMPAIGN_ID}) — NOT ACCESSED")
    print(f"Locations exported: {len(locations)}")
    print(f"Characters exported: {len(characters)}")
    print(f"Snapshot written to: {output_path}")
    print("No Kanka data was created, updated, deleted, copied, or moved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
