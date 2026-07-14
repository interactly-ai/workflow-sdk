from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.node import BaseNodeConfig, BaseNodeRunInput, BaseNodeRunOutput, NodeType

class StartConversationNodeConfig(BaseNodeConfig):
    type: Literal["start_conversation"] = Field(
        default=NodeType.START_CONVERSATION.value,
        description="Type of the node. Must be 'start_conversation'",
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
    is_voice_conversation: bool = Field(
        default=False,
        description="Whether this conversation is a voice-based conversation",
        title="Is Voice Conversation",
    )
    is_outbound_call: bool = Field(
        default=True,
        description="Whether this conversation is an outbound call",
        title="Is Outbound Call",
    )
    bearer_token: Optional[str] = Field(
        default=None,
        description="The bearer token used for authenticating with the outbound phone call service",
        title="Bearer Token",
    )
    assistant_number: Optional[str] = Field(
        default=None,
        description="The phone number assigned to the assistant to make the call from (in E.164 format)",
        title="Assistant Phone Number",
    )
    assistant_id: Optional[str] = Field(
        default=None,
        description="The ID of the assistant to use for the conversation",
        title="Assistant ID",
    )
    user_number: Optional[str] = Field(
        default=None,
        description="The phone number of the user to call (in E.164 format)",
        title="User Phone Number",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="The ID of the conversation to poll. If provided, an outbound call will not be initiated, and the system will instead poll for an existing conversation with this ID.",
        title="Conversation ID",
    )
    polling_interval_seconds: Optional[int] = Field(
        default=2,
        description="If polling for an existing conversation, the interval (in seconds) at which to poll for updates",
        title="Polling Interval Seconds",
    )
    ### We need to add more config options later for voice conversations ###
    ### e.g., TTS and STT settings, inbound vs outbound, phone number to call, etc ###
    model_config = ConfigDict(
        title="Start Conversation Node",
    )

class StartConversationNodeRunInput(BaseNodeRunInput):
    type: Literal["start_conversation"] = Field(
        default="start_conversation", description="Discriminator field which must always be 'start_conversation'"
    )

class StartConversationNodeRunOutput(BaseNodeRunOutput):
    type: Literal["start_conversation"] = Field(
        default="start_conversation", description="Discriminator field which must always be 'start_conversation'"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="The ID of the conversation that was created or polled during the outbound phone call",
        title="Conversation ID",
    )
