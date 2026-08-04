#!/usr/bin/env python3
"""Export Fogport's complete Kanka lore as read-only Voice-friendly files."""

from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # The GitHub workflow installs it; tests do not require it.
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kanka_librarian import KankaClient, KankaError  # noqa: E402

FOGPORT_CAMPAIGN_ID = 410879
FOGPORT_EXPECTED_NAME = "Fogport"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "fogport-voice-bible"


class MarkdownHTMLParser(HTMLParser):
    """Small, dependency-free converter for the HTML Kanka stores in entries."""

    BLOCK_START = {
        "p": "\n\n",
        "div": "\n\n",
        "blockquote": "\n\n> ",
        "ul": "\n",
        "ol": "\n",
        "table": "\n\n",
        "tr": "\n",
    }
    BLOCK_END = {"p", "div", "blockquote", "ul", "ol", "table", "tr"}
    HEADING = {f"h{level}": "#" * level for level in range(1, 7)}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.list_stack: list[dict[str, int | str]] = []
        self.href_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self.HEADING:
            self.parts.append(f"\n\n{self.HEADING[tag]} ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in ("strong", "b"):
            self.parts.append("**")
        elif tag in ("em", "i"):
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag in ("ul", "ol"):
            self.parts.append("\n")
            self.list_stack.append({"tag": tag, "index": 0})
        elif tag == "li":
            prefix = "- "
            if self.list_stack and self.list_stack[-1]["tag"] == "ol":
                self.list_stack[-1]["index"] = int(self.list_stack[-1]["index"]) + 1
                prefix = f"{self.list_stack[-1]['index']}. "
            self.parts.append(f"\n{prefix}")
        elif tag == "a":
            href = dict(attrs).get("href")
            self.href_stack.append(href)
            self.parts.append("[")
        elif tag in self.BLOCK_START:
            self.parts.append(self.BLOCK_START[tag])
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self.HEADING:
            self.parts.append("\n")
        elif tag in ("strong", "b"):
            self.parts.append("**")
        elif tag in ("em", "i"):
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self.parts.append("\n")
        elif tag == "a":
            href = self.href_stack.pop() if self.href_stack else None
            self.parts.append(f"]({href})" if href else "]")
        elif tag in self.BLOCK_END:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def markdown(self) -> str:
        value = html.unescape("".join(self.parts)).replace("\r\n", "\n")
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def html_to_markdown(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parser = MarkdownHTMLParser()
    parser.feed(text)
    parser.close()
    return parser.markdown()


def entity_type(entity: dict[str, Any]) -> str:
    """Return the most useful stable module/type label available."""
    for key in ("type", "type_name", "entity_type", "child_type"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = entity.get("type_id")
    return f"Type {value}" if value is not None else "Uncategorized"


def entity_name(entity: dict[str, Any]) -> str:
    return str(entity.get("name") or f"Unnamed entity {entity.get('id', '?')}").strip()


def collect_related(entity: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        records = entity.get(key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    return []


def normalize_entity(entity: dict[str, Any], posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep complete API records while adding stable Voice-oriented metadata."""
    normalized = dict(entity)
    normalized["voice_export"] = {
        "display_name": entity_name(entity),
        "display_type": entity_type(entity),
        "kanka_url": f"https://app.kanka.io/w/{FOGPORT_CAMPAIGN_ID}/entities/{int(entity['id'])}",
    }
    normalized["posts"] = posts
    return normalized


def visibility_label(record: dict[str, Any]) -> str:
    visibility_id = record.get("visibility_id")
    if record.get("is_private") is True or visibility_id == 3:
        return "PRIVATE / GM-RESTRICTED"
    if visibility_id == 1:
        return "PUBLIC TO CAMPAIGN MEMBERS"
    if visibility_id not in (None, 0):
        return f"RESTRICTED (Kanka visibility_id {visibility_id})"
    return "PUBLIC OR CAMPAIGN-DEFAULT"


def render_record_list(title: str, records: list[dict[str, Any]], fields: tuple[str, ...]) -> list[str]:
    if not records:
        return []
    lines = [f"#### {title}", ""]
    for record in records:
        bits = []
        for field in fields:
            value = record.get(field)
            if value not in (None, "", [], {}):
                bits.append(f"{field}: {value}")
        lines.append(f"- {'; '.join(bits) if bits else json.dumps(record, ensure_ascii=False)}")
    lines.append("")
    return lines


def render_markdown(campaign: dict[str, Any], entities: list[dict[str, Any]], generated_at: str) -> str:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(entity_type(entity), []).append(entity)

    lines = [
        "# Fogport Kanka Synopsis — Complete Voice GM Edition",
        "",
        f"Generated from Kanka at {generated_at}.",
        "",
        "> GM CONFIDENTIAL: This file can contain private entries, restricted posts, secrets, attributes, and relationships. Do not show it to players.",
        "",
        "## Instructions for ChatGPT Voice",
        "",
        "Treat this file as the current Kanka authority for Fogport. Use private or restricted material only as hidden GM knowledge; reveal it in play only when earned. Daniel controls Byl. You control Fogport, NPCs, adversaries, and Lott. Never invent a contradiction merely to preserve a mystery; resolve uncertainty through the most specific and most recently updated entry.",
        "",
        "When the file contains conflicting statements, prefer: explicit GM secrets; then specific character/location/organization entries; then general setting articles. Preserve uncertainty only when the lore itself says the truth is unknown.",
        "",
        "## Export Summary",
        "",
        f"- Campaign: {campaign.get('name')} (Kanka campaign {campaign.get('id')})",
        f"- Entries: {len(entities)}",
        f"- Private entries: {sum(bool(item.get('is_private')) for item in entities)}",
        f"- Attached posts: {sum(len(item.get('posts', [])) for item in entities)}",
        "- Mode: read-only export; Kanka was not changed",
        "",
        "## Entry Index",
        "",
    ]

    for kind in sorted(by_type, key=str.casefold):
        names = ", ".join(entity_name(item) for item in sorted(by_type[kind], key=lambda item: entity_name(item).casefold()))
        lines.append(f"- **{kind} ({len(by_type[kind])}):** {names}")

    for kind in sorted(by_type, key=str.casefold):
        lines.extend(["", f"# {kind}", ""])
        for entity in sorted(by_type[kind], key=lambda item: (entity_name(item).casefold(), int(item.get("id") or 0))):
            entity_id = int(entity["id"])
            lines.extend([
                f"## {entity_name(entity)}",
                "",
                f"- Kanka: https://app.kanka.io/w/{FOGPORT_CAMPAIGN_ID}/entities/{entity_id}",
                f"- Entity ID: {entity_id}",
                f"- Privacy: {visibility_label(entity)}",
                f"- Updated: {entity.get('updated_at') or 'unknown'}",
            ])
            subtype = entity.get("type")
            if subtype:
                lines.append(f"- Subtype: {subtype}")
            tags = entity.get("tags")
            if tags:
                lines.append(f"- Tags: {json.dumps(tags, ensure_ascii=False)}")
            lines.append("")

            entry = html_to_markdown(entity.get("entry_parsed") or entity.get("entry"))
            lines.extend([entry or "*(No main entry text.)*", ""])

            attributes = collect_related(entity, ("attributes",))
            lines.extend(render_record_list(
                "Attributes",
                attributes,
                ("name", "value", "parsed", "is_private", "is_pinned"),
            ))
            relationships = collect_related(entity, ("relations", "relationships"))
            lines.extend(render_record_list(
                "Relationships",
                relationships,
                ("relation", "owner_id", "target_id", "attitude", "visibility_id", "is_pinned"),
            ))

            posts = entity.get("posts", [])
            if posts:
                lines.extend(["### Attached Articles / Secrets", ""])
            for post in sorted(posts, key=lambda item: (int(item.get("position") or 0), int(item.get("id") or 0))):
                post_name = str(post.get("name") or f"Post {post.get('id', '?')}")
                lines.extend([
                    f"#### {post_name}",
                    "",
                    f"*Access: {visibility_label(post)}; post ID {post.get('id', '?')}*",
                    "",
                    html_to_markdown(post.get("entry")) or "*(No post text.)*",
                    "",
                ])

    return "\n".join(lines).strip() + "\n"


def build_snapshot(campaign: dict[str, Any], entities: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "mode": "read-only",
        "content_scope": "complete-fogport-voice-gm-context",
        "campaign": campaign,
        "counts": {
            "entities": len(entities),
            "private_entities": sum(bool(item.get("is_private")) for item in entities),
            "posts": sum(len(item.get("posts", [])) for item in entities),
        },
        "entities": entities,
    }


def export(client: KankaClient, output_dir: Path) -> tuple[Path, Path, Path]:
    campaign = client.get_campaign(FOGPORT_CAMPAIGN_ID)
    if int(campaign.get("id") or 0) != FOGPORT_CAMPAIGN_ID or str(campaign.get("name") or "").casefold() != FOGPORT_EXPECTED_NAME.casefold():
        raise KankaError(
            "SAFETY STOP: campaign identity mismatch. "
            f"Expected {FOGPORT_EXPECTED_NAME} ({FOGPORT_CAMPAIGN_ID})."
        )

    raw_entities = client.list_entities(FOGPORT_CAMPAIGN_ID, related=True)
    entities: list[dict[str, Any]] = []
    for raw in raw_entities:
        entity_id = int(raw.get("id") or 0)
        if not entity_id:
            raise KankaError("Kanka returned an entity without a valid generic entity ID.")
        posts = client.list_entity_posts(FOGPORT_CAMPAIGN_ID, entity_id)
        entities.append(normalize_entity(raw, posts))
    entities.sort(key=lambda item: (entity_type(item).casefold(), entity_name(item).casefold(), int(item["id"])))

    generated_at = datetime.now(timezone.utc).isoformat()
    snapshot = build_snapshot(campaign, entities, generated_at)
    markdown = render_markdown(campaign, entities, generated_at)
    snapshot_bytes = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    markdown_bytes = markdown.encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "FOGPORT_KANKA_SYNOPSIS.md"
    snapshot_path = output_dir / "fogport-kanka-snapshot.json"
    instructions_path = output_dir / "START_HERE.txt"
    markdown_path.write_bytes(markdown_bytes)
    snapshot_path.write_bytes(snapshot_bytes)
    instructions_path.write_text(
        "FOGPORT VOICE CHAT — START HERE\n\n"
        "1. Add FOGPORT_KANKA_SYNOPSIS.md to your Fogport ChatGPT Project.\n"
        "2. Start Voice inside that Project.\n"
        "3. Say: Run Fogport using the attached Kanka synopsis as canon. I control Byl.\n\n"
        "The JSON file is an audit copy. Keep this download private: it includes GM secrets.\n",
        encoding="utf-8",
    )
    manifest = {
        "markdown_sha256": hashlib.sha256(markdown_bytes).hexdigest(),
        "snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
    }
    (output_dir / "checksums.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return markdown_path, snapshot_path, instructions_path


def main() -> int:
    load_dotenv(ROOT / ".env")
    output_dir = Path(os.getenv("FOGPORT_VOICE_EXPORT_DIR", str(DEFAULT_OUTPUT_DIR)))
    try:
        client = KankaClient(
            token=os.getenv("KANKA_API_TOKEN", ""),
            base_url=os.getenv("KANKA_API_BASE_URL", "https://api.kanka.io/1.0"),
        )
        markdown_path, snapshot_path, _ = export(client, output_dir)
    except (KankaError, OSError, ValueError) as exc:
        print(f"Kanka Librarian export failed: {exc}", file=sys.stderr)
        return 1

    print("KANKA LIBRARIAN — FOGPORT VOICE BIBLE EXPORT COMPLETE")
    print(f"Campaign lock: {FOGPORT_EXPECTED_NAME} ({FOGPORT_CAMPAIGN_ID})")
    print(f"Synopsis: {markdown_path}")
    print(f"Audit snapshot: {snapshot_path}")
    print("No Kanka data was created, updated, or deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
