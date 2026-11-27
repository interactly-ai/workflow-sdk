# Pagination

All list methods that return more than a handful of items return an `AsyncPage[T]`
(or `SyncPage[T]` for the synchronous client). The list routes send the rows and the total across
all pages, not the page or size they served, so each list method records the page and size it asked for. Lists the
server pages by cursor return `AsyncCursorPage[T]` / `SyncCursorPage[T]` instead; see [Cursor pages](#cursor-pages).

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
print(page.page_number)   # current page number (1-based)
print(page.size)    # items per page
print(page.pages)   # total number of pages
print(page.items)   # List[T] for the current page only
```

---

## Fetching All Pages Automatically

Call `await page.list_all()` to collect every item across all pages into a single
list. Every list method supports it. Use with caution on large datasets.

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

`SyncPage` and `SyncCursorPage` also have `iter_pages()`, which yields each page in turn. The async pages do not;
use the loop above.

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

The newer filters:

- `runs.list(needs_attention=, logical_id=, version_number=)`. `needs_attention=True` selects the runs waiting on a
  person (see [Run control](guides/run_control.md)).
- `simulations.list(logical_id=, selected_workflow_id=, counter_workflow_id=, selected_version_number=,
  counter_version_number=, status=, start=, end=)`. Give `start` and `end` together, at most 31 days apart; one alone
  raises `ValueError`.
- `workflows.list(workflow_type=, logical_id=, categories=, created_by=, favorites=)`. Lists standard workflows unless
  `workflow_type="evaluation"`.
- `workflows.versions.list_active(search=, favorites=, categories=, created_by=, logical_id=, workflow_type=)`.
- `nodes.list()` and `edges.list()`: `logical_id=`, `version_number=`.
- `tools.list(logical_id=, name=, category=)`.
- `webhooks.list_events(search=)`.

The SDK offers only the filters the server reads. Several lists accept `start` and `end` on the server but ignore
them, so those lists take no dates.

Filter parameters vary by resource — see [api_async.md](api_async.md) for the full
parameter list for each `list` method.

---

## Page Object API

| Method / Attribute | Description |
|--------------------|-------------|
| `page.items` | `List[T]` — items on the current page. |
| `page.total` | `int` — total record count across all pages. |
| `page.page_number` | `int` — current 1-based page number. |
| `page.size` | `int` — items per page. |
| `page.pages` | `int` — total page count. |
| `page.has_next_page` | `bool` — whether more pages exist. |
| `await page.next_page()` | Fetch the next `AsyncPage[T]`; raises `NoMorePagesError` on the last page. |
| `await page.list_all()` | Collect all remaining pages into a flat `List[T]`. |
| `async for item in page` | Iterate items on the current page only. |
| `page.iter_pages()` | Sync pages only: yield this page and each following page. |

---

## Cursor pages

A run's pauses, signals and external jobs (`list_pauses`, `list_signals`, `list_external_jobs`) are paged by cursor:
the server sends no total, and the next page is the one `after` this page's last row. They come back as
`SyncCursorPage[T]` / `AsyncCursorPage[T]`, which iterate and collect like the pages above:

```python
page = await client.runs.list_pauses(run_id, limit=100)
async for pause in page:          # this page only
    ...
everything = await page.list_all()  # every page
```

| Method / Attribute | Description |
|--------------------|-------------|
| `page.items` | `List[T]` — rows on the current page. |
| `page.limit` | `int` — the most rows a page holds. |
| `page.next_after` | `str` — the cursor of the next page (this page's last row id); `None` on an empty page. |
| `page.has_next_page` | `bool` — `True` when this page is full. A full page may be followed by an empty one. |
| `await page.next_page()` | Fetch the next page; raises `NoMorePagesError` on the last page. |
| `await page.list_all()` | Collect every page into a flat `List[T]`. |

There is no `total`, `page` or `pages`. `iter_pages()` is on the sync cursor pages only.

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

for page in client.workflows.list(size=100).iter_pages():
    for workflow in page:
        print(workflow.id)
```

---

## See also

- [Run control](guides/run_control.md) — the cursor-paged pauses, signals and external jobs of a run
- [Simulations](guides/simulations.md) — simulation lists and their filters

---

## Gotchas

- **Async pages have no `iter_pages()`.** Loop with `has_next_page` and `await page.next_page()`, as in
  [Manual Pagination](#manual-pagination).
- **Rows written at the same moment can repeat or go missing.** On some lists the server orders rows by a timestamp
  alone, so rows written together (a workflow's nodes, for instance) can repeat on one page and be missing from the
  next. If that matters, compare rows by `id` and dedupe.
