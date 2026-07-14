"""
WorkflowWebhooksResource — CRUD for outbound webhook subscriptions plus event history.

Endpoints:
    POST   /v1/workflow-webhooks                                     → create
    GET    /v1/workflow-webhooks                                     → list
    (no single-item GET route)                                       → get (client-side via list)
    PATCH  /v1/workflow-webhooks/{id}                                → update
    DELETE /v1/workflow-webhooks/{id}                                → delete
    GET    /v1/workflow-webhooks/events                              → list_events
    GET    /v1/workflow-webhooks/events/{event_id}/attempts          → list_delivery_attempts
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx

from interactly._exceptions import NotFoundError
from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly.types.webhooks.webhook import (
    WebhookAction,
    WebhookDeliveryAttempt,
    WebhookEvent,
    WebhookEventStatus,
    WebhookSubscription,
)
from interactly._types import NOT_GIVEN, NotGivenOr

if TYPE_CHECKING:
    pass

__all__ = ["WorkflowWebhooksResource", "AsyncWorkflowWebhooksResource"]

_PATH = "/v1/workflow-webhooks"


def _webhook_not_found(webhook_id: str) -> NotFoundError:
    """Build a client-side ``NotFoundError`` for a missing webhook.

    The server has no single-item GET route, so ``get()`` resolves via
    ``list()``.  When no match is found we synthesise a 404-style error so
    callers can still catch :class:`NotFoundError` uniformly.
    """
    request = httpx.Request("GET", f"{_PATH}/{webhook_id}")
    response = httpx.Response(status_code=404, request=request)
    return NotFoundError(
        message=f"No webhook subscription found with id {webhook_id!r}",
        status_code=404,
        body=None,
        request=request,
        response=response,
    )


class WorkflowWebhooksResource(SyncAPIResource):
    """Synchronous interface to the Workflow Webhooks API."""

    def create(
        self,
        *,
        name: str,
        url: str,
        actions: List[WebhookAction],
        enabled: bool = True,
        bearer_token: Optional[str] = None,
        timeout_seconds: int = 10,
        max_retries: int = 3,
        retry_backoff_seconds: int = 10,
    ) -> WebhookSubscription:
        """
        Create a new outbound webhook subscription.

        Args:
            name:                  Display name for the webhook.
            url:                   Endpoint that will receive POST requests.
            actions:               List of event types that trigger delivery.
            enabled:               Whether the webhook is active (default True).
            bearer_token:          Optional bearer token sent in the ``Authorization`` header.
            timeout_seconds:       Delivery timeout in seconds (1–60, default 10).
            max_retries:           Maximum delivery retry attempts (0–10, default 3).
            retry_backoff_seconds: Delay between retries in seconds (1–300, default 10).

        Returns:
            The newly created :class:`WebhookSubscription`.
        """
        body: Dict[str, Any] = {
            "name": name,
            "url": url,
            "actions": [a.value if isinstance(a, WebhookAction) else a for a in actions],
            "enabled": enabled,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "retry_backoff_seconds": retry_backoff_seconds,
        }
        if bearer_token is not None:
            body["bearer_token"] = bearer_token
        return self._client.post(_PATH, body=body, cast_to=WebhookSubscription)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        enabled: Optional[bool] = None,
        action: Optional[WebhookAction] = None,
    ) -> SyncPage[WebhookSubscription]:
        """
        List webhook subscriptions for the team.

        Args:
            page:    Page number (1-indexed, default 1).
            size:    Items per page (default 20).
            search:  Fuzzy filter on name or URL.
            enabled: Filter by enabled state.
            action:  Filter to webhooks subscribed to a specific action.

        Returns:
            A :class:`SyncPage` of :class:`WebhookSubscription` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if enabled is not None:
            params["enabled"] = enabled
        if action is not None:
            params["action"] = action.value if isinstance(action, WebhookAction) else action
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, WebhookSubscription, lambda p: self.list(page=p, size=size, search=search, enabled=enabled, action=action))

    def get(self, webhook_id: str) -> WebhookSubscription:
        """
        Retrieve a single webhook subscription by ID.

        The server does not expose a single-item GET route, so this walks the
        paginated ``list()`` results and returns the matching subscription.

        Args:
            webhook_id: ObjectId of the webhook.

        Returns:
            The :class:`WebhookSubscription`.

        Raises:
            NotFoundError: If no webhook with the given ID exists.
        """
        for webhook in self.list().list_all():
            if webhook.id == webhook_id:
                return webhook
        raise _webhook_not_found(webhook_id)

    def update(
        self,
        webhook_id: str,
        *,
        name: NotGivenOr[Optional[str]] = NOT_GIVEN,
        url: NotGivenOr[Optional[str]] = NOT_GIVEN,
        actions: NotGivenOr[Optional[List[WebhookAction]]] = NOT_GIVEN,
        enabled: NotGivenOr[Optional[bool]] = NOT_GIVEN,
        bearer_token: NotGivenOr[Optional[str]] = NOT_GIVEN,
        clear_bearer_token: NotGivenOr[bool] = NOT_GIVEN,
        timeout_seconds: NotGivenOr[Optional[int]] = NOT_GIVEN,
        max_retries: NotGivenOr[Optional[int]] = NOT_GIVEN,
        retry_backoff_seconds: NotGivenOr[Optional[int]] = NOT_GIVEN,
    ) -> WebhookSubscription:
        """
        Partially update a webhook subscription.

        Only provided fields are changed; omitted fields retain their current values.

        Args:
            webhook_id:            The webhook to update.
            name:                  New display name.
            url:                   New target URL.
            actions:               Replace the full list of subscribed actions.
            enabled:               Enable or disable the webhook.
            bearer_token:          Set a new bearer token.
            clear_bearer_token:    Set to ``True`` to remove the existing bearer token.
            timeout_seconds:       New delivery timeout.
            max_retries:           New retry limit.
            retry_backoff_seconds: New retry delay.

        Returns:
            The updated :class:`WebhookSubscription`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(name):
            body["name"] = name
        if is_given(url):
            body["url"] = url
        if is_given(actions):
            body["actions"] = (
                [a.value if isinstance(a, WebhookAction) else a for a in actions] if actions is not None else None
            )
        if is_given(enabled):
            body["enabled"] = enabled
        if is_given(bearer_token):
            body["bearer_token"] = bearer_token
        if is_given(clear_bearer_token):
            body["clear_bearer_token"] = clear_bearer_token
        if is_given(timeout_seconds):
            body["timeout_seconds"] = timeout_seconds
        if is_given(max_retries):
            body["max_retries"] = max_retries
        if is_given(retry_backoff_seconds):
            body["retry_backoff_seconds"] = retry_backoff_seconds
        return self._client.patch(f"{_PATH}/{webhook_id}", body=body, cast_to=WebhookSubscription)

    def delete(self, webhook_id: str) -> None:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: ObjectId of the webhook to delete.
        """
        self._client.delete(f"{_PATH}/{webhook_id}", cast_to=type(None))

    def list_events(
        self,
        *,
        page: int = 1,
        size: int = 20,
        subscription_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        action: Optional[WebhookAction] = None,
        status: Optional[WebhookEventStatus] = None,
    ) -> SyncPage[WebhookEvent]:
        """
        List webhook delivery events for the team.

        Args:
            page:            Page number (1-indexed, default 1).
            size:            Items per page (default 20).
            subscription_id: Filter by a specific subscription.
            workflow_id:     Filter by a specific workflow.
            action:          Filter by event action type.
            status:          Filter by delivery status.

        Returns:
            A :class:`SyncPage` of :class:`WebhookEvent` objects, newest first.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if subscription_id is not None:
            params["subscription_id"] = subscription_id
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        if action is not None:
            params["action"] = action.value if isinstance(action, WebhookAction) else action
        if status is not None:
            params["status"] = status.value if isinstance(status, WebhookEventStatus) else status
        raw = self._client.get(f"{_PATH}/events", cast_to=dict, params=params)
        items = [WebhookEvent.model_validate(e) for e in raw.get("events", [])]
        total = raw.get("total", len(items))

        def _next_page(p: int) -> "SyncPage[WebhookEvent]":
            return self.list_events(
                page=p, size=size, subscription_id=subscription_id,
                workflow_id=workflow_id, action=action, status=status,
            )

        return SyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            WebhookEvent,
            _next_page,
        )

    def list_delivery_attempts(
        self,
        event_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> SyncPage[WebhookDeliveryAttempt]:
        """
        List delivery attempts for a single webhook event.

        Args:
            event_id: The external event ID (``event_id`` field on :class:`WebhookEvent`).
            page:     Page number (1-indexed, default 1).
            size:     Items per page (default 20).

        Returns:
            A :class:`SyncPage` of :class:`WebhookDeliveryAttempt` objects, newest first.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = self._client.get(f"{_PATH}/events/{event_id}/attempts", cast_to=dict, params=params)
        items = [WebhookDeliveryAttempt.model_validate(a) for a in raw.get("attempts", [])]
        total = raw.get("total", len(items))
        return SyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            WebhookDeliveryAttempt,
            lambda p: self.list_delivery_attempts(event_id, page=p, size=size),
        )

    def retry_event(self, event_id: str) -> Dict[str, str]:
        """
        Retry delivery of a failed or pending webhook event.

        Resets the event's status to ``pending`` and re-dispatches it
        immediately.  Use this to recover from transient delivery failures
        without waiting for the automatic retry schedule.

        Args:
            event_id: The ObjectId of the webhook event document
                      (the ``_id`` / doc-level ID, not the ``event_id`` string
                      field).  Obtain it from :meth:`list_events`.

        Returns:
            A dict with ``message`` and ``event_id``.

        Raises:
            NotFoundError: If the event does not exist or belongs to a
                           different team.
        """
        return self._client.post(f"{_PATH}/events/{event_id}/retry", body={}, cast_to=dict)


