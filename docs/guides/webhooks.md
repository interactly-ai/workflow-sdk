# Webhooks

Configure outbound webhooks to notify your systems when workflow events occur. Also receive and verify webhook payloads in your own endpoint.

## Setup

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # await client.webhooks.<...> calls go here
```

The examples below assume a `client` bound this way. Every call is awaited. Prefer
`AsyncWorkflowClient` — a synchronous `WorkflowClient` mirrors the same API and is shown at
the end.

## Create a webhook subscription

Subscribe to one or more event types and configure delivery parameters.

```python
from interactly.types.webhooks.webhook import WebhookAction

subscription = await client.webhooks.create(
    name="My Workflow Alerts",
    url="https://my-server.example.com/webhook",
    actions=[
        WebhookAction.RUN_COMPLETED,
        WebhookAction.RUN_FAILED,
    ],
    enabled=True,
    bearer_token="Bearer xyz...",  # optional: sent in Authorization header
    timeout_seconds=10,
    max_retries=3,
    retry_backoff_seconds=10,
)

print(f"Created webhook: {subscription.id}")
```

**Parameters:**
- `name`: Display name for the webhook.
- `url`: HTTPS endpoint that will receive POST requests.
- `actions`: List of event types (use `WebhookAction` enum values).
- `enabled`: Whether the webhook is active (default `True`).
- `bearer_token`: Optional bearer token sent in the `Authorization` header.
- `timeout_seconds`: Delivery timeout (1–60, default 10).
- `max_retries`: Max retry attempts (0–10, default 3).
- `retry_backoff_seconds`: Delay between retries (1–300, default 10).

**Returns:**
A `WebhookSubscription` object with `id`, `url`, `actions`, and delivery settings.

## List webhook subscriptions

```python
page = await client.webhooks.list(
    page=1,
    size=20,
    search="alerts",  # optional: fuzzy filter on name/URL
    enabled=True,  # optional: filter by enabled state
    action=WebhookAction.RUN_COMPLETED,  # optional: filter by action
)

async for webhook in page:
    print(f"{webhook.id}: {webhook.url} ({webhook.actions})")

# Iterate through all pages
for webhook in await page.list_all():
    print(webhook.id)
```

**Parameters:**
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).
- `search`: Fuzzy filter on name or URL.
- `enabled`: Filter by enabled state.
- `action`: Filter to webhooks subscribed to a specific action.

**Returns:**
An `AsyncPage` (or `SyncPage` on the synchronous client) of `WebhookSubscription` objects.

## Get a single webhook

The server does not expose a single-item GET route; `get()` walks the paginated list:

```python
webhook = await client.webhooks.get("webhook_id_123")

print(f"URL: {webhook.url}")
print(f"Actions: {webhook.actions}")
```

**Parameters:**
- `webhook_id`: ObjectId of the webhook.

**Returns:**
A `WebhookSubscription` object.

**Raises:**
`NotFoundError` if the webhook does not exist.

## Update a webhook subscription

Partially update a webhook. Only provided fields are changed.

```python
updated = await client.webhooks.update(
    "webhook_id_123",
    enabled=False,
    url="https://my-new-server.example.com/webhook",
    timeout_seconds=20,
)

print(f"Updated: {updated.url}")
```

**Parameters:**
- `webhook_id`: The webhook to update.
- `name`: New display name (optional).
- `url`: New target URL (optional).
- `actions`: Replace the full list of subscribed actions (optional).
- `enabled`: Enable or disable the webhook (optional).
- `bearer_token`: Set a new bearer token (optional).
- `clear_bearer_token`: Set to `True` to remove the existing bearer token (optional).
- `timeout_seconds`: New delivery timeout (optional).
- `max_retries`: New retry limit (optional).
- `retry_backoff_seconds`: New retry delay (optional).

**Returns:**
The updated `WebhookSubscription`.

## Delete a webhook subscription

```python
await client.webhooks.delete("webhook_id_123")
print("Webhook deleted")
```

**Parameters:**
- `webhook_id`: ObjectId of the webhook to delete.

**Returns:**
`None` on success.

## List webhook events

View the delivery history of webhook events.

```python
events_page = await client.webhooks.list_events(
    page=1,
    size=20,
    subscription_id="webhook_id_123",  # optional: filter by subscription
    workflow_id="workflow_456",  # optional: filter by workflow
    action=WebhookAction.RUN_COMPLETED,  # optional: filter by action
    status="delivered",  # optional: "pending", "delivered", "failed"
)

async for event in events_page:
    print(f"{event.id}: {event.action} → {event.status}")

# Paginate through all events
for event in await events_page.list_all():
    print(event.id)
```

**Parameters:**
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).
- `subscription_id`: Filter by a specific subscription (optional).
- `workflow_id`: Filter by a specific workflow (optional).
- `action`: Filter by event action type (optional).
- `status`: Filter by delivery status (optional).

**Returns:**
An `AsyncPage` (or `SyncPage` on the synchronous client) of `WebhookEvent` objects, newest first.

## List delivery attempts for an event

Inspect all delivery attempts (retries) for a single event.

```python
attempts_page = await client.webhooks.list_delivery_attempts(
    event_id="event_id_123",
    page=1,
    size=20,
)

async for attempt in attempts_page:
    print(f"Attempt {attempt.attempt_number}: HTTP {attempt.status_code}")
    print(f"  Tried at: {attempt.attempted_at}")
