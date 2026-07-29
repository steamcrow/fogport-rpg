"""Delete only the three audited duplicate Fogport transit Items.

The cleanup is intentionally ID-locked. It refuses to write unless the live inventory
matches the approved audit, and verifies the complete canonical set afterward.
"""

import json
import os
from pathlib import Path
from urllib.parse import urljoin

import requests

CAMPAIGN_ID = 410879
CANONICAL = {
    "Fogport Tramway System": (622124, 9635987),
    "Standard Passenger Tram": (622125, 9635988),
    "Industrial Freight Tram": (622126, 9635989),
    "Fogport Fire Brigade Tram": (622127, 9635990),
    "Civic Police Tram": (622128, 9635991),
    "Standard Transit Crate": (622129, 9635992),
}
DUPLICATES = {
    "Fogport Fire Brigade Tram": (622130, 9635993),
    "Civic Police Tram": (622131, 9635994),
    "Standard Transit Crate": (622132, 9635995),
}


def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kanka-Librarian/1.0",
    }


def fetch_all_items(token):
    url = f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/items"
    params = {"limit": 100}
    items = []
    pages = 0
    while url:
        response = requests.get(url, headers=headers(token), params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        pages += 1
        items.extend(payload.get("data", []))
        next_url = payload.get("links", {}).get("next")
        url = urljoin(response.url, next_url) if next_url else None
        params = None
    return items, pages


def transit_inventory(items):
    target_names = {name.casefold(): name for name in CANONICAL}
    matches = {name: [] for name in CANONICAL}
    for item in items:
        name = str(item.get("name", "")).strip()
        canonical_name = target_names.get(name.casefold())
        if canonical_name is None:
            continue
        matches[canonical_name].append((
            int(item["id"]),
            int(item.get("entity_id", 0)),
        ))
    for entries in matches.values():
        entries.sort()
    return matches


def expected_inventory(include_duplicates):
    expected = {name: [pair] for name, pair in CANONICAL.items()}
    if include_duplicates:
        for name, pair in DUPLICATES.items():
            expected[name].append(pair)
            expected[name].sort()
    return expected


def write_receipt(path, pages, before, after, deleted):
    report = {
        "schema_version": 1,
        "mode": "approved-transit-duplicate-cleanup",
        "campaign_id": CAMPAIGN_ID,
        "pages_scanned_before": pages,
        "canonical_entity_ids_preserved": [
            entity_id for _, entity_id in CANONICAL.values()
        ],
        "deleted": deleted,
        "inventory_before": before,
        "inventory_after": after,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    token = os.environ["KANKA_API_TOKEN"]
    receipt_path = os.environ.get(
        "REPORT_PATH", "receipts/transit-duplicate-cleanup.json"
    )
    base = f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/items"

    items, pages = fetch_all_items(token)
    before = transit_inventory(items)
    dirty = expected_inventory(include_duplicates=True)
    clean = expected_inventory(include_duplicates=False)

    if before == clean:
        write_receipt(receipt_path, pages, before, before, [])
        print("Duplicates were already absent; canonical transit set verified.")
        return
    if before != dirty:
        raise SystemExit(
            "Live transit inventory no longer matches the approved audit; "
            "refusing to delete anything.\n" + json.dumps(before, indent=2)
        )

    deleted = []
    for name, (item_id, entity_id) in DUPLICATES.items():
        response = requests.delete(
            f"{base}/{item_id}", headers=headers(token), timeout=60
        )
        if response.status_code not in (200, 204):
            raise SystemExit(
                f"Delete failed for {name} item {item_id}: "
                f"HTTP {response.status_code}: {response.text[:300]}"
            )
        deleted.append({
            "name": name,
            "item_id": item_id,
            "entity_id": entity_id,
        })

    remaining, _ = fetch_all_items(token)
    after = transit_inventory(remaining)
    if after != clean:
        raise SystemExit(
            "Post-delete verification failed.\n" + json.dumps(after, indent=2)
        )
    write_receipt(receipt_path, pages, before, after, deleted)


if __name__ == "__main__":
    main()
