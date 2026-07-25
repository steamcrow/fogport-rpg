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


def collect_related(
    sections: tuple[list[dict[str, Any]], ...],
    field: str,
) -> list[dict[str, Any]]:
    """Flatten related records while preserving their owning entity ID."""
    collected: list[dict[str, Any]] = []
    for section in sections:
        for entity in section:
            entity_id = entity.get("entity_id")
            related = entity.get(field, [])
            if not isinstance(related, list):
                continue
            for record in related:
                if isinstance(record, dict):
                    collected.append({"source_entity_id": entity_id, **record})
    return collected


def build_snapshot(
    campaign: dict[str, Any],
    locations: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    organizations: list[dict[str, Any]],
    creatures: list[dict[str, Any]],
    races: list[dict[str, Any]],
    families: list[dict[str, Any]],
    journals: list[dict[str, Any]],
    events: list[dict[str, Any]],
    items: list[dict[str, Any]],
    quests: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only",
        "content_scope": "full-lore-context",
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
                    "entry",
                    "tags",
                    "is_private",
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
                    "entry",
                    "tags",
                    "is_private",
                    "is_dead",
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
        "creatures": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "type",
                    "location_id",
                    "entry",
                    "tags",
                    "is_private",
                    "updated_at",
                ),
            )
            for item in sorted(
                creatures,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "peoples": [
            {
                **selected_fields(
                    item,
                    (
                        "id",
                        "entity_id",
                        "name",
                        "type",
                        "entry",
                        "tags",
                        "is_private",
                        "updated_at",
                    ),
                ),
                "source_entity_type": "race",
            }
            for item in sorted(
                races,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "families": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "type",
                    "family_id",
                    "location_id",
                    "entry",
                    "tags",
                    "is_private",
                    "updated_at",
                ),
            )
            for item in sorted(
                families,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "journals": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "type",
                    "date",
                    "character_id",
                    "entry",
                    "tags",
                    "is_private",
                    "updated_at",
                ),
            )
            for item in sorted(
                journals,
                key=lambda value: (
                    str(value.get("date") or ""),
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "events": [
            selected_fields(
                item,
                (
                    "id", "entity_id", "name", "type", "date", "location_id",
                    "entry", "tags", "is_private", "updated_at",
                ),
            )
            for item in sorted(
                events,
                key=lambda value: (
                    str(value.get("date") or ""),
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "items": [
            selected_fields(
                item,
                (
                    "id", "entity_id", "name", "type", "location_id",
                    "character_id", "price", "size", "entry", "tags",
                    "is_private", "updated_at",
                ),
            )
            for item in sorted(
                items,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "quests": [
            selected_fields(
                item,
                (
                    "id", "entity_id", "name", "type", "character_id",
                    "entry", "tags", "is_private", "updated_at",
                ),
            )
            for item in sorted(
                quests,
                key=lambda value: (
                    str(value.get("name") or "").casefold(),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "attributes": [
            selected_fields(
                item,
                (
                    "id", "entity_id", "source_entity_id", "name", "value", "parsed",
                    "type_id", "default_order", "is_private", "is_pinned",
                    "created_at", "updated_at",
                ),
            )
            for item in sorted(
                attributes,
                key=lambda value: (
                    int(value.get("source_entity_id") or value.get("entity_id") or 0),
                    int(value.get("default_order") or 0),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "relationships": [
            selected_fields(
                item,
                (
                    "id", "source_entity_id", "owner_id", "target_id", "relation",
                    "attitude", "visibility_id", "is_pinned", "colour",
                    "created_at", "updated_at",
                ),
            )
            for item in sorted(
                relationships,
                key=lambda value: (
                    int(value.get("owner_id") or value.get("source_entity_id") or 0),
                    int(value.get("target_id") or 0),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "posts": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "entry",
                    "position",
                    "visibility_id",
                    "is_private",
                    "created_at",
                    "updated_at",
                ),
            )
            for item in sorted(
                posts,
                key=lambda value: (
                    int(value.get("entity_id") or 0),
                    int(value.get("position") or 0),
                    int(value.get("id") or 0),
                ),
            )
        ],
        "organizations": [
            selected_fields(
                item,
                (
                    "id",
                    "entity_id",
                    "name",
                    "type",
                    "organisation_id",
                    "location_id",
                    "entry",
                    "tags",
                    "is_private",
                    "updated_at",
                ),
            )
            for item in sorted(
                organizations,
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

        locations = client.list_locations(MAELSTROS_CAMPAIGN_ID, related=True)
        characters = client.list_characters(MAELSTROS_CAMPAIGN_ID, related=True)
        organizations = client.list_organizations(MAELSTROS_CAMPAIGN_ID, related=True)
        creatures = client.list_creatures(MAELSTROS_CAMPAIGN_ID, related=True)
        races = client.list_races(MAELSTROS_CAMPAIGN_ID, related=True)
        families = client.list_families(MAELSTROS_CAMPAIGN_ID, related=True)
        journals = client.list_journals(MAELSTROS_CAMPAIGN_ID, related=True)
        events = client.list_events(MAELSTROS_CAMPAIGN_ID, related=True)
        items = client.list_items(MAELSTROS_CAMPAIGN_ID, related=True)
        quests = client.list_quests(MAELSTROS_CAMPAIGN_ID, related=True)

        sections = (
            locations, characters, organizations, creatures, races, families, journals,
            events, items, quests,
        )
        posts = collect_related(sections, "posts")
        attributes = collect_related(sections, "attributes")
        relationships = collect_related(sections, "relations")
    except KankaError as exc:
        print(f"Kanka Librarian error: {exc}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(
        campaign, locations, characters, organizations, creatures, races,
        families, journals, events, items, quests,
        posts, attributes, relationships,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("KANKA LIBRARIAN — READ-ONLY FULL-CONTENT SNAPSHOT")
    print(f"Target campaign: {actual_name} (ID: {actual_id})")
    print(f"Protected campaign: Fogport (ID: {FOGPORT_CAMPAIGN_ID}) — NOT ACCESSED")
    print(f"Locations exported: {len(locations)}")
    print(f"Characters exported: {len(characters)}")
    print(f"Organizations exported: {len(organizations)}")
    print(f"Creatures exported: {len(creatures)}")
    print(f"Peoples exported from Kanka Races: {len(races)}")
    print(f"Families exported: {len(families)}")
    print(f"Journals exported: {len(journals)}")
    print(f"Events exported: {len(events)}")
    print(f"Items exported: {len(items)}")
    print(f"Quests exported: {len(quests)}")
    print(f"Entity posts exported: {len(posts)}")
    print(f"Attributes exported: {len(attributes)}")
    print(f"Relationships exported: {len(relationships)}")
    print(f"Temporary snapshot written to: {output_path}")
    print("No Kanka data was created, updated, deleted, copied, or moved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
