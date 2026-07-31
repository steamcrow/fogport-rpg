"""Build a Kanka entity registry and add safe, idempotent entity links."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
from typing import Any


SECTION_METHODS = {
    "locations": "list_locations",
    "characters": "list_characters",
    "organizations": "list_organizations",
    "creatures": "list_creatures",
    "peoples": "list_races",
    "families": "list_families",
    "journals": "list_journals",
    "notes": "list_notes",
    "events": "list_events",
    "items": "list_items",
    "quests": "list_quests",
}

SECTION_ENDPOINTS = {
    "locations": "locations",
    "characters": "characters",
    "organizations": "organisations",
    "creatures": "creatures",
    "peoples": "races",
    "families": "families",
    "journals": "journals",
    "notes": "notes",
    "events": "events",
    "items": "items",
    "quests": "quests",
}

PROTECTED_TOKEN = re.compile(r"(\[entity:\d+(?:\|[^\]]*)?\]|<[^>]*>)", re.IGNORECASE)
EXISTING_LINK = re.compile(r"\[entity:(\d+)(?:\|[^\]]*)?\]", re.IGNORECASE)


class CrosslinkError(ValueError):
    """Raised when a registry or cleanup request is unsafe."""


def load_aliases(path: Path) -> dict[str, list[str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise CrosslinkError("Alias registry must use schema_version 1.")
    aliases = document.get("aliases", {})
    if not isinstance(aliases, dict):
        raise CrosslinkError("aliases must be an object keyed by canonical name.")
    result: dict[str, list[str]] = {}
    for name, values in aliases.items():
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise CrosslinkError(f"Aliases for {name!r} must be a list of strings.")
        cleaned = [value.strip() for value in values if value.strip()]
        result[str(name).strip()] = cleaned
    return result


def build_registry(
    client: Any,
    campaign_id: int,
    aliases: dict[str, list[str]] | None = None,
    *,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Read Kanka and return a disposable cache with both resource identifiers."""
    aliases = aliases or {}
    selected = sections or list(SECTION_METHODS)
    unknown = sorted(set(selected) - set(SECTION_METHODS))
    if unknown:
        raise CrosslinkError(f"Unsupported registry sections: {', '.join(unknown)}")

    entities: list[dict[str, Any]] = []
    for section in selected:
        method = getattr(client, SECTION_METHODS[section])
        for item in method(campaign_id):
            if not item.get("id") or not item.get("entity_id") or not item.get("name"):
                continue
            name = str(item["name"]).strip()
            entities.append(
                {
                    "canonical_name": name,
                    "aliases": aliases.get(name, []),
                    "section": section,
                    "endpoint": SECTION_ENDPOINTS[section],
                    "kanka_id": int(item["id"]),
                    "entity_id": int(item["entity_id"]),
                    "is_private": bool(item.get("is_private", False)),
                    "entry": str(item.get("entry") or ""),
                }
            )
    entities.sort(key=lambda item: (item["canonical_name"].casefold(), item["entity_id"]))
    return {
        "schema_version": 1,
        "campaign_id": int(campaign_id),
        "entities": entities,
    }


def _resolvable_phrases(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spelling: dict[str, str] = {}
    for entity in registry.get("entities", []):
        phrases = [entity["canonical_name"], *entity.get("aliases", [])]
        for phrase in phrases:
            cleaned = str(phrase).strip()
            if not cleaned:
                continue
            folded = cleaned.casefold()
            spelling.setdefault(folded, cleaned)
            if all(existing["entity_id"] != entity["entity_id"] for existing in candidates[folded]):
                candidates[folded].append(entity)
    ambiguous = {phrase for phrase, values in candidates.items() if len(values) != 1}
    resolved = {
        phrase: {"phrase": spelling[phrase], "entity": values[0]}
        for phrase, values in candidates.items()
        if len(values) == 1
    }
    return resolved, ambiguous


def link_entry(
    entry: str,
    registry: dict[str, Any],
    *,
    source_entity_id: int | None = None,
    source_private: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Link the first useful mention of each uniquely resolved entity."""
    resolved, ambiguous = _resolvable_phrases(registry)
    linked_ids = {int(value) for value in EXISTING_LINK.findall(entry)}
    eligible: dict[str, dict[str, Any]] = {}
    for folded, candidate in resolved.items():
        entity = candidate["entity"]
        entity_id = int(entity["entity_id"])
        if entity_id == source_entity_id or entity_id in linked_ids:
            continue
        if entity.get("is_private") and not source_private:
            continue
        eligible[folded] = candidate

    phrases = sorted(
        (candidate["phrase"] for candidate in eligible.values()),
        key=lambda value: (-len(value), value.casefold()),
    )
    if not phrases:
        return entry, {"links_added": [], "ambiguous_phrases": sorted(ambiguous)}

    phrase_pattern = re.compile(
        r"(?<![\w])(" + "|".join(re.escape(phrase) for phrase in phrases) + r")(?![\w])",
        re.IGNORECASE,
    )
    added: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        visible = match.group(0)
        candidate = eligible.get(visible.casefold())
        if not candidate:
            return visible
        entity = candidate["entity"]
        entity_id = int(entity["entity_id"])
        if entity_id in linked_ids:
            return visible
        linked_ids.add(entity_id)
        added.append(
            {
                "visible_text": visible,
                "canonical_name": entity["canonical_name"],
                "entity_id": entity_id,
            }
        )
        return f"[entity:{entity_id}|{visible}]"

    parts = PROTECTED_TOKEN.split(entry)
    for index in range(0, len(parts), 2):
        parts[index] = phrase_pattern.sub(replace, parts[index])
    return "".join(parts), {
        "links_added": added,
        "ambiguous_phrases": sorted(ambiguous),
    }
