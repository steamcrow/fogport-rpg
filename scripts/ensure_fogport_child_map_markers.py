"""Ensure every established immediate Fogport child has one linked map marker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kanka-Librarian/0.8",
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
        records.extend(item for item in body.get("data", []) if isinstance(item, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact_one(records: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
    matches = [
        item
        for item in records
        if str(item.get("name", "")).strip().casefold() == name.strip().casefold()
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one {kind} named {name!r}; found {len(matches)}.")
    return matches[0]


def validate_manifest(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Map-coverage manifest has the wrong campaign id.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Map-coverage manifest has the wrong campaign name.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or approval.get("approved_by") != "Daniel Davis":
        raise SystemExit("Daniel Davis approval is required.")
    children = document.get("immediate_children", [])
    if not isinstance(children, list) or not children:
        raise SystemExit("No immediate Fogport children were approved.")
    names = [str(item.get("name", "")).strip().casefold() for item in children]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise SystemExit("Immediate-child names must be present and unique.")
    for child in children:
        marker = child.get("missing_marker", {})
        if not {"latitude", "longitude", "shape_id", "icon"}.issubset(marker):
            raise SystemExit(f"Missing approved fallback marker for {child.get('name')!r}.")
    return document


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

    locations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations")
    fogport = exact_one(locations, "Fogport", "Fogport location")
    maps = all_pages(token, f"campaigns/{CAMPAIGN_ID}/maps")
    map_summary = exact_one(maps, str(document["map_name"]), "Fogport map")
    map_id = int(map_summary["id"])
    map_record = request(
        token, "GET", f"campaigns/{CAMPAIGN_ID}/maps/{map_id}"
    ).get("data", {})
    live_width = int(map_record.get("width") or 0)
    live_height = int(map_record.get("height") or 0)
    if not map_record.get("image_full") or live_width <= 0 or live_height <= 0:
        raise SystemExit("Fogport map has no usable processed image.")

    coordinate_space = document["coordinate_space"]
    source_width = int(coordinate_space["source_width"])
    source_height = int(coordinate_space["source_height"])
    source_ratio = source_width / source_height
    live_ratio = live_width / live_height
    if abs(source_ratio - live_ratio) / source_ratio > 0.005:
        raise SystemExit(
            "Live Fogport map has a different aspect ratio; "
            "refusing to place missing markers blindly."
        )

    marker_base = f"campaigns/{CAMPAIGN_ID}/maps/{map_id}/map_markers"
    markers = all_pages(token, marker_base)
    results: list[dict[str, Any]] = []

    for child_spec in document["immediate_children"]:
        location = exact_one(locations, str(child_spec["name"]), "location")
        entity_id = int(location["entity_id"])
        linked = [
            marker
            for marker in markers
            if int(marker.get("entity_id") or 0) == entity_id
        ]
        if len(linked) > 1:
            raise SystemExit(
                f"Multiple markers link to {location['name']!r}; refusing to guess."
            )
        if linked:
            final = linked[0]
            created = False
        else:
            approved = child_spec["missing_marker"]
            payload = {
                "entity_id": entity_id,
                "map_id": map_id,
                "latitude": round(
                    float(approved["latitude"]) * live_height / source_height, 3
                ),
                "longitude": round(
                    float(approved["longitude"]) * live_width / source_width, 3
                ),
                "shape_id": int(approved["shape_id"]),
                "icon": int(approved["icon"]),
                "is_draggable": bool(approved.get("is_draggable", True)),
                "is_popupless": bool(approved.get("is_popupless", False)),
                "opacity": int(approved.get("opacity", 100)),
                "visibility_id": int(approved.get("visibility_id", 1)),
                "colour": str(approved.get("colour", "#d4af37")),
            }
            final = request(token, "POST", marker_base, payload=payload).get("data", {})
            markers.append(final)
            created = True
        results.append(
            {
                "name": str(location["name"]),
                "location_id": int(location["id"]),
                "entity_id": entity_id,
                "marker_id": int(final["id"]),
                "created": created,
                "latitude": float(final["latitude"]),
                "longitude": float(final["longitude"]),
                "existing_position_preserved": not created,
            }
        )

    verified_markers = all_pages(token, marker_base)
    for result in results:
        matches = [
            marker
            for marker in verified_markers
            if int(marker.get("entity_id") or 0) == result["entity_id"]
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"Coverage verification failed for {result['name']!r}: "
                f"expected one marker, found {len(matches)}."
            )

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "fogport_location_id": int(fogport["id"]),
        "fogport_entity_id": int(fogport["entity_id"]),
        "map": str(map_record["name"]),
        "map_id": map_id,
        "map_width": live_width,
        "map_height": live_height,
        "scope": "Established immediate children of Fogport",
        "coverage_verified": True,
        "covered_count": len(results),
        "locations": results,
        "explore_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/maps/{map_id}/explore",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
