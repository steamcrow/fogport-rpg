"""Upload a checksum-locked main image to one exact Fogport organization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from publish_approved_main_image import upload_image
from kanka_librarian.client import KankaClient


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("approval", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document = json.loads(args.approval.read_text())
    if document.get("campaign_id") != CAMPAIGN_ID or document.get("campaign_name") != CAMPAIGN_NAME:
        raise SystemExit("Image approval is not locked to Fogport.")
    if document.get("approval", {}).get("status") != "approved":
        raise SystemExit("Image approval is not approved.")
    target = str(document.get("organization_name", "")).strip()
    image_path = (ROOT / str(document.get("repository_path", ""))).resolve()
    if not target or not image_path.is_file() or image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise SystemExit("Organization image approval is incomplete or invalid.")
    image_path.relative_to(ROOT)
    image_bytes = image_path.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != str(document.get("sha256", "")).lower():
        raise SystemExit("Organization image checksum mismatch.")
    client = KankaClient(os.environ["KANKA_API_TOKEN"])
    if str(client.get_campaign(CAMPAIGN_ID).get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")
    records = client._get(f"campaigns/{CAMPAIGN_ID}/organisations", params={"page": 1, "limit": 100}).get("data", [])
    matches = [item for item in records if str(item.get("name", "")).strip().casefold() == target.casefold()]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one organization named {target!r}; found {len(matches)}.")
    record = matches[0]
    entity_id = int(record["entity_id"])
    before = client._get(f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}").get("data", {})
    uploaded = upload_image(token=os.environ["KANKA_API_TOKEN"], campaign_id=CAMPAIGN_ID, entity_id=entity_id, image_bytes=image_bytes, image_name=image_path.name)
    image = client._get(f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}/image").get("data", {}).get("image", {})
    after = client._get(f"campaigns/{CAMPAIGN_ID}/entities/{entity_id}").get("data", {})
    stable = ("id", "name", "type_id", "is_private", "parent_id", "entry")
    changed = [key for key in stable if before.get(key) != after.get(key)]
    if image.get("uuid") != uploaded.get("uuid") or not image.get("full") or changed:
        raise SystemExit(f"Organization main-image verification failed; changed fields: {changed}")
    receipt = {"published": True, "operation": "organization-main-image-only", "entity_id": entity_id, "organization_name": target, "kanka_uuid": image["uuid"], "full": image["full"], "non_image_fields_changed": []}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
