"""
SDK-wide constants. Never import these directly — use the client's configuration
attributes or the DEFAULT_* module-level names.
"""

import httpx

# --------------------------------------------------------------------------- #
# Networking defaults                                                          #
# --------------------------------------------------------------------------- #

# Default base URL for the Workflow Service.
# Override via INTERACTLY_BASE_URL env var or the client's `base_url` argument.
DEFAULT_BASE_URL: str = "http://localhost:8611"

# Default request timeout (seconds). Applied as (connect=5, read=60, write=10, pool=5).
DEFAULT_TIMEOUT: httpx.Timeout = httpx.Timeout(timeout=60.0, connect=5.0)

# Number of automatic retries on transient server errors before raising.
DEFAULT_MAX_RETRIES: int = 2

# HTTP status codes that are safe to retry.
RETRY_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# --------------------------------------------------------------------------- #
# API versioning                                                               #
# --------------------------------------------------------------------------- #

# The backend API version this SDK release targets.
# Sent as `X-Interactly-API-Version` on every request so the server can route
# to the right response schema even after future breaking changes.
API_VERSION: str = "2026-04-01"

# --------------------------------------------------------------------------- #
# Environment variable names                                                   #
# --------------------------------------------------------------------------- #

ENV_API_KEY: str = "INTERACTLY_API_KEY"
ENV_TEAM_ID: str = "INTERACTLY_TEAM_ID"
ENV_USER_ID: str = "INTERACTLY_USER_ID"
ENV_BASE_URL: str = "INTERACTLY_BASE_URL"
ENV_MAX_RETRIES: str = "INTERACTLY_MAX_RETRIES"
ENV_TIMEOUT: str = "INTERACTLY_TIMEOUT"
ENV_LOG_LEVEL: str = "INTERACTLY_LOG"
