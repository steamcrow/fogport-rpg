"""Publish one subject chosen from the menu workflow.

Given a menu label like "character: lott", this script:
1. Resolves the label to its approved manifest and publisher script.
2. If the manifest names an approved image that only exists as base64
   chunks, rebuilds it first and verifies the checksum recorded inside
   the approved manifest itself (a mismatch is a correct stop).
3. Runs the mapped publisher exactly as its dedicated workflow used to,
   writing the receipt to receipts/<subject>.json.

The label must match a menu entry exactly; nothing is guessed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from publish_menu import resolve  # noqa: E402


def restore_image_if_chunked(manifest_path: Path) -> None:
    """Rebuild a chunked approved image using the manifest's own checksum."""
    import json

    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return
    image_path = manifest.get("image_path")
    expected_sha = manifest.get("sha256")
    if not image_path or not expected_sha:
        return
    image = REPOSITORY_ROOT / image_path
    if image.exists():
        return
    parts = sorted(image.parent.glob(f"{image.name}.b64.part-*"))
    if not parts:
        return
    print(f"Rebuilding {image_path} from {len(parts)} base64 chunks...")
    command = [
        sys.executable,
        str(REPOSITORY_ROOT / "scripts" / "restore_base64_chunks.py"),
        *[str(part) for part in parts],
        "--output",
        str(image),
        "--expected-sha256",
        str(expected_sha),
    ]
    completed = subprocess.run(command, cwd=REPOSITORY_ROOT)
    if completed.returncode != 0:
        raise SystemExit(
            "Image restore failed or the checksum did not match the approved "
            "manifest. This is a correct stop, not an error to bypass."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Menu label to publish")
    args = parser.parse_args()

    entry = resolve(args.subject)
    manifest = REPOSITORY_ROOT / entry["manifest"]
    script = REPOSITORY_ROOT / entry["script"]
    receipt = REPOSITORY_ROOT / entry["receipt"]

    if not manifest.is_file():
        raise SystemExit(f"Approved manifest not found: {entry['manifest']}")
    if not script.is_file():
        raise SystemExit(f"Publisher script not found: {entry['script']}")

    restore_image_if_chunked(manifest)
    receipt.parent.mkdir(parents=True, exist_ok=True)

    print(f"Publishing {entry['label']!r}")
    print(f"  manifest: {entry['manifest']}")
    print(f"  publisher: {entry['script']}")
    print(f"  receipt: {entry['receipt']}")

    completed = subprocess.run(
        [sys.executable, str(script), str(manifest), "--receipt", str(receipt)],
        cwd=REPOSITORY_ROOT,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)

    # Creature portraits are a second, checksum-locked publication phase.
    # Keeping it here makes a creature with an approved portrait one safe,
    # one-button operation while leaving creatures without portraits unchanged.
    if entry["label"].startswith("creature: "):
        portrait_manifest = (
            REPOSITORY_ROOT
            / "kanka_librarian"
            / "approved_creature_portraits"
            / f"{manifest.stem}.json"
        )
        portrait_script = REPOSITORY_ROOT / "scripts" / "publish_creature_portrait.py"
        if portrait_manifest.is_file():
            portrait_receipt = REPOSITORY_ROOT / "receipts" / f"{manifest.stem}-portrait.json"
            print(f"Publishing approved portrait for {entry['label']!r}")
            portrait_run = subprocess.run(
                [
                    sys.executable,
                    str(portrait_script),
                    str(portrait_manifest),
                    "--receipt",
                    str(portrait_receipt),
                ],
                cwd=REPOSITORY_ROOT,
            )
            raise SystemExit(portrait_run.returncode)


if __name__ == "__main__":
    main()
