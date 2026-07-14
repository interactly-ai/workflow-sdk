from typing import Literal

from pydantic import ConfigDict, Field
from typing_extensions import Optional

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
    NodeType,
)

class SendSMSNodeConfig(BaseNodeConfig):
    type: Literal["send_sms"] = Field(
        default=NodeType.SEND_SMS.value,
        description="Type of the node. Must be 'send_sms'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.COMMUNICATIONS.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.SMS.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    destination_phone_number: Optional[str] = Field(
        default=None,
        description="Destination phone number in E.164 format. Example of E.164 format: +1234567890",
        title="Destination Phone Number",
    )
    message: Optional[str] = Field(
        default=None,
        description="SMS message to be sent. Can include dynamic and runtime variable placeholders for dynamic content.",
        title="SMS Message",
    )

    model_config = ConfigDict(
        title="Send SMS Node",
    )

class SendSMSNodeRunInput(BaseNodeRunInput):
    type: Literal["send_sms"] = Field(
        default="send_sms", description="Discriminator field which must always be 'send_sms'"
    )
    override_destination_phone_number: Optional[str] = Field(
        default=None,
        description="Destination phone number in E.164 format. Example of E.164 format: +1234567890. This field, if provided, overrides the phone number in the node config.",
        title="Destination Phone Number",
    )
    override_message: Optional[str] = Field(
        default=None,
        description="SMS message to be sent. Can include dynamic and runtime variable placeholders for dynamic content. This field, if provided, overrides the message in the node config.",
        title="SMS Message",
    )

class SendSMSNodeRunOutput(BaseNodeRunOutput):
    type: Literal["send_sms"] = Field(
        default="send_sms", description="Discriminator field which must always be 'send_sms'"
    )
    success: bool = Field(
        default=False,
        description="Indicates whether the SMS was sent successfully",
        title="SMS Sent Successfully",
    )
    sent_sms_message: Optional[str] = Field(
        default=None,
        description="The SMS message that was sent",
        title="Sent SMS Message",
    )
