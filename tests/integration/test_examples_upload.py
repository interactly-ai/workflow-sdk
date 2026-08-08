"""Every curriculum example still builds a config the server accepts.

This closes the gap left by `wf_examples/_run_e2e.py`, which `CHANGELOG.md` described but which was
never in the repo — the same "documented but absent" shape as the API-reference generator restored in
Phase 4. Rather than recreate that script, the check lives here, where it runs as part of the suite
instead of waiting for someone to remember it.

Scope is deliberately narrow: **upload only**. Whether each example *runs* is already covered by the
notebook counterparts in ``notebooks/wf_example_notebooks/``, which the e2e sweep executes. What is
not covered anywhere else is whether the 25 configs are still *valid* — and a config that no longer
validates is precisely what a server-side rule change produces. That failure is silent until someone
opens the example.

Each upload is deleted immediately.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import List

import pytest

from interactly import AsyncWorkflowClient
from interactly.configs import WorkflowConfigFullyHydrated

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

_SDK_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _SDK_ROOT / "wf_examples"


def _example_modules() -> List[str]:
    """Every `wf_example_progression_N.py`, in curriculum order."""
    names = [p.stem for p in _EXAMPLES.glob("wf_example_progression_*.py")]
    return sorted(names, key=lambda n: int(n.rsplit("_", 1)[1]))


_MODULES = _example_modules()


def test_the_curriculum_was_discovered():
    """A parametrised suite over an empty list passes vacuously.

    Phase 0 found three of four quality gates in exactly that state, so the discovery gets its own
    assertion rather than being trusted.
    """
    assert len(_MODULES) >= 25, f"only found {len(_MODULES)} examples: {_MODULES}"


@pytest.fixture(scope="module")
def _examples_on_path():
    # The examples import `_shared_sdk` / `_shared_constants` as top-level modules, exactly as they do
    # when run directly from that directory.
    if str(_EXAMPLES) not in sys.path:
        sys.path.insert(0, str(_EXAMPLES))
    yield


@pytest.mark.parametrize("module_name", _MODULES)
async def test_example_config_is_accepted_by_the_server(module_name: str, _examples_on_path):
    """Build the example's config and upload it.

    Importing the module only defines functions — every example guards its driver behind
    ``if __name__ == "__main__"``, so nothing runs and no LLM is called here.
    """
    module = importlib.import_module(module_name)
    assert hasattr(module, "build_assistant_workflow"), (
        f"{module_name} has no build_assistant_workflow(); the curriculum convention is broken"
    )

    built = module.build_assistant_workflow()

    # The curriculum is not uniform here: some builders return the config alone, others return
    # ``(config, dynamic_variables)``. Accept both rather than churning a dozen files customers read
    # — but insist on finding a config, so a builder that starts returning something else fails
    # loudly instead of uploading nothing.
    config = built[0] if isinstance(built, tuple) else built
    assert isinstance(config, WorkflowConfigFullyHydrated), (
        f"{module_name}.build_assistant_workflow() returned {type(built).__name__}, "
        "which does not contain a WorkflowConfigFullyHydrated"
    )

    name = f"SDK_E2E upload check — {module_name}"

    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow = await client.workflows.create_from_config(config, name=name)
        workflow_id = workflow.id
        assert workflow_id, "the server accepted the config but returned no id"
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()
