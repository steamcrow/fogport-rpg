"""Repair only Lastlight's parent relationship in the Fogport Kanka campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kanka-Librarian/0.8",
    }


def request(
    token: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.request(
        method,
        f"https://api.kanka.io/1.0/{path}",
        headers=headers(token),
        json=payload,
        params=params,
        timeout=60,
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


def all_locations(token: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    path = f"campaigns/{CAMPAIGN_ID}/locations"
    while True:
        body = request(token, "GET", path, params={"page": page, "limit": 100})
        records.extend(x for x in body.get("data", []) if isinstance(x, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact(records: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [
        record
        for record in records
        if str(record.get("name", "")).strip().casefold() == name.casefold()
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly one location named {name!r}; found {len(matches)}."
        )
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select FOGPORT_410879.")

    token = os.environ["KANKA_API_TOKEN"]
    campaign = request(token, "GET", f"campaigns/{CAMPAIGN_ID}").get("data", {})
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity lock failed.")

    locations = all_locations(token)
    blackwake = exact(locations, "Blackwake")
    lastlight = exact(locations, "Lastlight")

    blackwake_entity_id = int(blackwake["entity_id"])
    lastlight_location_id = int(lastlight["id"])

    # Intentionally change only the parent relationship. Kanka's location GET
    # representation does not expose parent_id, so HTTP success is the durable
    # API acknowledgement; no other Lastlight fields are sent or rewritten.
    request(
        token,
        "PATCH",
        f"campaigns/{CAMPAIGN_ID}/locations/{lastlight_location_id}",
        payload={"parent_id": blackwake_entity_id},
    )

    still_present = exact(all_locations(token), "Lastlight")
    if int(still_present["id"]) != lastlight_location_id:
        raise SystemExit("Lastlight identity changed unexpectedly after parent repair.")

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "operation": "parent-only repair",
        "lastlight_location_id": lastlight_location_id,
        "lastlight_entity_id": int(lastlight["entity_id"]),
        "new_parent_name": "Blackwake",
        "new_parent_entity_id": blackwake_entity_id,
        "fields_sent": ["parent_id"],
        "patch_accepted_by_kanka": True,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
