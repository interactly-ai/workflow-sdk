# Retries and Timeouts

## Automatic Retries

The SDK retries failed requests automatically using **exponential backoff with
jitter**. Retries are attempted for:

| Scenario | Default Behaviour |
|----------|-------------------|
| `429 Too Many Requests` | Retry with backoff, honouring `Retry-After` header if present. |
| `500 / 502 / 503 / 504` server errors | Retry with backoff. |
| `APIConnectionError` (network failure) | Retry immediately, then with backoff. |
| `APITimeoutError` | Retry with backoff. |

All other errors (4xx except 429, `WebhookVerificationError`) are **not** retried.

---

## Configuring Retries

Set `max_retries` at client construction. The default is **2**. Use
`AsyncWorkflowClient` as an async context manager so connections are cleaned up
automatically:

```python
from interactly import AsyncWorkflowClient

# More aggressive retry policy
async with AsyncWorkflowClient(
    api_key=..., team_id=..., user_id=...,
    max_retries=4,
) as client:
    run = await client.runs.execute("wf-123")

# Disable retries entirely (useful for tests)
async with AsyncWorkflowClient(
    api_key=..., team_id=..., user_id=...,
    max_retries=0,
) as client:
    ...
```

---

## Backoff Formula

The delay between retries follows: $d_n = \min(2^n \cdot 0.5, 8) + \text{jitter}$

Where jitter is a random uniform value in `[0, 1)` seconds. This caps at
approximately 8–9 seconds per attempt.

---

## Timeouts

The default timeout is **60 seconds** per request, applied globally:

```python
async with AsyncWorkflowClient(
    api_key=..., team_id=..., user_id=...,
    timeout=90.0,  # seconds — increase for slow LLM-backed endpoints
) as client:
    ...
```

If a request times out, `APITimeoutError` is raised. The SDK retries timed-out
requests automatically (subject to `max_retries`).

---

## Implementing Your Own Retry Loop

If you need custom backoff logic (e.g. exponential with a much longer cap),
disable SDK retries and handle them yourself:

```python
import asyncio
from interactly import AsyncWorkflowClient, RateLimitError, InternalServerError

async def main():
    async with AsyncWorkflowClient(
        api_key=..., team_id=..., user_id=...,
        max_retries=0,   # disable SDK retries
    ) as client:

        async def with_retry(fn, max_attempts=5):
            for attempt in range(max_attempts):
                try:
                    return await fn()
                except (RateLimitError, InternalServerError) as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait = 2 ** attempt
                    print(f"Attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                    await asyncio.sleep(wait)

        run = await with_retry(lambda: client.runs.execute("wf-123"))

asyncio.run(main())
```

---

## Idempotency

The workflow execution endpoint (`POST /v1/workflows/{id}/execute`) is **not
idempotent** — each call creates a new run. If you retry an execute call after a
network failure, you may create duplicate runs. Use `await client.runs.list()` to
check for in-progress or recently completed runs before retrying.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await`
and use `with` instead of `async with`:

```python
from interactly import WorkflowClient

with WorkflowClient(
    api_key=..., team_id=..., user_id=...,
    max_retries=4,
    timeout=90.0,
) as client:
    run = client.runs.execute("wf-123")
    page = client.runs.list()  # check for existing runs before retrying
```
