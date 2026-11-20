"""
Response models for workflow webhook subscriptions, events, and delivery attempts.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, Union

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = [
    "WebhookAction",
    "WebhookEventStatus",
    "WebhookSubscription",
    "WebhookEvent",
    "WebhookDeliveryAttempt",
]


class WebhookAction(str, Enum):
    """Events that can trigger a webhook delivery."""

    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_UPDATED = "workflow_updated"
    WORKFLOW_DELETED = "workflow_deleted"
    WORKFLOW_RUN_STARTED = "workflow_run_started"
    WORKFLOW_RUN_COMPLETED = "workflow_run_completed"
    WORKFLOW_RUN_PAUSED = "workflow_run_paused"
    WORKFLOW_RUN_RESUMED = "workflow_run_resumed"


#: An action as the server sends it: a ``WebhookAction`` when this SDK knows the value, else the plain string. The
#: server adds actions over time, and an SDK that refused to parse a subscription or an event naming one it doesn't
#: know would break the moment someone subscribed to it. Known values stay ``WebhookAction`` members (tried first);
#: both compare equal to the string, so ``action == WebhookAction.WORKFLOW_RUN_PAUSED`` works either way.
ParsedWebhookAction = Annotated[Union[WebhookAction, str], Field(union_mode="left_to_right")]


class WebhookEventStatus(str, Enum):
    """Delivery status of a webhook event."""

    PENDING = "pending"
    RETRYING = "retrying"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookSubscription(BaseAPIModel):
    """A configured outbound webhook subscription for the team."""

    id: str
    name: str
    url: str
    actions: List[ParsedWebhookAction]
    enabled: bool
    has_bearer_token: bool
    timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: int


class WebhookEvent(BaseAPIModel):
    """A single webhook event dispatched for a subscription."""

    id: Optional[str] = None
    event_id: str
    subscription_id: str
    action: ParsedWebhookAction
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    workflow_run_id: Optional[str] = None
    workflow_run_status: Optional[str] = None
    payload: Dict[str, Any] = {}
    status: WebhookEventStatus
    attempts_count: int = 0
    delivered_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    last_status_code: Optional[int] = None
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WebhookDeliveryAttempt(BaseAPIModel):
    """A single delivery attempt for a webhook event."""

    id: Optional[str] = None
    event_id: str
    subscription_id: str
    attempt_number: int
    action: ParsedWebhookAction
    request_url: str
    success: bool
    response_status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: Optional[str] = None
