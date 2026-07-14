# Pagination

All list methods that return more than a handful of items return an `AsyncPage[T]`
(or `SyncPage[T]` for the synchronous client). Pages are thin wrappers around the
API's `{items, total, page, size, pages}` envelope.

---

## Iterating a Single Page

`AsyncPage` is directly async-iterable — no need to call `.items` explicitly.
Await the `list` call to get the page, then `async for` over it:

```python
import asyncio
from interactly import AsyncWorkflowClient

async def main():
    async with AsyncWorkflowClient(api_key=..., team_id=..., user_id=...) as client:
        page = await client.workflows.list(page=1, size=20)
        async for workflow in page:
            print(workflow.id, workflow.name)

asyncio.run(main())
```

---

## Inspecting Page Metadata

```python
page = await client.workflows.list(size=10)

print(page.total)   # total matching records across all pages
print(page.page)    # current page number (1-based)
print(page.size)    # items per page
print(page.pages)   # total number of pages
print(page.items)   # List[T] for the current page only
```

---

## Fetching All Pages Automatically

Call `await page.list_all()` to collect every item across all pages into a single
list. Use with caution on large datasets.

```python
page = await client.workflows.list(size=100)
all_workflows = await page.list_all()
print(f"Total: {len(all_workflows)}")
```

---

## Manual Pagination

Fetch pages one at a time using `await page.next_page()`. Guard the call with
`page.has_next_page` — `next_page()` raises `NoMorePagesError` when there are no
more pages:

```python
page = await client.workflows.list(page=1, size=50)

while True:
    async for workflow in page:
        process(workflow)
    if not page.has_next_page:
        break
    page = await page.next_page()
```

---

## Applying Filters

All list methods accept filter parameters that are forwarded as query strings:

```python
from interactly.types.shared import RunStatus

# Filter runs by workflow and status
page = await client.runs.list(
    workflow_id="wf-abc",
    status=RunStatus.COMPLETED,
    size=50,
)
```

Filter parameters vary by resource — see [api_async.md](api_async.md) for the full
parameter list for each `list` method.

---

## Page Object API

| Method / Attribute | Description |
|--------------------|-------------|
| `page.items` | `List[T]` — items on the current page. |
| `page.total` | `int` — total record count across all pages. |
| `page.page` | `int` — current 1-based page number. |
| `page.size` | `int` — items per page. |
| `page.pages` | `int` — total page count. |
| `page.has_next_page` | `bool` — whether more pages exist. |
| `await page.next_page()` | Fetch the next `AsyncPage[T]`; raises `NoMorePagesError` on the last page. |
| `await page.list_all()` | Collect all remaining pages into a flat `List[T]`. |
| `async for item in page` | Iterate items on the current page only. |

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await`
and use `with` instead of `async with`. List methods return a `SyncPage[T]` that
you iterate with a plain `for`, and `list_all()` is a normal method call:

```python
from interactly import WorkflowClient

client = WorkflowClient(api_key=..., team_id=..., user_id=...)

page = client.workflows.list(page=1, size=20)
for workflow in page:
    print(workflow.id, workflow.name)

all_workflows = client.workflows.list(size=100).list_all()
```
