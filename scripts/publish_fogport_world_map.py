"""Create and verify Fogport's approved keyable Kanka world map."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
KANKA_MAX_IMAGE_BYTES = 3072 * 1024
ROOT = Path(__file__).resolve().parents[1]


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


def validate_manifest(path: Path) -> tuple[dict[str, Any], Path, str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("World-map manifest has the wrong campaign id.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("World-map manifest has the wrong campaign name.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise SystemExit("World-map manifest is not explicitly approved.")

    image_path = (ROOT / str(document["image_path"])).resolve()
    try:
        image_path.relative_to(ROOT)
    except ValueError as exc:
        raise SystemExit("World-map image path escapes the repository.") from exc
    if not image_path.is_file() or image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise SystemExit("Approved world-map image is missing or invalid.")
    image_bytes = image_path.stat().st_size
    if image_bytes > KANKA_MAX_IMAGE_BYTES:
        raise SystemExit(
            "Approved world-map image exceeds Kanka's current 3072 KB upload limit: "
            f"{image_bytes} bytes."
        )
    actual_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    if actual_sha != str(document["sha256"]).lower():
        raise SystemExit("Approved world-map image changed after approval.")
    return document, image_path, actual_sha


def upload_image(token: str, entity_id: int, image_path: Path) -> dict[str, Any]:
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image",
            headers=headers(token),
            files={"file": (image_path.name, stream, mime)},
            timeout=180,
        )
    if not response.ok:
        raise SystemExit(
            f"Kanka map-image upload returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    image = response.json().get("data", {}).get("image", {})
    if not isinstance(image, dict) or not image.get("uuid"):
        raise SystemExit("Kanka did not return processed map-image metadata.")
    return image


def verified_map(token: str, map_id: int, uploaded_uuid: str) -> dict[str, Any]:
    """Allow Kanka's image processor time to update the Map resource."""
    last: dict[str, Any] = {}
    for _ in range(12):
        last = request(
            token, "GET", f"campaigns/{CAMPAIGN_ID}/maps/{map_id}"
        ).get("data", {})
        image = request(
            token,
            "GET",
            f"campaigns/{CAMPAIGN_ID}/entities/{int(last['entity_id'])}/image",
        ).get("data", {}).get("image", {})
        if (
            isinstance(image, dict)
            and image.get("uuid") == uploaded_uuid
            and last.get("image_full")
            and int(last.get("width") or 0) > 0
            and int(last.get("height") or 0) > 0
        ):
            return last
        time.sleep(5)
    raise SystemExit(
        "Kanka accepted the map image but its processed map read-back did not finish."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document, image_path, image_sha = validate_manifest(args.manifest)
    token = os.environ["KANKA_API_TOKEN"]

    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    fogport = exact_one(
        all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations"),
        "Fogport",
        "Fogport location",
    )
    maps = all_pages(token, f"campaigns/{CAMPAIGN_ID}/maps")
    matches = [
        item
        for item in maps
        if str(item.get("name", "")).strip().casefold()
        == str(document["map_name"]).casefold()
    ]
    if len(matches) > 1:
        raise SystemExit("Multiple Fogport city maps match the approved name.")

    payload = {
        "name": document["map_name"],
        "entry": document["entry"],
        "type": "City",
        "location_id": int(fogport["id"]),
        "is_real": False,
        "is_private": False,
    }
    if matches:
        map_id = int(matches[0]["id"])
        map_record = request(
            token,
            "PATCH",
            f"campaigns/{CAMPAIGN_ID}/maps/{map_id}",
            payload=payload,
        ).get("data", {})
        created = False
    else:
        map_record = request(
            token, "POST", f"campaigns/{CAMPAIGN_ID}/maps", payload=payload
        ).get("data", {})
        map_id = int(map_record["id"])
        created = True

    entity_id = int(map_record["entity_id"])
    uploaded = upload_image(token, entity_id, image_path)
    final = verified_map(token, map_id, str(uploaded["uuid"]))
    expected = {
        "name": document["map_name"],
        "entry": document["entry"],
        "type": "City",
        "location_id": int(fogport["id"]),
        "is_real": False,
        "is_private": False,
    }
    mismatches = {
        key: {"expected": value, "actual": final.get(key)}
        for key, value in expected.items()
        if final.get(key) != value
    }
    if mismatches:
        raise SystemExit(f"Fogport map read-back failed: {mismatches!r}")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "map": final["name"],
        "created": created,
        "map_id": map_id,
        "entity_id": int(final["entity_id"]),
        "location_id": int(final["location_id"]),
        "width": int(final["width"]),
        "height": int(final["height"]),
        "upload_bytes": image_path.stat().st_size,
        "source_sha256": image_sha,
        "kanka_uuid": uploaded["uuid"],
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/maps/{map_id}",
        "explore_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/maps/{map_id}/explore",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
