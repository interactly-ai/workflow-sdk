"""
Low-level HTTP client infrastructure.

SyncAPIClient and AsyncAPIClient handle:
  - Building request headers (auth, versioning, user-agent).
  - JSON serialisation of request bodies.
  - Retry with exponential backoff.
  - Error translation (status codes → typed exceptions).
  - Exposing a thin interface (get, post, put, patch, delete) consumed by resources.
"""

from __future__ import annotations

import os
from typing import Any, Optional, Type, TypeVar

import httpx

from interactly._constants import (
    API_VERSION,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MAX_RETRIES,
    ENV_TEAM_ID,
    ENV_TIMEOUT,
    ENV_USER_ID,
)
from interactly._exceptions import APIConnectionError, APITimeoutError
from interactly._response import APIResponse
from interactly._utils._logs import logger
from interactly._utils._retry import with_retry, with_retry_async
from interactly._utils._transform import build_body
from interactly._version import __version__

ModelT = TypeVar("ModelT")

__all__ = ["SyncAPIClient", "AsyncAPIClient"]


def _safe_request(exc: httpx.RequestError) -> Optional[httpx.Request]:
    """Return the request bound to an httpx error, or None if unavailable.

    ``httpx.PoolTimeout`` (and some other transport errors) may have no
    associated request; accessing ``.request`` then raises. Guard it so the
    SDK exception carries ``request=None`` rather than blowing up.
    """
    try:
        return exc.request
    except (RuntimeError, AttributeError):
        return None


def _base_url(provided: str | None) -> str:
    url = provided or os.getenv(ENV_BASE_URL) or "http://localhost:8611"
    return url.rstrip("/")


def _build_url(base_url: str, path: str) -> httpx.URL:
    """
    Join ``path`` onto ``base_url`` with proper normalization.

    Uses ``httpx.URL.join`` so that a ``base_url`` carrying its own path prefix
    (e.g. a proxied ``http://host/api``) or a ``path`` missing a leading slash
    does not misroute — unlike naive f-string concatenation.
    """
    base = httpx.URL(base_url if base_url.endswith("/") else base_url + "/")
    return base.join(path.lstrip("/"))


def _resolve_max_retries(max_retries: int | None) -> int:
    """Resolve max retries from the explicit arg, env var, or default.

    Guards the env-var parse so a malformed value falls back to the default
    with a clear warning naming the offending variable instead of raising a
    cryptic ValueError at client construction.
    """
    if max_retries is not None:
        return max_retries
    env_retries = os.getenv(ENV_MAX_RETRIES)
    if not env_retries:
        return DEFAULT_MAX_RETRIES
    try:
        return int(env_retries)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s=%r (expected an integer); falling back to default %d",
            ENV_MAX_RETRIES,
            env_retries,
            DEFAULT_MAX_RETRIES,
        )
        return DEFAULT_MAX_RETRIES


def _resolve_timeout(timeout: float | httpx.Timeout | None) -> httpx.Timeout:
    """Resolve the request timeout from the explicit arg, env var, or default.

    Guards the env-var parse so a malformed value falls back to the default
    with a clear warning naming the offending variable.
    """
    if isinstance(timeout, (int, float)):
        return httpx.Timeout(timeout=float(timeout))
    if isinstance(timeout, httpx.Timeout):
        return timeout
    if timeout is None:
        env_val = os.getenv(ENV_TIMEOUT)
        if not env_val:
            return DEFAULT_TIMEOUT
        try:
            return httpx.Timeout(float(env_val))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid %s=%r (expected a number of seconds); falling back to default",
                ENV_TIMEOUT,
                env_val,
            )
            return DEFAULT_TIMEOUT
    return DEFAULT_TIMEOUT


def _build_headers(
    api_key: str,
    team_id: str,
    user_id: str,
    extra_headers: dict[str, str] | None,
) -> dict[str, str]:
    """Assemble the standard auth + versioning headers for every request."""
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "teamid": team_id,
        "uuid": user_id,
        "X-Interactly-API-Version": API_VERSION,
        "User-Agent": f"interactly-python/{__version__}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _gateway_root_url(base_url: str) -> str:
    """Return the API-gateway root (scheme://host) for ``base_url``.

    The gateway's WebSocket session endpoint (``/v1/session``) lives at the root,
    not under the service path prefix (e.g. ``/workflows``), so strip any path.
    """
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


