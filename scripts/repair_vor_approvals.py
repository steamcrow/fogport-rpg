"""Repair approval digests for the explicitly approved Vor entries before publication."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kanka_librarian.publisher import proposal_digest

PATHS = [
    ROOT / "kanka_librarian" / "approved_organizations" / "red-church-of-vor.json",
    ROOT / "kanka_librarian" / "approved" / "temple-of-the-red-bat.json",
]

for path in PATHS:
    doc = json.loads(path.read_text())
    doc["approval"]["proposal_sha256"] = proposal_digest(doc)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Repaired approval digest: {path.name}")
