# 2. Installation & setup

## Build the environment (recommended)

This SDK is a **self-contained** package — everything it needs lives inside this folder. The docs,
notebooks, and examples are written to read like any published library — `import interactly` /
`import interactly_configs`, with **no `sys.path` hacks** once installed.

The quickest path is to build a virtualenv from the pinned `Pipfile` (Python 3.13), which installs the
SDK's runtime dependencies plus everything the notebooks and examples need:

```bash
PIPENV_VENV_IN_PROJECT=1 pipenv install --dev --python 3.13   # or: make install
```

## Editable install (into your own environment)

Prefer your own virtualenv? Editable-install both the SDK and its typed configs so the short names
resolve like any installed library:

```bash
pip install -e . -e ./configs
```

Then any snippet works from anywhere. The docs lead with the **async** client (the preferred way to
use the SDK — see [house style](03_concepts.md#house-style-async-first-typed-first)):

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...
```

### Running notebooks/examples without installing

If you'd rather not install, a small in-folder bootstrap adds this SDK's `src/` and
`configs/src/` to `sys.path` so the short names still resolve — everything it adds lives inside this
folder:

- **Notebooks** ([`notebooks/`](../notebooks/)): the first cell is `import _bootstrap`.
- **Examples** ([`wf_examples/`](../wf_examples/)): the first line is `import _shared_sdk`
  ([`wf_examples/_shared_sdk.py`](../wf_examples/_shared_sdk.py)).

Run examples directly, e.g. `python wf_examples/wf_example_progression_1.py`.

## The `[configs]` extra (typed authoring)

Authoring workflows with **typed** config classes requires the `interactly_configs` package. It is
**vendored inside this folder** under [`configs/`](../configs/) and importable as `interactly.configs`
(installed automatically by both options above). When consuming a published build of the SDK from PyPI,
it is available via the optional `[configs]` extra:

```bash
pip install "interactly[configs]"
```

**Typed configs are the preferred way to author workflows** — you get autocomplete, validation, and
typed responses. Without them the SDK still works fully — you just pass and receive plain `dict`
configs instead. See [Typed configs](configs.md).

## Streaming

Event streaming uses WebSockets and requires the `websockets` package (already a core dependency).
See [Streaming](streaming.md).

## Credentials

The client reads these environment variables (or accept them as constructor arguments):

| Variable | Purpose | Required |
|---|---|---|
| `INTERACTLY_API_KEY` | Bearer token | yes |
| `INTERACTLY_BASE_URL` | Server URL (e.g. `http://localhost:8611` or your instance) | yes (defaults to localhost:8611) |
| `INTERACTLY_TEAM_ID` | Team scoping header | yes |
| `INTERACTLY_USER_ID` | User scoping header | yes |
| `INTERACTLY_TIMEOUT` | Request timeout in seconds (default 60) | no |
| `INTERACTLY_MAX_RETRIES` | Automatic retry count (default 2) | no |

```bash
export INTERACTLY_API_KEY="…"
export INTERACTLY_BASE_URL="http://localhost:8611"
export INTERACTLY_TEAM_ID="…"
export INTERACTLY_USER_ID="…"
```

```python
from interactly import AsyncWorkflowClient

# From env vars (recommended)
client = AsyncWorkflowClient()

# Or explicitly
client = AsyncWorkflowClient(
    api_key="…",
    base_url="http://localhost:8611",
    team_id="…",
    user_id="…",
    timeout=60,
    max_retries=2,
)
```

**Never hardcode credentials** in committed code. See [Authentication](authentication.md) for header
details and security notes.

## Verify your setup

```python
import asyncio
from interactly import AsyncWorkflowClient

async def check():
    async with AsyncWorkflowClient() as client:
        page = await client.workflows.list(size=1)     # a cheap authenticated call
        print("Connected — team has", page.total, "workflows")

asyncio.run(check())
```

If this raises `AuthenticationError`, check your API key; if it raises `APIConnectionError`, check
`INTERACTLY_BASE_URL`. See [Error handling](error_handling.md).

## Synchronous alternative

Every constructor and method shown above also exists on the synchronous `WorkflowClient` — same
arguments and names, without `async`/`await`:

```python
from interactly import WorkflowClient

with WorkflowClient() as client:
    page = client.workflows.list(size=1)
    print("Connected — team has", page.total, "workflows")
```

---

**Next:** [3. Core concepts →](03_concepts.md)
