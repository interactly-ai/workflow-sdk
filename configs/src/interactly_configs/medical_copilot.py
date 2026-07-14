from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

class MedicalCopilotCommand(str, Enum):
    DATA = "data"
    STOP = "stop"

class MedicalCopilotInput(BaseModel):
    """Input to the medical copilot."""

    command: MedicalCopilotCommand = Field(
        default=MedicalCopilotCommand.DATA,
        description="Command to execute on the medical copilot",
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Input text for the medical copilot",
    )
    model: Optional[str] = Field(
        default="medgemma",
        description="Model to use for the medical copilot (medgemma, mediphi, medllama, auto)",
    )
    system: Optional[str] = Field(
        default=None,
        description="System prompt for the medical copilot",
    )
    file_url: Optional[str] = Field(
        default=None,
        description="Data URL for image input (only for medgemma). Format: data:image/png;base64,<BASE64>",
    )

class MedicalCopilotOutput(BaseModel):
    """Simple output model for the medical copilot."""

    type: Literal["text"] = Field(default="text", description="Type of the output")
    text: str = Field(description="Output text from the medical copilot")

class MedicalCopilotFinalPayload(BaseModel):
    """Final payload for the medical copilot response."""

    text: str = Field(description="Final text response from the medical copilot")

class MedicalCopilotEvent(BaseModel):
    """Event model for the medical copilot."""

    type: Literal["medical_copilot"] = Field(
        default="medical_copilot",
        description="Type of the medical copilot event",
    )

    payload: MedicalCopilotFinalPayload = Field(
        description="Payload of the medical copilot event",
    )
