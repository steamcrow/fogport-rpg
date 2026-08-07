"""Publish and verify The Civic Order organization and image."""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os
from pathlib import Path
import requests
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
from kanka_librarian.api import all_pages, exact, request
install_api_pacing()
CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"

def upload_image(token: str, entity_id: int, image_path: Path) -> dict:
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as stream:
        response = requests.post(
            f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            files={"file": (image_path.name, stream, mime)},
            timeout=120,
        )
    if not response.ok:
        raise SystemExit(f"Image upload failed: HTTP {response.status_code}")
    image = response.json().get("data", {}).get("image", {})
    if not image.get("uuid"):
        raise SystemExit("Kanka returned no image UUID.")
    return image

def main():
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
    root = Path(__file__).resolve().parents[1]
    image_path = (root / doc["image_path"]).resolve()
    if not image_path.is_file() or hashlib.sha256(image_path.read_bytes()).hexdigest() != doc["sha256"]:
        raise SystemExit("Approved Civic Order image checksum failed.")
    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")
    locations = all_pages(token, f"campaigns/{CAMPAIGN_ID}/locations")
    fogport = exact(locations, "Fogport", "location")
    if not fogport:
        raise SystemExit("Fogport location is missing.")
    fogport_link = f"[entity:{int(fogport['entity_id'])}|Fogport]"
    entry = doc["organization"]["entry"].replace("{{FOGPORT_LINK}}", fogport_link)
    path = f"campaigns/{CAMPAIGN_ID}/organisations"
    spec = doc["organization"]
    match = exact(all_pages(token, path), spec["name"], "organization")
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
    uploaded = upload_image(token, entity_id, image_path)
    image = request(token, "GET", f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image").get("data", {}).get("image", {})
    if image.get("uuid") != uploaded.get("uuid") or not image.get("full") or not image.get("thumbnail"):
        raise SystemExit("Civic Order image read-back failed.")
    receipt = {"published": True, "campaign": CAMPAIGN_NAME, "campaign_id": CAMPAIGN_ID, "organization": final["name"], "organization_id": organization_id, "entity_id": entity_id, "created": created, "entry_verified": True, "fogport_link_verified": fogport_link in entry, "image_verified": True, "image_uuid": image["uuid"], "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
