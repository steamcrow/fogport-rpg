"""Upload one approved main image without mutating any other Kanka fields."""

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
install_api_pacing()

from kanka_librarian.client import KankaClient


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def load_approval(path: Path) -> tuple[dict[str, Any], bytes, str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "campaign_id",
        "campaign_name",
        "entity_id",
        "entity_name",
        "repository_path",
        "sha256",
        "approval",
    }
    missing = sorted(required - document.keys())
    if missing:
        raise SystemExit(f"Image approval is missing: {', '.join(missing)}")
    if document["schema_version"] != 1:
        raise SystemExit("Unsupported image approval schema.")
    approval = document["approval"]
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise SystemExit("Image is not approved.")

    relative_path = str(document["repository_path"]).strip()
    candidate = (REPOSITORY_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise SystemExit("Approved image path escapes the repository.") from exc
    if not candidate.is_file():
        raise SystemExit(f"Approved image is missing: {relative_path}")
    if candidate.suffix == ".b64":
        image_name = candidate.stem
        image_suffix = Path(image_name).suffix.lower()
        try:
            image_bytes = base64.b64decode(
                candidate.read_text(encoding="ascii"), validate=True
            )
        except (ValueError, UnicodeError) as exc:
            raise SystemExit("Approved image base64 is invalid.") from exc
    else:
        image_name = candidate.name
        image_suffix = candidate.suffix.lower()
        image_bytes = candidate.read_bytes()
    if image_suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise SystemExit("Approved image must be PNG, JPEG, or WebP.")

    expected = str(document["sha256"]).strip().lower()
    actual = hashlib.sha256(image_bytes).hexdigest()
    if actual != expected:
        raise SystemExit("Approved image changed after approval; SHA-256 mismatch.")
    return document, image_bytes, image_name


def upload_image(
    *,
    token: str,
    campaign_id: int,
    entity_id: int,
    image_bytes: bytes,
    image_name: str,
) -> dict[str, Any]:
    url = (
        f"https://api.kanka.io/1.0/campaigns/{campaign_id}"
        f"/entities/{entity_id}/image"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/0.6",
    }
    mime_type = mimetypes.guess_type(image_name)[0] or "application/octet-stream"
    response = requests.post(
        url,
        headers=headers,
        files={"file": (image_name, image_bytes, mime_type)},
        timeout=60,
    )
    if not response.ok:
        raise SystemExit(
            f"Kanka image upload returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    image = response.json().get("data", {}).get("image", {})
    if not isinstance(image, dict) or not image.get("uuid"):
        raise SystemExit("Kanka did not return main-image metadata.")
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("approval", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    document, image_bytes, image_name = load_approval(args.approval)
    campaign_id = int(document["campaign_id"])
    entity_id = int(document["entity_id"])
    expected_campaign = str(document["campaign_name"]).strip()
    expected_entity = str(document["entity_name"]).strip()

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    campaign = client.get_campaign(campaign_id)
    actual_campaign = str(campaign.get("name", "")).strip()
    if actual_campaign.casefold() != expected_campaign.casefold():
        raise SystemExit(
            f"Campaign lock failed: {campaign_id} is {actual_campaign!r}, "
            f"not {expected_campaign!r}."
        )

    before = client._get(
        f"campaigns/{campaign_id}/entities/{entity_id}"
    ).get("data", {})
    actual_entity = str(before.get("name", "")).strip()
    if actual_entity.casefold() != expected_entity.casefold():
        raise SystemExit(
            f"Entity lock failed: {entity_id} is {actual_entity!r}, "
            f"not {expected_entity!r}."
        )

    uploaded = upload_image(
        token=token,
        campaign_id=campaign_id,
        entity_id=entity_id,
        image_bytes=image_bytes,
        image_name=image_name,
    )
    readback = client._get(
        f"campaigns/{campaign_id}/entities/{entity_id}/image"
    ).get("data", {}).get("image", {})
    if (
        not isinstance(readback, dict)
        or readback.get("uuid") != uploaded.get("uuid")
        or not readback.get("full")
        or not readback.get("thumbnail")
    ):
        raise SystemExit("Kanka main-image read-back did not match the upload.")

    after = client._get(
        f"campaigns/{campaign_id}/entities/{entity_id}"
    ).get("data", {})
    stable_fields = ("id", "name", "type_id", "is_private", "parent_id", "entry")
    changed = [key for key in stable_fields if before.get(key) != after.get(key)]
    if changed:
        raise SystemExit(
            "Image-only boundary failed; non-image fields changed: "
            + ", ".join(changed)
        )

    receipt = {
        "published": True,
        "operation": "main-image-only",
        "campaign": actual_campaign,
        "campaign_id": campaign_id,
        "entity_id": entity_id,
        "entity_name": actual_entity,
        "overview_url": f"https://app.kanka.io/w/{campaign_id}/entities/{entity_id}",
        "repository_path": document["repository_path"],
        "source_sha256": document["sha256"],
        "kanka_uuid": readback["uuid"],
        "full": readback["full"],
        "thumbnail": readback["thumbnail"],
        "non_image_fields_changed": [],
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Kanka main image verified\n\n")
            stream.write(f"- Entity: **{actual_entity}** (`{entity_id}`)\n")
            stream.write(f"- Kanka image UUID: `{readback['uuid']}`\n")
            stream.write("- Non-image fields changed: **none**\n")
            stream.write(f"- [Open Kanka Overview]({receipt['overview_url']})\n")


if __name__ == "__main__":
    main()
