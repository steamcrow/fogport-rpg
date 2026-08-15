"""Build a lightweight, read-only snapshot of the current Kanka campaign.

This is deliberately NOT the source of truth for publishing. Every
publisher script still re-fetches live data straight from Kanka before it
writes anything, so a stale or wrong snapshot can never cause an unsafe
publish -- at worst it makes an assistant suggest something that turns
out to already exist, which the publisher's own exact-name matching then
catches safely.

What this IS for: giving an AI assistant (ChatGPT, Claude, or similar) a
fast way to see what characters/creatures/locations/items/organizations/
etc. already exist -- by name, type, and Kanka id -- without needing a
live Kanka API credential of its own. It only needs read access to this
repository.

Deliberately excluded: full entry/description HTML, GM post bodies,
attributes, relationships. Those stay inside the approved_*/ manifests
where they already live, reviewed one change at a time. This file is
an index, not a mirror.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


class SnapshotClient(Protocol):
    """The subset of KankaClient this module actually needs.

    Spelled out as a Protocol (rather than importing KankaClient directly)
    so tests can pass in a lightweight fake without any network access.
    """

    def get_campaign(self, campaign_id: int) -> dict[str, Any]: ...
    def list_characters(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_creatures(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_locations(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_organizations(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_items(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_notes(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_journals(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_events(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_quests(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_races(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def list_families(self, campaign_id: int) -> list[dict[str, Any]]: ...
    def _get_all_pages(self, path: str) -> list[dict[str, Any]]: ...


# section name -> KankaClient method name that lists it
LIST_METHODS: dict[str, str] = {
    "characters": "list_characters",
    "creatures": "list_creatures",
    "locations": "list_locations",
    "organizations": "list_organizations",
    "items": "list_items",
    "notes": "list_notes",
    "journals": "list_journals",
    "events": "list_events",
    "quests": "list_quests",
    "races": "list_races",
    "families": "list_families",
}

# Fields kept per entity. Deliberately excludes "entry" (the full
# description/body) -- see module docstring.
ENTITY_FIELDS = ("id", "entity_id", "name", "type", "is_private")


def _slim_entity(record: dict[str, Any]) -> dict[str, Any]:
    slim = {field: record.get(field) for field in ENTITY_FIELDS}
    # Events carry a date; keep it when present, since "when did X happen"
    # is exactly the kind of question this snapshot exists to answer.
    if record.get("date") is not None:
        slim["date"] = record.get("date")
    return slim


def build_snapshot(
    client: SnapshotClient,
    *,
    campaign_id: int,
    campaign_name: str,
) -> dict[str, Any]:
    """Fetch every listed section and every timeline/era, and return one dict.

    Raises whatever the client raises (e.g. KankaError) on failure; callers
    should not catch and hide that -- a partial or silently-failed snapshot
    is worse than no snapshot, since an assistant reading it would trust
    it's complete.
    """
    campaign = client.get_campaign(campaign_id)
    actual_name = str(campaign.get("name", "")).strip()
    if actual_name.casefold() != campaign_name.casefold():
        raise ValueError(
            f"Campaign identity check failed: {campaign_id} is "
            f"{actual_name!r}, not {campaign_name!r}."
        )

    entities: dict[str, list[dict[str, Any]]] = {}
    for section, method_name in LIST_METHODS.items():
        records = getattr(client, method_name)(campaign_id)
        entities[section] = [
            _slim_entity(record)
            for record in sorted(records, key=lambda r: str(r.get("name", "")).casefold())
        ]

    timelines_raw = client._get_all_pages(f"campaigns/{campaign_id}/timelines")
    timelines: list[dict[str, Any]] = []
    for timeline in timelines_raw:
        timeline_id = int(timeline["id"])
        eras_raw = client._get_all_pages(
            f"campaigns/{campaign_id}/timelines/{timeline_id}/timeline_eras"
        )
        timelines.append(
            {
                "id": timeline_id,
                "name": timeline.get("name"),
                "eras": [
                    {
                        "id": era.get("id"),
                        "name": era.get("name"),
                        "abbreviation": era.get("abbreviation"),
                        "start_year": era.get("start_year"),
                        "end_year": era.get("end_year"),
                    }
                    for era in eras_raw
                ],
            }
        )

    return {
        "campaign_id": campaign_id,
        "campaign_name": actual_name,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "note": (
            "This is a read-only index for AI assistants: name/type/id only, "
            "no descriptions or private post bodies. It is NOT authoritative "
            "for publishing -- every publisher re-checks Kanka live before "
            "writing anything, regardless of what this file says."
        ),
        "entities": entities,
        "timelines": timelines,
    }
