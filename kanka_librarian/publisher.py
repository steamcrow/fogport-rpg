"""Apply an explicitly approved Kanka proposal in dependency-safe passes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Protocol

MAELSTROS_CAMPAIGN_ID = 29474
PROTECTED_FOGPORT_CAMPAIGN_ID = 410879


class PublishError(ValueError):
    """Raised before a proposal can make unsafe or unapproved writes."""


class EntityWriter(Protocol):
    def create_entity(
        self, campaign_id: int, section: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...

    def update_entity(
        self,
        campaign_id: int,
        section: str,
        kanka_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


def proposal_digest(proposal: dict[str, Any]) -> str:
    """Hash the exact proposal content, excluding its approval envelope."""
    unsigned = deepcopy(proposal)
    unsigned.pop("approval", None)
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def approve_proposal(
    proposal: dict[str, Any],
    *,
    approved_by: str,
    approved_at: str | None = None,
) -> dict[str, Any]:
    """Return a signed-by-digest approval envelope for human-reviewed content."""
    approved = deepcopy(proposal)
    approved["approval"] = {
        "status": "approved",
        "approved_by": approved_by,
        "approved_at": approved_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "proposal_sha256": proposal_digest(proposal),
    }
    return approved


def validate_approved_proposal(proposal: dict[str, Any]) -> None:
    """Reject the batch unless its content and approval are internally exact."""
    if proposal.get("mode") != "proposal-only":
        raise PublishError("Only proposal-only documents can be approved.")
    if proposal.get("campaign_id") != MAELSTROS_CAMPAIGN_ID:
        raise PublishError("Publisher is hard-locked to MAELSTROS campaign 29474.")
    if proposal.get("campaign_id") == PROTECTED_FOGPORT_CAMPAIGN_ID:
        raise PublishError("Fogport campaign 410879 is protected.")
    if proposal.get("approval_questions"):
        raise PublishError("Approval questions must be resolved before publishing.")

    approval = proposal.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise PublishError("An explicit approval envelope is required.")
    if not str(approval.get("approved_by") or "").strip():
        raise PublishError("Approval must identify who approved the batch.")
    if approval.get("proposal_sha256") != proposal_digest(proposal):
        raise PublishError("Proposal changed after approval; approval is invalid.")

    proposals = proposal.get("proposals")
    if not isinstance(proposals, list):
        raise PublishError("Proposal list is missing.")
    seen_temp_ids: set[str] = set()
    for change in proposals:
        action = change.get("action")
        if action not in {"create", "update"}:
            raise PublishError("Only create and update actions are supported; deletes are forbidden.")
        if change.get("blocked"):
            raise PublishError("Blocked changes cannot be published.")
        temp_id = str(change.get("temp_id") or "")
        if not temp_id or temp_id in seen_temp_ids:
            raise PublishError("Every change needs a unique temp_id.")
        seen_temp_ids.add(temp_id)
        if action == "update" and not change.get("kanka_id"):
            raise PublishError(f"Update {temp_id} is missing its Kanka resource id.")


def _render_entry(
    change: dict[str, Any], created_ids: dict[str, dict[str, int]]
) -> str:
    rendered = str(change.get("entry") or "")
    for reference in change.get("resolved_references", []):
        phrase = str(reference.get("phrase") or reference.get("name") or "")
        if not phrase:
            continue
        entity_id = reference.get("entity_id")
        if reference.get("status") == "pending_create":
            ids = created_ids.get(str(reference.get("temp_id") or ""))
            entity_id = ids and ids["entity_id"]
        if not entity_id:
            raise PublishError(f"Reference {phrase!r} has no real Kanka entity id.")
        rendered = re.sub(
            rf"(?<!\[entity:)\b{re.escape(phrase)}\b",
            lambda _: f"[entity:{entity_id}|{phrase}]",
            rendered,
            count=1,
            flags=re.IGNORECASE,
        )
    return rendered


def _payload(
    change: dict[str, Any],
    created_ids: dict[str, dict[str, int]],
    *,
    include_entry: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": str(change["name"])}
    for key in ("type", "is_private", "tags"):
        if key in change:
            payload[key] = change[key]
    fields = change.get("fields", {})
    if fields:
        if not isinstance(fields, dict):
            raise PublishError("change.fields must be an object.")
        payload.update(fields)
    parent_temp_id = change.get("parent_temp_id")
    if parent_temp_id:
        parent = created_ids.get(str(parent_temp_id))
        if not parent:
            raise PublishError(f"Parent {parent_temp_id} was not created first.")
        payload["parent_id"] = parent["entity_id"]
    if include_entry:
        payload["entry"] = _render_entry(change, created_ids)
    return payload


def apply_approved_proposal(
    proposal: dict[str, Any],
    writer: EntityWriter,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """Create shells first, then publish linked body copy and updates."""
    validate_approved_proposal(proposal)
    changes = {str(item["temp_id"]): item for item in proposal["proposals"]}
    create_order = [str(item) for item in proposal.get("create_order", [])]
    creates = [key for key, value in changes.items() if value["action"] == "create"]
    if set(create_order) != set(creates):
        raise PublishError("create_order must contain every create exactly once.")

    summary = {
        "campaign_id": MAELSTROS_CAMPAIGN_ID,
        "execute": execute,
        "creates_planned": len(creates),
        "updates_planned": sum(
            item["action"] == "update" for item in changes.values()
        ),
        "created": [],
        "updated": [],
        "kanka_writes_performed": False,
    }
    if not execute:
        return summary

    created_ids: dict[str, dict[str, int]] = {}
    for temp_id in create_order:
        change = changes[temp_id]
        result = writer.create_entity(
            MAELSTROS_CAMPAIGN_ID,
            str(change["section"]),
            _payload(change, created_ids, include_entry=False),
        )
        if not result.get("id") or not result.get("entity_id"):
            raise PublishError(f"Kanka did not return both ids for {temp_id}.")
        created_ids[temp_id] = {
            "id": int(result["id"]),
            "entity_id": int(result["entity_id"]),
        }
        summary["created"].append(
            {"temp_id": temp_id, "id": result["id"], "entity_id": result["entity_id"]}
        )

    for temp_id in create_order:
        change = changes[temp_id]
        writer.update_entity(
            MAELSTROS_CAMPAIGN_ID,
            str(change["section"]),
            created_ids[temp_id]["id"],
            _payload(change, created_ids, include_entry=True),
        )

    for temp_id, change in changes.items():
        if change["action"] != "update":
            continue
        writer.update_entity(
            MAELSTROS_CAMPAIGN_ID,
            str(change["section"]),
            int(change["kanka_id"]),
            _payload(change, created_ids, include_entry=True),
        )
        summary["updated"].append({"temp_id": temp_id, "id": int(change["kanka_id"])})

    summary["kanka_writes_performed"] = True
    return summary
