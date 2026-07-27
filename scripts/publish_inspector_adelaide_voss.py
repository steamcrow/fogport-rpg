"""Publish and verify Inspector Adelaide Voss in the Fogport Kanka campaign."""

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

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/1.0",
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
        timeout=120,
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


def required_exact(
    records: list[dict[str, Any]], names: list[str], kind: str
) -> dict[str, Any]:
    wanted = {name.strip().casefold() for name in names}
    matches = [
        record
        for record in records
        if str(record.get("name", "")).strip().casefold() in wanted
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly one {kind} matching {names!r}; found {len(matches)}."
        )
    return matches[0]


def validate(document: dict[str, Any]) -> tuple[bytes, str, str]:
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

    encoded_path = (REPOSITORY_ROOT / str(document["base64_path"])).resolve()
    try:
        encoded_path.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise SystemExit("Portrait path escapes the repository.") from exc
    if encoded_path.suffix.lower() != ".b64" or not encoded_path.is_file():
        raise SystemExit("Approved Adelaide Voss portrait is missing.")

    encoded = "".join(encoded_path.read_text(encoding="ascii").split())
    image_bytes = base64.b64decode(encoded, validate=True)
    actual_sha = hashlib.sha256(image_bytes).hexdigest()
    if actual_sha != str(document["sha256"]).lower():
        raise SystemExit("Approved Adelaide Voss portrait changed after approval.")
    return image_bytes, actual_sha, str(document["filename"])


def link(entity_id: int, label: str) -> str:
    return f"[entity:{entity_id}|{label}]"


def replace_links(text: str, links: dict[str, str]) -> str:
    for placeholder, value in links.items():
        text = text.replace(placeholder, value)
    if "{{" in text or "}}" in text:
        raise SystemExit("An unresolved entity-link placeholder remains.")
    return text


