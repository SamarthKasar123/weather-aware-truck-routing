"""Shared HTTP session for third-party providers (retries + timeouts)."""
from __future__ import annotations

import threading

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT_S = 25


class ProviderError(Exception):
    """An upstream API failed or returned something unusable (HTTP 502)."""


class InputError(Exception):
    """The request can't be fulfilled because of the user's input (HTTP 400)."""


_local = threading.local()


def session() -> requests.Session:
    """One pooled session per thread (requests.Session isn't thread-safe)."""
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,  # hand back the final response so we can explain it
        )
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
        s.headers["User-Agent"] = settings.HTTP_USER_AGENT
        _local.session = s
    return s


def get_json(url: str, params: dict | None = None, provider: str = "provider"):
    try:
        resp = session().get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
    except requests.RequestException as exc:
        raise ProviderError(f"{provider} is unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code == 429:
        raise ProviderError(f"{provider} is rate-limiting requests (free tier). Please retry in a minute.")
    if resp.status_code >= 500:
        raise ProviderError(f"{provider} returned HTTP {resp.status_code}")
    try:
        return resp.status_code, resp.json()
    except ValueError as exc:
        raise ProviderError(f"{provider} returned invalid JSON") from exc
