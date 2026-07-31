"""The one shared Kanka HTTP toolbox for every publish script.

Before this module existed, each script carried its own copy of these
helpers. The copies drifted apart and none of them handled Kanka's
30-requests-per-minute limit, so busy runs died with HTTP 429. Every
call made through this module is automatically paced and retried by
kanka_librarian.pacing.

Behaviour promises kept from the old copies:
- Failures raise SystemExit with the same style of message.
- headers() sends no Content-Type by default, so multipart image
  uploads made directly by scripts keep working.
- all_pages() always asks for 100 records per page, the Kanka maximum,
  so large campaigns need as few requests as possible.
"""

from __future__ import annotations

from typing import Any, Iterable

import requests

from .pacing import install_api_pacing

install_api_pacing()

BASE_URL = "https://api.kanka.io/1.0"
DEFAULT_TIMEOUT_SECONDS = 120
PAGE_SIZE = 100


def headers(token: str, *, json_body: bool = False) -> dict[str, str]:
    """Standard Kanka headers; add Content-Type only for JSON bodies."""
    built = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Kanka-Librarian/1.1",
    }
    if json_body:
        built["Content-Type"] = "application/json"
    return built


def request(
    token: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """One JSON call to Kanka; paced, retried on 429, SystemExit on failure."""
    response = requests.request(
        method,
        f"{BASE_URL}/{path.lstrip('/')}",
        headers=headers(token, json_body=True),
        json=payload,
        params=params,
        timeout=timeout,
    )
    if not response.ok:
        raise SystemExit(
            f"Kanka {method} {path} returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    body = response.json()
    if not isinstance(body, dict):
        raise SystemExit(f"Kanka {method} {path} returned invalid JSON.")
    return body


def all_pages(
    token: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read every page of a Kanka list, 100 records at a time."""
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        page_params = dict(params or {})
        page_params.update({"page": page, "limit": PAGE_SIZE})
        body = request(token, "GET", path, params=page_params)
        records.extend(x for x in body.get("data", []) if isinstance(x, dict))
        meta = body.get("meta", {})
        if page >= int(meta.get("last_page", page)):
            return records
        page += 1


def exact(
    records: list[dict[str, Any]],
    name: str,
    kind: str = "record",
) -> dict[str, Any] | None:
    """Find at most one record whose name matches exactly (ignoring case)."""
    wanted = name.strip().casefold()
    matches = [
        record
        for record in records
        if str(record.get("name", "")).strip().casefold() == wanted
    ]
    if len(matches) > 1:
        raise SystemExit(f"Multiple {kind} records named {name!r}; refusing to guess.")
    return matches[0] if matches else None


def exact_one(
    records: list[dict[str, Any]],
    names: Iterable[str],
    kind: str,
) -> dict[str, Any]:
    """Find exactly one record matching any of the given names, or stop."""
    folded = {name.casefold() for name in names}
    matches = [
        record
        for record in records
        if str(record.get("name", "")).strip().casefold() in folded
    ]
    if len(matches) != 1:
        found = [str(record.get("name")) for record in matches]
        raise SystemExit(
            f"Expected exactly one {kind} named one of {tuple(names)!r}; found {found!r}."
        )
    return matches[0]