class AsyncWorkflowWebhooksResource(AsyncAPIResource):
    """Asynchronous interface to the Workflow Webhooks API."""

    async def create(
        self,
        *,
        name: str,
        url: str,
        actions: List[WebhookAction],
        enabled: bool = True,
        bearer_token: Optional[str] = None,
        timeout_seconds: int = 10,
        max_retries: int = 3,
        retry_backoff_seconds: int = 10,
    ) -> WebhookSubscription:
        """Create a new outbound webhook subscription."""
        body: Dict[str, Any] = {
            "name": name,
            "url": url,
            "actions": [a.value if isinstance(a, WebhookAction) else a for a in actions],
            "enabled": enabled,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "retry_backoff_seconds": retry_backoff_seconds,
        }
        if bearer_token is not None:
            body["bearer_token"] = bearer_token
        return await self._client.post(_PATH, body=body, cast_to=WebhookSubscription)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        enabled: Optional[bool] = None,
        action: Optional[WebhookAction] = None,
    ) -> AsyncPage[WebhookSubscription]:
        """List webhook subscriptions for the team."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if enabled is not None:
            params["enabled"] = enabled
        if action is not None:
            params["action"] = action.value if isinstance(action, WebhookAction) else action
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, WebhookSubscription, lambda p: self.list(page=p, size=size, search=search, enabled=enabled, action=action))

    async def get(self, webhook_id: str) -> WebhookSubscription:
        """Retrieve a single webhook subscription by ID.

        The server does not expose a single-item GET route, so this walks the
        paginated ``list()`` results and returns the matching subscription.
        """
        page = await self.list()
        for webhook in await page.list_all():
            if webhook.id == webhook_id:
                return webhook
        raise _webhook_not_found(webhook_id)

    async def update(
        self,
        webhook_id: str,
        *,
        name: NotGivenOr[Optional[str]] = NOT_GIVEN,
        url: NotGivenOr[Optional[str]] = NOT_GIVEN,
        actions: NotGivenOr[Optional[List[WebhookAction]]] = NOT_GIVEN,
        enabled: NotGivenOr[Optional[bool]] = NOT_GIVEN,
        bearer_token: NotGivenOr[Optional[str]] = NOT_GIVEN,
        clear_bearer_token: NotGivenOr[bool] = NOT_GIVEN,
        timeout_seconds: NotGivenOr[Optional[int]] = NOT_GIVEN,
        max_retries: NotGivenOr[Optional[int]] = NOT_GIVEN,
        retry_backoff_seconds: NotGivenOr[Optional[int]] = NOT_GIVEN,
    ) -> WebhookSubscription:
        """Partially update a webhook subscription."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(name):
            body["name"] = name
        if is_given(url):
            body["url"] = url
        if is_given(actions):
            body["actions"] = (
                [a.value if isinstance(a, WebhookAction) else a for a in actions] if actions is not None else None
            )
        if is_given(enabled):
            body["enabled"] = enabled
        if is_given(bearer_token):
            body["bearer_token"] = bearer_token
        if is_given(clear_bearer_token):
            body["clear_bearer_token"] = clear_bearer_token
        if is_given(timeout_seconds):
            body["timeout_seconds"] = timeout_seconds
        if is_given(max_retries):
            body["max_retries"] = max_retries
        if is_given(retry_backoff_seconds):
            body["retry_backoff_seconds"] = retry_backoff_seconds
        return await self._client.patch(f"{_PATH}/{webhook_id}", body=body, cast_to=WebhookSubscription)

    async def delete(self, webhook_id: str) -> None:
        """Delete a webhook subscription."""
        await self._client.delete(f"{_PATH}/{webhook_id}", cast_to=type(None))

    async def list_events(
        self,
        *,
        page: int = 1,
        size: int = 20,
        subscription_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        action: Optional[WebhookAction] = None,
        status: Optional[WebhookEventStatus] = None,
    ) -> AsyncPage[WebhookEvent]:
        """List webhook delivery events for the team."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if subscription_id is not None:
            params["subscription_id"] = subscription_id
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        if action is not None:
            params["action"] = action.value if isinstance(action, WebhookAction) else action
        if status is not None:
            params["status"] = status.value if isinstance(status, WebhookEventStatus) else status
        raw = await self._client.get(f"{_PATH}/events", cast_to=dict, params=params)
        items = [WebhookEvent.model_validate(e) for e in raw.get("events", [])]
        total = raw.get("total", len(items))

        def _next_page(p: int) -> "AsyncPage[WebhookEvent]":
            return self.list_events(
                page=p, size=size, subscription_id=subscription_id,
                workflow_id=workflow_id, action=action, status=status,
            )

        return AsyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            WebhookEvent,
            _next_page,
        )

    async def list_delivery_attempts(
        self,
        event_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> AsyncPage[WebhookDeliveryAttempt]:
        """List delivery attempts for a single webhook event."""
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = await self._client.get(f"{_PATH}/events/{event_id}/attempts", cast_to=dict, params=params)
        items = [WebhookDeliveryAttempt.model_validate(a) for a in raw.get("attempts", [])]
        total = raw.get("total", len(items))
        return AsyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            WebhookDeliveryAttempt,
            lambda p: self.list_delivery_attempts(event_id, page=p, size=size),
        )

    async def retry_event(self, event_id: str) -> Dict[str, str]:
        """Retry delivery of a failed or pending webhook event."""
        return await self._client.post(f"{_PATH}/events/{event_id}/retry", body={}, cast_to=dict)
