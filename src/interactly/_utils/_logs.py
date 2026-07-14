"""
SDK structured logging.

Set the log level via the INTERACTLY_LOG environment variable:
    INTERACTLY_LOG=debug   → detailed request/response tracing
    INTERACTLY_LOG=info    → request/response summary lines
    (unset)                → no SDK logging output

Usage inside the SDK:
    from interactly._utils._logs import logger
    logger.debug("Sending request", extra={"url": url, "method": method})
"""

from __future__ import annotations

import logging
import os
import sys

from interactly._constants import ENV_LOG_LEVEL

__all__ = ["logger", "setup_logging"]

_VALID_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _get_level_from_env() -> int | None:
    raw = os.getenv(ENV_LOG_LEVEL, "").lower().strip()
    if not raw:
        return None
    level = _VALID_LEVELS.get(raw)
    if level is None:
        raise ValueError(
            f"Invalid value for {ENV_LOG_LEVEL!r}: {raw!r}. "
            f"Must be one of: {', '.join(_VALID_LEVELS)}"
        )
    return level


def setup_logging() -> logging.Logger:
    log = logging.getLogger("interactly")
    level = _get_level_from_env()
    if level is not None:
        log.setLevel(level)
        if not log.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
            log.addHandler(handler)
    return log


logger: logging.Logger = setup_logging()
