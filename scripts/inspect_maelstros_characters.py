#!/usr/bin/env python3
"""Inspect MAELSTROS characters without changing any Kanka data."""

from __future__ import annotations

import os
import sys
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


def clean(value: Any, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def character_summary(character: dict[str, Any]) -> str:
    name = clean(character.get("name"), "Unnamed character")
    character_id = character.get("id", "?")
    character_type = clean(character.get("type"))
    title = clean(character.get("title"))
    location_id = character.get("location_id")
    location = f"location:{location_id}" if location_id else "location:—"
    privacy = "PRIVATE" if character.get("is_private") else "PUBLIC"
    dead = "DEAD" if character.get("is_dead") else "ACTIVE/UNKNOWN"
    return (
        f"- {name} [character:{character_id}]\n"
        f"  type: {character_type} | title: {title}\n"
        f"  {location} | visibility: {privacy} | status: {dead}"
    )


def main() -> int:
    load_dotenv(ROOT / ".env")

    if MAELSTROS_CAMPAIGN_ID == FOGPORT_CAMPAIGN_ID:
        print("SAFETY STOP: MAELSTROS and Fogport campaign IDs must never match.", file=sys.stderr)
        return 2

    token = os.getenv("KANKA_API_TOKEN", "")
    base_url = os.getenv("KANKA_API_BASE_URL", "https://api.kanka.io/1.0")

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

        characters = client.list_characters(MAELSTROS_CAMPAIGN_ID)
    except KankaError as exc:
        print(f"Kanka Librarian error: {exc}", file=sys.stderr)
        return 1

    characters.sort(key=lambda item: str(item.get("name") or "").casefold())

    print("KANKA LIBRARIAN — READ-ONLY CHARACTER INSPECTION")
    print(f"Target campaign: {actual_name} (ID: {actual_id})")
    print(f"Protected campaign: Fogport (ID: {FOGPORT_CAMPAIGN_ID}) — NOT ACCESSED")
    print("Allowed operation: HTTP GET only")
    print(f"Characters found: {len(characters)}\n")

    if characters:
        for character in characters:
            print(character_summary(character))
    else:
        print("No characters were found in MAELSTROS.")

    print("\nRead-only character inspection complete.")
    print("No Kanka data was created, updated, deleted, copied, or moved.")
    print("Fogport was not read or modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
