"""Upload an approved, checksum-locked image set to the Fogport Kanka gallery."""

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
from kanka_librarian.api import headers as _headers
install_api_pacing()

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _get(token: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
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


def _validated_images(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("campaign_id") != CAMPAIGN_ID:
        raise SystemExit("Gallery manifest has the wrong campaign id.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Gallery manifest has the wrong campaign name.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved" or not approval.get("approved_by"):
        raise SystemExit("Gallery manifest is not explicitly approved.")

    approved: list[dict[str, Any]] = []
    for item in document.get("images", []):
        relative_path = str(item.get("path", "")).strip()
        expected_sha = str(item.get("sha256", "")).strip().lower()
        if not relative_path or len(expected_sha) != 64:
            raise SystemExit("Every gallery image needs a path and SHA-256.")
        image_path = (REPOSITORY_ROOT / relative_path).resolve()
        try:
            image_path.relative_to(REPOSITORY_ROOT)
        except ValueError as exc:
            raise SystemExit("Gallery image path escapes the repository.") from exc
        if image_path.suffix.lower() not in ALLOWED_SUFFIXES or not image_path.is_file():
            raise SystemExit(f"Approved gallery image is missing or invalid: {relative_path}")
        actual_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise SystemExit(f"Approved gallery image changed: {relative_path}")
        approved.append(
            {
                **item,
                "path": image_path,
                "relative_path": relative_path,
                "size": image_path.stat().st_size,
            }
        )
    if not approved:
        raise SystemExit("Gallery manifest contains no images.")
    return approved


def _list_gallery(token: str) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _get(
            token,
            f"campaigns/{CAMPAIGN_ID}/images",
            params={"page": page, "limit": 100},
        )
        images.extend(payload.get("data", []))
        meta = payload.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return images
        page += 1


def _same_name(remote: dict[str, Any], filename: str) -> bool:
    remote_name = str(remote.get("name") or "")
    return remote_name.casefold() in {filename.casefold(), Path(filename).stem.casefold()}


def _upload(token: str, image: dict[str, Any]) -> dict[str, Any]:
    path: Path = image["path"]
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as stream:
        response = requests.post(
            f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/images",
            headers=_headers(token),
            files={"file[]": (path.name, stream, mime_type)},
            data={"visibility_id": int(image.get("visibility_id", 1))},
            timeout=120,
        )
    if not response.ok:
        raise SystemExit(
            f"Kanka gallery upload returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    data = response.json().get("data", [])
    if not isinstance(data, list) or len(data) != 1 or not data[0].get("id"):
        raise SystemExit("Kanka gallery upload did not return one image UUID.")
    return data[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    approved = _validated_images(document)
    token = os.environ["KANKA_API_TOKEN"]
    campaign = _get(token, f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    gallery = _list_gallery(token)
    results: list[dict[str, Any]] = []
    for image in approved:
        filename = image["path"].name
        matches = [remote for remote in gallery if _same_name(remote, filename)]
        if len(matches) > 1:
            raise SystemExit(f"Multiple gallery images match {filename}; refusing to guess.")
        if matches:
            remote = matches[0]
            created = False
        else:
            remote = _upload(token, image)
            gallery.append(remote)
            created = True

        verified = _get(
            token,
            f"campaigns/{CAMPAIGN_ID}/images/{remote['id']}",
        ).get("data", {})
        if (
            str(verified.get("id")) != str(remote["id"])
            or not _same_name(verified, filename)
            or not verified.get("path")
        ):
            raise SystemExit(f"Gallery read-back failed for {filename}.")
        results.append(
            {
                "filename": filename,
                "repository_path": image["relative_path"],
                "sha256": image["sha256"],
                "gallery_uuid": str(verified["id"]),
                "gallery_path": verified["path"],
                "created": created,
            }
        )

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "images_verified": results,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