```

**Parameters:**
- `event_id`: The external event ID (from `WebhookEvent.event_id`).
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).

**Returns:**
An `AsyncPage` (or `SyncPage` on the synchronous client) of `WebhookDeliveryAttempt` objects, newest first.

## Retry a failed event

Manually re-queue a failed or pending event for immediate delivery.

```python
result = await client.webhooks.retry_event("event_id_123")

print(f"Retry triggered: {result}")
```

**Parameters:**
- `event_id`: ObjectId of the webhook event document (`_id` field, not the `event_id` string). Obtain it from `list_events()`.

**Returns:**
A dict with `message` and `event_id`.

**Raises:**
`NotFoundError` if the event does not exist or belongs to a different team.

## Receiving webhooks with signature verification

When the Interactly server sends a webhook to your endpoint, it signs the request with HMAC-SHA256. Verify the signature to ensure the payload came from Interactly.

### Signature headers

Interactly sends these headers with every webhook POST:

- `X-Interactly-Signature`: HMAC-SHA256 hex digest of the raw request body.
- `X-Interactly-Timestamp`: Unix timestamp in seconds (for replay protection).

### Verify the signature

```python
from interactly.webhooks import verify_signature, WebhookVerificationError

payload = await request.body()
signature = request.headers.get("X-Interactly-Signature")
timestamp = request.headers.get("X-Interactly-Timestamp")

try:
    verify_signature(
        payload=payload,
        secret="whsec_your_webhook_secret_from_dashboard",
        signature_header=signature,
        timestamp_header=timestamp,
        max_age_seconds=300,  # reject payloads older than 5 minutes
    )
except WebhookVerificationError as e:
    # Signature is invalid or payload is too old
    return {"error": str(e)}, 400
```

**Parameters:**
- `payload`: Raw request body bytes.
- `secret`: Your webhook signing secret (from the Interactly dashboard).
- `signature_header`: Value of the `X-Interactly-Signature` header.
- `timestamp_header`: Value of the `X-Interactly-Timestamp` header (optional, but recommended for replay protection).
- `max_age_seconds`: Reject payloads older than this (default 300 seconds). Only applied if `timestamp_header` is provided.

**Raises:**
`WebhookVerificationError` if the signature is absent, malformed, doesn't match, or the payload is too old.

### Full FastAPI receiver example

See the complete working example at `../../wf_examples/webhook_receiver.py`:

```python
from fastapi import FastAPI, HTTPException, Request
import json
from interactly import AsyncWorkflowClient
from interactly.webhooks import verify_signature, WebhookVerificationError

app = FastAPI()
client = AsyncWorkflowClient()

WEBHOOK_SECRET = "whsec_your_secret"

@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Interactly-Signature")
    timestamp = request.headers.get("X-Interactly-Timestamp")

    try:
        verify_signature(
            payload=body,
            secret=WEBHOOK_SECRET,
            signature_header=signature,
            timestamp_header=timestamp,
            max_age_seconds=300,
        )
    except WebhookVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event = json.loads(body)
    event_type = event.get("type")

    # Route to handler
    if event_type == "run.completed":
        await handle_run_completed(event)
    elif event_type == "run.failed":
        await handle_run_failed(event)

    return {"received": True}

async def handle_run_completed(event: dict):
    run_id = event.get("run_id")
    run = await client.runs.get(run_id)
    print(f"Run {run_id} completed with output: {run.output}")

async def handle_run_failed(event: dict):
    run_id = event.get("run_id")
    error = event.get("error")
    print(f"Run {run_id} failed: {error}")
    # Add comment to run
    await client.runs.add_comment(run_id, content=f"Failed: {error}")
```

## Key concepts

### Event types

Common `WebhookAction` values:
- `RUN_COMPLETED`: A workflow run finished (success or failure).
- `RUN_FAILED`: A workflow run errored.
- `WEBHOOK_DELIVERY_FAILED`: Webhook delivery failed after retries.

### Delivery guarantees

- At-least-once delivery: Events may be delivered multiple times (use `event_id` to deduplicate).
- Retries: Failed deliveries are retried with exponential backoff.
- Idempotency: Your endpoint should handle duplicate deliveries gracefully.

### Bearer tokens

If you provide a `bearer_token` when creating a webhook, it is sent as:

```
Authorization: Bearer <bearer_token>
```

Keep the token secret; it's not returned in list/get responses.

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient
from interactly.types.webhooks.webhook import WebhookAction

client = WorkflowClient()

subscription = client.webhooks.create(
    name="My Workflow Alerts",
    url="https://my-server.example.com/webhook",
    actions=[WebhookAction.RUN_COMPLETED, WebhookAction.RUN_FAILED],
)

page = client.webhooks.list(size=20)
for webhook in page:
    print(webhook.id)

client.webhooks.delete("webhook_id_123")
```

`webhooks.verify_signature(...)` is identical on both clients — it does no I/O, so there is
never an `await`.

## See also

- [Webhook receiver example](../../wf_examples/webhook_receiver.py) — full FastAPI integration
- [Webhooks API reference](../api_async.md) — endpoint documentation
- [Event types](../api_async.md) — all available `WebhookAction` values

## Gotchas

- Always verify the signature in your receiver endpoint. A missing or invalid signature means the request did not come from Interactly.
- Return HTTP 2xx for successful deliveries. Any non-2xx status triggers a retry.
- Webhook endpoints should be idempotent. Use the `event_id` to detect and skip duplicate deliveries.
- Store your webhook secret securely (environment variables, secret management tools). Never commit it to version control.
