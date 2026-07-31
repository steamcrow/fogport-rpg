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
    # Wyvern-subscriber pace: 90 requests/minute allowed, one per 0.7s used.
    minimum_request_interval_seconds: float = 0.7
    max_rate_limit_retries: int = 8
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

        response: requests.Response | None = None
        for attempt in range(self.max_rate_limit_retries + 1):
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

            if response.status_code != 429:
                break

            if attempt >= self.max_rate_limit_retries:
                raise KankaError(
                    "Kanka's API rate limit remained exhausted after "
                    f"{self.max_rate_limit_retries} automatic retries."
                )

            retry_after_header = response.headers.get("Retry-After")
            reset_header = response.headers.get("X-RateLimit-Reset")
            delay_seconds = 60.0

            if retry_after_header:
                try:
                    delay_seconds = max(1.0, float(retry_after_header))
                except ValueError:
                    pass
            elif reset_header:
                try:
                    delay_seconds = max(1.0, float(reset_header) - time.time())
                except ValueError:
                    pass

            # Add a small cushion so the retry does not arrive on the reset boundary.
            time.sleep(delay_seconds + 1.0)

        if response is None:
            raise KankaError("Kanka did not return a response.")
        if response.status_code == 401:
            raise KankaError("Kanka rejected the token. Check that it was copied correctly and has not expired.")
        if response.status_code == 403:
            raise KankaError("Kanka denied access to this campaign or endpoint.")
        if response.status_code == 404:
            raise KankaError("Kanka could not find the requested campaign or entity.")
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

    def _get_all_pages(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Read every page from a Kanka list endpoint."""
        items: list[dict[str, Any]] = []
        page = 1

        while True:
            page_params = dict(params or {})
            page_params["page"] = page
            # Ask for Kanka's maximum page size so big campaigns need
            # far fewer requests (and therefore far less waiting).
            page_params.setdefault("limit", 100)
            payload = self._get(path, params=page_params)
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

    def list_locations(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every location in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/locations", params=params)

    def list_characters(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every character in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/characters", params=params)

    def list_organizations(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every organization in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/organisations", params=params)

    def list_creatures(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every creature in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/creatures", params=params)

    def list_races(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every Kanka race in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/races", params=params)

    def list_families(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every family in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/families", params=params)

    def list_journals(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every journal in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/journals", params=params)

    def list_notes(
        self,
        campaign_id: int,
        *,
        related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every note in one campaign without changing anything."""
        params = {"related": 1} if related else None
        return self._get_all_pages(f"campaigns/{campaign_id}/notes", params=params)

    def list_events(
        self, campaign_id: int, *, related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every event in one campaign without changing anything."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/events",
            params={"related": 1} if related else None,
        )

    def list_calendars(self, campaign_id: int) -> list[dict[str, Any]]:
        """Return every calendar in one campaign without changing anything."""
        return self._get_all_pages(f"campaigns/{campaign_id}/calendars")

    def list_calendar_reminders(
        self, campaign_id: int, calendar_id: int,
    ) -> list[dict[str, Any]]:
        """Return every reminder displayed on one calendar."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/calendars/{int(calendar_id)}/reminders"
        )

    def list_entity_reminders(
        self, campaign_id: int, entity_id: int,
    ) -> list[dict[str, Any]]:
        """Return every calendar reminder attached to one entity."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/entities/{int(entity_id)}/reminders"
        )

    def list_items(
        self, campaign_id: int, *, related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every item in one campaign without changing anything."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/items",
            params={"related": 1} if related else None,
        )

    def list_quests(
        self, campaign_id: int, *, related: bool = False,
    ) -> list[dict[str, Any]]:
        """Return every quest in one campaign without changing anything."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/quests",
            params={"related": 1} if related else None,
        )

    def list_entity_posts(self, campaign_id: int, entity_id: int) -> list[dict[str, Any]]:
        """Return every public and private post attached to one entity."""
        return self._get_all_pages(
            f"campaigns/{campaign_id}/entities/{entity_id}/posts"
        )
