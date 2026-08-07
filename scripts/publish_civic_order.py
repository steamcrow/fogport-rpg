"""Publish and verify The Civic Order organization."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import all_pages, exact, request
install_api_pacing()
CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"

def upload_image(token,eid,path):\n r=requests.post(f"https://api.kanka.io/1.0/campaigns/{CID}/entities/{eid}/image",headers={"Authorization":f"Bearer {token}","Accept":"application/json"},files={"file":(path.name,path.open("rb"),mimetypes.guess_type(path.name)[0] or "application/octet-stream")},timeout=120)\n if not r.ok: raise SystemExit(f"Image upload failed: {r.status_code}")\n return r.json().get("data",{}).get("image",{})\n\ndef main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    doc = json.loads(args.manifest.read_text(encoding="utf-8"))
    if doc.get("campaign_id") != CAMPAIGN_ID or doc.get("campaign_name") != CAMPAIGN_NAME:
        raise SystemExit("Manifest is not locked to Fogport.")
    if doc.get("approval", {}).get("status") != "approved" or doc["approval"].get("approved_by") != "Daniel Davis":
        raise SystemExit("Daniel Davis approval is required.")
    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")
    locations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations")
    fogport = exact(locations, "Fogport", "location")
    if not fogport:
        raise SystemExit("Fogport location is missing.")
    entry = doc["organization"]["entry"].replace("{{FOGPORT_LINK}}", f"[entity:{int(fogport['entity_id'])}|Fogport]")
    path = f"campaigns/{CAMPAIGN_ID}/organisations"
    organizations = all_pages(token, path)
    spec = doc["organization"]
    match = exact(organizations, spec["name"], "organization")
    payload = {"name": spec["name"], "type": spec["type"], "entry": entry, "is_private": bool(spec.get("is_private", False))}
    if match:
        organization_id = int(match["id"])
        request(token, "PATCH", f"{path}/{organization_id}", payload=payload)
        created = False
    else:
        made = request(token, "POST", path, payload=payload).get("data", {})
        organization_id = int(made["id"])
        created = True
    final = request(token, "GET", f"{path}/{organization_id}").get("data", {})
    if any([str(final.get("name")) != payload["name"], str(final.get("type")) != payload["type"], bool(final.get("is_private")) is not payload["is_private"], str(final.get("entry") or "") != entry]):
        raise SystemExit("Civic Order organization read-back failed.")
    entity_id = int(final["entity_id"])
    receipt = {"published": True, "campaign": CAMPAIGN_NAME, "campaign_id": CAMPAIGN_ID, "organization": final["name"], "organization_id": organization_id, "entity_id": entity_id, "created": created, "entry_verified": True, "fogport_link_verified": True, "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
if __name__ == "__main__":
    main()
