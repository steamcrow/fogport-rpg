"""Build reviewable, read-only Kanka change proposals from normalized note findings."""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from typing import Any
import re
import unicodedata

ENTITY_SECTIONS = (
    "locations", "characters", "organizations", "creatures", "peoples",
    "families", "journals", "events", "items", "quests",
)


class ProposalError(ValueError):
    """Raised when proposed changes are unsafe or internally inconsistent."""


def normalize_name(value: str) -> str:
    """Normalize entity names for duplicate detection without fuzzy guessing."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def build_registry(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Index snapshot entities by normalized name while retaining all collisions."""
    registry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in ENTITY_SECTIONS:
        for entity in snapshot.get(section, []):
            if not isinstance(entity, dict) or not entity.get("name"):
                continue
            registry[normalize_name(str(entity["name"]))].append({
                "name": entity["name"],
                "entity_id": entity.get("entity_id"),
                "section": section,
            })
    return dict(registry)


def _candidate_matches(
    registry: dict[str, list[dict[str, Any]]],
    name: str,
    section: str | None,
) -> list[dict[str, Any]]:
    matches = registry.get(normalize_name(name), [])
    if section:
        matches = [item for item in matches if item["section"] == section]
    return matches


def _topological_create_order(changes: list[dict[str, Any]]) -> list[str]:
    creates = {
        str(change["temp_id"]): change
        for change in changes
        if change.get("action") == "create"
    }
    indegree = {temp_id: 0 for temp_id in creates}
    children: dict[str, list[str]] = defaultdict(list)

    for temp_id, change in creates.items():
        parent = change.get("parent_temp_id")
        if parent is None:
            continue
        parent = str(parent)
        if parent not in creates:
            raise ProposalError(f"{temp_id} refers to missing parent_temp_id {parent}.")
        indegree[temp_id] += 1
        children[parent].append(temp_id)

    queue = deque(sorted(key for key, count in indegree.items() if count == 0))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(creates):
        raise ProposalError("New-entity dependencies contain a cycle.")
    return ordered


def render_existing_mentions(
    text: str,
    resolved_references: list[dict[str, Any]],
) -> str:
    """Render only references that already have real Kanka IDs."""
    rendered = text
    for reference in resolved_references:
        if reference.get("status") != "existing":
            continue
        entity_id = reference.get("entity_id")
        phrase = str(reference.get("phrase") or reference.get("name") or "")
        if not entity_id or not phrase:
            continue
        syntax = f"[entity:{entity_id}|{phrase}]"
        rendered = re.sub(
            rf"(?<!\[entity:)\b{re.escape(phrase)}\b",
            lambda _: syntax,
            rendered,
            count=1,
            flags=re.IGNORECASE,
        )
    return rendered


def build_proposal(
    snapshot: dict[str, Any],
    findings: dict[str, Any],
) -> dict[str, Any]:
    """Compare normalized findings with a snapshot and produce an approval plan."""
    registry = build_registry(snapshot)
    changes = deepcopy(findings.get("changes", []))
    if not isinstance(changes, list):
        raise ProposalError("findings.changes must be a list.")

    create_order = _topological_create_order(changes)
    proposed_names: dict[str, list[dict[str, str]]] = defaultdict(list)
    for change in changes:
        if change.get("action") != "create":
            continue
        name = str(change.get("name") or "").strip()
        section = str(change.get("section") or "").strip()
        temp_id = str(change.get("temp_id") or "").strip()
        if not name or section not in ENTITY_SECTIONS or not temp_id:
            raise ProposalError("Every create needs temp_id, name, and a supported section.")
        proposed_names[normalize_name(name)].append({
            "name": name, "section": section, "temp_id": temp_id,
        })

    proposals: list[dict[str, Any]] = []
    approval_questions: list[dict[str, Any]] = []

    for change in changes:
        proposal = deepcopy(change)
        references_out: list[dict[str, Any]] = []
        for reference in change.get("references", []):
            name = str(reference.get("name") or "").strip()
            section = reference.get("section")
            phrase = str(reference.get("phrase") or name)
            existing = _candidate_matches(registry, name, section)
            pending = [
                item for item in proposed_names.get(normalize_name(name), [])
                if not section or item["section"] == section
            ]

            result = {"name": name, "phrase": phrase, "section": section}
            candidates = existing + pending
            if len(candidates) == 1 and existing:
                result.update(status="existing", **existing[0])
            elif len(candidates) == 1 and pending:
                result.update(status="pending_create", **pending[0])
            elif len(candidates) > 1:
                result.update(status="ambiguous", candidates=candidates)
                approval_questions.append({
                    "change": change.get("temp_id"),
                    "reference": name,
                    "reason": "multiple_exact_matches",
                    "candidates": candidates,
                })
            else:
                result["status"] = "unresolved"
                approval_questions.append({
                    "change": change.get("temp_id"),
                    "reference": name,
                    "reason": "no_exact_match_or_approved_create",
                })
            references_out.append(result)

        proposal["resolved_references"] = references_out
        proposal["rendered_entry"] = render_existing_mentions(
            str(change.get("entry") or ""), references_out
        )
        proposal["blocked"] = any(
            item["status"] in {"ambiguous", "unresolved"}
            for item in references_out
        )
        proposals.append(proposal)

    return {
        "schema_version": 1,
        "mode": "proposal-only",
        "campaign_id": snapshot.get("campaign", {}).get("id"),
        "create_order": create_order,
        "proposals": proposals,
        "approval_questions": approval_questions,
        "kanka_writes_performed": False,
    }
