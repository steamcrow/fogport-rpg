"""Publish one approved Fogport character and verify the exact Kanka record."""

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
install_api_pacing()

from kanka_librarian.client import KankaClient
from kanka_librarian.crosslinks import build_registry, link_entry, load_aliases
from kanka_librarian.publisher import validate_approved_proposal
from kanka_librarian.writer import KankaWriter


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _approved_main_image(
    change: dict[str, Any],
) -> tuple[Path, str] | None:
    """Resolve and verify a content-locked repository portrait."""
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
        raise SystemExit(
            "Approved artwork must be a PNG, JPEG, or WebP image."
        )
    if not candidate.is_file():
        raise SystemExit(f"Approved artwork is missing: {relative_path}")

    actual_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SystemExit(
            "Approved artwork changed after approval; SHA-256 does not match."
        )
    return candidate, actual_sha256


def _upload_main_image(
    *,
    token: str,
    entity_id: int,
    image_path: Path,
) -> dict[str, Any]:
    """Set and return Kanka's main-image metadata for an entity."""
    url = (
        f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}"
        f"/entities/{entity_id}/image"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/0.5",
    }
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            url,
            headers=headers,
            files={"file": (image_path.name, stream, mime_type)},
            timeout=60,
        )
    if not response.ok:
        raise SystemExit(
            f"Kanka image upload returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
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


def _link_unique_reference(
    entry: str,
    reference: dict[str, object],
    *,
    locations: list[dict[str, object]],
    characters: list[dict[str, object]],
) -> str:
    phrase = str(reference.get("phrase", "")).strip()
    name = str(reference.get("name", phrase)).strip()
    section = str(reference.get("section", "")).strip()
    if not phrase or not name:
        return entry
    candidates = locations if section == "locations" else characters if section == "characters" else []
    matches = [
        item
        for item in candidates
        if str(item.get("name", "")).casefold() == name.casefold()
    ]
    if len(matches) != 1 or phrase not in entry:
        return entry
    return entry.replace(phrase, f"[entity:{int(matches[0]['entity_id'])}|{phrase}]", 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.proposal.read_text(encoding="utf-8"))
    campaign_id = validate_approved_proposal(document)
    if campaign_id != CAMPAIGN_ID:
        raise SystemExit(f"Fogport publisher refuses campaign {campaign_id}.")
    if len(document["proposals"]) != 1:
        raise SystemExit("Character publisher requires exactly one approved change.")

    change = document["proposals"][0]
    if change.get("section") != "characters":
        raise SystemExit("Character publisher refuses non-character changes.")
    approved_image = _approved_main_image(change)

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    campaign = client.get_campaign(CAMPAIGN_ID)
    actual_name = str(campaign.get("name", "")).strip()
    if actual_name.casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit(
            f"Campaign lock failed: {CAMPAIGN_ID} is {actual_name!r}, not {CAMPAIGN_NAME!r}."
        )

    characters = client.list_characters(CAMPAIGN_ID)
    locations = client.list_locations(CAMPAIGN_ID)
    matches = [
        item
        for item in characters
        if str(item.get("name", "")).casefold() == str(change["name"]).casefold()
    ]
    if len(matches) > 1:
        raise SystemExit(f"More than one {change['name']!r} exists; refusing to guess.")

    entry = str(change.get("entry", ""))
    for reference in change.get("publication", {}).get("references", []):
        entry = _link_unique_reference(
            entry,
            reference,
            locations=locations,
            characters=characters,
        )
    alias_path = (
        Path(__file__).resolve().parents[1]
        / "kanka_librarian"
        / "crosslink_aliases.json"
    )
    registry = build_registry(
        client,
        CAMPAIGN_ID,
        load_aliases(alias_path),
    )
    entry, _ = link_entry(
        entry,
        registry,
        source_entity_id=int(matches[0]["entity_id"]) if matches else None,
        source_private=bool(change.get("is_private", False)),
    )

    payload = {
        "name": str(change["name"]),
        "type": str(change.get("type", "")),
        "is_private": bool(change.get("is_private", False)),
        "entry": entry,
    }

    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    if matches:
        character_id = int(matches[0]["id"])
        created = False
    else:
        created_item = writer.create_entity(CAMPAIGN_ID, "characters", payload)
        character_id = int(created_item["id"])
        created = True

    writer.update_entity(CAMPAIGN_ID, "characters", character_id, payload)
    item = client._get(
        f"campaigns/{CAMPAIGN_ID}/characters/{character_id}"
    ).get("data", {})
    expected_character = {
        "name": payload["name"],
        "type": payload["type"],
        "is_private": payload["is_private"],
        "entry": payload["entry"],
    }
    actual_character = {key: item.get(key) for key in expected_character}
    if actual_character != expected_character:
        raise SystemExit(
            "Kanka character read-back did not match approval:\n"
            + json.dumps(
                {"expected": expected_character, "actual": actual_character},
                indent=2,
            )
        )

    entity_id = int(item["entity_id"])
    image_verified = None
    if approved_image is not None:
        image_path, image_sha256 = approved_image
        uploaded_image = _upload_main_image(
            token=token,
            entity_id=entity_id,
            image_path=image_path,
        )
        image_readback = client._get(
            f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image"
        ).get("data", {})
        readback_main = (
            image_readback.get("image", {})
            if isinstance(image_readback, dict)
            else {}
        )
        if (
            not isinstance(readback_main, dict)
            or readback_main.get("uuid") != uploaded_image.get("uuid")
            or not readback_main.get("full")
            or not readback_main.get("thumbnail")
        ):
            raise SystemExit(
                "Kanka main-image read-back did not match the uploaded portrait."
            )
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
            raise SystemExit(
                f"GM post {post_name!r} must use administrator-only visibility_id 3."
            )

        existing_posts = client.list_entity_posts(CAMPAIGN_ID, entity_id)
        post_matches = [
            post
            for post in existing_posts
            if str(post.get("name", "")).casefold() == post_name.casefold()
        ]
        if len(post_matches) > 1:
            raise SystemExit(
                f"More than one post named {post_name!r} exists; refusing to guess."
            )
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
                + json.dumps(
                    {"expected": expected_post, "actual": actual_post},
                    indent=2,
                )
            )
        posts_verified.append(
            {
                "id": post_id,
                "name": post_name,
                "created": post_created,
                "visibility_id": 3,
            }
        )

    receipt = {
        "published": True,
        "created": created,
        "campaign": actual_name,
        "campaign_id": CAMPAIGN_ID,
        "character_id": character_id,
        "entity_id": entity_id,
        "name": item["name"],
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
        "main_image_verified": image_verified,
        "private_posts_verified": posts_verified,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Fogport character publication verified\n\n")
            stream.write(f"- Character: **{item['name']}**\n")
            stream.write(f"- [Open Kanka Overview]({receipt['overview_url']})\n")
            if image_verified:
                stream.write(
                    "- Main portrait verified: "
                    f"`{image_verified['repository_path']}`\n"
                )
            for post in posts_verified:
                stream.write(
                    f"- Private post verified: **{post['name']}** "
                    "(administrators only)\n"
                )


if __name__ == "__main__":
    main()
