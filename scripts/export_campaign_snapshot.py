"""Export a read-only campaign snapshot as a downloadable artifact.

This never writes to the repository -- it follows the same pattern as
scripts/export_fogport_voice_bible.py: read from Kanka, write to a
local artifacts directory, and let the GitHub Actions workflow upload
that directory as a run artifact. An AI assistant with Actions-read
access to this repo can download the artifact from the completed run
without ever holding a Kanka credential.

Run manually:
    python scripts/export_campaign_snapshot.py

Or via the "Kanka Librarian — Export campaign snapshot (read only)"
GitHub Actions workflow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
install_api_pacing()

from kanka_librarian.client import KankaClient
from kanka_librarian.snapshot import build_snapshot

CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1] / "artifacts" / "fogport-campaign-snapshot"
)


def main() -> None:
    output_dir = Path(os.environ.get("FOGPORT_SNAPSHOT_EXPORT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "campaign_snapshot.json"

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    snapshot = build_snapshot(client, campaign_id=CAMPAIGN_ID, campaign_name=CAMPAIGN_NAME)
    output_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    counts = {section: len(records) for section, records in snapshot["entities"].items()}
    print(f"Wrote {output_path}")
    print(json.dumps(counts, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Campaign snapshot exported (read only)\n\n")
            stream.write(f"Generated at {snapshot['generated_at']}\n\n")
            for section, count in counts.items():
                stream.write(f"- {section}: {count}\n")
            stream.write(f"- timelines: {len(snapshot['timelines'])}\n")


if __name__ == "__main__":
    main()
