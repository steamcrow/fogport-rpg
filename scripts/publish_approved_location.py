"""Publish one approved Fogport location and verify the exact Kanka record."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kanka_librarian.client import KankaClient
from kanka_librarian.publisher import validate_approved_proposal
from kanka_librarian.writer import KankaWriter


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


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
        raise SystemExit("Location publisher requires exactly one approved change.")

    change = document["proposals"][0]
    if change.get("section") != "locations":
        raise SystemExit("Location publisher refuses non-location changes.")
    publication = change.get("publication", {})
    parent_name = str(publication.get("parent_name", "")).strip()
    link_phrase = str(publication.get("parent_link_phrase", parent_name)).strip()
    if not parent_name:
        raise SystemExit("Approved change is missing publication.parent_name.")

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    campaign = client.get_campaign(CAMPAIGN_ID)
    actual_name = str(campaign.get("name", "")).strip()
    if actual_name.casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit(
            f"Campaign lock failed: {CAMPAIGN_ID} is {actual_name!r}, not {CAMPAIGN_NAME!r}."
        )

    locations = client.list_locations(CAMPAIGN_ID)
    parents = [
        item for item in locations
        if str(item.get("name", "")).casefold() == parent_name.casefold()
    ]
    matches = [
        item for item in locations
        if str(item.get("name", "")).casefold() == str(change["name"]).casefold()
    ]
    if len(parents) != 1:
        raise SystemExit(f"Expected one parent {parent_name!r}; found {len(parents)}.")
    if len(matches) > 1:
        raise SystemExit(f"More than one {change['name']!r} exists; refusing to guess.")

    # Kanka uses two different identifiers for a location. Despite its name,
    # the locations API's `parent_id` field expects the parent's global entity
    # ID, not the parent location record ID. The location record ID is used
    # only in the locations endpoint path when updating that location.
    parent_location_id = int(parents[0]["id"])
    parent_entity_id = int(parents[0]["entity_id"])
    entry = str(change.get("entry", ""))
    if link_phrase:
        entry = entry.replace(
            link_phrase, f"[entity:{parent_entity_id}|{link_phrase}]", 1
        )
    payload = {
        "name": str(change["name"]),
        "type": str(change.get("type", "")),
        "is_private": bool(change.get("is_private", False)),
        "entry": entry,
        "parent_id": parent_entity_id,
    }

    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    if matches:
        location_id = int(matches[0]["id"])
        created = False
    else:
        created_item = writer.create_entity(CAMPAIGN_ID, "locations", payload)
        location_id = int(created_item["id"])
        created = True

    writer.update_entity(CAMPAIGN_ID, "locations", location_id, payload)
    direct = client._get(f"campaigns/{CAMPAIGN_ID}/locations/{location_id}")
    item = direct.get("data", {})
    expected = {
        "name": payload["name"],
        "type": payload["type"],
        "is_private": payload["is_private"],
        "entry": payload["entry"],
        "parent_id": payload["parent_id"],
    }
    actual = {key: item.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(
            "Kanka read-back did not match approval:\n"
            + json.dumps({"expected": expected, "actual": actual}, indent=2)
        )

    entity_id = int(item["entity_id"])
    posts_verified = []
    for approved_post in change.get("posts", []):
        post_name = str(approved_post.get("name", "")).strip()
        if not post_name:
            raise SystemExit("Approved post is missing its name.")
        post_payload = {
            "name": post_name,
            "entry": str(approved_post.get("entry", "")),
            "entity_id": entity_id,
            "visibility_id": int(approved_post.get("visibility_id", 3)),
        }
        if post_payload["visibility_id"] != 3:
            raise SystemExit(
                f"GM post {post_name!r} must use administrator-only visibility_id 3."
            )

        existing_posts = client.list_entity_posts(CAMPAIGN_ID, entity_id)
        post_matches = [
            post for post in existing_posts
            if str(post.get("name", "")).casefold() == post_name.casefold()
        ]
        if len(post_matches) > 1:
            raise SystemExit(
                f"More than one post named {post_name!r} exists; refusing to guess."
            )
        if post_matches:
            post_id = int(post_matches[0]["id"])
            post_created = False
            writer.update_post(
                CAMPAIGN_ID, entity_id, post_id, post_payload
            )
        else:
            created_post = writer.create_post(
                CAMPAIGN_ID, entity_id, post_payload
            )
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
                    {"expected": expected_post, "actual": actual_post}, indent=2
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
        "location_id": location_id,
        "entity_id": entity_id,
        "parent_location_id": parent_location_id,
        "parent_entity_id": parent_entity_id,
        "name": item["name"],
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
        "private_posts_verified": posts_verified,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Fogport publication verified\n\n")
            stream.write(f"- Entity: **{item['name']}**\n")
            stream.write(f"- [Open Kanka Overview]({receipt['overview_url']})\n")
            for post in posts_verified:
                stream.write(
                    f"- Private post verified: **{post['name']}** "
                    "(administrators only)\n"
                )


if __name__ == "__main__":
    main()
