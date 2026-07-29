"""Publish The Bellworks and its direct Fogport relationships."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from typing import Any
import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
BASE = f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}"
APP = f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities"

def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Kanka-Librarian/1.0"}

def call(token: str, method: str, path: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.request(method, f"{BASE}/{path}", headers=headers(token), json=payload, params=params, timeout=90)
    if not response.ok:
        raise SystemExit(f"Kanka {method} {path}: HTTP {response.status_code}: {response.text[:500]}")
    return response.json()

def pages(token: str, module: str) -> list[dict[str, Any]]:
    result, page = [], 1
    while True:
        body = call(token, "GET", module, params={"page": page, "limit": 100})
        result.extend(row for row in body.get("data", []) if isinstance(row, dict))
        if page >= int(body.get("meta", {}).get("last_page", page)):
            return result
        page += 1

def one(rows: list[dict[str, Any]], names: tuple[str, ...], kind: str) -> dict[str, Any]:
    targets = {name.casefold() for name in names}
    found = [row for row in rows if str(row.get("name", "")).strip().casefold() in targets]
    if len(found) != 1:
        raise SystemExit(f"Expected exactly one {kind} named {names!r}; found {[row.get('name') for row in found]!r}.")
    return found[0]

def related(entry: str, targets: list[dict[str, Any]]) -> str:
    marker = '<p data-fogport-crosslinks="bellworks">'
    start = entry.find(marker)
    if start >= 0:
        end = entry.find("</p>", start)
        if end < 0: raise SystemExit("Malformed existing Bellworks Related block.")
        entry = entry[:start] + entry[end + 4:]
    links = "; ".join(f'<a href="{APP}/{int(t["entity_id"])}">{t["name"]}</a>' for t in targets)
    return entry.rstrip() + marker + f"<strong>Related:</strong> {links}</p>"

def link(token: str, module: str, record: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    record_id = int(record["id"])
    direct = call(token, "GET", f"{module}/{record_id}").get("data", {})
    entry = related(str(direct.get("entry") or ""), targets)
    call(token, "PATCH", f"{module}/{record_id}", {"entry": entry})
    final = call(token, "GET", f"{module}/{record_id}").get("data", {})
    urls = [f"{APP}/{int(target['entity_id'])}" for target in targets]
    if str(final.get("entry") or "") != entry or entry.count('data-fogport-crosslinks="bellworks"') != 1 or any(url not in entry for url in urls):
        raise SystemExit(f"Cross-link read-back failed for {record['name']!r}.")
    return final

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.manifest.read_text(encoding="utf-8"))
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879" or spec.get("campaign_id") != CAMPAIGN_ID or spec.get("approval", {}).get("approved_by") != "Daniel Davis":
        raise SystemExit("Fogport campaign and Daniel Davis approval locks are required.")
    token = os.environ["KANKA_API_TOKEN"]
    campaign = requests.get(f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}", headers=headers(token), timeout=60).json().get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")
    locations, items = pages(token, "locations"), pages(token, "items")
    fogport = one(locations, ("Fogport",), "parent location")
    existing = [row for row in locations if str(row.get("name", "")).strip().casefold() == "the bellworks"]
    if len(existing) > 1: raise SystemExit("Multiple Bellworks entries exist; refusing to guess.")
    payload = {"name": "The Bellworks", "type": "Industrial District", "entry": spec["entry"], "is_private": False, "parent_id": int(fogport["entity_id"])}
    if existing:
        location_id, created = int(existing[0]["id"]), False
        call(token, "PATCH", f"locations/{location_id}", payload)
    else:
        location_id, created = int(call(token, "POST", "locations", payload).get("data", {})["id"]), True
    bellworks = call(token, "GET", f"locations/{location_id}").get("data", {})
    entity = call(token, "GET", f"entities/{int(bellworks['entity_id'])}").get("data", {})
    if str(bellworks.get("name")) != "The Bellworks" or str(bellworks.get("entry") or "") != spec["entry"] or int(entity.get("parent_id") or 0) != int(fogport["entity_id"]):
        raise SystemExit("Bellworks read-back failed.")
    tramway = one(items, ("Fogport Tramway System", "Tramway System"), "tramway item")
    bellworks = link(token, "locations", bellworks, [fogport, tramway])
    fogport = link(token, "locations", fogport, [bellworks])
    tramway = link(token, "items", tramway, [bellworks])
    receipt = {"published": True, "campaign": CAMPAIGN_NAME, "campaign_id": CAMPAIGN_ID, "created": created, "bellworks_url": f"{APP}/{int(bellworks['entity_id'])}", "crosslinked": [fogport["name"], tramway["name"]]}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
