"""Publish approved Kanka abilities onto one existing Fogport entity and verify read-back."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
from typing import Any

from kanka_librarian.client import KankaClient
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.writer import KankaWriter

install_api_pacing()
CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


def digest_without_approval(document: dict[str, Any]) -> str:
    body = {k: v for k, v in document.items() if k != "approval"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    doc = json.loads(args.proposal.read_text(encoding="utf-8"))
    if doc.get("mode") != "approved-entity-abilities" or int(doc.get("campaign_id", 0)) != CAMPAIGN_ID or doc.get("campaign_name") != CAMPAIGN_NAME:
        raise SystemExit("Ability publisher refuses this proposal or campaign.")
    approval = doc.get("approval", {})
    if approval.get("status") != "approved" or approval.get("proposal_sha256") != digest_without_approval(doc):
        raise SystemExit("Ability proposal approval digest is missing or stale.")
    target = doc.get("entity", {})
    if target.get("section") != "characters" or not target.get("name"):
        raise SystemExit("This publisher currently supports an explicitly named character only.")

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Fogport campaign-name lock failed.")

    matches = [c for c in client.list_characters(CAMPAIGN_ID) if str(c.get("name", "")).casefold() == str(target["name"]).casefold()]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one character named {target['name']!r}; found {len(matches)}.")
    entity_id = int(matches[0]["entity_id"])

    all_abilities = client._get_all_pages(f"campaigns/{CAMPAIGN_ID}/abilities")
    existing_links = client._get_all_pages(f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/entity_abilities")
    verified = []
    for position, approved in enumerate(doc.get("abilities", []), start=1):
        name = str(approved.get("name", "")).strip()
        if not name:
            raise SystemExit("Approved ability has no name.")
        same = [a for a in all_abilities if str(a.get("name", "")).casefold() == name.casefold()]
        if len(same) > 1:
            raise SystemExit(f"More than one campaign ability named {name!r}; refusing to guess.")
        payload = {"name": name, "entry": str(approved.get("entry", "")), "type": str(approved.get("type", "Fate Core")), "is_private": bool(approved.get("is_private", False))}
        if same:
            ability_id = int(same[0]["id"])
            writer._send("PATCH", f"campaigns/{CAMPAIGN_ID}/abilities/{ability_id}", payload)
        else:
            created = writer._send("POST", f"campaigns/{CAMPAIGN_ID}/abilities", payload)
            ability_id = int(created["id"])
            all_abilities.append(created)

        direct = client._get(f"campaigns/{CAMPAIGN_ID}/abilities/{ability_id}").get("data", {})
        expected = {k: payload[k] for k in ("name", "entry", "type", "is_private")}
        actual = {k: direct.get(k) for k in expected}
        if actual != expected:
            raise SystemExit("Kanka ability read-back mismatch:\n" + json.dumps({"expected": expected, "actual": actual}, indent=2))

        links = [link for link in existing_links if int(link.get("ability_id", 0)) == ability_id]
        if len(links) > 1:
            raise SystemExit(f"Ability {name!r} is attached to Lott more than once.")
        link_payload = {"abilities": [ability_id], "visibility_id": int(approved.get("visibility_id", 1)), "position": int(approved.get("position", position * 10)), "note": ""}
        if links:
            link_id = int(links[0]["id"])
            writer._send("PATCH", f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/entity_abilities/{link_id}", link_payload)
        else:
            created_link = writer._send("POST", f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/entity_abilities", link_payload)
            link_id = int(created_link["id"])
            existing_links.append(created_link)

        readback = client._get(f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/entity_abilities/{link_id}").get("data", {})
        if int(readback.get("ability_id", 0)) != ability_id or int(readback.get("visibility_id", 0)) != link_payload["visibility_id"] or int(readback.get("position", -1)) != link_payload["position"]:
            raise SystemExit(f"Kanka entity-ability read-back mismatch for {name!r}.")
        verified.append({"name": name, "ability_id": ability_id, "entity_ability_id": link_id, "position": link_payload["position"]})

    receipt = {"published": True, "campaign": CAMPAIGN_NAME, "campaign_id": CAMPAIGN_ID, "entity": target["name"], "entity_id": entity_id, "abilities_verified": verified, "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
