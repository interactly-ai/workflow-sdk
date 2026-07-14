"""
TypedDicts for webhook subscription request parameters.
"""

from __future__ import annotations

from typing import List, Optional

from typing_extensions import NotRequired, TypedDict

from interactly.types.webhooks.webhook import WebhookAction

__all__ = ["WebhookCreateParams", "WebhookUpdateParams", "WebhookListParams"]


class WebhookCreateParams(TypedDict, total=False):
    name: str
    url: str
    actions: List[WebhookAction]
    enabled: bool
    bearer_token: Optional[str]
    timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: int


class WebhookUpdateParams(TypedDict, total=False):
    name: NotRequired[Optional[str]]
    url: NotRequired[Optional[str]]
    actions: NotRequired[Optional[List[WebhookAction]]]
    enabled: NotRequired[Optional[bool]]
    bearer_token: NotRequired[Optional[str]]
    clear_bearer_token: NotRequired[bool]
    timeout_seconds: NotRequired[Optional[int]]
    max_retries: NotRequired[Optional[int]]
    retry_backoff_seconds: NotRequired[Optional[int]]


class WebhookListParams(TypedDict, total=False):
    page: int
    size: int
    search: str
    enabled: Optional[bool]
    action: Optional[WebhookAction]
