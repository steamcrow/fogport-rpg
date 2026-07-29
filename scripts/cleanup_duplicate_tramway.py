"""Audit every Kanka Item page for duplicate Fogport transit entries.

This command is deliberately read-only. It never sends POST, PUT, PATCH, or DELETE.
"""

import json
import os
from pathlib import Path
from urllib.parse import urljoin

import requests

CAMPAIGN_ID = 410879
TARGET_NAMES = (
    "Fogport Tramway System",
    "Standard Passenger Tram",
    "Industrial Freight Tram",
    "Fogport Fire Brigade Tram",
    "Civic Police Tram",
    "Standard Transit Crate",
)


def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
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


def main():
    token = os.environ["KANKA_API_TOKEN"]
    report_path = Path(os.environ.get(
        "REPORT_PATH", "receipts/transit-duplicate-audit.json"
    ))
    items, pages = fetch_all_items(token)
    targets = {name.casefold(): name for name in TARGET_NAMES}
    matches = {name: [] for name in TARGET_NAMES}

    for item in items:
        normalized = str(item.get("name", "")).strip().casefold()
        canonical_name = targets.get(normalized)
        if canonical_name is None:
            continue
        entity_id = int(item.get("entity_id", 0))
        matches[canonical_name].append({
            "item_id": int(item["id"]),
            "entity_id": entity_id,
            "name": str(item.get("name", "")).strip(),
            "url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{entity_id}",
        })

    for found in matches.values():
        found.sort(key=lambda entry: (entry["entity_id"], entry["item_id"]))

    report = {
        "schema_version": 1,
        "mode": "read-only-transit-duplicate-audit",
        "campaign_id": CAMPAIGN_ID,
        "pages_scanned": pages,
        "items_scanned": len(items),
        "targets": matches,
        "duplicate_titles": [
            name for name, found in matches.items() if len(found) > 1
        ],
        "missing_titles": [
            name for name, found in matches.items() if not found
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
