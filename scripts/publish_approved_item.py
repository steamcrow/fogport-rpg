"""Publish one approved Fogport item and verify the exact Kanka record.

This is the generic item publisher. Any new item that does not already
have a bespoke script (see kanka_librarian/generic_publish.py OVERRIDES
notes and scripts/publish_menu.py) is published through this file. To add
a new item, you do not need to write any code: put an approved JSON file
in kanka_librarian/approved_items/, run
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
        section="items",
        subject_label="item",
        list_method="list_items",
        id_field_name="item_id",
        optional_location_link=True,
    )


if __name__ == "__main__":
    main()
