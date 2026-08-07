"""
Extra-config schema for the call_forward configurable inbuilt tool.

This module defines the user-configurable fields that can be set when a user creates a persisted
call_forward tool. It is used solely for JSON-schema generation and validation — it is **not** part
of the ToolConfig discriminated union.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Upstream re-exports this from ``agentic_workflow_framework.tools.communication.call_forward``,
# which is server-side runtime code. The mirror inlines the literal instead: it is the registry key
# the server matches on, so the value is contract even though the module holding it is not.
CALL_FORWARD_REGISTRY_TOOL_ID = "call_forward"
CALL_FORWARD_CONFIGURABLE_KEY = "call_forward"


class CallForwardExtraConfig(BaseModel):
    """
    User-configurable extra fields for the call_forward inbuilt tool.

    The JSON schema of this model is what ``GET /v1/tools/configurable-inbuilt/call_forward``
    returns, and what a dashboard renders as a form after the user selects 'Call Forward'.
    """

    warm_transfer_conversation_workflow_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of the workflow to use for the warm-transfer conversation when the call is forwarded. "
            "If left empty, the warm transfer will not be conversation-based and will simply transfer "
            "the call with a single message to the human recipient."
        ),
        title="Warm Transfer Conversation Workflow ID",
    )

    model_config = ConfigDict(title="Call Forward — Extra Configuration")
