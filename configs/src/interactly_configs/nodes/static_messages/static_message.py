from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.node import BaseNodeConfig, BaseNodeRunInput, BaseNodeRunOutput, NodeType
from interactly_configs.prompt import StaticMessagesConfig

class SayStaticMessageNodeConfig(BaseNodeConfig):
    type: Literal["say_static"] = Field(
        default=NodeType.SAY_STATIC.value,
        description="Type of the node. Must be 'say_static'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default="System",
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default="Static Message",
        description="Secondary category of the node",
        title="Secondary Category",
    )
    static_messages_config: Optional[StaticMessagesConfig] = Field(
        default=None,
        description="Configuration for static messages. Contains a list of pre-configured messages",
        title="Static Messages Configuration",
    )

    model_config = ConfigDict(
        title="Static Messages Node",
    )

class SayStaticMessageNodeRunInput(BaseNodeRunInput):
    type: Literal["say_static"] = Field(
        default="say_static", description="Discriminator field which must always be 'say_static'"
    )

class SayStaticMessageNodeRunOutput(BaseNodeRunOutput):
    type: Literal["say_static"] = Field(
        default="say_static", description="Discriminator field which must always be 'say_static'"
    )
