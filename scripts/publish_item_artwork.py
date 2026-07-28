"""Attach checksum-locked artwork to verified Fogport Item entities."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/1.0",
    }


def _get(token: str, path: str) -> dict[str, Any]:
    response = requests.get(
        f"https://api.kanka.io/1.0/{path}",
        headers=_headers(token),
        timeout=60,
    )
    if not response.ok:
        raise SystemExit(
            f"Kanka GET {path} returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    return response.json()


def _validated(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Artwork manifest has the wrong campaign id.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Artwork manifest has the wrong campaign name.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise SystemExit("Artwork manifest is not explicitly approved.")

    results: list[dict[str, Any]] = []
    for item in document.get("items", []):
        relative_path = str(item.get("image_path", "")).strip()
        image_path = (REPOSITORY_ROOT / relative_path).resolve()
        try:
            image_path.relative_to(REPOSITORY_ROOT)
        except ValueError as exc:
            raise SystemExit("Artwork path escapes the repository.") from exc
        if image_path.suffix.lower() not in ALLOWED_SUFFIXES or not image_path.is_file():
            raise SystemExit(f"Approved artwork is missing or invalid: {relative_path}")
        actual_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if actual_sha != str(item.get("sha256", "")).strip().lower():
            raise SystemExit(f"Approved artwork changed: {relative_path}")
        results.append({**item, "path": image_path})
    if not results:
        raise SystemExit("Artwork manifest contains no items.")
    return results


def _upload(token: str, entity_id: int, image_path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}"
            f"/entities/{entity_id}/image",
            headers=_headers(token),
            files={"file": (image_path.name, stream, mime_type)},
            timeout=120,
        )
    if not response.ok:
        raise SystemExit(
            f"Kanka item-artwork upload returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    image = response.json().get("data", {}).get("image", {})
    if not isinstance(image, dict) or not image.get("uuid"):
        raise SystemExit("Kanka did not return main-image metadata.")
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    approved = _validated(document)
    token = os.environ["KANKA_API_TOKEN"]
    campaign = _get(token, f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    results = []
    for item in approved:
        entity_id = int(item["entity_id"])
        entity = _get(
            token, f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}"
        ).get("data", {})
        if (
            int(entity.get("id", 0)) != entity_id
            or str(entity.get("name", "")).casefold()
            != str(item["name"]).casefold()
        ):
            raise SystemExit(
                f"Entity identity lock failed for {item['name']} ({entity_id})."
            )
        uploaded = _upload(token, entity_id, item["path"])
        readback = _get(
            token, f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image"
        ).get("data", {}).get("image", {})
        if (
            not isinstance(readback, dict)
            or readback.get("uuid") != uploaded.get("uuid")
            or not readback.get("full")
            or not readback.get("thumbnail")
        ):
            raise SystemExit(f"Kanka artwork read-back failed for {item['name']}.")
        results.append(
            {
                "name": item["name"],
                "entity_id": entity_id,
                "source_sha256": item["sha256"],
                "kanka_uuid": readback["uuid"],
                "overview_url": (
                    f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"
                ),
            }
        )

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "items_verified": results,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
