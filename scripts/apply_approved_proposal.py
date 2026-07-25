#!/usr/bin/env python3
"""Validate or execute one explicitly approved Kanka proposal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kanka_librarian.publisher import apply_approved_proposal
from kanka_librarian.writer import KankaWriter


class DryRunWriter:
    def create_entity(self, *args, **kwargs):
        raise AssertionError("Dry-run validation attempted a create.")

    def update_entity(self, *args, **kwargs):
        raise AssertionError("Dry-run validation attempted an update.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path, help="Approved proposal JSON file")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write the approved batch to MAELSTROS",
    )
    args = parser.parse_args()
    document = json.loads(args.proposal.read_text(encoding="utf-8"))

    if args.execute:
        if os.environ.get("KANKA_ENABLE_WRITES") != "MAELSTROS_29474":
            parser.error(
                "--execute also requires KANKA_ENABLE_WRITES=MAELSTROS_29474"
            )
        writer = KankaWriter(token=os.environ.get("KANKA_API_TOKEN", ""))
    else:
        writer = DryRunWriter()

    summary = apply_approved_proposal(document, writer, execute=args.execute)
    # The summary intentionally contains IDs and counts, never campaign body copy.
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
