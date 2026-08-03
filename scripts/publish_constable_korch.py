"""Publish and verify Constable Korch in the Fogport Kanka campaign."""
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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import all_pages, exact, headers, request

install_api_pacing()
CAMPAIGN_ID = 410879
ROOT = Path(__file__).resolve().parents[1]


def one(records: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
    matches = [r for r in records if str(r.get("name", "")).strip().casefold() == name.casefold()]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one {kind} named {name!r}; found {len(matches)}.")
    return matches[0]


def link(entity_id: int, label: str) -> str:
    return f"[entity:{entity_id}|{label}]"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    spec = json.loads(args.manifest.read_text(encoding="utf-8"))
    if spec.get("campaign_id") != CAMPAIGN_ID or spec.get("approval", {}).get("approved_by") != "Daniel Davis":
        raise SystemExit("Manifest is not an approved Fogport publication.")
    image_path = (ROOT / spec["base64_path"]).resolve()
    image_path.relative_to(ROOT)
    image = base64.b64decode("".join(image_path.read_text(encoding="ascii").split()), validate=True)
    source_sha = hashlib.sha256(image).hexdigest()
    if source_sha != spec["sha256"]:
        raise SystemExit("Approved Korch portrait changed after approval.")

    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != "fogport":
        raise SystemExit("Kanka campaign identity lock failed.")
    characters = all_pages(token, f"campaigns/{CAMPAIGN_ID}/characters")
    organisations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/organisations")
    vigilance = one(organisations, "The Civic Vigilance", "organisation")
    character_spec = spec["character"]
    entry = character_spec["entry"].replace("{{CIVIC_VIGILANCE_LINK}}", link(int(vigilance["entity_id"]), "Civic Vigilance"))
    if "{{" in entry:
        raise SystemExit("Unresolved entity link in Korch entry.")
    path = f"campaigns/{CAMPAIGN_ID}/characters"
    payload = {**{k: character_spec[k] for k in ("name", "title", "age", "sex", "pronouns", "type", "is_private")}, "entry": entry}
    existing = [c for c in characters if str(c.get("name", "")).strip().casefold() == "constable korch"]
    if len(existing) > 1:
        raise SystemExit("Refusing duplicate Constable Korch records.")
    if existing:
        character_id, created = int(existing[0]["id"]), False
        request(token, "PATCH", f"{path}/{character_id}", payload=payload)
    else:
        character_id, created = int(request(token, "POST", path, payload=payload)["data"]["id"]), True
    final = request(token, "GET", f"{path}/{character_id}").get("data", {})
    if str(final.get("name")) != "Constable Korch" or str(final.get("entry") or "") != entry:
        raise SystemExit("Constable Korch character read-back failed.")

    members_path = f"campaigns/{CAMPAIGN_ID}/organisations/{int(vigilance['id'])}/organisation_members"
    members = all_pages(token, members_path)
    current = [m for m in members if int(m.get("character_id", 0)) == character_id]
    if len(current) > 1:
        raise SystemExit("Refusing duplicate Korch Civic Vigilance memberships.")
    membership = spec["membership"]
    member_payload = {"organisation_id": int(vigilance["id"]), "character_id": character_id, **membership}
    if current:
        member_id = int(current[0]["id"])
        request(token, "PATCH", f"{members_path}/{member_id}", payload=member_payload)
    else:
        member_id = int(request(token, "POST", members_path, payload=member_payload)["data"]["id"])
    verified = [m for m in all_pages(token, members_path) if int(m.get("character_id", 0)) == character_id]
    if len(verified) != 1 or str(verified[0].get("role") or "") != membership["role"]:
        raise SystemExit("Korch Civic Vigilance membership read-back failed.")

    response = requests.post(f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/entities/{int(final['entity_id'])}/image", headers=headers(token), files={"file": (spec["filename"], image, mimetypes.guess_type(spec["filename"])[0] or "image/jpeg")}, timeout=120)
    if not response.ok:
        raise SystemExit(f"Kanka image upload returned HTTP {response.status_code}: {response.text[:500]}")
    uploaded = response.json().get("data", {}).get("image", {})
    image_back = request(token, "GET", f"campaigns/{CAMPAIGN_ID}/entities/{int(final['entity_id'])}/image").get("data", {}).get("image", {})
    if not uploaded.get("uuid") or image_back.get("uuid") != uploaded.get("uuid"):
        raise SystemExit("Korch portrait read-back failed.")

    receipt = {"published": True, "campaign": "Fogport", "campaign_id": CAMPAIGN_ID, "character": final["name"], "character_id": character_id, "entity_id": int(final["entity_id"]), "created": created, "entry_verified": True, "organization": vigilance["name"], "membership_id": member_id, "membership_verified": True, "source_sha256": source_sha, "image_uuid": image_back["uuid"], "image_verified": True, "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{int(final['entity_id'])}"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
