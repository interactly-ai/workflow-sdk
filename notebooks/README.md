# `notebooks/` — Interactive SDK lessons

A hands-on, runnable tour of the Interactly Workflow SDK. Each notebook is self-contained: it
builds an `AsyncWorkflowClient`, does one focused thing, and cleans up after itself. Work through
them roughly in order — later notebooks assume concepts introduced earlier.

> **New to the SDK?** Start with the docs tour at [`../docs/README.md`](../docs/README.md), then come
> back here to run things for real. Prefer complete, workflow-authoring scripts? See
> [`../wf_examples/README.md`](../wf_examples/README.md).

---

## Setup (once)

From the `workflow_sdk/` directory, build the environment from the `Pipfile` and provide credentials:

```bash
# 1. Create the virtualenv (Python 3.13) and install everything the notebooks need
PIPENV_VENV_IN_PROJECT=1 pipenv install --dev --python 3.13     # or: make install

# 2. Provide credentials — either export them, or put them in workflow_sdk/.env
export INTERACTLY_API_KEY="…"
export INTERACTLY_BASE_URL="https://api-dev.interactly.ai/workflows"
export INTERACTLY_TEAM_ID="…"
export INTERACTLY_USER_ID="…"
```

Every notebook's **first code cell** runs `import _bootstrap`, which puts this SDK's `src/` and
`configs/src/` on `sys.path` so `import interactly` / `import interactly_configs` resolve **with no
install needed**. It also calls `nest_asyncio.apply()` so top-level `await` works inside Jupyter, and
loads credentials from `workflow_sdk/.env` if present. Everything it needs lives inside this folder.

### Running them

- **In VS Code / Jupyter:** open any `.ipynb`, select the `workflow_sdk/.venv` kernel, and run cells.
- **Headless (all notebooks, PASS/FAIL report):**

  ```bash
  set -a && source .env && set +a
  .venv/bin/python notebooks/_run_e2e.py            # run all
  .venv/bin/python notebooks/_run_e2e.py 01 09 16   # run a subset by number/name
  .venv/bin/python notebooks/_run_e2e.py --list     # list what would run
  ```

---

## The lessons

Suggested order is top to bottom.

| # | Notebook | What it teaches |
|---|---|---|
| 00 | [index](00_index.ipynb) | This series' table of contents and setup notes |
| 01 | [quickstart](01_quickstart.ipynb) | Build a client, make your first call, list workflows, run a workflow |
| 02 | [interactive workflow](02_interactive_workflow.ipynb) | Drive a multi-turn conversation turn-by-turn |
| 03 | [workflow versions](03_workflow_versions.ipynb) | Create, activate, clone, and delete workflow versions |
| 04 | [tools & inbuilt](04_tools_and_inbuilt.ipynb) | Inbuilt tools and how nodes call them |
| 05 | [workflow with tools](05_workflow_with_tools.ipynb) | Author a workflow whose nodes use tools |
| 06 | [scheduling & webhooks](06_scheduling_and_webhooks.ipynb) | Scheduled runs and webhook subscriptions/delivery |
| 07 | [global variables](07_global_variables.ipynb) | Team-scoped global variables |
| 08 | [super nodes](08_super_nodes.ipynb) | Compose sub-workflows via super nodes |
| 09 | [simulations](09_simulations.ipynb) | Batch-simulate conversations against a workflow |
| 10 | [llm configs](10_llm_configs.ipynb) | Named / saved LLM configurations and referencing them |
| 11 | [reusable assets](11_reusable_assets.ipynb) | Node libraries, templates, and categories |
| 12 | [runtime handles](12_runtime_handles.ipynb) | `WorkflowHandle`, `run_id`/session semantics, the event catalog |
| 13 | [error handling](13_error_handling.ipynb) | The SDK exception hierarchy and how to catch it |
| 14 | [pagination & filtering](14_pagination_and_filtering.ipynb) | Paging through list endpoints; `search` / filter params |
| 15 | [websocket streaming events](15_websocket_streaming_events.ipynb) | Stream run events over the WebSocket API |
| 16 | [nodes & edges](16_nodes_and_edges.ipynb) | The building blocks in depth: node & edge types |
| 17 | [interactly configs](17_interactly_configs.ipynb) | The typed `configs` module: providers, nodes, edges, tools |

### `wf_example_notebooks/`

The [`wf_example_notebooks/`](wf_example_notebooks/) subfolder holds interactive counterparts of the
scripts in [`../wf_examples/`](../wf_examples/) — the same 23-example progression, each building a full
workflow and driving a capped, scripted conversation against the server. For the illustrated write-up of
each (schematic diagram + node/edge tables), read the matching `../wf_examples/wf_example_progression_N.md`.

---

## Maintainer scripts

Underscore-prefixed files are tooling, not lessons: `_bootstrap.py` (the `sys.path` shim every notebook
imports) and `_run_e2e.py` (a headless runner that executes every notebook and reports PASS/FAIL).

## Where to go next

- **Docs tour** — [`../docs/README.md`](../docs/README.md): concepts, installation, authentication,
  pagination, retries, streaming, runtime, and per-topic guides.
- **Runnable examples** — [`../wf_examples/README.md`](../wf_examples/README.md): end-to-end
  workflow-authoring scripts, each with an illustrated guide.
- **SDK front door** — [`../README.md`](../README.md).
