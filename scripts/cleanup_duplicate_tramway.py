"""Delete only the accidental duplicate Fogport Tramway System item."""

import os
import requests

CAMPAIGN_ID = 410879
KEEP_ENTITY_ID = 9635987
NAME = "Fogport Tramway System"


def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kanka-Librarian/1.0",
    }


def main():
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    token = os.environ["KANKA_API_TOKEN"]
    base = f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/items"
    response = requests.get(base, headers=headers(token), params={"limit": 100}, timeout=60)
    response.raise_for_status()
    matches = [
        item for item in response.json().get("data", [])
        if str(item.get("name", "")).strip().casefold() == NAME.casefold()
    ]
    keep = [item for item in matches if int(item.get("entity_id", 0)) == KEEP_ENTITY_ID]
    duplicates = [item for item in matches if int(item.get("entity_id", 0)) != KEEP_ENTITY_ID]
    if len(keep) != 1:
        raise SystemExit(f"Expected verified entity {KEEP_ENTITY_ID} exactly once; found {len(keep)}.")
    if not duplicates:
        print("No duplicate remains; verified entity is intact.")
        return
    if len(duplicates) != 1:
        raise SystemExit(f"Expected exactly one duplicate; found {len(duplicates)}. Refusing to guess.")
    duplicate = duplicates[0]
    duplicate_id = int(duplicate["id"])
    duplicate_entity_id = int(duplicate["entity_id"])
    deleted = requests.delete(f"{base}/{duplicate_id}", headers=headers(token), timeout=60)
    if deleted.status_code not in (200, 204):
        raise SystemExit(f"Delete failed: HTTP {deleted.status_code}: {deleted.text[:300]}")
    verify = requests.get(base, headers=headers(token), params={"limit": 100}, timeout=60)
    verify.raise_for_status()
    remaining = [
        item for item in verify.json().get("data", [])
        if str(item.get("name", "")).strip().casefold() == NAME.casefold()
    ]
    if len(remaining) != 1 or int(remaining[0].get("entity_id", 0)) != KEEP_ENTITY_ID:
        raise SystemExit("Post-delete verification failed.")
    print(f"Deleted duplicate entity {duplicate_entity_id}; preserved {KEEP_ENTITY_ID}.")


if __name__ == "__main__":
    main()
