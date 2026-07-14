# Versioning and Compatibility

## Workflow Versioning

Every workflow has one or more immutable **versions**. A version is a named snapshot
of the workflow's configuration (nodes, edges, prompts, tools). Versions allow you to:

- Roll back to a previous configuration.
- A/B test different workflow designs.
- Pin production traffic to a specific version.

### Creating a Version

```python
import asyncio

from interactly import AsyncWorkflowClient


async def main():
    async with AsyncWorkflowClient(api_key=..., team_id=..., user_id=...) as client:
        version = await client.workflows.versions.create(
            workflow_id="wf-123",
            version_name="v2 — improved intake flow",
        )
        print(version.version_number)  # e.g. 3


asyncio.run(main())
```

The remaining examples all run inside the same `async with AsyncWorkflowClient() as client:`
context.

### Listing Versions

```python
versions = await client.workflows.versions.list("wf-123")
for v in versions:
    print(v.version_number, v.version_name, v.is_active)
```

### Activating a Version

Only the **active version** is used for new runs. Activate a specific version:

```python
await client.workflows.versions.activate("wf-123", version_number=3)
```

You can also create and activate in one step by passing `mark_as_active=True` to
`create(...)`.

### Running a Specific Version

Pass `version_number` when executing or streaming to target a non-active version:

```python
run = await client.runs.execute(
    workflow_id="wf-123",
    version_number=2,   # run version 2 instead of active
)
```

---

## SDK Versioning

The SDK follows **Semantic Versioning** (`MAJOR.MINOR.PATCH`):

| Increment | When |
|-----------|------|
| `MAJOR` | Breaking change to the public API. |
| `MINOR` | New methods, new optional parameters, new models. Backward compatible. |
| `PATCH` | Bug fixes, documentation updates. No API changes. |

Check the installed version:

```python
import interactly as interactly
print(interactly.__version__)
```

---

## Backward Compatibility Policy

### What is guaranteed stable

- All public method names and signatures in `WorkflowClient` and `AsyncWorkflowClient`.
- All public model class names and field names exposed in `interactly.__init__`.
- All exception class names and their hierarchy.
- The `verify_signature` helper.

### What may change between minor versions

- **New optional parameters** may be added to existing methods. These always have
  defaults so existing callers are unaffected.
- **New response fields** may be added to existing models. Pydantic ignores unknown
  fields by default; your code will not break.
- **New exception subclasses** may be added under `APIError`. Catch the parent
  (`APIError`) for future-proofing.

### What requires a major version bump

- Removing or renaming a method.
- Removing or renaming a model field.
- Changing a parameter from optional to required.
- Changing a return type in a breaking way.

---

## Pinning Dependencies

For production use, pin the SDK to a compatible minor version range in your
`requirements.txt` or `Pipfile`:

```
# requirements.txt
interactly>=0.1.0,<0.2.0  # allow patches, but not breaking minor changes
```

Or in `pyproject.toml`:

```toml
[tool.poetry.dependencies]
interactly = "^0.1.0"
```

---

## Detecting Breaking Changes

The public API surface is tracked in [`api_surface_baseline.json`](../api_surface_baseline.json) at the
SDK root. The generated [API reference](api_async.md) is produced from the live resource classes by
`python wf_examples/internal/gen_api_reference.py`, which writes both `api_async.md` and
`api_sync.md`; run it in `--check` mode to detect drift before releasing:

```bash
# Fails (exit 1) if api_async.md / api_sync.md no longer match the code — i.e. the surface changed.
python wf_examples/internal/gen_api_reference.py --check
```

When the surface changes intentionally, regenerate both references (drop `--check` to rewrite
`api_async.md` and `api_sync.md`, and refresh `api_surface_baseline.json`) and record the change in the
[CHANGELOG](../CHANGELOG.md).

---

## Changelog

All notable changes are documented in [CHANGELOG.md](../CHANGELOG.md), following
the [Keep a Changelog](https://keepachangelog.com/) format.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient

with WorkflowClient(api_key=..., team_id=..., user_id=...) as client:
    version = client.workflows.versions.create(
        workflow_id="wf-123",
        version_name="v2 — improved intake flow",
    )
    client.workflows.versions.activate("wf-123", version_number=version.version_number)
    run = client.runs.execute(workflow_id="wf-123", version_number=2)
```
