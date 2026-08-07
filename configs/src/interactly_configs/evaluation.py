from typing import Optional

from pydantic import BaseModel, Field


class EvaluationConfig(BaseModel):
    evaluator_workflow_id: Optional[str] = Field(
        default=None,
        description="ID of the workflow to be used as the evaluator",
        title="Evaluator Workflow ID",
    )

    evaluator_workflow_version_number: Optional[int] = Field(
        default=None,
        description="Version number of the evaluator workflow to be used. If not specified, the active version will be used.",
        title="Evaluator Workflow Version Number",
    )

    enable_turn_by_turn_evaluation: bool = Field(
        default=False,
        description="If true, enables turn-by-turn evaluation of the workflow execution",
        title="Enable Turn-by-Turn Evaluation",
    )

class EvaluationRunInfo(BaseModel):
    """
    Contains information about the evaluation that was triggered for a workflow run.
    This is stored in the source workflow run after evaluation completes.
    """

    evaluation_workflow_run_id: Optional[str] = Field(
        default=None,
        description="ID of the evaluation workflow run that was triggered for this source workflow run.",
        title="Evaluation Workflow Run ID",
    )
