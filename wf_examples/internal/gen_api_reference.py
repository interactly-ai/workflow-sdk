"""Regenerate ``docs/api_async.md`` and ``docs/api_sync.md`` from the client classes.

Both pages are pure introspection of the resource classes: one row per public method, with its
signature and the first line of its docstring. Keeping them generated is the point — a hand-written
method table drifts the moment a resource gains an endpoint, and the drift is invisible until a
reader tries the call.

Run from the repo root::

    python wf_examples/internal/gen_api_reference.py

Exit code 1 means a resource was added to the client but not to ``SECTIONS`` below. Add it there
(choosing where it belongs in the reading order) rather than letting it be silently omitted.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "src"), str(_ROOT / "configs" / "src")]

from interactly import AsyncWorkflowClient, WorkflowClient  # noqa: E402

#: Resource attribute → heading, in the order a reader should meet them. This is deliberately
#: curated rather than alphabetical: the reference follows the same arc as the guides.
SECTIONS: List[Tuple[str, str]] = [
    ("workflows", "Workflows"),
    ("nodes", "Nodes"),
    ("edges", "Edges"),
    ("tools", "Tools"),
    ("runs", "Runs"),
    ("reruns", "Re-runs"),
    ("schedules", "Schedules"),
    ("webhooks", "Webhooks"),
    ("simulations", "Simulations"),
    ("global_variables", "Global variables"),
    ("super_nodes", "Super nodes"),
    ("node_libraries", "Node libraries"),
    ("templates", "Templates"),
    ("categories", "Categories"),
    ("llm_configs", "LLM configs"),
]

#: Attributes on the client that are not method-table resources.
_NOT_A_RESOURCE = {"runtime"}

_HEADER = """# API reference ({flavour})

> **Generated file — do not edit by hand.** Regenerate with `python wf_examples/internal/gen_api_reference.py`.

{lede}

Construct the client from `INTERACTLY_*` environment variables:

```python
from interactly import {client}

{opener} {client}() as client:
    workflow = {await_}client.workflows.get("wf-123")
```

See the [capability guides](README.md#capability-guides) for runnable examples.
"""

_ASYNC_LEDE = (
    "Every method below is on `AsyncWorkflowClient` — **the preferred way to use the SDK** "
    "(`await` each call). The synchronous surface is identical; see [api_sync.md](api_sync.md)."
)
_SYNC_LEDE = (
    "Every method below is on `WorkflowClient` (the synchronous convenience client). The async "
    "surface is identical and preferred — see [api_async.md](api_async.md)."
)


def _first_docstring_line(func: Any) -> str:
    doc = inspect.getdoc(func) or ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.replace("|", "\\|")
    return ""


def _signature(func: Any) -> str:
    sig = inspect.signature(func)
    params = [p for name, p in sig.parameters.items() if name != "self"]
    rendered = str(sig.replace(parameters=params))
    return rendered.replace("|", "\\|")


def _public_methods(resource: Any) -> List[Tuple[str, Any]]:
    cls = type(resource)
    out = []
    for name, member in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if not (inspect.isfunction(member) or inspect.iscoroutinefunction(member)):
            continue
        out.append((name, member))
    return sorted(out)


def _sub_resources(resource: Any) -> List[Tuple[str, Any]]:
    """Nested resources such as ``client.workflows.versions``."""
    out = []
    for name, value in vars(resource).items():
        if name.startswith("_"):
            continue
        if _public_methods(value):
            out.append((name, value))
    return sorted(out)


def _method_table(resource: Any) -> str:
    rows = [
        f"| `{name}` | `{_signature(func)}` | {_first_docstring_line(func)} |"
        for name, func in _public_methods(resource)
    ]
    if not rows:
        return ""
    return "| Method | Signature | Description |\n|---|---|---|\n" + "\n".join(rows) + "\n"


def _render(client: Any, flavour: str) -> str:
    is_async = flavour == "async"
    body = [
        _HEADER.format(
            flavour=flavour,
            lede=_ASYNC_LEDE if is_async else _SYNC_LEDE,
            client="AsyncWorkflowClient" if is_async else "WorkflowClient",
            opener="async with" if is_async else "with",
            await_="await " if is_async else "",
        )
    ]

    known = {attr for attr, _ in SECTIONS} | _NOT_A_RESOURCE
    unlisted = sorted(
        attr
        for attr in vars(client)
        if not attr.startswith("_") and attr not in known and _public_methods(getattr(client, attr))
    )
    if unlisted:
        print(f"error: resource(s) on the client but missing from SECTIONS: {', '.join(unlisted)}", file=sys.stderr)
        raise SystemExit(1)

    for attr, heading in SECTIONS:
        resource = getattr(client, attr)
        body.append(f"\n## {heading}\n\n`client.{attr}`\n\n\n")
        body.append(_method_table(resource))
        for sub_attr, sub in _sub_resources(resource):
            body.append(f"\n### `client.{attr}.{sub_attr}`\n\n")
            body.append(_method_table(sub))

    return "".join(body)


def main() -> Optional[int]:
    docs = _ROOT / "docs"
    (docs / "api_async.md").write_text(_render(AsyncWorkflowClient(api_key="x", base_url="http://x"), "async"))
    (docs / "api_sync.md").write_text(_render(WorkflowClient(api_key="x", base_url="http://x"), "sync"))
    print(f"wrote {docs / 'api_async.md'}\nwrote {docs / 'api_sync.md'}")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
