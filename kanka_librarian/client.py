"""Small read-only client for the Kanka API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class KankaError(RuntimeError):
    """Raised when Kanka cannot complete a request."""


@dataclass(slots=True)
class KankaClient:
    token: str
    base_url: str = "https://api.kanka.io/1.0"
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        self.token = self.token.strip()
        self.base_url = self.base_url.rstrip("/")
        if not self.token or self.token == "replace_with_your_kanka_token":
            raise KankaError("KANKA_API_TOKEN is missing or still contains the placeholder.")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Kanka-Librarian/0.1",
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise KankaError(f"Could not reach Kanka: {exc}") from exc

        if response.status_code == 401:
            raise KankaError("Kanka rejected the token. Check that it was copied correctly and has not expired.")
        if response.status_code == 429:
            raise KankaError("Kanka's API rate limit was reached. Wait briefly before trying again.")
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

    def list_campaigns(self) -> list[dict[str, Any]]:
        """Return every campaign available to the authenticated Kanka user."""
        campaigns: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = self._get("campaigns", params={"page": page})
            data = payload.get("data", [])
            if not isinstance(data, list):
                raise KankaError("Kanka's campaigns response did not contain a list.")
            campaigns.extend(item for item in data if isinstance(item, dict))

            meta = payload.get("meta", {})
            current_page = int(meta.get("current_page", page)) if isinstance(meta, dict) else page
            last_page = int(meta.get("last_page", current_page)) if isinstance(meta, dict) else current_page
            if current_page >= last_page:
                break
            page = current_page + 1

        return campaigns
