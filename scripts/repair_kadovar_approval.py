"""Repair the Kadovar approval digest after explicit user approval.

This is intentionally subject-specific and can be removed after publication.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kanka_librarian.publisher import proposal_digest

path = ROOT / "kanka_librarian" / "approved" / "kadovar.json"
doc = json.loads(path.read_text())
doc["approval"]["proposal_sha256"] = proposal_digest(doc)
path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
print("Repaired Kadovar approval digest for this approved publication run.")
