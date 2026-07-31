"""The publish menu: one list of every approved subject and its publisher.

This replaces the old pattern of writing a brand-new workflow file for
every published subject. The menu scans the approved manifest folders,
routes each manifest to the correct publisher script, and gives each a
human-readable label like "character: inspector-adelaide-voss".

Safety properties preserved from the old dedicated workflows:
- Only manifests inside the approved folders can appear. Nothing can be
  typed in by hand, so path traversal and typos are impossible.
- Manifests with a bespoke publisher are routed to that exact script via
  the OVERRIDES table; unknown bespoke manifests are skipped entirely
  rather than guessed at.
- Multi-phase subjects (the annual observances calendar) keep their own
  dedicated workflows and are deliberately excluded here.

Usage:
  python scripts/publish_menu.py --list       # show every menu entry
  python scripts/publish_menu.py --labels     # labels only, for the menu
  python scripts/publish_menu.py --resolve "character: lott"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIBRARIAN = REPOSITORY_ROOT / "kanka_librarian"

SENTINEL = "-- choose a subject --"

# Folder -> (kind label, default publisher script)
FOLDER_ROUTES = {
    "approved": ("location", "scripts/publish_approved_location.py"),
    "approved_characters": ("character", "scripts/publish_approved_character.py"),
    "approved_creatures": ("creature", "scripts/publish_approved_creature.py"),
    "approved_batches": ("episode-batch", "scripts/publish_approved_batch.py"),
    "approved_episodes": ("episode", "scripts/publish_compiled_episode.py"),
    "approved_items": ("item", None),           # bespoke; see OVERRIDES
    "approved_organizations": ("organization", None),  # bespoke; see OVERRIDES
}

# Manifests that must use a specific publisher script.
OVERRIDES = {
    "approved_characters/inspector-adelaide-voss.json": "scripts/publish_inspector_adelaide_voss.py",
    "approved_items/cinderhack.json": "scripts/publish_cinderhack.py",
    "approved_organizations/civic-vigilance.json": "scripts/publish_civic_vigilance.py",
    "approved_organizations/daughters-last-bell.json": "scripts/publish_daughters_last_bell.py",
    "approved_organizations/order-last-landing.json": "scripts/publish_order_last_landing.py",
    "approved/fogport-history.json": "scripts/publish_fogport_history.py",
}

# Manifests whose mode selects a generic publisher regardless of folder.
# Each mode also corrects the kind label shown in the menu.
MODE_ROUTES = {
    "approved-item-batch": ("item-batch", "scripts/publish_approved_item_batch.py"),
    "approved-batch": ("episode-batch", "scripts/publish_approved_batch.py"),
    "compiled-episode": ("episode", "scripts/publish_compiled_episode.py"),
}

# Multi-phase subjects that keep their own dedicated workflows.
EXCLUDED = {
    "approved/fogport-annual-observances.json",
    "approved/fogport-calendar.json",
}


def build_menu() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for folder, (kind, default_script) in FOLDER_ROUTES.items():
        directory = LIBRARIAN / folder
        if not directory.is_dir():
            continue
        for manifest in sorted(directory.glob("*.json")):
            relative = f"{folder}/{manifest.name}"
            if relative in EXCLUDED:
                continue
            script = OVERRIDES.get(relative)
            if script is None:
                try:
                    mode = json.loads(manifest.read_text()).get("mode")
                except (OSError, ValueError):
                    mode = None
                if mode in MODE_ROUTES:
                    kind_label, script = MODE_ROUTES[mode]
                else:
                    kind_label, script = kind, default_script
            else:
                kind_label = kind
            if script is None:
                continue  # bespoke manifest with no known publisher: never guess
            entries.append(
                {
                    "label": f"{kind_label}: {manifest.stem}",
                    "manifest": f"kanka_librarian/{relative}",
                    "script": script,
                    "receipt": f"receipts/{manifest.stem}.json",
                }
            )
    entries.sort(key=lambda e: e["label"])
    return entries


def resolve(label: str) -> dict[str, str]:
    wanted = label.strip()
    if not wanted or wanted == SENTINEL:
        raise SystemExit(
            "No subject was chosen. Pick a subject from the menu and run again."
        )
    for entry in build_menu():
        if entry["label"] == wanted:
            return entry
    raise SystemExit(
        f"Unknown subject {wanted!r}. Refresh the menu with "
        "scripts/refresh_publish_menu.py after adding new approved manifests."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--labels", action="store_true")
    group.add_argument("--resolve", metavar="LABEL")
    args = parser.parse_args()

    if args.resolve:
        entry = resolve(args.resolve)
        print(json.dumps(entry, indent=2))
        return

    for entry in build_menu():
        if args.labels:
            print(entry["label"])
        else:
            print(f"{entry['label']:45} -> {entry['script']}  ({entry['manifest']})")


if __name__ == "__main__":
    main()
