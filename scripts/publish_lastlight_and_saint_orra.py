"""Publish Lastlight, Saint Orra's Colossus, and its linked Fogport map marker."""

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
        records.extend(x for x in body.get("data", []) if isinstance(x, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact(records: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any] | None:
    matches = [
        x for x in records
        if str(x.get("name", "")).strip().casefold() == name.strip().casefold()
    ]
    if len(matches) > 1:
        raise SystemExit(f"Multiple {kind} records named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def read_location(token: str, location_id: int) -> dict[str, Any]:
    return request(
        token, "GET", f"campaigns/{CAMPAIGN_ID}/locations/{location_id}"
    ).get("data", {})


def upsert_location(
    token: str,
    records: list[dict[str, Any]],
    spec: dict[str, Any],
    parent_id: int,
) -> tuple[dict[str, Any], bool]:
    match = exact(records, str(spec["name"]), "location")
    payload = {
        "name": str(spec["name"]),
        "type": str(spec["type"]),
        "entry": str(spec["entry"]),
        "is_private": bool(spec.get("is_private", False)),
        "location_id": parent_id,
    }
    path = f"campaigns/{CAMPAIGN_ID}/locations"
    if match:
        location_id = int(match["id"])
        request(token, "PATCH", f"{path}/{location_id}", payload=payload)
        created = False
    else:
        made = request(token, "POST", path, payload=payload).get("data", {})
        location_id = int(made["id"])
        records.append(made)
        created = True
    final = read_location(token, location_id)
    if (
        str(final.get("name")) != payload["name"]
        or int(final.get("location_id") or 0) != parent_id
        or str(final.get("type")) != payload["type"]
        or bool(final.get("is_private")) is not payload["is_private"]
    ):
        raise SystemExit(f"Location read-back failed for {payload['name']!r}.")
    return final, created


def upsert_post(
    token: str,
    entity_id: int,
    post: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    base = f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/posts"
    current = all_pages(token, base)
    match = exact(current, str(post["name"]), "entity post")
    payload = {
        "name": str(post["name"]),
        "entry": str(post["entry"]),
        "entity_id": entity_id,
        "visibility_id": 3,
    }
    if match:
        post_id = int(match["id"])
        request(token, "PATCH", f"{base}/{post_id}", payload=payload)
        created = False
    else:
        made = request(token, "POST", base, payload=payload).get("data", {})
        post_id = int(made["id"])
        created = True
    final = request(token, "GET", f"{base}/{post_id}").get("data", {})
    if str(final.get("name")) != payload["name"] or int(final.get("visibility_id") or 0) != 3:
        raise SystemExit("Saint Orra GM post read-back failed.")
    return final, created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Manifest is not locked to Fogport 410879.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or approval.get("approved_by") != "Daniel Davis":
        raise SystemExit("Daniel Davis approval is required.")

    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    locations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations")
    fogport = exact(locations, "Fogport", "Fogport location")
    blackwake = exact(locations, str(document["district"]["parent_name"]), "Blackwake location")
    if not fogport or not blackwake:
        raise SystemExit("Fogport or Blackwake is missing; refusing to invent a parent.")
    if int(blackwake.get("location_id") or 0) != int(fogport["id"]):
        raise SystemExit("Blackwake is not nested directly beneath Fogport.")

    district, district_created = upsert_location(
        token, locations, document["district"], int(blackwake["id"])
    )
    colossus, colossus_created = upsert_location(
        token, locations, document["location"], int(district["id"])
    )

    station = exact(locations, str(document["station_name"]), "Grand Heliot Station")
    if not station:
        raise SystemExit("Grand Heliot Station is missing.")
    station_id = int(station["id"])
    station_direct = read_location(token, station_id)
    station_payload = {
        "name": str(station_direct["name"]),
        "type": str(station_direct.get("type") or ""),
        "entry": str(station_direct.get("entry") or ""),
        "is_private": bool(station_direct.get("is_private", False)),
        "location_id": int(district["id"]),
    }
    request(
        token, "PATCH", f"campaigns/{CAMPAIGN_ID}/locations/{station_id}",
        payload=station_payload,
    )
    station_final = read_location(token, station_id)
    if int(station_final.get("location_id") or 0) != int(district["id"]):
        raise SystemExit("Grand Heliot Station nesting read-back failed.")

    post, post_created = upsert_post(
        token, int(colossus["entity_id"]), document["location"]["gm_post"]
    )

    maps = all_pages(token, f"campaigns/{CAMPAIGN_ID}/maps")
    map_record = exact(maps, str(document["map_name"]), "Fogport map")
    if not map_record:
        raise SystemExit("Approved Fogport map is missing.")
    map_id = int(map_record["id"])
    map_direct = request(
        token, "GET", f"campaigns/{CAMPAIGN_ID}/maps/{map_id}"
    ).get("data", {})
    if not map_direct.get("image_full"):
        raise SystemExit("Fogport map has no processed image.")
    if (
        int(map_direct.get("width") or 0) != int(document["expected_map_width"])
        or int(map_direct.get("height") or 0) != int(document["expected_map_height"])
    ):
        raise SystemExit("Fogport map dimensions do not match the approved radial map.")

    approved = document["marker"]
    marker_payload = {
        "entity_id": int(colossus["entity_id"]),
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
    marker_base = f"campaigns/{CAMPAIGN_ID}/maps/{map_id}/map_markers"
    markers = all_pages(token, marker_base)
    linked = [
        x for x in markers
        if int(x.get("entity_id") or 0) == int(colossus["entity_id"])
    ]
    if len(linked) > 1:
        raise SystemExit("Multiple Saint Orra markers exist; refusing to guess.")
    if linked:
        marker_id = int(linked[0]["id"])
        marker = request(
            token, "PATCH", f"{marker_base}/{marker_id}", payload=marker_payload
        ).get("data", {})
        marker_created = False
    else:
        marker = request(token, "POST", marker_base, payload=marker_payload).get("data", {})
        marker_id = int(marker["id"])
        marker_created = True
    if (
        int(marker.get("entity_id") or 0) != int(colossus["entity_id"])
        or float(marker.get("latitude")) != marker_payload["latitude"]
        or float(marker.get("longitude")) != marker_payload["longitude"]
    ):
        raise SystemExit("Saint Orra marker read-back failed.")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "district": {
            "name": district["name"],
            "id": int(district["id"]),
            "entity_id": int(district["entity_id"]),
            "created": district_created,
        },
        "location": {
            "name": colossus["name"],
            "id": int(colossus["id"]),
            "entity_id": int(colossus["entity_id"]),
            "created": colossus_created,
        },
        "station_nested_under_lastlight": True,
        "gm_post_id": int(post["id"]),
        "gm_post_created": post_created,
        "map_id": map_id,
        "marker_id": marker_id,
        "marker_created": marker_created,
        "latitude": marker_payload["latitude"],
        "longitude": marker_payload["longitude"],
        "district_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{int(district['entity_id'])}",
        "location_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{int(colossus['entity_id'])}",
        "explore_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/maps/{map_id}/explore",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
