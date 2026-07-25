"""Apply an explicitly approved Kanka proposal in dependency-safe passes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Protocol

SUPPORTED_CAMPAIGNS = {
    29474: "MAELSTROS",
    410879: "Fogport",
}


class PublishError(ValueError):
    """Raised before a proposal can make unsafe or unapproved writes."""


class EntityWriter(Protocol):
    def create_entity(self, campaign_id: int, section: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_entity(self, campaign_id: int, section: str, kanka_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def create_post(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def create_attribute(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def create_relation(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...


def proposal_digest(proposal: dict[str, Any]) -> str:
    unsigned = deepcopy(proposal)
    unsigned.pop("approval", None)
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def approve_proposal(proposal: dict[str, Any], *, approved_by: str, approved_at: str | None = None) -> dict[str, Any]:
    approved = deepcopy(proposal)
    approved["approval"] = {
        "status": "approved",
        "approved_by": approved_by,
        "approved_at": approved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "proposal_sha256": proposal_digest(proposal),
    }
    return approved


def validate_approved_proposal(proposal: dict[str, Any]) -> int:
    if proposal.get("mode") != "proposal-only":
        raise PublishError("Only proposal-only documents can be approved.")
    try:
        campaign_id = int(proposal.get("campaign_id"))
    except (TypeError, ValueError) as exc:
        raise PublishError("Proposal is missing a valid campaign_id.") from exc
    if campaign_id not in SUPPORTED_CAMPAIGNS:
        raise PublishError(
            f"Campaign {campaign_id} is not configured. Supported campaigns: "
            + ", ".join(f"{name} ({key})" for key, name in SUPPORTED_CAMPAIGNS.items())
        )
    expected_name = SUPPORTED_CAMPAIGNS[campaign_id]
    supplied_name = str(proposal.get("campaign_name") or "")
    if supplied_name and supplied_name.casefold() != expected_name.casefold():
        raise PublishError(
            f"Campaign identity mismatch: {campaign_id} must be named {expected_name}."
        )
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
        dependents = change.get("posts", []) or change.get("attributes", []) or change.get("relationships", [])
        if action == "update" and dependents and not change.get("entity_id"):
            raise PublishError(f"Update {temp_id} needs its Kanka entity_id for dependent content.")
        for field in ("posts", "attributes", "relationships"):
            if field in change and not isinstance(change[field], list):
                raise PublishError(f"{temp_id}.{field} must be a list.")
    return campaign_id


def _render_entry(change: dict[str, Any], created_ids: dict[str, dict[str, int]]) -> str:
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


def _payload(change: dict[str, Any], created_ids: dict[str, dict[str, int]], *, include_entry: bool) -> dict[str, Any]:
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


def _entity_id(change: dict[str, Any], created_ids: dict[str, dict[str, int]]) -> int:
    if change["action"] == "create":
        return created_ids[str(change["temp_id"])]["entity_id"]
    return int(change["entity_id"])


def _relationship_payload(relationship: dict[str, Any], created_ids: dict[str, dict[str, int]]) -> dict[str, Any]:
    payload = {key: value for key, value in relationship.items() if key != "target_temp_id"}
    target_temp_id = relationship.get("target_temp_id")
    if target_temp_id:
        target = created_ids.get(str(target_temp_id))
        if not target:
            raise PublishError(f"Relationship target {target_temp_id} was not created.")
        payload["target_id"] = target["entity_id"]
    if not payload.get("target_id"):
        raise PublishError("Every relationship needs target_id or target_temp_id.")
    return payload


def apply_approved_proposal(proposal: dict[str, Any], writer: EntityWriter, *, execute: bool = False) -> dict[str, Any]:
    """Create shells, write linked entries, then publish approved dependent content."""
    campaign_id = validate_approved_proposal(proposal)
    changes = {str(item["temp_id"]): item for item in proposal["proposals"]}
    create_order = [str(item) for item in proposal.get("create_order", [])]
    creates = [key for key, value in changes.items() if value["action"] == "create"]
    if set(create_order) != set(creates):
        raise PublishError("create_order must contain every create exactly once.")

    summary = {
        "campaign_id": campaign_id,
        "campaign_name": SUPPORTED_CAMPAIGNS[campaign_id],
        "execute": execute,
        "creates_planned": len(creates),
        "updates_planned": sum(item["action"] == "update" for item in changes.values()),
        "posts_planned": sum(len(item.get("posts", [])) for item in changes.values()),
        "attributes_planned": sum(len(item.get("attributes", [])) for item in changes.values()),
        "relationships_planned": sum(len(item.get("relationships", [])) for item in changes.values()),
        "created": [], "updated": [], "posts_created": [], "attributes_created": [], "relationships_created": [],
        "kanka_writes_performed": False,
    }
    if not execute:
        return summary

    created_ids: dict[str, dict[str, int]] = {}
    for temp_id in create_order:
        change = changes[temp_id]
        result = writer.create_entity(campaign_id, str(change["section"]), _payload(change, created_ids, include_entry=False))
        if not result.get("id") or not result.get("entity_id"):
            raise PublishError(f"Kanka did not return both ids for {temp_id}.")
        created_ids[temp_id] = {"id": int(result["id"]), "entity_id": int(result["entity_id"])}
        summary["created"].append({"temp_id": temp_id, **created_ids[temp_id]})

    for temp_id in create_order:
        change = changes[temp_id]
        writer.update_entity(campaign_id, str(change["section"]), created_ids[temp_id]["id"], _payload(change, created_ids, include_entry=True))
    for temp_id, change in changes.items():
        if change["action"] != "update":
            continue
        writer.update_entity(campaign_id, str(change["section"]), int(change["kanka_id"]), _payload(change, created_ids, include_entry=True))
        summary["updated"].append({"temp_id": temp_id, "id": int(change["kanka_id"])})

    for temp_id, change in changes.items():
        entity_id = _entity_id(change, created_ids)
        for post in change.get("posts", []):
            result = writer.create_post(campaign_id, entity_id, dict(post))
            summary["posts_created"].append({"temp_id": temp_id, "id": result.get("id")})
        for attribute in change.get("attributes", []):
            result = writer.create_attribute(campaign_id, entity_id, dict(attribute))
            summary["attributes_created"].append({"temp_id": temp_id, "id": result.get("id")})
        for relationship in change.get("relationships", []):
            result = writer.create_relation(campaign_id, entity_id, _relationship_payload(relationship, created_ids))
            summary["relationships_created"].append({"temp_id": temp_id, "id": result.get("id")})

    summary["kanka_writes_performed"] = True
    return summary
