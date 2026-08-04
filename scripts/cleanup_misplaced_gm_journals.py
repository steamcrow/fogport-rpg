"""Delete only the nine audited Journal entities misplaced by GM publication."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from kanka_librarian.api import headers
from kanka_librarian.client import KankaClient
from kanka_librarian.pacing import install_api_pacing


install_api_pacing()
CAMPAIGN_ID = 410879
MISPLACED = {
    "START HERE — Running a Fogport Episode": (182123, 9635834),
    "GM Source Checklist — Before Every Episode": (182124, 9635835),
    "Canon Authority & Contradictions": (182125, 9635836),
    "Preparing a Fogport Episode": (182126, 9635837),
    "Current Creative Direction — Adventure, Mystery & Restraint": (182834, 9666865),
    "Voice Play — Arbor Protocol": (182835, 9666866),
    "Running a Fogport Episode": (182127, 9635838),
    "After the Episode — Continuity & Kanka": (182128, 9635839),
    "Campaign Director’s Notebook — Maintenance Rules": (182129, 9635840),
}


def inventory(journals: list[dict]) -> dict[str, tuple[int, int]]:
    names = set(MISPLACED)
    return {
        str(item.get("name")): (int(item["id"]), int(item["entity_id"]))
        for item in journals
        if str(item.get("name")) in names
    }


def main() -> None:
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select Fogport.")
    token = os.environ["KANKA_API_TOKEN"]
    report_path = Path(os.environ["REPORT_PATH"])
    client = KankaClient(token)
    before = inventory(client.list_journals(CAMPAIGN_ID, related=True))
    if not before:
        deleted = []
    elif before != MISPLACED:
        raise SystemExit(
            "Live Journal inventory differs from the approved cleanup; "
            "refusing to delete anything.\n" + json.dumps(before, indent=2)
        )
    else:
        deleted = []
        for name, (journal_id, entity_id) in MISPLACED.items():
            response = requests.delete(
                f"https://api.kanka.io/1.0/campaigns/{CAMPAIGN_ID}/journals/{journal_id}",
                headers=headers(token), timeout=60,
            )
            if response.status_code not in (200, 204):
                raise SystemExit(
                    f"Delete failed for {name} ({journal_id}): "
                    f"HTTP {response.status_code}: {response.text[:300]}"
                )
            deleted.append({"name": name, "journal_id": journal_id, "entity_id": entity_id})

    after = inventory(client.list_journals(CAMPAIGN_ID, related=True))
    if after:
        raise SystemExit("Post-delete verification failed: " + json.dumps(after, indent=2))
    report = {
        "cleanup_verified": True,
        "campaign_id": CAMPAIGN_ID,
        "target_count": len(MISPLACED),
        "deleted": deleted,
        "remaining_target_journals": after,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