# --------------------------------------------------------------------------- #
# Synchronous client                                                           #
# --------------------------------------------------------------------------- #

class SyncAPIClient:
    """
    Synchronous HTTP client backed by httpx.

    Args:
        api_key:      Bearer token for authentication. Falls back to INTERACTLY_API_KEY env var.
        team_id:      Team identifier. Falls back to INTERACTLY_TEAM_ID env var.
        user_id:      User identifier. Falls back to INTERACTLY_USER_ID env var.
        base_url:     Override the default server URL. Falls back to INTERACTLY_BASE_URL env var.
        timeout:      Request timeout in seconds or an httpx.Timeout object.
        max_retries:  Retry attempts on transient failures. Falls back to INTERACTLY_MAX_RETRIES env var.
        http_client:  Provide a custom httpx.Client for full transport control (e.g. proxies).
    """

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | None = None,
        http_client: httpx.Client | None = None,
        _extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv(ENV_API_KEY) or ""
        self._team_id = team_id or os.getenv(ENV_TEAM_ID) or ""
        self._user_id = user_id or os.getenv(ENV_USER_ID) or ""
        self._base_url = _base_url(base_url)
        self._extra_headers = _extra_headers

        self._timeout = _resolve_timeout(timeout)
        self._max_retries = _resolve_max_retries(max_retries)

        self._http_client = http_client or httpx.Client(timeout=self._timeout)

    # ---------------------------------------------------------------------- #
    # Auth / headers                                                           #
    # ---------------------------------------------------------------------- #

    def _headers(self) -> dict[str, str]:
        return _build_headers(
            api_key=self._api_key,
            team_id=self._team_id,
            user_id=self._user_id,
            extra_headers=self._extra_headers,
        )

    # ---------------------------------------------------------------------- #
    # WebSocket URL builder                                                    #
    # ---------------------------------------------------------------------- #

    def _ws_base_url(self) -> str:
        """Convert http(s):// → ws(s)://."""
        url = self._base_url
        if url.startswith("https://"):
            return url.replace("https://", "wss://", 1)
        return url.replace("http://", "ws://", 1)

    def ws_headers(self) -> dict[str, str]:
        """Auth headers to attach to WebSocket connections."""
        return _build_headers(
            api_key=self._api_key,
            team_id=self._team_id,
            user_id=self._user_id,
            extra_headers=self._extra_headers,
        )

    def _mint_ws_session_token(self) -> str | None:
        """Mint a single-use WebSocket session token from the gateway.

        The API gateway authenticates WS upgrades via a short-lived ``?token=``
        session (see the gateway's ``wsProxyHandler``), not the bearer JWT.
        Returns ``None`` when no gateway session endpoint is reachable (e.g. a
        direct-to-service deployment), so callers fall back to header auth.
        """
        try:
            resp = self._http_client.get(
                f"{_gateway_root_url(self._base_url)}/v1/session",
                headers=self._headers(),
            )
        except Exception:  # noqa: BLE001 - fall back to header auth on any error
            return None
        if resp.status_code != 200:
            return None
        try:
            return (resp.json().get("data") or {}).get("id")
        except Exception:  # noqa: BLE001
            return None

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        cast_to: Type[ModelT] | None,
    ) -> ModelT:
        url = _build_url(self._base_url, path)
        headers = self._headers()

        def _send() -> httpx.Response:
            # NB: never log json_body — request bodies may carry PII/PHI.
            logger.debug("→ %s %s", method, url, extra={"params": params})
            try:
                return self._http_client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
            except httpx.TimeoutException as exc:
                raise APITimeoutError(
                    message="Request timed out",
                    request=_safe_request(exc),
                ) from exc
            except httpx.ConnectError as exc:
                raise APIConnectionError(
                    message=f"Connection error: {exc}",
                    request=_safe_request(exc),
                ) from exc
            except httpx.RequestError as exc:
                raise APIConnectionError(
                    message=f"Request error: {exc}",
                    request=_safe_request(exc),
                ) from exc

        response = with_retry(_send, self._max_retries, method)
        return APIResponse(http_response=response, cast_to=cast_to).parse()

    # ---------------------------------------------------------------------- #
    # Convenience verbs                                                        #
    # ---------------------------------------------------------------------- #

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return self._request("GET", path, params=params, cast_to=cast_to)

    def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return self._request("POST", path, params=params, json_body=build_body(body), cast_to=cast_to)

    def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return self._request("PUT", path, params=params, json_body=build_body(body), cast_to=cast_to)

    def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return self._request("PATCH", path, params=params, json_body=build_body(body), cast_to=cast_to)

    def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return self._request("DELETE", path, params=params, cast_to=cast_to)

    # ---------------------------------------------------------------------- #
    # Lifecycle                                                                #
    # ---------------------------------------------------------------------- #

    def close(self) -> None:
        """Close the underlying httpx.Client and free connections."""
        self._http_client.close()

    def __enter__(self) -> "SyncAPIClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Asynchronous client                                                          #
