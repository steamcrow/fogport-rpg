"""Create or update one approved, entity-linked marker on Fogport's Kanka map."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


def headers(token: str, *, json_body: bool = False) -> dict[str, str]:
    result = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/0.8",
    }
    if json_body:
        result["Content-Type"] = "application/json"
    return result


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
        headers=headers(token, json_body=payload is not None),
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
        raise SystemExit(f"Kanka {method} {path} returned an invalid response.")
    return body


def all_pages(token: str, path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        body = request(token, "GET", path, params={"page": page, "limit": 100})
        records.extend(item for item in body.get("data", []) if isinstance(item, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact_one(records: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
    matches = [
        item
        for item in records
        if str(item.get("name", "")).strip().casefold() == name.casefold()
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one {kind} named {name!r}; found {len(matches)}.")
    return matches[0]


def validate_manifest(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Map-marker manifest has the wrong campaign id.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Map-marker manifest has the wrong campaign name.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise SystemExit("Map-marker manifest is not explicitly approved.")
    marker = document.get("marker", {})
    required = {"latitude", "longitude", "shape_id", "icon"}
    if not required.issubset(marker):
        raise SystemExit("Map-marker manifest is missing required coordinates or display fields.")
    return document


def comparable(record: dict[str, Any], key: str) -> Any:
    value = record.get(key)
    if key in {"latitude", "longitude"}:
        return float(value)
    if key in {"entity_id", "map_id", "shape_id", "icon", "opacity", "visibility_id"}:
        return int(value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document = validate_manifest(args.manifest)
    token = os.environ["KANKA_API_TOKEN"]

    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    map_summary = exact_one(
        all_pages(token, f"campaigns/{CAMPAIGN_ID}/maps"),
        str(document["map_name"]),
        "map",
    )
    map_id = int(map_summary["id"])
    map_record = request(
        token, "GET", f"campaigns/{CAMPAIGN_ID}/maps/{map_id}"
    ).get("data", {})
    if not map_record.get("image_full"):
        raise SystemExit("Fogport world map exists but does not yet have a processed image.")

    location = exact_one(
        all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations"),
        str(document["location_name"]),
        "location",
    )
    entity_id = int(location["entity_id"])

    approved = dict(document["marker"])
    payload = {
        "entity_id": entity_id,
        "map_id": map_id,
        "latitude": float(approved["latitude"]),
        "longitude": float(approved["longitude"]),
        "shape_id": int(approved["shape_id"]),
        "icon": int(approved["icon"]),
        "is_draggable": bool(approved.get("is_draggable", True)),
        "is_popupless": bool(approved.get("is_popupless", False)),
        "opacity": int(approved.get("opacity", 100)),
        "visibility_id": int(approved.get("visibility_id", 1)),
        "colour": str(approved.get("colour", "#d4af37")),
    }

    marker_path = f"campaigns/{CAMPAIGN_ID}/maps/{map_id}/map_markers"
    markers = all_pages(token, marker_path)
    matches = [item for item in markers if int(item.get("entity_id") or 0) == entity_id]
    if len(matches) > 1:
        raise SystemExit(
            f"Multiple markers already link to {document['location_name']!r}; refusing to guess."
        )
    if matches:
        marker_id = int(matches[0]["id"])
        final = request(
            token,
            "PATCH",
            f"{marker_path}/{marker_id}",
            payload=payload,
        ).get("data", {})
        created = False
    else:
        final = request(token, "POST", marker_path, payload=payload).get("data", {})
        marker_id = int(final["id"])
        created = True

    expected = dict(payload)
    mismatches = {
        key: {"expected": value, "actual": final.get(key)}
        for key, value in expected.items()
        if comparable(final, key) != value
    }
    if mismatches:
        raise SystemExit(f"Grand Heliot Station marker read-back failed: {mismatches!r}")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "map": map_record["name"],
        "map_id": map_id,
        "location": location["name"],
        "location_id": int(location["id"]),
        "entity_id": entity_id,
        "marker_id": marker_id,
        "created": created,
        "latitude": float(final["latitude"]),
        "longitude": float(final["longitude"]),
        "is_draggable": bool(final["is_draggable"]),
        "explore_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/maps/{map_id}/explore",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
