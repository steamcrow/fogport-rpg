"""Automatic pacing and rate-limit retries for every Kanka API call.

Kanka allows roughly 30 requests per minute. The dedicated publish scripts
make dozens of rapid calls while rebuilding the campaign registry, so an
unpaced run trips HTTP 429 and dies. Importing install_api_pacing() from any
script wraps the requests library so that:

1. Consecutive Kanka API calls are spaced at least 2.1 seconds apart.
2. An HTTP 429 answer is retried automatically, honouring Retry-After.

Non-Kanka URLs are left untouched.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

_KANKA_HOST = "api.kanka.io"
# Daniel has a Wyvern subscription: Kanka allows 90 requests/minute,
# so one call every 0.7 seconds stays safely inside the limit. If the
# subscription ever lapses, set KANKA_MIN_INTERVAL_SECONDS=2.1 in the
# workflow environment to return to the free-tier pace.
try:
    _MIN_INTERVAL_SECONDS = max(
        0.0, float(os.environ.get("KANKA_MIN_INTERVAL_SECONDS", "0.7"))
    )
except ValueError:
    _MIN_INTERVAL_SECONDS = 0.7
_MAX_RATE_LIMIT_RETRIES = 8

_last_call_at = 0.0
_installed = False
_original_request = requests.request
_original_api_request = requests.api.request


def _is_kanka(url: Any) -> bool:
    return isinstance(url, str) and _KANKA_HOST in url


def _wait_for_slot() -> None:
    global _last_call_at
    elapsed = time.monotonic() - _last_call_at
    remaining = _MIN_INTERVAL_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)


def _delay_from_headers(response: requests.Response) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass
    reset = response.headers.get("X-RateLimit-Reset")
    if reset:
        try:
            return max(1.0, float(reset) - time.time())
        except ValueError:
            pass
    return 60.0


def _paced_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    global _last_call_at
    if not _is_kanka(url):
        return _original_request(method, url, **kwargs)

    response: requests.Response | None = None
    for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
        _wait_for_slot()
        response = _original_request(method, url, **kwargs)
        _last_call_at = time.monotonic()
        if response.status_code != 429:
            return response
        if attempt >= _MAX_RATE_LIMIT_RETRIES:
            return response
        # Add a one-second cushion so the retry clears the reset boundary.
        time.sleep(_delay_from_headers(response) + 1.0)
    assert response is not None
    return response


def install_api_pacing() -> None:
    """Route every requests call through the paced, retrying wrapper."""
    global _installed
    if _installed:
        return
    _installed = True

    requests.request = _paced_request
    requests.api.request = _paced_request

    def _make_verb(verb: str):
        def call(url: str, **kwargs: Any) -> requests.Response:
            return _paced_request(verb, url, **kwargs)

        return call

    for verb in ("get", "post", "patch", "put", "delete", "head", "options"):
        setattr(requests, verb, _make_verb(verb.upper()))
