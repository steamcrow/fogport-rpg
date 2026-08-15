"""One shared engine for publishing 'simple' Fogport entities.

'Simple' means: the entity has a name, a type, a public/private flag, an
entry (the description), maybe one approved main image, and maybe some
GM-only posts. That covers items and organizations. Locations and
characters have their own scripts because they have extra pieces
(locations nest inside a parent location; characters get portrait-style
image handling).

This file does the actual work. The two scripts that use it
(scripts/publish_approved_item.py and scripts/publish_approved_organization.py)
are each only a few lines long: they just say "run this for items" or
"run this for organizations."

Why this exists: before this file, every new item or organization needed
a brand-new, hand-written Python script copied from an older one. That is
exactly the kind of "write code every time" problem this file removes.
Adding a new item or organization from now on only requires a new JSON
file in the matching approved_* folder — no new code.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests

from .client import KankaClient
from .crosslinks import build_registry, link_entry, load_aliases
from .publisher import validate_approved_proposal
from .writer import KankaWriter

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _approved_main_image(change: dict[str, Any]) -> tuple[Path, str] | None:
    """Resolve and verify a content-locked repository image, if one was approved."""
    artwork = change.get("artwork")
    if artwork is None:
        return None
    if not isinstance(artwork, dict):
        raise SystemExit("Approved artwork metadata must be an object.")

    relative_path = str(artwork.get("main_image_path", "")).strip()
    expected_sha256 = str(artwork.get("sha256", "")).strip().lower()
    if not relative_path or not expected_sha256:
        raise SystemExit("Approved artwork needs main_image_path and sha256.")
    if len(expected_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in expected_sha256
    ):
        raise SystemExit("Approved artwork sha256 is invalid.")

    candidate = (REPOSITORY_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise SystemExit("Approved artwork path escapes the repository.") from exc
    if candidate.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        raise SystemExit("Approved artwork must be a PNG, JPEG, or WebP image.")
    if not candidate.is_file():
        raise SystemExit(f"Approved artwork is missing: {relative_path}")

    actual_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SystemExit("Approved artwork changed after approval; SHA-256 does not match.")
    return candidate, actual_sha256


def _upload_main_image(*, token: str, entity_id: int, image_path: Path) -> dict[str, Any]:
    """Set and return Kanka's main-image metadata for an entity."""
    url = f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/1.1",
    }
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            url, headers=headers, files={"file": (image_path.name, stream, mime_type)}, timeout=60,
        )
    if not response.ok:
        raise SystemExit(
            f"Kanka image upload returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit("Kanka image upload did not return JSON.") from exc
    data = payload.get("data", {})
    image = data.get("image", {}) if isinstance(data, dict) else {}
    if not isinstance(image, dict) or not image.get("uuid"):
        raise SystemExit("Kanka did not return main-image metadata.")
    return image


def publish_simple_entity(
    proposal_path: Path,
    receipt_path: Path,
    *,
    section: str,
    subject_label: str,
    list_method: str,
    id_field_name: str,
    optional_location_link: bool = False,
) -> None:
    """Publish one approved item or organization and verify the exact Kanka record.

    section: the proposal's "section" value and the Kanka API's plural name
        for this kind of entity ("items" or "organizations").
    subject_label: what to call this kind of thing in messages ("item",
        "organization").
    list_method: the KankaClient method name used to fetch every existing
        record of this kind, e.g. "list_items".
    id_field_name: what to call the Kanka record id in the receipt, e.g.
        "item_id".
    optional_location_link: items can optionally belong to a location; if
        the approved change includes publication.location_name, this looks
        up that location's entity id and includes it as location_id.
    """
    document = json.loads(proposal_path.read_text(encoding="utf-8"))
    campaign_id = validate_approved_proposal(document)
    if campaign_id != CAMPAIGN_ID:
        raise SystemExit(f"Fogport publisher refuses campaign {campaign_id}.")
    if len(document["proposals"]) != 1:
        raise SystemExit(f"The {subject_label} publisher requires exactly one approved change.")

    change = document["proposals"][0]
    if change.get("section") != section:
        raise SystemExit(f"The {subject_label} publisher refuses non-{section} changes.")
    approved_image = _approved_main_image(change)

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    campaign = client.get_campaign(CAMPAIGN_ID)
    actual_name = str(campaign.get("name", "")).strip()
    if actual_name.casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit(
            f"Campaign lock failed: {CAMPAIGN_ID} is {actual_name!r}, not {CAMPAIGN_NAME!r}."
        )

    existing_records = getattr(client, list_method)(CAMPAIGN_ID)
    matches = [
        record for record in existing_records
        if str(record.get("name", "")).casefold() == str(change["name"]).casefold()
    ]
    if len(matches) > 1:
        raise SystemExit(f"More than one {change['name']!r} exists; refusing to guess.")

    alias_path = REPOSITORY_ROOT / "kanka_librarian" / "crosslink_aliases.json"
    registry = build_registry(client, CAMPAIGN_ID, load_aliases(alias_path))
    entry, _ = link_entry(
        str(change.get("entry", "")),
        registry,
        source_entity_id=int(matches[0]["entity_id"]) if matches else None,
        source_private=bool(change.get("is_private", False)),
    )

    payload: dict[str, Any] = {
        "name": str(change["name"]),
        "type": str(change.get("type", "")),
        "is_private": bool(change.get("is_private", False)),
        "entry": entry,
    }

    if optional_location_link:
        location_name = str(change.get("publication", {}).get("location_name", "")).strip()
        if location_name:
            locations = client.list_locations(CAMPAIGN_ID)
            location_matches = [
                item for item in locations
                if str(item.get("name", "")).casefold() == location_name.casefold()
            ]
            if len(location_matches) != 1:
                raise SystemExit(
                    f"Expected exactly one location named {location_name!r}; "
                    f"found {len(location_matches)}. Refusing to guess."
                )
            payload["location_id"] = int(location_matches[0]["entity_id"])

    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    if matches:
        record_id = int(matches[0]["id"])
        created = False
    else:
        created_item = writer.create_entity(CAMPAIGN_ID, section, payload)
        record_id = int(created_item["id"])
        created = True

    writer.update_entity(CAMPAIGN_ID, section, record_id, payload)
    endpoint = "organisations" if section == "organizations" else section
    item = client._get(f"campaigns/{CAMPAIGN_ID}/{endpoint}/{record_id}").get("data", {})
    expected_record = {
        "name": payload["name"],
        "type": payload["type"],
        "is_private": payload["is_private"],
        "entry": payload["entry"],
    }
    actual_record = {key: item.get(key) for key in expected_record}
    if actual_record != expected_record:
        raise SystemExit(
            f"Kanka {subject_label} read-back did not match approval:\n"
            + json.dumps({"expected": expected_record, "actual": actual_record}, indent=2)
        )

    entity_id = int(item["entity_id"])
    image_verified = None
    if approved_image is not None:
        image_path, image_sha256 = approved_image
        uploaded_image = _upload_main_image(token=token, entity_id=entity_id, image_path=image_path)
        image_readback = client._get(f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image").get("data", {})
        readback_main = image_readback.get("image", {}) if isinstance(image_readback, dict) else {}
        if (
            not isinstance(readback_main, dict)
            or readback_main.get("uuid") != uploaded_image.get("uuid")
            or not readback_main.get("full")
            or not readback_main.get("thumbnail")
        ):
            raise SystemExit("Kanka main-image read-back did not match the uploaded artwork.")
        image_verified = {
            "repository_path": str(image_path.relative_to(REPOSITORY_ROOT)),
            "source_sha256": image_sha256,
            "kanka_uuid": readback_main["uuid"],
            "full": readback_main["full"],
            "thumbnail": readback_main["thumbnail"],
        }

    posts_verified = []
    for approved_post in change.get("posts", []):
        post_name = str(approved_post.get("name", "")).strip()
        if not post_name:
            raise SystemExit("Approved post is missing its name.")
        post_entry, _ = link_entry(
            str(approved_post.get("entry", "")),
            registry,
            source_entity_id=entity_id,
            source_private=int(approved_post.get("visibility_id", 3)) == 3,
        )
        post_payload = {
            "name": post_name,
            "entry": post_entry,
            "entity_id": entity_id,
            "visibility_id": int(approved_post.get("visibility_id", 3)),
        }
        if post_payload["visibility_id"] != 3:
            raise SystemExit(f"GM post {post_name!r} must use administrator-only visibility_id 3.")

        existing_posts = client.list_entity_posts(CAMPAIGN_ID, entity_id)
        post_matches = [
            post for post in existing_posts
            if str(post.get("name", "")).casefold() == post_name.casefold()
        ]
        if len(post_matches) > 1:
            raise SystemExit(f"More than one post named {post_name!r} exists; refusing to guess.")
        if post_matches:
            post_id = int(post_matches[0]["id"])
            post_created = False
            writer.update_post(CAMPAIGN_ID, entity_id, post_id, post_payload)
        else:
            created_post = writer.create_post(CAMPAIGN_ID, entity_id, post_payload)
            post_id = int(created_post["id"])
            post_created = True

        direct_post = client._get(
            f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/posts/{post_id}"
        ).get("data", {})
        expected_post = {
            "name": post_payload["name"],
            "entry": post_payload["entry"],
            "entity_id": post_payload["entity_id"],
            "visibility_id": post_payload["visibility_id"],
        }
        actual_post = {key: direct_post.get(key) for key in expected_post}
        if actual_post != expected_post:
            raise SystemExit(
                "Kanka GM-post read-back did not match approval:\n"
                + json.dumps({"expected": expected_post, "actual": actual_post}, indent=2)
            )
        posts_verified.append(
            {"id": post_id, "name": post_name, "created": post_created, "visibility_id": 3}
        )

    receipt = {
        "published": True,
        "created": created,
        "campaign": actual_name,
        "campaign_id": CAMPAIGN_ID,
        id_field_name: record_id,
        "entity_id": entity_id,
        "name": item["name"],
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
        "main_image_verified": image_verified,
        "private_posts_verified": posts_verified,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"# Fogport {subject_label} publication verified\n\n")
            stream.write(f"- {subject_label.title()}: **{item['name']}**\n")
            stream.write(f"- [Open Kanka Overview]({receipt['overview_url']})\n")
            if image_verified:
                stream.write(f"- Main image verified: `{image_verified['repository_path']}`\n")
            for post in posts_verified:
                stream.write(f"- Private post verified: **{post['name']}** (administrators only)\n")
