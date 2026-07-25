"""Safely add Kanka entity links to existing Fogport entries and posts."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from kanka_librarian.client import KankaClient
from kanka_librarian.crosslinks import (
    SECTION_ENDPOINTS,
    build_registry,
    link_entry,
    load_aliases,
)
from kanka_librarian.writer import KankaWriter


CAMPAIGN_ID = 410879
CAMPAIGN_NAME = "Fogport"


class CleanupError(ValueError):
    """Raised before any write when cleanup approval or scope is invalid."""


def cleanup_digest(document: dict[str, Any]) -> str:
    unsigned = deepcopy(document)
    unsigned.pop("approval", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_manifest(document: dict[str, Any], repository_root: Path) -> tuple[list[str], Path]:
    if document.get("schema_version") != 1 or document.get("mode") != "approved-crosslink-cleanup":
        raise CleanupError("Manifest must use schema_version 1 and mode approved-crosslink-cleanup.")
    if int(document.get("campaign_id", 0)) != CAMPAIGN_ID:
        raise CleanupError(f"Cleanup is locked to Fogport campaign {CAMPAIGN_ID}.")
    if str(document.get("campaign_name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise CleanupError("Campaign identity must be Fogport.")
    approval = document.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise CleanupError("Cleanup requires an explicit approval envelope.")
    if not str(approval.get("approved_by", "")).strip():
        raise CleanupError("Cleanup approval must identify the approver.")
    if approval.get("cleanup_sha256") != cleanup_digest(document):
        raise CleanupError("Cleanup manifest changed after approval.")
    if document.get("link_policy") != "first-meaningful-occurrence":
        raise CleanupError("Only the first-meaningful-occurrence policy is supported.")
    if document.get("preserve_prose") is not True:
        raise CleanupError("The cleanup must be locked to link-only prose preservation.")

    sections = document.get("sections")
    if not isinstance(sections, list) or not sections:
        raise CleanupError("Cleanup sections must be a non-empty list.")
    unknown = sorted(set(sections) - set(SECTION_ENDPOINTS))
    if unknown:
        raise CleanupError(f"Unsupported cleanup sections: {', '.join(unknown)}")

    relative_aliases = Path(str(document.get("aliases", "")))
    if relative_aliases.is_absolute() or relative_aliases.suffix != ".json":
        raise CleanupError("Alias path must be a relative JSON file.")
    root = repository_root.resolve()
    alias_path = (root / relative_aliases).resolve()
    allowed = (root / "kanka_librarian").resolve()
    if allowed not in alias_path.parents or not alias_path.is_file():
        raise CleanupError("Alias file must exist inside kanka_librarian/.")
    return [str(section) for section in sections], alias_path


def _post_is_private(owner_private: bool, post: dict[str, Any]) -> bool:
    visibility_id = post.get("visibility_id")
    return owner_private or visibility_id == 3 or bool(post.get("is_private", False))


def plan_cleanup(
    client: KankaClient,
    registry: dict[str, Any],
    *,
    include_posts: bool,
) -> list[dict[str, Any]]:
    """Read every scoped source before allowing the first write."""
    changes: list[dict[str, Any]] = []
    for entity in registry["entities"]:
        old_entry = str(entity.get("entry") or "")
        new_entry, report = link_entry(
            old_entry,
            registry,
            source_entity_id=int(entity["entity_id"]),
            source_private=bool(entity["is_private"]),
        )
        if new_entry != old_entry:
            changes.append(
                {
                    "kind": "entity",
                    "section": entity["section"],
                    "endpoint": entity["endpoint"],
                    "kanka_id": int(entity["kanka_id"]),
                    "entity_id": int(entity["entity_id"]),
                    "name": entity["canonical_name"],
                    "old_entry_sha256": hashlib.sha256(old_entry.encode("utf-8")).hexdigest(),
                    "new_entry": new_entry,
                    "links_added": report["links_added"],
                }
            )

        if not include_posts:
            continue
        for post in client.list_entity_posts(CAMPAIGN_ID, int(entity["entity_id"])):
            post_id = int(post["id"])
            if "entry" not in post:
                post = client._get(
                    f"campaigns/{CAMPAIGN_ID}/entities/{entity['entity_id']}/posts/{post_id}"
                ).get("data", {})
            old_post_entry = str(post.get("entry") or "")
            new_post_entry, post_report = link_entry(
                old_post_entry,
                registry,
                source_entity_id=int(entity["entity_id"]),
                source_private=_post_is_private(bool(entity["is_private"]), post),
            )
            if new_post_entry == old_post_entry:
                continue
            changes.append(
                {
                    "kind": "post",
                    "post_id": post_id,
                    "entity_id": int(entity["entity_id"]),
                    "owner_name": entity["canonical_name"],
                    "name": str(post.get("name") or ""),
                    "visibility_id": int(post.get("visibility_id") or 1),
                    "old_entry_sha256": hashlib.sha256(old_post_entry.encode("utf-8")).hexdigest(),
                    "new_entry": new_post_entry,
                    "links_added": post_report["links_added"],
                }
            )
    return changes


def apply_changes(
    client: KankaClient,
    writer: KankaWriter,
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for change in changes:
        expected_entry = change["new_entry"]
        if change["kind"] == "entity":
            writer.update_entity(
                CAMPAIGN_ID,
                change["section"],
                change["kanka_id"],
                {"entry": expected_entry},
            )
            actual = client._get(
                f"campaigns/{CAMPAIGN_ID}/{change['endpoint']}/{change['kanka_id']}"
            ).get("data", {})
        else:
            payload = {
                "name": change["name"],
                "entry": expected_entry,
                "entity_id": change["entity_id"],
                "visibility_id": change["visibility_id"],
            }
            writer.update_post(
                CAMPAIGN_ID,
                change["entity_id"],
                change["post_id"],
                payload,
            )
            actual = client._get(
                f"campaigns/{CAMPAIGN_ID}/entities/{change['entity_id']}/posts/{change['post_id']}"
            ).get("data", {})
        if str(actual.get("entry") or "") != expected_entry:
            raise SystemExit(
                f"Cross-link read-back failed for {change['kind']} {change['name']!r}."
            )
        verified.append(
            {
                "kind": change["kind"],
                "name": change["name"],
                "entity_id": change["entity_id"],
                "post_id": change.get("post_id"),
                "links_added": change["links_added"],
                "overview_url": (
                    f"https://app.kanka.io/w/{CAMPAIGN_ID}/entities/{change['entity_id']}"
                ),
            }
        )
    return verified


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    sections, alias_path = validate_manifest(document, repository_root)
    if args.apply and os.environ.get("KANKA_ENABLE_WRITES") != "FOGPORT_410879":
        raise SystemExit("Kanka writes are disabled or not locked to Fogport 410879.")

    token = os.environ["KANKA_API_TOKEN"]
    client = KankaClient(token)
    campaign = client.get_campaign(CAMPAIGN_ID)
    if str(campaign.get("name", "")).casefold() != CAMPAIGN_NAME.casefold():
        raise SystemExit("Kanka campaign identity check failed.")

    aliases = load_aliases(alias_path)
    registry = build_registry(client, CAMPAIGN_ID, aliases, sections=sections)
    args.registry.parent.mkdir(parents=True, exist_ok=True)
    args.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    changes = plan_cleanup(
        client,
        registry,
        include_posts=bool(document.get("include_posts", True)),
    )
    writer = KankaWriter(token=token, expected_campaign_id=CAMPAIGN_ID)
    verified = apply_changes(client, writer, changes) if args.apply else []
    receipt = {
        "campaign": CAMPAIGN_NAME,
        "campaign_id": CAMPAIGN_ID,
        "applied": bool(args.apply),
        "entities_indexed": len(registry["entities"]),
        "changes_planned": len(changes),
        "changes_verified": len(verified),
        "links_planned": sum(len(change["links_added"]) for change in changes),
        "verified": verified,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("# Fogport cross-link cleanup verified\n\n")
            stream.write(f"- Entities indexed: **{receipt['entities_indexed']}**\n")
            stream.write(f"- Entries/posts changed: **{receipt['changes_verified']}**\n")
            stream.write(f"- Links added: **{receipt['links_planned']}**\n")
            for item in verified:
                stream.write(f"- [{item['name']}]({item['overview_url']})\n")


if __name__ == "__main__":
    main()

