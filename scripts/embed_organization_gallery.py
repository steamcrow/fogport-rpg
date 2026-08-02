"""Embed approved Kanka gallery images into one exact Fogport organization entry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kanka_librarian.client import KankaClient
from kanka_librarian.writer import KankaWriter

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
ROOT = Path(__file__).resolve().parents[1]
MARKER = '<section data-fogport-gallery="brawla-portraits">'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("approval", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    document = json.loads(args.approval.read_text())
    if document.get("campaign_id") != CAMPAIGN_ID or document.get("campaign_name") != CAMPAIGN_NAME or document.get("approval", {}).get("status") != "approved":
        raise SystemExit("Gallery embed approval is not approved for Fogport.")
    target = str(document.get("organization_name", "")).strip()
    gallery_document = json.loads((ROOT / str(document.get("gallery_manifest", ""))).read_text())
    filenames = [Path(item["path"]).name for item in gallery_document.get("images", [])]
    if len(filenames) != 3 or not target:
        raise SystemExit("Expected exactly three approved Brawla gallery portraits.")
    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    if str(client.get_campaign(CAMPAIGN_ID).get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")
    organizations = client._get(f"campaigns/{CAMPAIGN_ID}/organisations", params={"page": 1, "limit": 100}).get("data", [])
    matches = [item for item in organizations if str(item.get("name", "")).strip().casefold() == target.casefold()]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one organization named {target!r}; found {len(matches)}.")
    record = matches[0]
    galleries = client._get(f"campaigns/{CAMPAIGN_ID}/images", params={"page": 1, "limit": 100}).get("data", [])
    selected = []
    for filename in filenames:
        found = [image for image in galleries if str(image.get("name", "")).casefold() in {filename.casefold(), Path(filename).stem.casefold()}]
        if len(found) != 1 or not found[0].get("path"):
            raise SystemExit(f"Expected exactly one gallery image for {filename!r}; found {len(found)}.")
        selected.append(found[0])
    resource_id = int(record["id"])
    before = client._get(f"campaigns/{CAMPAIGN_ID}/organisations/{resource_id}").get("data", {})
    titles = ("Bruiser", "Cutler", "Soaker")
    block = MARKER + "<h2>Brawla Portraits</h2>" + "".join(f'<figure><img src="{image["path"]}" alt="Brawla {title}"><figcaption>{title}</figcaption></figure>' for title, image in zip(titles, selected)) + "</section>"
    entry = str(before.get("entry", ""))
    if MARKER not in entry:
        entry = entry.rstrip() + "\n" + block
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    writer.update_entity(CAMPAIGN_ID, "organizations", resource_id, {"entry": entry})
    after = client._get(f"campaigns/{CAMPAIGN_ID}/organisations/{resource_id}").get("data", {})
    stable = ("id", "name", "type", "is_private")
    changed = [key for key in stable if before.get(key) != after.get(key)]
    actual_entry = str(after.get("entry", ""))
    paths = [str(image["path"]) for image in selected]
    if changed or MARKER not in actual_entry or any(path not in actual_entry for path in paths):
        raise SystemExit(f"Gallery embed read-back failed; changed fields: {changed}")
    receipt = {"published": True, "operation": "organization-gallery-embed", "organization_name": target, "entity_id": int(after["entity_id"]), "gallery_images_verified": [{"filename": filename, "path": image["path"]} for filename, image in zip(filenames, selected)], "non_entry_fields_changed": []}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
