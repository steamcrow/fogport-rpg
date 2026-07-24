#!/usr/bin/env python3
"""List Kanka campaigns without changing any Kanka data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kanka_librarian import KankaClient, KankaError  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env")

    token = os.getenv("KANKA_API_TOKEN", "")
    base_url = os.getenv("KANKA_API_BASE_URL", "https://api.kanka.io/1.0")

    try:
        client = KankaClient(token=token, base_url=base_url)
        campaigns = client.list_campaigns()
    except KankaError as exc:
        print(f"Kanka Librarian error: {exc}", file=sys.stderr)
        return 1

    if not campaigns:
        print("No accessible Kanka campaigns were found.")
        return 0

    print(f"Found {len(campaigns)} Kanka campaign(s):\n")
    for campaign in sorted(campaigns, key=lambda item: str(item.get("name", "")).lower()):
        campaign_id = campaign.get("id", "?")
        name = campaign.get("name", "Unnamed campaign")
        visibility = campaign.get("visibility", "unknown")
        print(f"- {name} (ID: {campaign_id}, visibility: {visibility})")

    print("\nRead-only check complete. No Kanka data was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
