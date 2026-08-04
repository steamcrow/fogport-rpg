"""Update and verify the exact Fogport Gamemaster Guide Note and post."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from kanka_librarian.client import KankaClient
from kanka_librarian.writer import KankaWriter
from scripts.publish_compiled_episode import normalize_kanka_html


CAMPAIGN_ID = 410879
NOTE_ID = 332976
ENTITY_ID = 9626686
POST_ID = 1413484


def digest(document: dict) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_manifest(document: dict) -> None:
    if document.get("mode") != "exact-note-update":
        raise SystemExit("Expected an exact-note-update manifest.")
    locks = (
        int(document.get("campaign_id", 0)),
        int(document.get("note_id", 0)),
        int(document.get("entity_id", 0)),
        int(document.get("post", {}).get("id", 0)),
    )
    if locks != (CAMPAIGN_ID, NOTE_ID, ENTITY_ID, POST_ID):
        raise SystemExit("Exact Note identity lock failed; refusing to write.")
    approval = document.get("approval", {})
    if approval.get("status") != "approved":
        raise SystemExit("Approved manifest required.")
    if approval.get("document_sha256") != digest(document):
        raise SystemExit("Manifest changed after approval; refusing to write.")


def main() -> None:
    if os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("KANKA_ENABLE_WRITES must explicitly select Fogport.")
    manifest = Path(os.environ["MANIFEST_PATH"])
    receipt_path = Path(os.environ["REPORT_PATH"])
    document = json.loads(manifest.read_text(encoding="utf-8"))
    verify_manifest(document)

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != "fogport":
        raise SystemExit("Campaign identity mismatch; refusing to write.")

    notes = [
        note for note in client.list_notes(CAMPAIGN_ID, related=True)
        if int(note.get("id", 0)) == NOTE_ID
        and int(note.get("entity_id", 0)) == ENTITY_ID
        and str(note.get("name", "")) == "Gamemaster Guide"
    ]
    posts = [
        post for post in client.list_entity_posts(CAMPAIGN_ID, ENTITY_ID)
        if int(post.get("id", 0)) == POST_ID
        and str(post.get("name", "")) == "GM Style Guide"
    ]
    if len(notes) != 1 or len(posts) != 1:
        raise SystemExit("Live exact Note or post no longer matches the audit.")

    note_payload = {
        "name": document["name"],
        "entry": document["entry"],
        "type": document["type"],
        "is_private": bool(document["is_private"]),
    }
    post_payload = {
        "name": document["post"]["name"],
        "entry": document["post"]["entry"],
        "entity_id": ENTITY_ID,
        "visibility_id": int(document["post"]["visibility_id"]),
    }
    writer.update_entity(CAMPAIGN_ID, "notes", NOTE_ID, note_payload)
    writer.update_post(CAMPAIGN_ID, ENTITY_ID, POST_ID, post_payload)

    note_back = client._get(
        f"campaigns/{CAMPAIGN_ID}/notes/{NOTE_ID}"
    ).get("data", {})
    post_back = client._get(
        f"campaigns/{CAMPAIGN_ID}/entities/{ENTITY_ID}/posts/{POST_ID}"
    ).get("data", {})
    if (
        int(note_back.get("entity_id", 0)) != ENTITY_ID
        or note_back.get("name") != note_payload["name"]
        or normalize_kanka_html(note_back.get("entry", ""))
        != normalize_kanka_html(note_payload["entry"])
        or int(post_back.get("id", 0)) != POST_ID
        or post_back.get("name") != post_payload["name"]
        or int(post_back.get("visibility_id", 0)) != 1
        or normalize_kanka_html(post_back.get("entry", ""))
        != normalize_kanka_html(post_payload["entry"])
    ):
        raise SystemExit("Exact Kanka read-back failed; cleanup must not run.")

    receipt = {
        "published": True,
        "campaign_id": CAMPAIGN_ID,
        "note_id": NOTE_ID,
        "entity_id": ENTITY_ID,
        "post_id": POST_ID,
        "note_verified": True,
        "post_verified": True,
        "document_sha256": digest(document),
        "overview_url": f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{ENTITY_ID}",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
