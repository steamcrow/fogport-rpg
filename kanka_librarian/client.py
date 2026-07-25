"""Small read-only client for the Kanka API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import time

import requests


class KankaError(RuntimeError):
    """Raised when Kanka cannot complete a request."""


@dataclass(slots=True)
class KankaClient:
    token: str
    base_url: str = "https://api.kanka.io/1.0"
    timeout_seconds: int = 20
    minimum_request_interval_seconds: float = 2.1
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.token = self.token.strip()
        self.base_url = self.base_url.rstrip("/")
        if not self.token or self.token == "replace_with_your_kanka_token":
            raise KankaError("KANKA_API_TOKEN is missing or still contains the placeholder.")

    def _wait_for_rate_limit(self) -> None:
        """Keep requests below Kanka's standard 30-request-per-minute limit."""
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.minimum_request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Kanka-Librarian/0.4",
        }

        self._wait_for_rate_limit()
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
            self._last_request_at = time.monotonic()
        except requests.RequestException as exc:
            raise KankaError(f"Could not reach Kanka: {exc}") from exc

        if response.status_code == 401:
            raise KankaError("Kanka rejected the token. Check that it was copied correctly and has not expired.")
        if response.status_code == 403:
            raise KankaError("Kanka denied access to this campaign or endpoint.")
        if response.status_code == 404:
            raise KankaError("Kanka could not find the requested campaign or entity.")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "a short time")
            raise KankaError(f"Kanka's API rate limit was reached. Retry after {retry_after}.")
        if not response.ok:
            raise KankaError(
                f"Kanka returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise KankaError("Kanka returned a response that was not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise KankaError("Kanka returned an unexpected response shape.")
        return payload

    def _get_all_pages(self, path: str) -> list[dict[str, Any]]:
        """Read every page from a Kanka list endpoint."""
        items: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = self._get(path, params={"page": page})
            data = payload.get("data", [])
            if not isinstance(data, list):
                raise KankaError(f"Kanka's {path} response did not contain a list.")
            items.extend(item for item in data if isinstance(item, dict))

            meta = payload.get("meta", {})
            current_page = int(meta.get("current_page", page)) if isinstance(meta, dict) else page
            last_page = int(meta.get("last_page", current_page)) if isinstance(meta, dict) else current_page
            if current_page >= last_page:
                break
            page = current_page + 1

        return items

    def list_campaigns(self) -> list[dict[str, Any]]:
        """Return every campaign available to the authenticated Kanka user."""
        return self._get_all_pages("campaigns")

    def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        """Return one campaign by ID without changing it."""
        payload = self._get(f"campaigns/{campaign_id}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise KankaError("Kanka's campaign response did not contain an object.")
        return data

    def list_locations(self, campaign_id: int) -> list[dict[str, Any]]:
        """Return every location in one campaign without changing anything."""
        return self._get_all_pages(f"campaigns/{campaign_id}/locations")

    def list_characters(self, campaign_id: int) -> list[dict[str, Any]]:
        """Return every character in one campaign without changing anything."""
        return self._get_all_pages(f"campaigns/{campaign_id}/characters")

    def list_organizations(self, campaign_id: int) -> list[dict[str, Any]]:
        """Return every organization in one campaign without changing anything."""
        return self._get_all_pages(f"campaigns/{campaign_id}/organisations")

    def list_creatures(self, campaign_id: int) -> list[dict[str, Any]]:
        """Return every creature in one campaign without changing anything."""
        return self._get_all_pages(f"campaigns/{campaign_id}/creatures")


    def list_entity_posts(self, campaign_id: int, entity_id: int) -> list[dict[str, Any]]:
        """Return every public and private post attached to one entity."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/entities/{entity_id}/posts"
        )
