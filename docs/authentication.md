# Authentication

The SDK uses three required header credentials on every request:

| Header | Description |
|--------|-------------|
| `Authorization: Bearer <api_key>` | Your API key. |
| `teamid: <team_id>` | Your team's UUID. |
| `uuid: <user_id>` | The caller's user UUID. |

All three values are passed once at client construction time and automatically
attached to every subsequent request.

---

## Constructing the Client

`AsyncWorkflowClient` is the recommended entry point. Use it as an async context
manager so connections are cleaned up automatically:

```python
import asyncio
from interactly import AsyncWorkflowClient

async def main():
    async with AsyncWorkflowClient(
        api_key="ik-live-...",      # obtain from the Interactly dashboard
        team_id="team-...",
        user_id="user-...",
    ) as client:
        workflow = await client.workflows.get("wf-123")
        print(workflow.name)

asyncio.run(main())
```

You can also instantiate the client directly and call `await client.close()`
when you're done instead of using `async with`.

### Environment Variables (recommended)

Instead of hardcoding credentials, read them from environment variables. Each
constructor argument falls back to its matching `INTERACTLY_*` variable when
omitted, so you can construct the client with no arguments at all:

```python
import asyncio
from interactly import AsyncWorkflowClient

async def main():
    # api_key, team_id, and user_id are read from INTERACTLY_API_KEY,
    # INTERACTLY_TEAM_ID, and INTERACTLY_USER_ID respectively.
    async with AsyncWorkflowClient() as client:
        workflow = await client.workflows.get("wf-123")
        print(workflow.name)

asyncio.run(main())
```

Set those variables in your shell or `.env` file:

```bash
export INTERACTLY_API_KEY="ik-live-..."
export INTERACTLY_TEAM_ID="team-..."
export INTERACTLY_USER_ID="user-..."
```

### Base URL Override

For local development or staging environments, override the base URL (this also
falls back to the `INTERACTLY_BASE_URL` environment variable):

```python
async with AsyncWorkflowClient(
    base_url="http://localhost:8611",   # your local Interactly server
) as client:
    ...
```

---

## Security Notes

- Never commit credentials to source control. Use environment variables or a
  secrets manager (AWS SSM, HashiCorp Vault, etc.).
- API keys are long-lived bearer tokens. Rotate them periodically via the
  Interactly dashboard.
- All requests are made over HTTPS. The base URL must use `https://` in
  production.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient

# api_key, team_id, and user_id fall back to the INTERACTLY_* env vars.
with WorkflowClient() as client:
    workflow = client.workflows.get("wf-123")
    print(workflow.name)
```
