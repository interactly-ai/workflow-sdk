# Error Handling

The SDK raises typed exceptions for every failure scenario. Nearly all inherit
from `InteractlyError` (the exception is `WebhookVerificationError`, a standalone
`Exception`), and every exception below can be imported directly from `interactly`.

---

## Exception Hierarchy

```
InteractlyError
├── APIError                       # Any response received from the API
│   ├── BadRequestError            # 400 — request rejected as invalid
│   ├── AuthenticationError        # 401 — invalid or missing credentials
│   ├── PermissionDeniedError      # 403 — caller lacks required permissions
│   ├── NotFoundError              # 404 — resource does not exist
│   ├── ConflictError              # 409 — duplicate / state conflict
│   ├── UnprocessableEntityError   # 422 — request body failed validation
│   ├── RateLimitError             # 429 — too many requests
│   └── InternalServerError        # 5xx — backend error
├── APIConnectionError             # Network failure (no response)
│   └── APITimeoutError            # Request timed out
├── NoMorePagesError               # Advanced past the last page of a paginator
└── StreamError                    # WebSocket / streaming failure
    ├── InvalidStreamInputError    # close 4006 — start frame carried client-supplied state
    └── RerunTokenError            # close 4007 — re-run token expired or mismatched

WebhookVerificationError           # Standalone Exception (not an InteractlyError) — HMAC signature mismatch
```

---

## Basic Error Handling

```python
from interactly import (
    AsyncWorkflowClient,
    NotFoundError,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    InteractlyError,
)

async with AsyncWorkflowClient(api_key=..., team_id=..., user_id=...) as client:
    try:
        workflow = await client.workflows.get("wf-does-not-exist")
    except NotFoundError:
        print("Workflow not found — check the ID.")
    except AuthenticationError:
        print("Invalid API key or team/user ID.")
    except RateLimitError:
        # The SDK retries automatically, but if max_retries is exhausted:
        print("Rate limit exceeded — back off and retry.")
    except APIConnectionError as e:
        print(f"Network error: {e}")
    except InteractlyError as e:
        # Catch-all for any other SDK error
        print(f"Unexpected error: {e}")
```

---

## Inspecting the Response

Every `APIError` exposes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `status_code` | `int` | HTTP status code. |
| `message` | `str \| None` | Error message from the API response body. |
| `body` | `str` | Raw response body text. |
| `request` | `httpx.Request` | The outgoing request that caused the error. |
| `response` | `httpx.Response` | The raw HTTP response. |

```python
from interactly import AsyncWorkflowClient, UnprocessableEntityError

async with AsyncWorkflowClient() as client:
    try:
        await client.workflows.create(name="")  # empty name is invalid
    except UnprocessableEntityError as e:
        print(e.status_code)   # 422
        print(e.message)       # validation detail from the backend
        print(e.body)          # raw JSON body
```

---

## Validation Errors (422)

The backend returns `422 Unprocessable Entity` when the request body fails
schema validation. The `message` attribute will contain a description of the
failing fields.

```python
from interactly import AsyncWorkflowClient, UnprocessableEntityError

async with AsyncWorkflowClient() as client:
    try:
        await client.schedules.create(
            workflow_id="wf-123",
            cron="not-a-cron",   # invalid cron expression
        )
    except UnprocessableEntityError as e:
        print(e.message)
```

---

## Graph Validation Errors (400)

The workflow service rejects a graph that violates one of its structural rules with
`400 Bad Request` — companion-thread layout, evaluate-while-waiting edges, and similar. These arrive as
`BadRequestError`.

Such responses carry **two** strings: `message` names the category, and `error` says which rule
actually failed. The SDK joins both, so the exception tells you what to change rather than only that
something is wrong:

```python
from interactly import AsyncWorkflowClient, BadRequestError

async with AsyncWorkflowClient() as client:
    try:
        await client.workflows.create_from_config(config)
    except BadRequestError as exc:
        print(exc)
        # Invalid 'evaluate while waiting for user input' edge configuration:
        # Edge 'e1' has evaluate_while_waiting_config enabled but its source node also has
        # outgoing direct edges, which take precedence on the normal transition path.

        print(exc.body)   # the raw {"message": ..., "error": ...} dict
```

The rules behind these are documented in
[Companion threads](guides/companion_threads.md#the-four-graph-rules) and
[Evaluate while waiting](guides/waiting_evaluation.md#the-validation-rules).

---

## Streaming Errors

Most WebSocket closures simply end the stream. Two are the server rejecting your start frame, and each
raises a specific subclass of `StreamError`:

```python
from interactly import InvalidStreamInputError, RerunTokenError, StreamError

try:
    async with client.runs.stream(workflow_id=wf_id, rerun_token=token) as events:
        async for event in events:
            ...
except InvalidStreamInputError:
    # close 4006 — the frame carried `initial_state`. A client is never the source of run
    # state; mint a re-run token instead.
    ...
except RerunTokenError:
    # close 4007 — expired, or minted for a different workflow/version. Mint a fresh one.
    ...
except StreamError:
    # anything else: an abnormal closure.
    ...
```

See [Streaming → close codes](streaming.md#close-codes-and-errors).

---

## Conflicts (409)

`ConflictError` covers duplicate creates and state conflicts. One case worth knowing: **feedback on a
run that is still in progress**.

```python
from interactly import ConflictError

try:
    await client.runs.set_turn_rating(run_id, 0, "up")
except ConflictError as exc:
    print(exc)
    # Feedback cannot be left while the run is still in progress.
```

See [Run feedback](guides/run_feedback.md).

---

## Automatic Retries

The SDK automatically retries on:
- `429 RateLimitError` — with exponential backoff + jitter
- `500`, `502`, `503`, `504` `InternalServerError`
- `APIConnectionError` and `APITimeoutError`

Default: **2 retries**. Configurable via `max_retries`:

```python
client = AsyncWorkflowClient(
    ...,
    max_retries=4,   # 0 to disable retries entirely
)
```

Per-request override is not currently supported — set `max_retries=0` on the
client and implement your own retry loop if needed.

---

## Timeouts

The default timeout is **30 seconds** for all operations. Adjust at construction:

```python
client = AsyncWorkflowClient(
    ...,
    timeout=60.0,   # seconds
)
```

A timed-out request raises `APITimeoutError`, which is retried automatically
(subject to `max_retries`).

---

## Webhook Verification Errors

```python
from interactly import verify_signature, WebhookVerificationError

try:
    verify_signature(body, signature_header, secret=WEBHOOK_SECRET)
except WebhookVerificationError as e:
    # Signature mismatch or stale timestamp (> 5 minutes old)
    return 400, str(e)
```

`verify_signature` is a sync-safe helper — it performs no I/O, so there is no
`await` and no async variant. Call it the same way from async and sync code.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient, NotFoundError, InteractlyError

client = WorkflowClient(api_key=..., team_id=..., user_id=...)

try:
    workflow = client.workflows.get("wf-does-not-exist")
except NotFoundError:
    print("Workflow not found — check the ID.")
except InteractlyError as e:
    print(f"Unexpected error: {e}")
```
