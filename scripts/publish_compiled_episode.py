"""Publish one compiled Fogport episode with exact, idempotent Kanka read-back.

This publisher deliberately supports the entity kinds produced by an episode:
characters, locations, organisations, creatures, items, and events. Existing
records are matched only by approved exact names (including explicit former
names); ambiguous matches stop the run.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from kanka_librarian.client import KankaClient
from kanka_librarian.writer import KankaWriter


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
ENDPOINTS = {
    "characters": "characters",
    "locations": "locations",
    "organizations": "organisations",
    "creatures": "creatures",
    "items": "items",
    "events": "events",
}


class EpisodeError(ValueError):
    """Raised before an unsafe or ambiguous episode publication."""


def document_digest(document: dict[str, Any]) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema_version") != 1 or document.get("mode") != "compiled-episode":
        raise EpisodeError("Expected schema_version 1 and mode compiled-episode.")
    if int(document.get("campaign_id", 0)) != CAMPAIGN_ID:
        raise EpisodeError(f"Publisher is locked to Fogport campaign {CAMPAIGN_ID}.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise EpisodeError("Campaign name must be Fogport.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise EpisodeError("The compiled episode is not approved.")
    if approval.get("document_sha256") != document_digest(document):
        raise EpisodeError("The compiled episode changed after approval.")
    changes = document.get("changes")
    if not isinstance(changes, list) or not changes:
        raise EpisodeError("The compiled episode has no changes.")

    seen: set[tuple[str, str]] = set()
    for change in changes:
        section = str(change.get("section", ""))
        name = str(change.get("name", "")).strip()
        if section not in ENDPOINTS or not name:
            raise EpisodeError(f"Unsupported or unnamed change: {change!r}")
        key = (section, name.casefold())
        if key in seen:
            raise EpisodeError(f"Duplicate compiled change: {section}/{name}.")
        seen.add(key)
        if change.get("posts") and not isinstance(change["posts"], list):
            raise EpisodeError(f"{name}.posts must be a list.")
    return changes


def _list_section(client: KankaClient, section: str) -> list[dict[str, Any]]:
    endpoint = ENDPOINTS[section]
    page = 1
    records: list[dict[str, Any]] = []
    while True:
        response = client._get(
            f"campaigns/{CAMPAIGN_ID}/{endpoint}",
            params={"page": page, "limit": 100},
        )
        records.extend(response.get("data", []))
        meta = response.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def _approved_names(change: dict[str, Any]) -> set[str]:
    values = [change["name"], *change.get("match_names", [])]
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def find_match(
    records: list[dict[str, Any]],
    change: dict[str, Any],
) -> dict[str, Any] | None:
    approved = _approved_names(change)
    matches = [
        record
        for record in records
        if str(record.get("name", "")).strip().casefold() in approved
    ]
    if len(matches) > 1:
        names = ", ".join(str(item.get("name")) for item in matches)
        raise EpisodeError(
            f"Multiple records match approved names for {change['name']}: {names}."
        )
    return matches[0] if matches else None


def compose_entry(current: str, change: dict[str, Any]) -> str:
    if "entry" in change:
        entry = str(change.get("entry", ""))
    else:
        entry = current
    for old, new in change.get("text_replacements", {}).items():
        entry = entry.replace(str(old), str(new))
    addition = str(change.get("append_entry", "")).strip()
    marker = str(change.get("append_marker", addition)).strip()
    if addition and marker not in entry:
        entry = f"{entry.rstrip()}\n\n{addition}".strip()
    return entry


def _resolve_reference(
    reference: dict[str, Any],
    registry: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    section = str(reference.get("section", ""))
    name = str(reference.get("name", "")).strip().casefold()
    matches = registry.get((section, name), [])
    return matches[0] if len(matches) == 1 else None


def resolve_location_parent_id(
    parent_name: str,
    registry: dict[tuple[str, str], list[dict[str, Any]]],
) -> int:
    """Return the Kanka location resource id, never its generic entity id."""
    matches = registry.get(("locations", parent_name.strip().casefold()), [])
    if len(matches) != 1:
        raise EpisodeError(
            f"Location parent {parent_name!r} is missing or ambiguous."
        )
    return int(matches[0]["id"])


def render_references(
    entry: str,
    references: list[dict[str, Any]],
    registry: dict[tuple[str, str], list[dict[str, Any]]],
) -> str:
    rendered = entry
    for reference in references:
        target = _resolve_reference(reference, registry)
        phrase = str(reference.get("phrase") or reference.get("name") or "")
        if not target or not phrase or f"|{phrase}]" in rendered:
            continue
        rendered = re.sub(
            rf"(?<!\[entity:)\b{re.escape(phrase)}\b",
            lambda _: f"[entity:{int(target['entity_id'])}|{phrase}]",
            rendered,
            count=1,
            flags=re.IGNORECASE,
        )
    return rendered


def _build_registry(
    sections: dict[str, list[dict[str, Any]]],
    aliases: dict[str, list[str]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    registry: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for section, records in sections.items():
        for record in records:
            name = str(record.get("name", "")).strip()
            if not name:
                continue
            registry.setdefault((section, name.casefold()), []).append(record)
            by_name.setdefault(name.casefold(), []).append(record)
    for canonical, values in aliases.items():
        targets = by_name.get(canonical.casefold(), [])
        if len(targets) != 1:
            continue
        target = targets[0]
        section = str(target["_section"])
        for alias in values:
            registry.setdefault((section, alias.casefold()), []).append(target)
    return registry


def _upsert_post(
    client: KankaClient,
    writer: KankaWriter,
    entity_id: int,
    post: dict[str, Any],
    registry: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    name = str(post.get("name", "")).strip()
    if not name:
        raise EpisodeError("GM post is missing a name.")
    if int(post.get("visibility_id", 3)) != 3:
        raise EpisodeError(f"GM post {name!r} is not administrator-only.")
    entry = render_references(
        str(post.get("entry", "")),
        post.get("references", []),
        registry,
    )
    payload = {
        "name": name,
        "entry": entry,
        "entity_id": entity_id,
        "visibility_id": 3,
    }
    existing = client.list_entity_posts(CAMPAIGN_ID, entity_id)
    matches = [
        item
        for item in existing
        if str(item.get("name", "")).casefold() == name.casefold()
    ]
    if len(matches) > 1:
        raise EpisodeError(f"Multiple GM posts named {name!r}; refusing to guess.")
    if matches:
        post_id = int(matches[0]["id"])
        writer.update_post(CAMPAIGN_ID, entity_id, post_id, payload)
        created = False
    else:
        result = writer.create_post(CAMPAIGN_ID, entity_id, payload)
        post_id = int(result["id"])
        created = True
    direct = client._get(
        f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/posts/{post_id}"
    ).get("data", {})
    expected = {
        "name": name,
        "entry": entry,
        "entity_id": entity_id,
        "visibility_id": 3,
    }
    actual = {key: direct.get(key) for key in expected}
    if actual != expected:
        raise EpisodeError(f"GM post read-back failed for {name!r}.")
    return {"id": post_id, "name": name, "created": created, "visibility_id": 3}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.document.read_text(encoding="utf-8"))
    changes = validate_document(document)
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise EpisodeError("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise EpisodeError("Kanka campaign identity lock failed.")

    needed_sections = sorted({str(change["section"]) for change in changes})
    sections = {section: _list_section(client, section) for section in needed_sections}
    records_by_change: dict[str, dict[str, Any]] = {}
    created_names: set[str] = set()

    # Pass 1: resolve or create shells so all episode cross-links can be real.
    for change in changes:
        section = str(change["section"])
        match = find_match(sections[section], change)
        if match is None:
            shell = {
                "name": str(change["name"]),
                "type": str(change.get("type", "")),
                "is_private": bool(change.get("is_private", False)),
                "entry": "",
            }
            match = writer.create_entity(CAMPAIGN_ID, section, shell)
            created_names.add(str(change["name"]))
            sections[section].append(match)
        # Use the approved canonical name in the in-memory registry even when
        # the live record is about to be renamed from an approved former name.
        match["name"] = str(change["name"])
        match["_section"] = section
        records_by_change[str(change["name"])] = match

    for section, records in sections.items():
        for record in records:
            record["_section"] = section
    registry = _build_registry(sections, document.get("aliases", {}))

    # Pass 2: write complete linked entries and nested location parents.
    receipts: list[dict[str, Any]] = []
    for change in changes:
        section = str(change["section"])
        record = records_by_change[str(change["name"])]
        resource_id = int(record["id"])

        # List responses are intentionally compact and may omit entry/type. Read
        # the resource before composing so an append never erases existing canon.
        current = client._get(
            f"campaigns/{CAMPAIGN_ID}/{ENDPOINTS[section]}/{resource_id}"
        ).get("data", {})
        entry = compose_entry(str(current.get("entry") or ""), change)
        entry = render_references(entry, change.get("references", []), registry)
        payload = {
            "name": str(change["name"]),
            "is_private": bool(
                change.get("is_private", current.get("is_private", False))
            ),
            "entry": entry,
        }
        if "type" in change:
            payload["type"] = str(change.get("type") or "")
        elif current.get("type") is not None:
            payload["type"] = str(current.get("type") or "")

        parent_name = str(change.get("parent_name", "")).strip()
        if parent_name:
            # Kanka locations use location_id (the parent's location resource
            # id), not parent_id and not the parent's generic entity_id.
            payload["location_id"] = resolve_location_parent_id(
                parent_name, registry
            )

        writer.update_entity(CAMPAIGN_ID, section, resource_id, payload)
        direct = client._get(
            f"campaigns/{CAMPAIGN_ID}/{ENDPOINTS[section]}/{resource_id}"
        ).get("data", {})
        expected = {
            key: payload[key]
            for key in ("name", "type", "is_private", "entry")
            if key in payload
        }
        actual = {key: direct.get(key) for key in expected}
        if actual != expected:
            mismatches = {
                key: {"expected": expected[key], "actual": actual[key]}
                for key in expected
                if actual[key] != expected[key]
            }
            raise EpisodeError(
                f"Entity read-back failed for {change['name']!r}: {mismatches!r}."
            )
        entity_id = int(direct["entity_id"])
        if parent_name:
            if int(direct.get("location_id") or 0) != int(payload["location_id"]):
                raise EpisodeError(
                    f"Location parent read-back failed for {change['name']!r}: "
                    f"expected location_id {payload['location_id']}, "
                    f"received {direct.get('location_id')!r}."
                )
        posts = [
            _upsert_post(client, writer, entity_id, post, registry)
            for post in change.get("posts", [])
        ]
        receipts.append(
            {
                "section": section,
                "name": direct["name"],
                "created": str(change["name"]) in created_names,
                "resource_id": resource_id,
                "entity_id": entity_id,
                "overview_url": (
                    f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"
                ),
                "private_posts_verified": posts,
            }
        )

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "episode": document.get("episode"),
        "entities_verified": len(receipts),
        "entities": receipts,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Fogport compiled episode verified\n\n")
            stream.write(f"- Episode: **{document.get('episode')}**\n")
            stream.write(f"- Entities verified: **{len(receipts)}**\n")
            for item in receipts:
                stream.write(f"- [{item['name']}]({item['overview_url']})\n")


if __name__ == "__main__":
    main()
