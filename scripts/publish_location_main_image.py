"""Attach one checksum-locked main image to one exact Fogport location."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import all_pages, headers, request

install_api_pacing()

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def exact_one(records: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [
        item for item in records
        if str(item.get("name", "")).strip().casefold() == name.casefold()
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one location named {name!r}; found {len(matches)}.")
    return matches[0]


def validate(document: dict[str, Any]) -> tuple[Path, str]:
    if document.get("schema_version") != 1 or document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Image manifest is not locked to Fogport 410879.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Image manifest campaign name is not Fogport.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise SystemExit("Image manifest is not explicitly approved.")
    path = (REPOSITORY_ROOT / str(document.get("repository_path", ""))).resolve()
    try:
        path.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise SystemExit("Approved image path escapes the repository.") from exc
    if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise SystemExit("Approved location image is missing or invalid.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != str(document.get("sha256", "")).strip().lower():
        raise SystemExit("Approved location image changed after approval.")
    return path, digest


def upload(token: str, entity_id: int, image_path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image",
            headers=headers(token),
            files={"file": (image_path.name, stream, mime_type)},
            timeout=120,
        )
    if not response.ok:
        raise SystemExit(f"Kanka location image upload returned HTTP {response.status_code}: {response.text[:300]}")
    image = response.json().get("data", {}).get("image", {})
    if not isinstance(image, dict) or not image.get("uuid"):
        raise SystemExit("Kanka did not return location-image metadata.")
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA writes are disabled or not locked to Fogport 410879.")

    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    image_path, image_sha = validate(document)
    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")
    location = exact_one(all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations"), str(document["location_name"]))
    location_id, entity_id = int(location["id"]), int(location["entity_id"])
    before = request(token, "GET", f"campaigns/{CAMPAIGN_ID}/locations/{location_id}").get("data", {})
    uploaded = upload(token, entity_id, image_path)
    image = request(token, "GET", f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image").get("data", {}).get("image", {})
    if not isinstance(image, dict) or image.get("uuid") != uploaded.get("uuid") or not image.get("full") or not image.get("thumbnail"):
        raise SystemExit("Kanka location image read-back failed.")
    after = request(token, "GET", f"campaigns/{CAMPAIGN_ID}/locations/{location_id}").get("data", {})
    stable = ("id", "entity_id", "name", "type", "is_private", "parent_id", "entry")
    changed = [key for key in stable if before.get(key) != after.get(key)]
    if changed:
        raise SystemExit("Image-only boundary failed; non-image location fields changed: " + ", ".join(changed))
    receipt = {
        "published": True, "operation": "location-main-image-only",
        "campaign": CAMPAIGN_NAME, "campaign_id": CAMPAIGN_ID,
        "location": after["name"], "location_id": location_id, "entity_id": entity_id,
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
        "source_sha256": image_sha, "kanka_uuid": image["uuid"],
        "full": image["full"], "thumbnail": image["thumbnail"], "non_image_fields_changed": [],
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
