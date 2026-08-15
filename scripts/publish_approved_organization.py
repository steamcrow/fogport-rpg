"""Publish one approved Fogport organization and verify the exact Kanka record.

This is the generic organization publisher. Any new organization that does
not already have a bespoke script is published through this file. To add
a new organization, you do not need to write any code: put an approved
JSON file in kanka_librarian/approved_organizations/, run
`python scripts/refresh_publish_menu.py`, and it appears in the dropdown.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from kanka_librarian.pacing import install_api_pacing
install_api_pacing()

from kanka_librarian.generic_publish import publish_simple_entity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    publish_simple_entity(
        args.proposal,
        args.receipt,
        section="organizations",
        subject_label="organization",
        list_method="list_organizations",
        id_field_name="organization_id",
    )


if __name__ == "__main__":
    main()
