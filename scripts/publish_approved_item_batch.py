"""Publish and exactly verify an approval-locked batch of Fogport Kanka items."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


def canonical_digest(document: dict[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != "approval"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kanka-Librarian/1.0",
    }


def request(
    token: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.request(
        method,
        f"https://api.kanka.io/1.0/{path}",
        headers=headers(token),
        json=payload,
        params=params,
        timeout=60,
    )
    if not response.ok:
        raise SystemExit(
            f"Kanka {method} {path} returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    body = response.json()
    if not isinstance(body, dict):
        raise SystemExit(f"Kanka {method} {path} returned invalid JSON.")
    return body


def all_pages(token: str, path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        body = request(token, "GET", path, params={"page": page, "limit": 100})
        records.extend(x for x in body.get("data", []) if isinstance(x, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact(records: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in records
        if str(item.get("name", "")).strip().casefold() == name.strip().casefold()
    ]
    if len(matches) > 1:
        raise SystemExit(f"Multiple Kanka items named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def entity_link(
    token: str, section: str, names: list[str], label: str
) -> tuple[str, bool]:
    records = all_pages(token, f"campaigns/{CAMPAIGN_ID}/{section}")
    for name in names:
        matches = [
            item
            for item in records
            if str(item.get("name", "")).strip().casefold() == name.casefold()
        ]
        if len(matches) == 1:
            return f"[entity:{int(matches[0]['entity_id'])}|{label}]", True
        if len(matches) > 1:
            raise SystemExit(f"Ambiguous link target {name!r} in {section}.")
    return label, False


def validate(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 1:
        raise SystemExit("Unsupported item-batch schema.")
    if document.get("mode") != "approved-item-batch":
        raise SystemExit("Manifest is not an approved item batch.")
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Manifest is not locked to Fogport 410879.")
    if str(document.get("campaign_name", "")).casefold() != "fogport":
        raise SystemExit("Manifest campaign name is not Fogport.")
    approval = document.get("approval", {})
    if (
        approval.get("status") != "approved"
        or approval.get("approved_by") != "Daniel Davis"
    ):
        raise SystemExit("Daniel Davis approval is required.")
    if approval.get("batch_sha256") != canonical_digest(document):
        raise SystemExit("Approved item batch changed after approval.")
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit("Approved item batch is empty.")
    names = [str(item.get("name", "")).strip().casefold() for item in items]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise SystemExit("Approved item names must be non-empty and unique.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate(document)
    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    links = {
        "{{HELIOT}}": ("locations", ["Grand Heliot Station"], "Grand Heliot Station"),
        "{{BLACKWAKE}}": ("locations", ["Blackwake"], "Blackwake"),
        "{{CATASTROPHE}}": ("events", ["The Catastrophe", "Catastrophe"], "Catastrophe"),
        "{{WAR}}": ("events", ["War of 100 Kingdoms", "The War of 100 Kingdoms"], "War of 100 Kingdoms"),
    }
    rendered_links: dict[str, tuple[str, bool]] = {}
    for placeholder, (section, names, label) in links.items():
        rendered_links[placeholder] = entity_link(token, section, names, label)

    item_path = f"campaigns/{CAMPAIGN_ID}/items"
    receipts: list[dict[str, Any]] = []
    known = all_pages(token, item_path)
    created_entities: dict[str, int] = {}

    for spec in document["items"]:
        entry = str(spec["entry"])
        status: dict[str, bool] = {}
        for placeholder, (_, _, label) in links.items():
            rendered, linked = rendered_links[placeholder]
            entry = entry.replace(placeholder, rendered)
            status[label] = linked
        for placeholder, target, label in (
            ("{{CRATE_PLURAL}}", "Standard Transit Crate", "transit crates"),
            ("{{FREIGHT_TRAM}}", "Industrial Freight Tram", "Industrial Freight Tram"),
        ):
            entity_id = created_entities.get(target)
            rendered = f"[entity:{entity_id}|{label}]" if entity_id else label
            entry = entry.replace(placeholder, rendered)
            status[target] = entity_id is not None

        payload = {
            "name": str(spec["name"]),
            "type": str(spec["type"]),
            "entry": entry,
            "is_private": bool(spec.get("is_private", False)),
        }
        match = exact(known, payload["name"])
        if match:
            item_id = int(match["id"])
            request(token, "PATCH", f"{item_path}/{item_id}", payload=payload)
            created = False
        else:
            made = request(token, "POST", item_path, payload=payload).get("data", {})
            item_id = int(made["id"])
            created = True
        final = request(token, "GET", f"{item_path}/{item_id}").get("data", {})
        if any(
            (
                str(final.get("name")) != payload["name"],
                str(final.get("type")) != payload["type"],
                bool(final.get("is_private")) is not payload["is_private"],
                str(final.get("entry") or "") != entry,
            )
        ):
            raise SystemExit(f"Exact read-back failed for {payload['name']!r}.")
        entity_id = int(final["entity_id"])
        created_entities[payload["name"]] = entity_id
        receipts.append(
            {
                "name": payload["name"],
                "item_id": item_id,
                "entity_id": entity_id,
                "created": created,
                "entry_verified": True,
                "link_status": status,
                "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
            }
        )
        known.append(final)

    # Re-render once every item has an entity ID so sibling links work in both
    # directions without relying on manifest order.
    for spec, receipt in zip(document["items"], receipts, strict=True):
        entry = str(spec["entry"])
        status: dict[str, bool] = {}
        for placeholder, (_, _, label) in links.items():
            rendered, linked = rendered_links[placeholder]
            entry = entry.replace(placeholder, rendered)
            status[label] = linked
        for placeholder, target, label in (
            ("{{CRATE_PLURAL}}", "Standard Transit Crate", "transit crates"),
            ("{{FREIGHT_TRAM}}", "Industrial Freight Tram", "Industrial Freight Tram"),
        ):
            entity_id = created_entities.get(target)
            rendered = f"[entity:{entity_id}|{label}]" if entity_id else label
            entry = entry.replace(placeholder, rendered)
            status[target] = entity_id is not None
        match = exact(known, str(spec["name"]))
        if not match:
            raise SystemExit(f"Published item {spec['name']!r} disappeared.")
        item_id = int(match["id"])
        payload = {
            "name": str(spec["name"]),
            "type": str(spec["type"]),
            "entry": entry,
            "is_private": bool(spec.get("is_private", False)),
        }
        request(token, "PATCH", f"{item_path}/{item_id}", payload=payload)
        final = request(token, "GET", f"{item_path}/{item_id}").get("data", {})
        if str(final.get("entry") or "") != entry:
            raise SystemExit(f"Cross-linked read-back failed for {spec['name']!r}.")
        receipt["link_status"] = status
        receipt["entry_verified"] = True

    result = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "batch_sha256": canonical_digest(document),
        "items": receipts,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
