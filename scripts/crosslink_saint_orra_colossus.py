"""Cross-link Saint Orra's Colossus with its closest related Fogport entries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
BASE = f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}"
APP_BASE = f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities"


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kanka-Librarian/0.8",
    }


def request(token: str, method: str, path: str, *, payload: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.request(
        method, f"{BASE}/{path}", headers=headers(token), json=payload,
        params=params, timeout=60,
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


def all_pages(token: str, module: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        body = request(token, "GET", module, params={"page": page, "limit": 100})
        records.extend(x for x in body.get("data", []) if isinstance(x, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact(records: list[dict[str, Any]], names: tuple[str, ...], kind: str) -> dict[str, Any]:
    folded = {name.casefold() for name in names}
    matches = [x for x in records if str(x.get("name", "")).strip().casefold() in folded]
    if len(matches) != 1:
        found = [str(x.get("name")) for x in matches]
        raise SystemExit(
            f"Expected exactly one {kind} named one of {names!r}; found {found!r}."
        )
    return matches[0]


def link(entity: dict[str, Any], label: str | None = None) -> str:
    entity_id = int(entity["entity_id"])
    text = label or str(entity["name"])
    return f'<a href="{APP_BASE}/{entity_id}">{text}</a>'


def replace_related(entry: str, related_html: str) -> str:
    marker = '<p data-fogport-crosslinks="saint-orra">'
    start = entry.find(marker)
    if start >= 0:
        end = entry.find("</p>", start)
        if end < 0:
            raise SystemExit("Existing Saint Orra cross-link block is malformed.")
        entry = entry[:start] + entry[end + 4:]
    return entry.rstrip() + marker + "<strong>Related:</strong> " + related_html + "</p>"


def patch_and_verify(token: str, module: str, record: dict[str, Any],
                     related: list[dict[str, Any]]) -> dict[str, Any]:
    record_id = int(record["id"])
    direct = request(token, "GET", f"{module}/{record_id}").get("data", {})
    related_html = "; ".join(link(target) for target in related)
    updated_entry = replace_related(str(direct.get("entry") or ""), related_html)
    request(token, "PATCH", f"{module}/{record_id}", payload={"entry": updated_entry})
    final = request(token, "GET", f"{module}/{record_id}").get("data", {})
    final_entry = str(final.get("entry") or "")
    expected_urls = [f"{APP_BASE}/{int(target['entity_id'])}" for target in related]
    if (
        int(final.get("id") or 0) != record_id
        or final_entry.count('data-fogport-crosslinks="saint-orra"') != 1
        or any(url not in final_entry for url in expected_urls)
    ):
        raise SystemExit(f"Cross-link read-back failed for {record['name']!r}.")
    return {
        "name": str(final["name"]),
        "id": record_id,
        "entity_id": int(final["entity_id"]),
        "url": f"{APP_BASE}/{int(final['entity_id'])}",
        "linked_to": [str(target["name"]) for target in related],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")
    token = os.environ["KANKA_API_TOKEN"]
    campaign = requests.get(
        f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}",
        headers=headers(token), timeout=60,
    )
    if not campaign.ok:
        raise SystemExit(f"Campaign check failed: HTTP {campaign.status_code}.")
    campaign_data = campaign.json().get("data", {})
    if str(campaign_data.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    locations = all_pages(token, "locations")
    items = all_pages(token, "items")

    lastlight = exact(locations, ("Lastlight",), "location")
    colossus = exact(locations, ("Saint Orra's Colossus",), "location")
    station = exact(locations, ("Grand Heliot Station",), "location")
    tramway = exact(
        items, ("Fogport Tramway System", "Tramway System"), "tramway item"
    )

    updates = [
        patch_and_verify(token, "locations", lastlight, [colossus]),
        patch_and_verify(token, "items", tramway, [lastlight, colossus, station]),
        patch_and_verify(token, "locations", station, [lastlight, colossus, tramway]),
        patch_and_verify(token, "locations", colossus, [lastlight, station, tramway]),
    ]

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "crosslink_set": "Saint Orra's Colossus",
        "updates": updates,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
