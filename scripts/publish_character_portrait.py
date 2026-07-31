"""Upload and verify one checksum-locked Fogport character portrait."""

from __future__ import annotations

import argparse
import base64
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
from kanka_librarian.api import headers as _headers
install_api_pacing()

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _get(
    token: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.get(
        f"https://api.kanka.io/1.0/{path}",
        headers=_headers(token),
        params=params,
        timeout=60,
    )
    if not response.ok:
        raise SystemExit(
            f"Kanka GET {path} returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    return response.json()


def _find_character(token: str, accepted_names: list[str]) -> dict[str, Any]:
    wanted = {name.casefold() for name in accepted_names}
    matches: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _get(
            token,
            f"campaigns/{CAMPAIGN_ID}/characters",
            params={"page": page, "limit": 100},
        )
        matches.extend(
            item
            for item in payload.get("data", [])
            if str(item.get("name", "")).casefold() in wanted
        )
        meta = payload.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            break
        page += 1
    if len(matches) != 1:
        raise SystemExit(
            "Expected exactly one Fogport character matching "
            f"{accepted_names!r}; found {len(matches)}."
        )
    return matches[0]


def _validated_image(document: dict[str, Any]) -> tuple[bytes, str, str]:
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Portrait manifest has the wrong campaign id.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Portrait manifest has the wrong campaign name.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise SystemExit("Portrait manifest is not explicitly approved.")

    relative_path = str(document.get("base64_path", "")).strip()
    encoded_path = (REPOSITORY_ROOT / relative_path).resolve()
    try:
        encoded_path.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise SystemExit("Portrait path escapes the repository.") from exc
    if encoded_path.suffix.lower() != ".b64" or not encoded_path.is_file():
        raise SystemExit(f"Approved portrait is missing or invalid: {relative_path}")

    encoded = "".join(encoded_path.read_text(encoding="ascii").split())
    image_bytes = base64.b64decode(encoded, validate=True)
    actual_sha = hashlib.sha256(image_bytes).hexdigest()
    expected_sha = str(document.get("sha256", "")).strip().lower()
    if actual_sha != expected_sha:
        raise SystemExit("Approved portrait changed after approval.")
    return image_bytes, actual_sha, str(document.get("filename", "portrait.jpg"))


def _upload(
    token: str,
    entity_id: int,
    image_bytes: bytes,
    filename: str,
) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = requests.post(
        (
            f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}"
            f"/entities/{entity_id}/image"
        ),
        headers=_headers(token),
        files={"file": (filename, image_bytes, mime_type)},
        timeout=120,
    )
    if not response.ok:
        raise SystemExit(
            f"Kanka portrait upload returned HTTP {response.status_code}: "
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
    image_bytes, image_sha, filename = _validated_image(document)
    token = os.environ["KANKA_API_TOKEN"]

    campaign = _get(token, f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    character = _find_character(token, list(document["accepted_character_names"]))
    entity_id = int(character["entity_id"])
    uploaded = _upload(token, entity_id, image_bytes, filename)
    readback = _get(
        token,
        f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image",
    ).get("data", {}).get("image", {})
    if (
        not isinstance(readback, dict)
        or readback.get("uuid") != uploaded.get("uuid")
        or not readback.get("full")
        or not readback.get("thumbnail")
    ):
        raise SystemExit("Kanka character portrait read-back failed.")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "character": character["name"],
        "resource_id": int(character["id"]),
        "entity_id": entity_id,
        "source_sha256": image_sha,
        "kanka_uuid": readback["uuid"],
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
