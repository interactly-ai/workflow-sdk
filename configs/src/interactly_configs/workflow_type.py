from enum import Enum


class WorkflowType(str, Enum):
    """What a workflow is: set at creation and never changed. A stored workflow without one is standard."""

    STANDARD = "standard"
    # Post-call analysis of a finished conversation, run by workflow_service; never on a live call.
    EVALUATION = "evaluation"
