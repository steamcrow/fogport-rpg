"""Publish one approved era onto an existing Fogport timeline.

To add a new era, you do not need to write any code: put an approved
JSON file in kanka_librarian/approved_eras/ (see
kanka_librarian/era_publish.py for the exact shape), run
`python scripts/refresh_publish_menu.py`, and it appears in the dropdown.

This script only adds an era to a timeline that already exists. Creating
a brand-new timeline is a separate, rarer operation and still needs a
dedicated script (see scripts/publish_fogport_history.py for the one
that built the original Fogport History timeline).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
install_api_pacing()

from kanka_librarian.era_publish import publish_era


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    publish_era(args.proposal, args.receipt)


if __name__ == "__main__":
    main()
