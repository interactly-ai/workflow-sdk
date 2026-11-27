"""An evaluation workflow is created from a template, found where evaluation workflows are listed and nowhere else,
and read by version.

Creating one runs nothing: it imports the template's nodes. It is deleted.

    pytest tests/integration/test_evaluation_workflows_e2e.py -m integration
"""

from __future__ import annotations

import os
import uuid

import pytest

from interactly import NotFoundError, WorkflowClient, WorkflowType

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]

_ANALYSIS_NODES = {"conversation_fetch", "analysis_llm", "store_analysis"}


def test_the_analysis_nodes_are_offered_for_evaluation_workflows_only():
    with WorkflowClient() as client:
        standard = {t["type"] for t in client.nodes.types()}
        evaluation = {t["type"] for t in client.nodes.types(workflow_type=WorkflowType.EVALUATION)}
        presets = client.evaluation_workflows.node_presets()

    assert _ANALYSIS_NODES <= evaluation
    assert not _ANALYSIS_NODES & standard
    assert {p.node_type for p in presets} == _ANALYSIS_NODES


def test_an_evaluation_workflow_from_a_template_is_listed_as_one_and_read_by_version():
    name = f"SDK_E2E evaluation {uuid.uuid4().hex[:8]}"
    with WorkflowClient() as client:
        template = client.evaluation_workflows.templates()[0]
        workflow = client.evaluation_workflows.create_from_template(template_id=template.template_id, name=name)
        try:
            listed = [w for w in client.evaluation_workflows.list() if w.workflow_id == workflow.id]
            as_evaluation = [w.id for w in client.workflows.list(search=name, workflow_type="evaluation")]
            as_default = [w.id for w in client.workflows.list(search=name)]
            fetched = client.workflows.get(workflow.id)
            version = client.workflows.versions.get(workflow.id, 0)
            hydrated = client.workflows.get_fully_hydrated(workflow.id, version_number=0)
            with pytest.raises(NotFoundError):
                client.workflows.versions.get(workflow.id, 7)
        finally:
            client.workflows.delete(workflow.id)

    assert [(w.name, w.active_version_number) for w in listed] == [(name, 0)]
    assert [v.version_name for v in listed[0].versions] == [template.name]
    assert (as_evaluation, as_default) == ([workflow.id], [])
    assert (fetched.id, fetched.active_version_number) == (workflow.id, 0)
    assert (version.version_number, version.is_active) == (0, True)
    assert {n.type for n in hydrated.node_configs} >= {"conversation_fetch", "store_analysis"}


def test_an_unknown_template_is_not_found():
    with WorkflowClient() as client:
        with pytest.raises(NotFoundError, match="Unknown template"):
            client.evaluation_workflows.create_from_template(template_id="sdk_e2e_no_such_template", name="x")
