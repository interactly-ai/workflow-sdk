"""Loads a finished call so the analysis steps after it can read it."""

from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.analysis.base import BaseAnalysisNodeConfig
from interactly_configs.nodes.node import BaseNodeRunInput, BaseNodeRunOutput, NodeType


class ConversationFetchNodeConfig(BaseAnalysisNodeConfig):
    type: Literal["conversation_fetch"] = Field(
        default=NodeType.CONVERSATION_FETCH.value,
        description="Type of the node. Must be 'conversation_fetch'",
        title="Node Type",
    )
    conversation_id: str = Field(
        default="{{conversation_id}}",
        description=(
            "Call to load in a test run (Test on a call fills it in). Post-call analysis always loads the call being "
            "analysed, whatever this says."
        ),
        title="Conversation ID",
    )
    include_tool_activity: bool = Field(
        default=True,
        description="Put the call's tool calls and results into [[transcript]] where they happened.",
        title="Include Tool Activity",
    )

    model_config = ConfigDict(title="Conversation Fetch Node")


class ConversationFetchNodeRunInput(BaseNodeRunInput):
    type: Literal["conversation_fetch"] = Field(
        default="conversation_fetch", description="Discriminator field which must always be 'conversation_fetch'"
    )


class ConversationFetchNodeRunOutput(BaseNodeRunOutput):
    type: Literal["conversation_fetch"] = Field(
        default="conversation_fetch", description="Discriminator field which must always be 'conversation_fetch'"
    )
    conversation_id: Optional[str] = Field(default=None, description="Call loaded", title="Conversation ID")
    turns: int = Field(default=0, description="Spoken turns in the transcript", title="Turns")
    tool_events: int = Field(default=0, description="Tool calls and results loaded", title="Tool Events")
    workflow_run_id: Optional[str] = Field(default=None, description="The call's workflow run", title="Workflow Run")
