"""Write-only Kanka adapter locked to one explicitly selected campaign."""

from __future__ import annotations

from typing import Any
import time

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
        response: requests.Response | None = None
        for attempt in range(self.max_rate_limit_retries + 1):
            self._wait_for_rate_limit()
            try:
                response = requests.request(
                    method, url, headers=headers, json=payload, timeout=self.timeout_seconds
                )
                self._last_request_at = time.monotonic()
            except requests.RequestException as exc:
                raise KankaError(f"Could not reach Kanka: {exc}") from exc
            if response.status_code != 429:
                break
            if attempt >= self.max_rate_limit_retries:
                raise KankaError("Kanka's API rate limit remained exhausted.")
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
            time.sleep(delay + 1.0)
        if response is None or not response.ok:
            status = response.status_code if response is not None else "no response"
            detail = response.text[:300] if response is not None else ""
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

    def create_attribute(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/entities/{int(entity_id)}/attributes", payload)

    def create_relation(self, campaign_id: int, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_campaign(campaign_id)
        return self._send("POST", f"campaigns/{campaign_id}/entities/{int(entity_id)}/relations", payload)