# --------------------------------------------------------------------------- #

class AsyncAPIClient:
    """
    Async HTTP client backed by httpx.AsyncClient.
    See SyncAPIClient for parameter documentation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        _extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv(ENV_API_KEY) or ""
        self._team_id = team_id or os.getenv(ENV_TEAM_ID) or ""
        self._user_id = user_id or os.getenv(ENV_USER_ID) or ""
        self._base_url = _base_url(base_url)
        self._extra_headers = _extra_headers

        self._timeout = _resolve_timeout(timeout)
        self._max_retries = _resolve_max_retries(max_retries)

        self._http_client = http_client or httpx.AsyncClient(timeout=self._timeout)

    def _headers(self) -> dict[str, str]:
        return _build_headers(
            api_key=self._api_key,
            team_id=self._team_id,
            user_id=self._user_id,
            extra_headers=self._extra_headers,
        )

    def _ws_base_url(self) -> str:
        url = self._base_url
        if url.startswith("https://"):
            return url.replace("https://", "wss://", 1)
        return url.replace("http://", "ws://", 1)

    def ws_headers(self) -> dict[str, str]:
        return _build_headers(
            api_key=self._api_key,
            team_id=self._team_id,
            user_id=self._user_id,
            extra_headers=self._extra_headers,
        )

    async def _mint_ws_session_token(self) -> str | None:
        """Async variant of :meth:`SyncAPIClient._mint_ws_session_token`."""
        try:
            resp = await self._http_client.get(
                f"{_gateway_root_url(self._base_url)}/v1/session",
                headers=self._headers(),
            )
        except Exception:  # noqa: BLE001 - fall back to header auth on any error
            return None
        if resp.status_code != 200:
            return None
        try:
            return (resp.json().get("data") or {}).get("id")
        except Exception:  # noqa: BLE001
            return None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        cast_to: Type[ModelT] | None,
    ) -> ModelT:
        url = _build_url(self._base_url, path)
        headers = self._headers()

        async def _send() -> httpx.Response:
            # NB: never log json_body — request bodies may carry PII/PHI.
            logger.debug("→ %s %s", method, url, extra={"params": params})
            try:
                return await self._http_client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
            except httpx.TimeoutException as exc:
                raise APITimeoutError(
                    message="Request timed out",
                    request=_safe_request(exc),
                ) from exc
            except httpx.ConnectError as exc:
                raise APIConnectionError(
                    message=f"Connection error: {exc}",
                    request=_safe_request(exc),
                ) from exc
            except httpx.RequestError as exc:
                raise APIConnectionError(
                    message=f"Request error: {exc}",
                    request=_safe_request(exc),
                ) from exc

        response = await with_retry_async(_send, self._max_retries, method)
        return APIResponse(http_response=response, cast_to=cast_to).parse()

    async def get(self, path: str, *, params: dict[str, Any] | None = None, cast_to: Type[ModelT]) -> ModelT:
        return await self._request("GET", path, params=params, cast_to=cast_to)

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return await self._request("POST", path, params=params, json_body=build_body(body), cast_to=cast_to)

    async def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return await self._request("PUT", path, params=params, json_body=build_body(body), cast_to=cast_to)

    async def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return await self._request("PATCH", path, params=params, json_body=build_body(body), cast_to=cast_to)

    async def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        cast_to: Type[ModelT],
    ) -> ModelT:
        return await self._request("DELETE", path, params=params, cast_to=cast_to)

    async def close(self) -> None:
        await self._http_client.aclose()

    async def __aenter__(self) -> "AsyncAPIClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
