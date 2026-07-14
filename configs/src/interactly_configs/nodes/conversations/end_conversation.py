from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.llm_group import LLMOrGroupConfig
from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeType,
)
from interactly_configs.prompt import PromptConfig

class EndConversationNodeConfig(BaseNodeConfig):
    type: Literal["end_conversation"] = Field(
        default=NodeType.END_CONVERSATION.value,
        description="Type of the node. Must be 'end_conversation'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default="System",
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default="Conversation",
        description="Secondary category of the node",
        title="Secondary Category",
    )
    process_transcript_prompt: Optional[PromptConfig] = Field(
        default=None,
        description="Prompt configuration for processing the conversation transcript",
        title="Process Transcript Prompt Configuration",
    )
    process_transcript_llms_config: Optional[LLMOrGroupConfig] = Field(
        default=None,
        description="LLM or a group of LLMs to be used for processing the conversation transcript",
        title="Process Transcript LLM(s) Configuration",
    )

    model_config = ConfigDict(
        title="End Conversation Node",
    )

class EndConversationNodeRunInput(BaseNodeRunInput):
    type: Literal["end_conversation"] = Field(
        default="end_conversation", description="Discriminator field which must always be 'end_conversation'"
    )

class EndConversationNodeRunOutput(BaseNodeRunOutput):
    type: Literal["end_conversation"] = Field(
        default="end_conversation", description="Discriminator field which must always be 'end_conversation'"
    )
