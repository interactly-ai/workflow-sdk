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
│   ├── RequestTooLargeError       # 413 — request body over the server's limit
│   ├── RateLimitError             # 429 — too many requests
│   └── InternalServerError        # 5xx — backend error
├── APIConnectionError             # Network failure (no response)
│   └── APITimeoutError            # Request timed out
├── NoMorePagesError               # Advanced past the last page of a paginator
└── StreamError                    # WebSocket / streaming failure (close code in parentheses)
    ├── StreamPermissionError      # 1008 — caller's role may not run workflows
    ├── StreamServerError          # 1011 — server failed while handling the run
    ├── StreamRejectedError        # 4000 — start frame or configuration refused
    ├── UnrunnableWorkflowError    # 4001, 4002, 4005 — stored workflow cannot run
    ├── ConcurrencyLimitError      # 4003 — too many runs at once
    ├── InvalidStreamInputError    # 4006 — start frame carried client-supplied state
    ├── RerunTokenError            # 4007 — re-run token expired or mismatched
    ├── RunChangedElsewhereError   # 4009 — run paused, resumed or cancelled elsewhere
    ├── TakeBackRefusedError       # 4010 — run could not be taken back
    ├── TakeBackForbiddenError     # 4030 — role below developer, for a take-back
    ├── StreamNotFoundError        # 4040 — workflow or run does not exist
    └── ResumeInputRejectedError   # 4400 — frame carried a resume input

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
| `message` | `str` | The message built from the body. See [Validation Errors](#validation-errors-422). |
| `body` | `Any \| None` | The parsed JSON response body, when there is one. |
| `request_id` | `str \| None` | The `X-Request-Id` response header, if present. |
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

The backend returns `422 Unprocessable Entity` when the request body fails schema validation. `message` names
the failing fields and why. The full error list, or the paths a refusal names, stays on `body`.

`message` is built the same way for every API error:

- A string `detail` is the message. When the body also has an `error` key, the two are joined as `detail: error`.
- When `detail` is a list (FastAPI's validation errors) or a dict, the body's `message` beside it is used, if there
  is one. A `message` that is itself a dict reads as its own `message`, so a refusal naming `field_errors` reads as
  its text. A server message names the fields as a person knows them, such as `Node Name: Input should be a valid
  string; …`.
- With no `message`, a list reads as `field: why` pairs joined by `; `. The `body`, `query` and `path` locations are
  dropped from the field name.
- When the body has both `message` and `error`, they are joined as `message: error`. The `message` names the
  category and `error` names the rule that failed.

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

A workflow import that names a secret path it does not list is refused with the paths on `body`:

```python
async with AsyncWorkflowClient() as client:
    try:
        await client.workflows.import_bundle(bundle)
    except UnprocessableEntityError as e:
        print(e.message)
        print(e.body["field_errors"])   # the paths the refusal names
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

## Request too large (413)

A request body over the server's limit raises `RequestTooLargeError`. A run's signal body and its resume data are
limited to 64 KiB.

```python
from interactly import AsyncWorkflowClient, RequestTooLargeError

async with AsyncWorkflowClient() as client:
    try:
        await client.runs.send_signal(run_id, "approval", large_body)
    except RequestTooLargeError as e:
        print(e.message)   # The signal body is N bytes, over the 65536 byte limit.
```

## Refusals (403) and hidden resources (404)

Some resources are restricted by role. A refused write arrives as `PermissionDeniedError`; servers before
October 2026 reported several of these as a 500, so if you were catching `InternalServerError` around
them, catch `PermissionDeniedError` instead. Codebase-function tools are the main case: every route that
creates, updates, executes, imports or lists one requires an Interactly super-admin.

```python
from interactly import PermissionDeniedError

try:
    await client.tools.codebase_functions()
except PermissionDeniedError:
    ...   # staff-only
```

Reading a restricted resource you are not allowed to see is a **`NotFoundError`, not a 403**. The server
answers exactly as it would for an id that does not exist, so a refusal does not confirm that the
resource is there. That applies to a codebase-function tool fetched by a non-staff role, and to copilot
conversation runs.

A date window wider than 31 days on `runs.list()` is a `BadRequestError` whose message says so:
`"Date range should be less than or equal to 31 days"`.

---

## Streaming Errors

A run socket closed with code 1000 ends iteration. Any other close raises a `StreamError` subclass named for
the close code. A code the SDK does not map raises plain `StreamError`, with `code` and `reason` set. The full
table is in [Streaming → close codes](streaming.md#close-codes-and-errors).

Every `StreamError` carries `code`, `reason` and `server_message`. `server_message` is the full message of the
`workflow_error` frame the server sent before closing, or `None`. A close reason holds only 123 bytes, so read
`server_message` when the reason looks cut off.

```python
from interactly import (
    AsyncWorkflowClient,
    InvalidStreamInputError,
    RerunTokenError,
    StreamError,
    StreamPermissionError,
)

async with AsyncWorkflowClient() as client:
    try:
        async with client.runs.stream(workflow_id=wf_id, rerun_token=token) as events:
            async for event in events:
                ...
    except InvalidStreamInputError:
        ...   # close 4006: the frame carried initial_state; use a rerun token instead
    except RerunTokenError:
        ...   # close 4007: expired, or minted for a different workflow or version
    except StreamPermissionError:
        ...   # close 1008: a viewer; running a workflow needs developer access
    except StreamError as exc:
        print(exc.code, exc.server_message or exc.reason)
```

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

Run control is the exception to the 503 rule. On `pause`, `resume`, `cancel` and `send_signal`, a 409 that carries
`Retry-After` is retried within `max_retries`, and a 503 is raised at once as `InternalServerError`.

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

---

## See also

- [Streaming](streaming.md) — the run socket's close codes and the turn protocol
- [Run control](guides/run_control.md) — pausing, resuming and signalling durable runs
- [Companion threads](guides/companion_threads.md#the-four-graph-rules) — the graph rules behind 400s

## Gotchas

- **`body` is not always a dict.** Check `isinstance(e.body, dict)` before indexing it. When it is not a dict,
  `message` reads as the HTTP reason phrase.
- **`message` is a summary.** For the full error list, read `e.body`.
- **A viewer's stream raises `StreamPermissionError` (1008), not `PermissionDeniedError`.** The latter is a REST
  refusal. A take-back by a role below developer raises `TakeBackForbiddenError` (4030).
- **A `workflow_error` does not always end the run.** A node failure the server tolerated (`fatal: false`) ends the
  turn, and the socket stays open; `is_terminal()` is False for it. When the workflow's error limits end the run,
  iteration raises `StreamServerError` (1011). See [Streaming](streaming.md#gotchas).
- **A refusal met while sending is raised by iteration**, not by `send()`.
