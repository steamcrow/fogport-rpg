"""Publish Fogport's approved civic history and its linked Kanka timeline."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import html
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
    "creatures": "creatures",
    "events": "events",
    "families": "families",
    "locations": "locations",
}


class HistoryError(ValueError):
    """Raised before an unsafe or ambiguous history publication."""


def document_digest(document: dict[str, Any]) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def normal(value: Any) -> str:
    value = html.unescape(str(value or "")).replace("\r\n", "\n").strip()
    return re.sub(r">\s+<", "><", value)


def exact_match(records: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any] | None:
    matches = [
        item for item in records
        if str(item.get("name", "")).strip().casefold() == name.strip().casefold()
    ]
    if len(matches) > 1:
        raise HistoryError(f"Multiple {kind} records named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def list_all(client: KankaClient, path: str) -> list[dict[str, Any]]:
    return client._get_all_pages(f"campaigns/{CAMPAIGN_ID}/{path}")


def validate(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 1:
        raise HistoryError("Expected history schema version 1.")
    if int(document.get("campaign_id", 0)) != CAMPAIGN_ID:
        raise HistoryError("History publisher is locked to Fogport 410879.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise HistoryError("Campaign name must be Fogport.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or approval.get("approved_by") != "Daniel Davis":
        raise HistoryError("Daniel Davis approval is required.")
    if approval.get("document_sha256") != document_digest(document):
        raise HistoryError("History document changed after approval.")
    keys = [str(item.get("key", "")) for item in document.get("entities", [])]
    if not keys or len(keys) != len(set(keys)):
        raise HistoryError("Every history entity needs one unique key.")
    for item in document["entities"]:
        if item.get("section") not in ENDPOINTS or not str(item.get("name", "")).strip():
            raise HistoryError(f"Unsupported or unnamed history entity: {item!r}")


def build_registry(
    sections: dict[str, list[dict[str, Any]]],
    keyed: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    registry: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for section, records in sections.items():
        for record in records:
            name = str(record.get("name", "")).strip().casefold()
            if name:
                registry.setdefault((section, name), []).append(record)
    for record in keyed.values():
        section = str(record["_section"])
        name = str(record["name"]).strip().casefold()
        if record not in registry.setdefault((section, name), []):
            registry[(section, name)].append(record)
    return registry


def render_references(
    entry: str,
    references: list[dict[str, Any]],
    registry: dict[tuple[str, str], list[dict[str, Any]]],
    keyed: dict[str, dict[str, Any]],
) -> str:
    rendered = entry
    for reference in references:
        phrase = str(reference.get("phrase") or reference.get("name") or "").strip()
        if not phrase:
            continue
        if reference.get("key"):
            target = keyed.get(str(reference["key"]))
        else:
            matches = registry.get(
                (
                    str(reference.get("section", "")),
                    str(reference.get("name", "")).strip().casefold(),
                ),
                [],
            )
            target = matches[0] if len(matches) == 1 else None
        if not target:
            continue
        rendered = re.sub(
            rf"(?<!\[entity:)\b{re.escape(phrase)}\b",
            lambda _: f"[entity:{int(target['entity_id'])}|{phrase}]",
            rendered,
            count=1,
            flags=re.IGNORECASE,
        )
    return rendered


def upsert_post(
    client: KankaClient,
    writer: KankaWriter,
    entity_id: int,
    post: dict[str, Any],
) -> dict[str, Any]:
    name = str(post["name"])
    if int(post.get("visibility_id", 3)) != 3:
        raise HistoryError(f"GM post {name!r} must be administrator-only.")
    payload = {
        "name": name,
        "entry": str(post.get("entry", "")),
        "entity_id": entity_id,
        "visibility_id": 3,
    }
    match = exact_match(client.list_entity_posts(CAMPAIGN_ID, entity_id), name, "post")
    if match:
        post_id = int(match["id"])
        writer.update_post(CAMPAIGN_ID, entity_id, post_id, payload)
        created = False
    else:
        post_id = int(writer.create_post(CAMPAIGN_ID, entity_id, payload)["id"])
        created = True
    direct = client._get(
        f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/posts/{post_id}"
    ).get("data", {})
    if str(direct.get("name")) != name or normal(direct.get("entry")) != normal(payload["entry"]):
        raise HistoryError(f"GM post read-back failed for {name!r}.")
    if int(direct.get("visibility_id") or 0) != 3:
        raise HistoryError(f"GM post {name!r} is not administrator-only after write.")
    return {"id": post_id, "name": name, "created": created}


def upsert_era(
    client: KankaClient,
    writer: KankaWriter,
    timeline_id: int,
    era: dict[str, Any],
) -> dict[str, Any]:
    path = f"campaigns/{CAMPAIGN_ID}/timelines/{timeline_id}/timeline_eras"
    match = exact_match(client._get_all_pages(path), str(era["name"]), "timeline era")
    payload = {
        "era": str(era["name"]),
        "abbreviation": str(era["abbreviation"]),
        "start_year": era.get("start_year"),
        "end_year": era.get("end_year"),
        "visibility": str(era.get("visibility", "all")),
    }
    if match:
        era_id = int(match["id"])
        writer._send("PATCH", f"{path}/{era_id}", payload)
    else:
        era_id = int(writer._send("POST", path, payload)["id"])
    direct = client._get(f"{path}/{era_id}").get("data", {})
    if str(direct.get("name")) != str(era["name"]):
        raise HistoryError(f"Timeline era read-back failed for {era['name']!r}.")
    return direct


def upsert_element(
    client: KankaClient,
    writer: KankaWriter,
    timeline_id: int,
    element: dict[str, Any],
    era_id: int,
    entity_id: int,
) -> dict[str, Any]:
    path = f"campaigns/{CAMPAIGN_ID}/timelines/{timeline_id}/timeline_elements"
    match = exact_match(client._get_all_pages(path), str(element["name"]), "timeline element")
    payload = {
        "name": str(element["name"]),
        "entity_id": entity_id,
        "era_id": era_id,
        "entry": str(element.get("entry", "")),
        "date": str(element.get("date", "")),
        "colour": str(element.get("colour", "blue")),
        "position": int(element["position"]),
        "visibility_id": int(element.get("visibility_id", 1)),
    }
    if match:
        element_id = int(match["id"])
        writer._send("PATCH", f"{path}/{element_id}", payload)
        created = False
    else:
        element_id = int(writer._send("POST", path, payload)["id"])
        created = True
    direct = client._get(f"{path}/{element_id}").get("data", {})
    expected = {
        "name": payload["name"],
        "entity_id": entity_id,
        "era_id": era_id,
        "date": payload["date"],
        "visibility_id": payload["visibility_id"],
    }
    for key, value in expected.items():
        actual = direct.get(key)
        if key in {"entity_id", "era_id", "visibility_id"}:
            actual = int(actual or 0)
        if actual != value:
            raise HistoryError(
                f"Timeline element read-back failed for {element['name']!r}: {key}."
            )
    return {"id": element_id, "name": payload["name"], "created": created}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.document.read_text(encoding="utf-8"))
    validate(document)
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise HistoryError("KANKA_ENABLE_WRITES must select FOGPORT_410879.")

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise HistoryError("Kanka campaign identity lock failed.")

    needed = set(ENDPOINTS)
    sections = {section: list_all(client, endpoint) for section, endpoint in ENDPOINTS.items()}
    keyed: dict[str, dict[str, Any]] = {}
    created_entities: list[str] = []

    # Create exact-name shells first, so every cross-reference can resolve.
    for change in document["entities"]:
        section = str(change["section"])
        match = exact_match(sections[section], str(change["name"]), section)
        if match is None:
            shell = {
                "name": str(change["name"]),
                "type": str(change.get("type", "")),
                "is_private": bool(change.get("is_private", False)),
                "entry": "",
            }
            if section == "events" and change.get("date"):
                shell["date"] = str(change["date"])
            match = writer.create_entity(CAMPAIGN_ID, section, shell)
            sections[section].append(match)
            created_entities.append(str(change["name"]))
        match = dict(match)
        match["_section"] = section
        keyed[str(change["key"])] = match

    registry = build_registry(sections, keyed)
    posts: list[dict[str, Any]] = []

    # Write final linked copy and verify exact public read-back.
    for change in document["entities"]:
        section = str(change["section"])
        record = keyed[str(change["key"])]
        entry = render_references(
            str(change.get("entry", "")),
            change.get("references", []),
            registry,
            keyed,
        )
        payload = {
            "name": str(change["name"]),
            "type": str(change.get("type", "")),
            "is_private": bool(change.get("is_private", False)),
            "entry": entry,
        }
        if section == "events" and change.get("date"):
            payload["date"] = str(change["date"])
        updated = writer.update_entity(
            CAMPAIGN_ID, section, int(record["id"]), payload
        )
        if str(updated.get("name")) != payload["name"]:
            raise HistoryError(f"Entity name read-back failed for {payload['name']!r}.")
        if normal(updated.get("entry")) != normal(entry):
            raise HistoryError(f"Entity entry read-back failed for {payload['name']!r}.")
        keyed[str(change["key"])].update(updated)
        keyed[str(change["key"])]["_section"] = section
        for post in change.get("posts", []):
            posts.append(
                upsert_post(client, writer, int(updated["entity_id"]), post)
            )

    timeline_data = document["timeline"]
    timelines = list_all(client, "timelines")
    timeline = exact_match(timelines, str(timeline_data["name"]), "timeline")
    timeline_payload = {
        "name": str(timeline_data["name"]),
        "entry": str(timeline_data.get("entry", "")),
        "type": str(timeline_data.get("type", "")),
        "is_private": bool(timeline_data.get("is_private", False)),
    }
    if timeline:
        timeline_id = int(timeline["id"])
        writer._send(
            "PATCH", f"campaigns/{CAMPAIGN_ID}/timelines/{timeline_id}", timeline_payload
        )
        timeline_created = False
    else:
        timeline = writer._send(
            "POST", f"campaigns/{CAMPAIGN_ID}/timelines", timeline_payload
        )
        timeline_id = int(timeline["id"])
        timeline_created = True
    timeline_direct = client._get(
        f"campaigns/{CAMPAIGN_ID}/timelines/{timeline_id}"
    ).get("data", {})
    if str(timeline_direct.get("name")) != timeline_payload["name"]:
        raise HistoryError("Timeline read-back failed.")

    eras: dict[str, dict[str, Any]] = {}
    for era in timeline_data["eras"]:
        eras[str(era["key"])] = upsert_era(client, writer, timeline_id, era)

    elements: list[dict[str, Any]] = []
    for element in document["elements"]:
        elements.append(
            upsert_element(
                client,
                writer,
                timeline_id,
                element,
                int(eras[str(element["era_key"])]["id"]),
                int(keyed[str(element["entity_key"])]["entity_id"]),
            )
        )

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "timeline_id": timeline_id,
        "timeline_entity_id": int(timeline_direct["entity_id"]),
        "timeline_created": timeline_created,
        "entities_created": created_entities,
        "entity_count": len(document["entities"]),
        "gm_posts": posts,
        "timeline_elements": elements,
        "overview_url": (
            f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/"
            f"{int(timeline_direct['entity_id'])}"
        ),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("# Fogport history publication verified\n\n")
            summary.write(f"- Timeline: **{timeline_payload['name']}**\n")
            summary.write(f"- Linked elements: **{len(elements)}**\n")
            summary.write(f"- [Open Timeline Overview]({receipt['overview_url']})\n")


if __name__ == "__main__":
    main()
