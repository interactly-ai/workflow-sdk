# interactly-configs

Pure-Pydantic data contracts for the Interactly workflow engine — the typed
config classes (`WorkflowConfig`, node/edge/LLM/tool configs, `WorkflowRunInput`,
events, …) used by the Interactly SDK to author workflows as typed Python.

These classes are client-safe: server-only identifiers and ACL constants are
stripped, so the package depends only on `pydantic`.

## Install

```bash
pip install interactly-configs
```

Or, for local development from a checkout:

```bash
pip install -e ./configs
```

## Usage

```python
import interactly_configs
from interactly_configs import WorkflowConfig, WorkflowConfigFullyHydrated, WorkflowRunInput
```

The Interactly SDK re-exports these under `interactly.configs`, so SDK users can
instead write `from interactly.configs import WorkflowConfig`.
