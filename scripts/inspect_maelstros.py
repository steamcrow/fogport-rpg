#!/usr/bin/env python3
"""Inspect MAELSTROS locations without changing any Kanka data."""

from __future__ import annotations

import os
import sys
from collections import defaultdict
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


def display_name(location: dict[str, Any]) -> str:
    name = str(location.get("name") or "Unnamed location")
    location_type = str(location.get("type") or "").strip()
    privacy = " [PRIVATE]" if location.get("is_private") else ""
    type_suffix = f" ({location_type})" if location_type else ""
    return f"{name}{type_suffix}{privacy}"


def print_location_tree(locations: list[dict[str, Any]]) -> None:
    """Print a hierarchy, matching Kanka parent IDs against entity IDs or location IDs."""
    by_location_id = {
        int(item["id"]): item
        for item in locations
        if isinstance(item.get("id"), int)
    }
    by_entity_id = {
        int(item["entity_id"]): item
        for item in locations
        if isinstance(item.get("entity_id"), int)
    }

    children: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    resolved_parent: dict[int, int | None] = {}

    for item in locations:
        item_id = item.get("id")
        if not isinstance(item_id, int):
            continue

        parent_id = item.get("parent_id")
        parent_location: dict[str, Any] | None = None
        if isinstance(parent_id, int):
            parent_location = by_entity_id.get(parent_id) or by_location_id.get(parent_id)

        parent_location_id = (
            int(parent_location["id"])
            if parent_location and isinstance(parent_location.get("id"), int)
            else None
        )
        resolved_parent[item_id] = parent_location_id
        children[parent_location_id].append(item)

    for siblings in children.values():
        siblings.sort(key=lambda item: str(item.get("name", "")).casefold())

    visited: set[int] = set()

    def walk(item: dict[str, Any], prefix: str, is_last: bool) -> None:
        item_id = item.get("id")
        if not isinstance(item_id, int):
            return
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{display_name(item)} [location:{item_id}]")
        if item_id in visited:
            print(f"{prefix}{'    ' if is_last else '│   '}└── [cycle detected]")
            return
        visited.add(item_id)
        descendants = children.get(item_id, [])
        next_prefix = prefix + ("    " if is_last else "│   ")
        for index, child in enumerate(descendants):
            walk(child, next_prefix, index == len(descendants) - 1)

    roots = children.get(None, [])
    for index, root in enumerate(roots):
        walk(root, "", index == len(roots) - 1)

    orphans = [item for item in locations if isinstance(item.get("id"), int) and item["id"] not in visited]
    if orphans:
        print("\nUnresolved/orphaned locations:")
        for item in sorted(orphans, key=lambda value: str(value.get("name", "")).casefold()):
            print(
                f"- {display_name(item)} [location:{item.get('id')}, "
                f"parent_id:{item.get('parent_id')}]"
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

        locations = client.list_locations(MAELSTROS_CAMPAIGN_ID)
    except KankaError as exc:
        print(f"Kanka Librarian error: {exc}", file=sys.stderr)
        return 1

    print("KANKA LIBRARIAN — READ-ONLY INSPECTION")
    print(f"Target campaign: {actual_name} (ID: {actual_id})")
    print(f"Protected campaign: Fogport (ID: {FOGPORT_CAMPAIGN_ID}) — NOT ACCESSED")
    print("Allowed operation: HTTP GET only")
    print(f"Locations found: {len(locations)}\n")

    if locations:
        print_location_tree(locations)
    else:
        print("No locations were found in MAELSTROS.")

    print("\nRead-only inspection complete.")
    print("No Kanka data was created, updated, deleted, copied, or moved.")
    print("Fogport was not read or modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
