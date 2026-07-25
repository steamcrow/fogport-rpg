#!/usr/bin/env python3
"""Validate or execute one explicitly approved Kanka proposal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kanka_librarian.publisher import SUPPORTED_CAMPAIGNS, apply_approved_proposal
from kanka_librarian.writer import KankaWriter


class DryRunWriter:
    def __getattr__(self, name):
        raise AssertionError(f"Dry-run validation attempted writer operation {name}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path, help="Approved proposal JSON file")
    parser.add_argument("--execute", action="store_true", help="Actually write the approved batch to its named Kanka campaign")
    args = parser.parse_args()
    document = json.loads(args.proposal.read_text(encoding="utf-8"))
    campaign_id = int(document.get("campaign_id", 0))

    if args.execute:
        campaign_name = SUPPORTED_CAMPAIGNS.get(campaign_id)
        if not campaign_name:
            parser.error(f"Campaign {campaign_id} is not configured.")
        required_phrase = f"{campaign_name.upper()}_{campaign_id}"
        if os.environ.get("KANKA_ENABLE_WRITES") != required_phrase:
            parser.error(f"--execute also requires KANKA_ENABLE_WRITES={required_phrase}")
        writer = KankaWriter(
            token=os.environ.get("KANKA_API_TOKEN", ""),
            expected_campaign_id=campaign_id,
        )
    else:
        writer = DryRunWriter()

    summary = apply_approved_proposal(document, writer, execute=args.execute)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
