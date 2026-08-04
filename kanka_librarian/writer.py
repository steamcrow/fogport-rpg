"""Write-only Kanka adapter locked to one explicitly selected campaign."""

from __future__ import annotations

from typing import Any

import requests

from .client import KankaClient, KankaError

SECTION_ENDPOINTS = {
    "locations": "locations",
    "characters": "characters",
    "organizations": "organisations",
    "creatures": "creatures",
    "peoples": "races",
    "families": "families",
    "journals": "journals",
    "notes": "notes",
    "events": "events",
    "items": "items",
    "quests": "quests",
}


class KankaWriter(KankaClient):
    """Create and update entities in exactly one campaign; exposes no delete."""

    def __init__(self, *, token: str, expected_campaign_id: int, **kwargs: Any) -> None:
        super().__init__(token=token, **kwargs)
        self.expected_campaign_id = int(expected_campaign_id)

    def _assert_campaign(self, campaign_id: int) -> None:
        if int(campaign_id) != self.expected_campaign_id:
            raise KankaError(
                f"Cross-campaign write blocked: writer is locked to "
                f"{self.expected_campaign_id}, received {campaign_id}."
            )

    def _send(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Kanka-Librarian/0.6",
        }
        try:
            response = requests.request(
                method, url, headers=headers, json=payload, timeout=self.timeout_seconds
            )
        except requests.RequestException as exc:
            raise KankaError(f"Could not reach Kanka: {exc}") from exc

        if not response.ok:
            status = response.status_code
            detail = response.text[:300]
            raise KankaError(f"Kanka write failed ({status}): {detail}")
        body = response.json()
        data = body.get("data")
        if not isinstance(data, dict):
            raise KankaError("Kanka write response did not contain an object.")
        return data

    @staticmethod
    def _endpoint(section: str) -> str:
        try:
            return SECTION_ENDPOINTS[section]
        except KeyError as exc:
            raise KankaError(f"Unsupported Kanka section: {section}") from exc

    def create_entity(self, campaign_id: int, section: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/{self._endpoint(section)}", payload)

    def update_entity(self, campaign_id: int, section: str, kanka_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("PATCH", f"campaigns/{campaign_id}/{self._endpoint(section)}/{int(kanka_id)}", payload)

    def create_post(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/entities/{int(entity_id)}/posts", payload)

    def update_post(
        self,
        campaign_id: int,
        entity_id: int,
        post_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send(
            "PATCH",
            f"campaigns/{campaign_id}/entities/{int(entity_id)}/posts/{int(post_id)}",
            payload,
        )

    def create_attribute(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/entities/{int(entity_id)}/attributes", payload)

    def create_relation(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/entities/{int(entity_id)}/relations", payload)

    def create_calendar(self, campaign_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/calendars", payload)

    def update_calendar(
        self, campaign_id: int, calendar_id: int, payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send(
            "PATCH", f"campaigns/{campaign_id}/calendars/{int(calendar_id)}", payload
        )

    def create_entity_reminder(
        self, campaign_id: int, entity_id: int, payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send(
            "POST", f"campaigns/{campaign_id}/entities/{int(entity_id)}/reminders", payload
        )

    def update_entity_reminder(
        self,
        campaign_id: int,
        entity_id: int,
        reminder_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send(
            "PATCH",
            f"campaigns/{campaign_id}/entities/{int(entity_id)}/reminders/{int(reminder_id)}",
            payload,
        )