def upload_image(
    token: str, entity_id: int, image_bytes: bytes, filename: str
) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = requests.post(
        f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image",
        headers=headers(token),
        files={"file": (filename, image_bytes, mime_type)},
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


def upsert_post(
    token: str,
    entity_id: int,
    name: str,
    entry: str,
    visibility_id: int,
) -> dict[str, Any]:
    path = f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/posts"
    posts = all_pages(token, path)
    match = exact(posts, name, "post")
    payload = {
        "name": name,
        "entry": entry,
        "entity_id": entity_id,
        "visibility_id": visibility_id,
    }
    if match:
        request(token, "PATCH", f"{path}/{int(match['id'])}", payload=payload)
        post_id = int(match["id"])
    else:
        made = request(token, "POST", path, payload=payload).get("data", {})
        post_id = int(made["id"])
    final = request(token, "GET", f"{path}/{post_id}").get("data", {})
    if (
        str(final.get("name")) != name
        or str(final.get("entry") or "") != entry
        or int(final.get("visibility_id", 0)) != visibility_id
    ):
        raise SystemExit("Inspector Voss confidential post read-back failed.")
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    image_bytes, image_sha, filename = validate(document)
    token = os.environ["KANKA_API_TOKEN"]

    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    locations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations")
    characters = all_pages(token, f"campaigns/{CAMPAIGN_ID}/characters")
    organisations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/organisations")

    fogport = required_exact(locations, ["Fogport"], "Fogport location")
    nine_spoons = required_exact(locations, ["Nine Spoons"], "Nine Spoons location")
    byl = required_exact(
        characters, ["Byl Hasbaine", "Byl Häsbaine", "Byl Blacksaft"], "Byl character"
    )
    lott = required_exact(characters, ["Lott"], "Lott character")
    vigilance = required_exact(
        organisations, ["The Civic Vigilance", "Civic Vigilance"], "organization"
    )

    links = {
        "{{CIVIC_VIGILANCE_LINK}}": link(
            int(vigilance["entity_id"]), "Civic Vigilance"
        ),
        "{{FOGPORT_LINK}}": link(int(fogport["entity_id"]), "Fogport"),
        "{{NINE_SPOONS_LINK}}": link(int(nine_spoons["entity_id"]), "Nine Spoons"),
        "{{BYL_LINK}}": link(int(byl["entity_id"]), "Byl Hasbaine"),
        "{{LOTT_LINK}}": link(int(lott["entity_id"]), "Lott"),
    }

    spec = document["character"]
    entry = replace_links(str(spec["entry"]), links)
    character_path = f"campaigns/{CAMPAIGN_ID}/characters"
    match = exact(characters, str(spec["name"]), "character")
    payload = {
        "name": str(spec["name"]),
        "title": str(spec["title"]),
        "age": str(spec["age"]),
        "sex": str(spec["sex"]),
        "pronouns": str(spec["pronouns"]),
        "type": str(spec["type"]),
        "entry": entry,
        "is_private": bool(spec.get("is_private", False)),
    }
    if match:
        character_id = int(match["id"])
        request(token, "PATCH", f"{character_path}/{character_id}", payload=payload)
        created = False
    else:
        made = request(token, "POST", character_path, payload=payload).get("data", {})
        character_id = int(made["id"])
        created = True

    final = request(token, "GET", f"{character_path}/{character_id}").get("data", {})
    entity_id = int(final["entity_id"])
    if (
        str(final.get("name")) != payload["name"]
        or str(final.get("entry") or "") != entry
        or str(final.get("title") or "") != payload["title"]
        or str(final.get("type") or "") != payload["type"]
        or bool(final.get("is_private")) is not payload["is_private"]
    ):
        raise SystemExit("Inspector Adelaide Voss character read-back failed.")

    membership = document["membership"]
    members_path = (
        f"campaigns/{CAMPAIGN_ID}/organisations/{int(vigilance['id'])}"
        "/organisation_members"
    )
    members = all_pages(token, members_path)
    matches = [
        member
        for member in members
        if int(member.get("character_id", 0)) == character_id
    ]
    if len(matches) > 1:
        raise SystemExit("Inspector Voss has duplicate Civic Vigilance memberships.")
    member_payload = {
        "organisation_id": int(vigilance["id"]),
        "character_id": character_id,
        "role": str(membership["role"]),
        "is_private": bool(membership["is_private"]),
        "pin_id": int(membership["pin_id"]),
        "status_id": int(membership["status_id"]),
    }
    if matches:
        member_id = int(matches[0]["id"])
        request(token, "PATCH", f"{members_path}/{member_id}", payload=member_payload)
    else:
        made = request(token, "POST", members_path, payload=member_payload).get(
            "data", {}
        )
        member_id = int(made["id"])

    members_after = all_pages(token, members_path)
    verified_members = [
        member
        for member in members_after
        if int(member.get("character_id", 0)) == character_id
    ]
    if (
        len(verified_members) != 1
        or str(verified_members[0].get("role") or "") != member_payload["role"]
    ):
        raise SystemExit("Civic Vigilance membership read-back failed.")

    gm_spec = document["gm_post"]
    gm_entry = replace_links(str(gm_spec["entry"]), links)
    gm_post = upsert_post(
        token,
        entity_id,
        str(gm_spec["name"]),
        gm_entry,
        int(gm_spec["visibility_id"]),
    )

    uploaded = upload_image(token, entity_id, image_bytes, filename)
    image_readback = request(
        token, "GET", f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image"
    ).get("data", {}).get("image", {})
    if (
        not isinstance(image_readback, dict)
        or image_readback.get("uuid") != uploaded.get("uuid")
        or not image_readback.get("full")
        or not image_readback.get("thumbnail")
    ):
        raise SystemExit("Inspector Voss portrait read-back failed.")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "character": final["name"],
        "character_id": character_id,
        "entity_id": entity_id,
        "created": created,
        "entry_verified": True,
        "links_verified": all(value in entry or value in gm_entry for value in links.values()),
        "organization": vigilance["name"],
        "organization_id": int(vigilance["id"]),
        "membership_id": member_id,
        "membership_verified": True,
        "gm_post_id": int(gm_post["id"]),
        "gm_post_visibility_id": int(gm_post["visibility_id"]),
        "source_sha256": image_sha,
        "image_uuid": image_readback["uuid"],
        "image_verified": True,
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
