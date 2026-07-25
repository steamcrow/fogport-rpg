"""Publish one approval-locked Fogport batch through the proven entity publishers."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"
PUBLISHERS = {
    "character": (
        Path("kanka_librarian/approved_characters"),
        Path("scripts/publish_approved_character.py"),
    ),
    "location": (
        Path("kanka_librarian/approved"),
        Path("scripts/publish_approved_location.py"),
    ),
}


class BatchError(ValueError):
    """Raised before an unsafe or malformed batch can execute."""


def batch_digest(document: dict[str, Any]) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_batch(document: dict[str, Any], repository_root: Path) -> list[tuple[str, Path, Path]]:
    if document.get("schema_version") != 1 or document.get("mode") != "approved-batch":
        raise BatchError("Batch must use schema_version 1 and mode approved-batch.")
    if int(document.get("campaign_id", 0)) != CAMPAIGN_ID:
        raise BatchError(f"Batch publisher is locked to Fogport campaign {CAMPAIGN_ID}.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise BatchError("Batch campaign name must be Fogport.")

    approval = document.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise BatchError("Batch requires an explicit approval envelope.")
    if not str(approval.get("approved_by", "")).strip():
        raise BatchError("Batch approval must identify the approver.")
    if approval.get("batch_sha256") != batch_digest(document):
        raise BatchError("Batch changed after approval; approval is invalid.")

    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise BatchError("Batch must contain at least one proposal.")

    root = repository_root.resolve()
    resolved: list[tuple[str, Path, Path]] = []
    seen: set[Path] = set()
    for item in items:
        if not isinstance(item, dict):
            raise BatchError("Every batch item must be an object.")
        kind = str(item.get("kind", "")).strip()
        if kind not in PUBLISHERS:
            raise BatchError(f"Unsupported batch item kind: {kind!r}.")
        relative = Path(str(item.get("proposal", "")))
        if relative.suffix != ".json" or relative.is_absolute():
            raise BatchError("Proposal paths must be relative JSON files.")

        approved_directory, publisher = PUBLISHERS[kind]
        proposal = (root / relative).resolve()
        allowed_root = (root / approved_directory).resolve()
        if allowed_root not in proposal.parents:
            raise BatchError(
                f"{kind.title()} proposal must be inside {approved_directory}/."
            )
        if proposal in seen:
            raise BatchError(f"Duplicate proposal in batch: {relative}.")
        if not proposal.is_file():
            raise BatchError(f"Approved proposal does not exist: {relative}.")
        seen.add(proposal)
        resolved.append((kind, proposal, root / publisher))
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    document = json.loads(args.batch.read_text(encoding="utf-8"))
    items = validate_batch(document, repository_root)

    item_receipt_dir = args.receipt.parent / f"{args.receipt.stem}-items"
    item_receipt_dir.mkdir(parents=True, exist_ok=True)
    verified: list[dict[str, Any]] = []

    for index, (kind, proposal, publisher) in enumerate(items, start=1):
        item_receipt = item_receipt_dir / f"{index:02d}-{proposal.stem}.json"
        print(f"Publishing {index}/{len(items)}: {kind} {proposal.name}", flush=True)
        completed = subprocess.run(
            [
                sys.executable,
                str(publisher),
                str(proposal),
                "--receipt",
                str(item_receipt),
            ],
            cwd=repository_root,
            env=os.environ.copy(),
            check=False,
        )
        if completed.returncode:
            raise SystemExit(
                f"Batch stopped at item {index} ({proposal.name}); "
                "verified earlier items are safe to rerun."
            )
        child = json.loads(item_receipt.read_text(encoding="utf-8"))
        if child.get("published") is not True or not child.get("overview_url"):
            raise SystemExit(f"Item {index} did not produce a verified receipt.")
        verified.append(
            {
                "kind": kind,
                "proposal": str(proposal.relative_to(repository_root)),
                "name": child.get("name"),
                "created": child.get("created"),
                "entity_id": child.get("entity_id"),
                "overview_url": child.get("overview_url"),
                "private_posts_verified": child.get("private_posts_verified", []),
            }
        )

    receipt = {
        "published": True,
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "batch": args.batch.name,
        "items_verified": len(verified),
        "items": verified,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Fogport episode batch verified\n\n")
            stream.write(f"- Verified items: **{len(verified)}**\n")
            for item in verified:
                stream.write(f"- [{item['name']}]({item['overview_url']})\n")


if __name__ == "__main__":
    main()
