"""Publish and verify Fogport's Cinderhack item and main image."""

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


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/0.9",
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
        headers={**headers(token), "Content-Type": "application/json"},
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


def exact(
    records: list[dict[str, Any]], name: str, kind: str
) -> dict[str, Any] | None:
    matches = [
        record
        for record in records
        if str(record.get("name", "")).strip().casefold()
        == name.strip().casefold()
    ]
    if len(matches) > 1:
        raise SystemExit(f"Multiple {kind} records named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def optional_link(
    token: str,
    section: str,
    names: list[str],
    label: str,
) -> tuple[str, bool]:
    records = all_pages(token, f"campaigns/{CAMPAIGN_ID}/{section}")
    for name in names:
        matches = [
            record
            for record in records
            if str(record.get("name", "")).strip().casefold() == name.casefold()
        ]
        if len(matches) == 1:
            return f"[entity:{int(matches[0]['entity_id'])}|{label}]", True
        if len(matches) > 1:
            return label, False
    return label, False


def validate_manifest(document: dict[str, Any]) -> tuple[Path, str]:
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Manifest is not locked to Fogport 410879.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Manifest campaign name is not Fogport.")
    approval = document.get("approval", {})
    if (
        approval.get("status") != "approved"
        or approval.get("approved_by") != "Daniel Davis"
    ):
        raise SystemExit("Daniel Davis approval is required.")

    image_path = (REPOSITORY_ROOT / str(document["image_path"])).resolve()
    try:
        image_path.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise SystemExit("Image path escapes the repository.") from exc
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise SystemExit("Approved image has an unsupported file type.")
    if not image_path.is_file():
        raise SystemExit("Approved Cinderhack image is missing.")
    actual_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    if actual_sha != str(document["sha256"]).lower():
        raise SystemExit("Approved Cinderhack image changed after approval.")
    return image_path, actual_sha


def upload_image(
    token: str, entity_id: int, image_path: Path
) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            (
                f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}"
                f"/entities/{entity_id}/image"
            ),
            headers=headers(token),
            files={"file": (image_path.name, stream, mime_type)},
            timeout=120,
        )
    if not response.ok:
        raise SystemExit(
            f"Kanka image upload returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
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

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    image_path, image_sha = validate_manifest(document)
    token = os.environ["KANKA_API_TOKEN"]

    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    link_specs = {
        "{{FOGPORT}}": ("locations", ["Fogport"], "Fogport"),
        "{{SHAMBLES}}": ("locations", ["The Shambles", "Shambles"], "the Shambles"),
        "{{CATASTROPHE}}": ("events", ["The Catastrophe", "Catastrophe"], "Catastrophe"),
        "{{THRALLO}}": ("creatures", ["Thrallo", "Thrallos"], "Thrallo"),
        "{{HORSEMEN}}": ("creatures", ["Horsemen", "Horseman"], "Horsemen"),
    }
    spec = document["item"]
    entry = str(spec["entry"])
    link_status: dict[str, bool] = {}
    for placeholder, (section, names, label) in link_specs.items():
        rendered, linked = optional_link(token, section, names, label)
        entry = entry.replace(placeholder, rendered)
        link_status[label] = linked

    item_path = f"campaigns/{CAMPAIGN_ID}/items"
    items = all_pages(token, item_path)
    match = exact(items, str(spec["name"]), "item")
    payload = {
        "name": str(spec["name"]),
        "type": str(spec["type"]),
        "entry": entry,
        "is_private": bool(spec.get("is_private", False)),
    }
    if match:
        item_id = int(match["id"])
        request(token, "PATCH", f"{item_path}/{item_id}", payload=payload)
        created = False
    else:
        made = request(token, "POST", item_path, payload=payload).get("data", {})
        item_id = int(made["id"])
        created = True

    final = request(token, "GET", f"{item_path}/{item_id}").get("data", {})
    if (
        str(final.get("name")) != payload["name"]
        or str(final.get("type")) != payload["type"]
        or bool(final.get("is_private")) is not payload["is_private"]
        or str(final.get("entry") or "") != entry
    ):
        raise SystemExit("Cinderhack item read-back failed.")

    entity_id = int(final["entity_id"])
    uploaded = upload_image(token, entity_id, image_path)
    image_readback = request(
        token, "GET", f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image"
    ).get("data", {}).get("image", {})
    if (
        not isinstance(image_readback, dict)
        or image_readback.get("uuid") != uploaded.get("uuid")
        or not image_readback.get("full")
        or not image_readback.get("thumbnail")
    ):
        raise SystemExit("Cinderhack image read-back failed.")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "item": final["name"],
        "item_id": item_id,
        "entity_id": entity_id,
        "created": created,
        "type": final["type"],
        "is_private": bool(final["is_private"]),
        "entry_verified": True,
        "link_status": link_status,
        "source_sha256": image_sha,
        "image_uuid": image_readback["uuid"],
        "image_verified": True,
        "overview_url": (
            f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"
        ),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
