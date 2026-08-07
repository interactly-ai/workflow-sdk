"""
Response models for Workflow Run resources.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import Field, model_validator

from interactly._models import BaseAPIModel

# ``RunStatus`` is re-exported for callers who want to compare ``Run.status``
# against known values; the field itself is typed ``Optional[str]`` so that
# server-side additions to the status vocabulary don't raise ``ValidationError``.
from interactly.types.shared import RunStatus  # noqa: F401

if TYPE_CHECKING:
    # Static type only: type-checkers and IDEs see the concrete typed pair
    # (``run_input: WorkflowRunInput``, ``run_output: WorkflowRunOutput`` -> ``.events``).
    from interactly_configs import WorkflowRunInputOutputPair
else:
    # At runtime the ``[configs]`` extra may be absent, so the annotation resolves
    # to ``Any``; the ``_coerce_input_output_pairs`` validator upgrades each element
    # to a real ``WorkflowRunInputOutputPair`` when the package is installed.
    WorkflowRunInputOutputPair = Any

__all__ = ["Run", "RunComment", "RunEvaluationResult"]


class RunComment(BaseAPIModel):
    """A comment attached to a workflow run."""

    logical_id: str
    content: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _extract_from_run(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Already a bare comment.
        if "logical_id" in data and "content" in data:
            return data
        # The add-comment endpoints echo back the whole run document; dig out
        # the newest comment (run-level first, then any event-level comment).
        record = data.get("workflow_run", data)
        if not isinstance(record, dict):
            return data
        state = record.get("workflow_run", record)
        if not isinstance(state, dict):
            return data
        comments = state.get("comments")
        if isinstance(comments, list) and comments:
            return comments[-1]
        newest = None
        for pair in state.get("input_output_pairs") or []:
            output = (pair or {}).get("run_output") or {}
            for event in output.get("events") or []:
                event_comments = (event or {}).get("comments") or []
                if event_comments:
                    newest = event_comments[-1]
        return newest if newest is not None else data


class RunEvaluationResult(BaseAPIModel):
    """Evaluation result for a workflow run."""

    score: Optional[float] = None
    passed: Optional[bool] = None
    details: Optional[Dict[str, Any]] = None
    evaluated_at: Optional[datetime] = None


class Run(BaseAPIModel):
    """Full representation of a Workflow Run as returned by the API.

    This is the SDK's flat, forward-compatible API-response DTO. It is distinct
    from ``interactly_configs.WorkflowRun`` (the rich, server-mirroring runtime
    execution-state model that this DTO is flattened from).
    """

    id: str
    workflow_id: str

    # Typed as ``str`` (not ``RunStatus``) for forward-compat with unknown
    # server values; compare against ``RunStatus`` members as needed.
    status: Optional[str] = None

    # Who or what triggered the run.
    run_by: Optional[str] = None

    # Which workflow version was used.
    version_number: Optional[int] = None

    # Per-turn input/output captured during the run. Each pair corresponds to a
    # contiguous execution segment; ``run_output.events`` holds the generated
    # events (assistant responses, user messages, node/edge events, ...).
    # Elements are ``Dict`` when interactly_configs is not installed; upgraded to
    # ``WorkflowRunInputOutputPair`` by the validator.
    input_output_pairs: List[WorkflowRunInputOutputPair] = Field(default_factory=list)

    # Error details if the run failed.
    error: Optional[str] = None

    team_id: Optional[str] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    comments: Optional[List[RunComment]] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_run(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = cls._flatten_server_document(data)
        return cls._coerce_input_output_pairs(data)

    @staticmethod
    def _flatten_server_document(data: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten the server's nested run document into this model's flat shape.

        The workflow-runs endpoints return a persisted record that nests the run
        *state* under its own ``workflow_run`` key alongside envelope metadata::

            # single get: an outer ``{"workflow_run": <record>}`` envelope
            {"workflow_run": {"_id": ..., "team_id": ..., "created_at": ...,
                              "workflow_run": {"workflow_run_id": ..., "workflow_id": ...,
                                               "status": ..., "input_output_pairs": [...], ...}}}
            # list rows: the ``<record>`` itself (no outer envelope)

        Already-flat payloads (with a top-level ``id``/``workflow_id``) pass
        through untouched.
        """
        if "id" in data and "workflow_id" in data:
            return data

        # Unwrap the outer single-object envelope from single-get responses.
        record = data
        if isinstance(record.get("workflow_run"), dict) and "_id" not in record and "id" not in record:
            record = record["workflow_run"]

        state = record.get("workflow_run")
        if not isinstance(state, dict):
            return data

        return {
            "id": state.get("workflow_run_id") or record.get("_id") or record.get("id"),
            "workflow_id": state.get("workflow_id"),
            "status": state.get("status"),
            "run_by": state.get("run_by") or record.get("created_by"),
            "version_number": state.get("version_number"),
            "input_output_pairs": state.get("input_output_pairs"),
            "error": state.get("termination_source") if state.get("status") == "failed" else None,
            "team_id": record.get("team_id"),
            "started_at": record.get("created_at"),
            "completed_at": record.get("updated_at"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "comments": state.get("comments"),
        }

    @staticmethod
    def _coerce_input_output_pairs(data: Dict[str, Any]) -> Dict[str, Any]:
        """Upgrade each raw input/output pair dict into a typed
        ``WorkflowRunInputOutputPair`` when ``interactly_configs`` is installed.

        Leaves elements as plain dicts if the package is absent or an individual
        pair fails validation, so the SDK degrades gracefully without the
        ``[configs]`` extra.
        """
        raw_pairs = data.get("input_output_pairs")
        # The server returns ``null`` for runs that have no turns yet (and may omit the
        # key entirely). Normalise both to ``[]`` so the non-optional ``List`` field
        # validates and callers can always iterate ``run.input_output_pairs``.
        if raw_pairs is None:
            data["input_output_pairs"] = []
            return data
        if not isinstance(raw_pairs, list):
            return data
        try:
            from interactly_configs import WorkflowRunInputOutputPair as _Pair
            from pydantic import TypeAdapter

            adapter = TypeAdapter(_Pair)
        except Exception:
            return data

        coerced: List[Any] = []
        for pair in raw_pairs:
            if isinstance(pair, dict):
                try:
                    coerced.append(adapter.validate_python(pair))
                    continue
                except Exception:
                    pass
            coerced.append(pair)
        data["input_output_pairs"] = coerced
        return data
