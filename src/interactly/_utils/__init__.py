"""
Public surface of the _utils sub-package.

Only symbols exported from here are considered part of the stable internal API.
"""

from interactly._utils._logs import logger, setup_logging
from interactly._utils._retry import backoff_delay, should_retry, with_retry, with_retry_async
from interactly._utils._serialise import serialise_config
from interactly._utils._transform import build_body, strip_not_given
from interactly._utils._typing import NOT_GIVEN, NotGiven, NotGivenOr, is_given

__all__ = [
    # Logging
    "logger",
    "setup_logging",
    # Retry
    "should_retry",
    "backoff_delay",
    "with_retry",
    "with_retry_async",
    # Serialisation
    "serialise_config",
    # Transform
    "strip_not_given",
    "build_body",
    # NOT_GIVEN
    "NOT_GIVEN",
    "NotGiven",
    "NotGivenOr",
    "is_given",
]
