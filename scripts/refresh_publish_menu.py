"""Regenerate the subject dropdown inside publish-approved.yml.

Run this after approving a new manifest:

  python scripts/refresh_publish_menu.py

It rewrites only the options list between the AUTO-MENU markers, so the
rest of the workflow file is never touched. Commit the updated workflow
and the new subject appears in the menu.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from publish_menu import RECENT_LIMIT, SENTINEL, build_menu  # noqa: E402

WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "publish-approved.yml"
BEGIN = "          # BEGIN AUTO-MENU (run scripts/refresh_publish_menu.py)\n"
END = "          # END AUTO-MENU\n"


def main() -> None:
    labels = [SENTINEL] + [entry["label"] for entry in build_menu()[:RECENT_LIMIT]]
    options = "".join(f'          - "{label}"\n' for label in labels)

    text = WORKFLOW.read_text()
    start = text.index(BEGIN) + len(BEGIN)
    end = text.index(END)
    WORKFLOW.write_text(text[:start] + options + text[end:])
    print(
        f"Menu refreshed with {len(labels) - 1} recent subjects "
        f"(of {len(build_menu())}) in {WORKFLOW.name}."
    )


if __name__ == "__main__":
    main()
