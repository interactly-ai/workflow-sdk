"""A workflow's secret survives export and import through ``secret_overrides``; a version's settings change through
``update_config``; and a workflow reports the workflows that use it.

The workflows here run nothing: one HTTP Request node, whose ``Authorization`` header is a made-up value, pointing at
a host that can never resolve. Everything created is deleted.

    pytest tests/integration/test_workflow_bundles_e2e.py -m integration
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator, List, Optional

import pytest

from interactly import WorkflowClient
from interactly.configs import EvaluationConfig, HttpRequestNodeConfig, WorkflowConfig, WorkflowConfigFullyHydrated

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]

_HEADER = "Bearer sdk-e2e-not-a-secret"


def _workflow(name: str, evaluator_workflow_id: Optional[str] = None) -> WorkflowConfigFullyHydrated:
    node = HttpRequestNodeConfig(
        name="Ping",
        is_start=True,
        url="https://api.unreachable.invalid/ping",
        headers={"Authorization": _HEADER, "Accept": "application/json"},
    )
    evaluation = EvaluationConfig(evaluator_workflow_id=evaluator_workflow_id) if evaluator_workflow_id else None
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(
            name=f"SDK_E2E {name} {uuid.uuid4().hex[:8]}", description="original", evaluation_config=evaluation
        ),
        node_configs=[node],
        edge_configs=[],
    )


def _authorization(client: WorkflowClient, workflow_id: str) -> Optional[str]:
    node = next(n for n in client.workflows.get_fully_hydrated(workflow_id).node_configs if n.type == "http_request")
    return (node.headers or {}).get("Authorization")


@pytest.fixture
def session() -> Iterator[tuple]:
    """A client, and a list the test adds every workflow it creates to; each is deleted afterwards."""
    client = WorkflowClient()
    created: List[str] = []
    try:
        yield client, created
    finally:
        for workflow_id in reversed(created):
            client.workflows.delete(workflow_id)
        client.close()


def test_a_secret_cleared_on_export_comes_back_through_secret_overrides(session):
    client, created = session
    source = client.workflows.create_from_config(_workflow("bundle source")).id
    created.append(source)

    bundle = client.workflows.export(source, version_numbers=[0], active_version_number=0)
    overrides = {r["path"]: _HEADER for r in bundle["redactions"]}
    restored = client.workflows.import_bundle(bundle, workflow_name="SDK_E2E restored", secret_overrides=overrides)
    created.append(restored.id)
    left_empty = client.workflows.import_bundle(bundle, workflow_name="SDK_E2E left empty")
    created.append(left_empty.id)

    assert bundle["secrets_included"] is False
    assert list(overrides) == ["versions.0.workflow_config.node_configs.0.headers.Authorization"]
    assert (_authorization(client, restored.id), restored.warnings) == (_HEADER, [])
    assert _authorization(client, left_empty.id) == ""
    assert any("not supplied" in warning for warning in left_empty.warnings)


def test_update_config_changes_only_the_settings_given(session):
    client, created = session
    workflow_id = client.workflows.create_from_config(_workflow("settings")).id
    created.append(workflow_id)

    updated = client.workflows.versions.update_config(workflow_id, 0, config={"description": "changed by the SDK"})
    stored = next(v for v in client.workflows.versions.list(workflow_id) if v.version_number == 0)

    assert updated.config.description == stored.config.description == "changed by the SDK"
    assert stored.config.name.startswith("SDK_E2E settings")
    assert _authorization(client, workflow_id) == _HEADER


def test_a_workflow_reports_the_workflows_that_use_it(session):
    client, created = session
    used = client.workflows.create_from_config(_workflow("evaluator")).id
    created.append(used)
    user = client.workflows.create_from_config(_workflow("evaluated", evaluator_workflow_id=used)).id
    created.append(user)

    report = client.workflows.usage(used)

    assert [(entry.workflow_id, entry.version_numbers) for entry in report.used_by] == [(user, [0])]
    assert client.workflows.usage(user).used_by == []
