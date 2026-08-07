from enum import Enum
from typing import Annotated, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCopilotStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"

class WorkflowCopilotCommand(str, Enum):
    DATA = "data"
    STOP = "stop"

class WorkflowCopilotOutputType(str, Enum):
    TEXT = "text"
    BUTTONS = "buttons"
    MARKDOWN = "markdown"
    CODE = "code"
    WORKFLOW_CARD = "workflowCard"
    CHECKBOXES = "checkboxes"

class Button(BaseModel):
    label: Optional[str] = Field(
        default="Button",
        description="Label for the button",
        title="Button Label",
    )
    value: Optional[str] = Field(
        default="button_value",
        description="Value for the button",
        title="Button Value",
    )
    action: Optional[str] = Field(
        default="button_action",
        description="Action for the button",
        title="Button Action",
    )

class LabelValue(BaseModel):
    label: Optional[str] = Field(
        default="Checkbox",
        description="Label for the checkbox",
        title="Checkbox Label",
    )
    value: Optional[str] = Field(
        default="checkbox_value",
        description="Value for the checkbox",
        title="Checkbox Value",
    )

class Checkboxes(BaseModel):
    options: List[LabelValue] = Field(
        default_factory=list,
        description="Options for the checkboxes",
        title="Workflow Copilot Checkboxes Options",
    )
    submit_label: Optional[str] = Field(
        default="Submit",
        description="Label for the submit button",
        title="Workflow Copilot Checkboxes Submit Label",
    )
    multi_select: Optional[bool] = Field(
        default=True,
        description="Allow multiple selections",
        title="Workflow Copilot Checkboxes Multi Select",
    )
    select_all_label: Optional[str] = Field(
        default="Select All",
        description="Label for the select all button",
        title="Workflow Copilot Checkboxes Select All Label",
    )

class WorkflowCopilotInput(BaseModel):
    """
    Input to the workflow copilot, used to kick off or resume a workflow copilot.
    """

    command: WorkflowCopilotCommand = Field(
        default=WorkflowCopilotCommand.DATA,
        description="Command to execute on the workflow copilot",
        title="Workflow Copilot Command",
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Input text for the workflow copilot",
        title="Workflow Copilot Input Text",
    )
    file_id: Optional[str] = Field(
        default=None,
        description="File ID for the workflow copilot",
        title="Workflow Copilot File ID",
    )

class BaseOutput(BaseModel):
    """
    Base output model for the workflow copilot.
    """

    logical_id: Optional[str] = Field(
        default_factory=lambda: "workflow_template_" + str(uuid4()),
        description="Unique identifier for the workflow template",
        title="Workflow Template Logical ID",
    )

    role: Literal["assistant"] = Field(
        default="assistant",
        description="Role of the workflow copilot",
        title="Workflow Copilot Role",
    )

# Text Output
class TextOutput(BaseOutput):
    """
    Output model for the workflow copilot text response.
    """

    type: Literal["text"] = Field(
        default=WorkflowCopilotOutputType.TEXT.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    text: Optional[str] = Field(
        default=None,
        description="Output text from the workflow copilot",
        title="Workflow Copilot Output Text",
    )

    model_config = ConfigDict(
        title="Text Output",
    )

# Buttons Output
class ButtonsOutput(BaseOutput):
    """
    Output model for the workflow copilot buttons response.
    """

    type: Literal["buttons"] = Field(
        default=WorkflowCopilotOutputType.BUTTONS.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    layout: Literal["horizontal", "vertical"] = Field(
        default="vertical",
        description="Layout for the button",
        title="Button Layout",
    )

    buttons: Optional[List[Button]] = Field(
        default_factory=list,
        description="Output buttons from the workflow copilot",
        title="Workflow Copilot Output Buttons",
    )

    model_config = ConfigDict(
        title="Buttons Output",
    )

# Markdown Output
class MarkdownOutput(BaseOutput):
    """
    Output model for the workflow copilot markdown response.
    """

    type: Literal["markdown"] = Field(
        default=WorkflowCopilotOutputType.MARKDOWN.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    markdown: Optional[str] = Field(
        default=None,
        description="Output markdown from the workflow copilot",
        title="Workflow Copilot Output Markdown",
    )

    model_config = ConfigDict(
        title="Markdown Output",
    )

# Code Output
class CodeOutput(BaseOutput):
    """
    Output model for the workflow copilot code response.
    """

    type: Literal["code"] = Field(
        default=WorkflowCopilotOutputType.CODE.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    code: Optional[str] = Field(
        default=None,
        description="Output code from the workflow copilot",
        title="Workflow Copilot Output Code",
    )

    filename: Optional[str] = Field(
        default=None,
        description="Filename for the code output",
        title="Code Output Filename",
    )
    language: Optional[str] = Field(
        default=None,
        description="Programming language for the code output",
        title="Code Output Language",
    )
    showLineNumbers: Optional[bool] = Field(
        default=True,
        description="Whether to show line numbers in the code output",
        title="Code Output Show Line Numbers",
    )
    highlightLines: Optional[List[int]] = Field(
        default=None,
        description="List of line numbers to highlight in the code output",
        title="Code Output Highlight Lines",
    )
    wrapLongLines: Optional[bool] = Field(
        default=None,
        description="Whether to wrap long lines in the code output",
        title="Code Output Wrap Long Lines",
    )
    collapsed: Optional[bool] = Field(
        default=None,
        description="Whether the code output is collapsed",
        title="Code Output Collapsed",
    )
    collapseHeight: Optional[int] = Field(
        default=None,
        description="Height of the collapsed code output",
        title="Code Output Collapse Height",
    )

    model_config = ConfigDict(
        title="Code Output",
    )

# Workflow Card Output
class WorkflowCardOutput(BaseOutput):
    """
    Output model for the workflow copilot card response.
    """

    type: Literal["workflowCard"] = Field(
        default=WorkflowCopilotOutputType.WORKFLOW_CARD.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    id: Optional[str] = Field(
        default=None,
        description="ID for the workflow card output",
        title="Workflow Card Output ID",
    )
    title: Optional[str] = Field(
        default=None,
        description="Title for the workflow card output",
        title="Workflow Card Output Title",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description for the workflow card output",
        title="Workflow Card Output Description",
    )
    steps: Optional[int] = Field(
        default=None,
        description="Number of steps for the workflow card output",
        title="Workflow Card Output Steps",
    )

    model_config = ConfigDict(
        title="Workflow Card Output",
    )

# Checkboxes Output
class CheckboxesOutput(BaseOutput):
    """
    Output model for the workflow copilot checkboxes response.
    """

    type: Literal["checkboxes"] = Field(
        default=WorkflowCopilotOutputType.CHECKBOXES.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    checkboxes: Optional[Checkboxes] = Field(
        default_factory=list,
        description="Output checkboxes from the workflow copilot",
        title="Workflow Copilot Output Checkboxes",
    )

    model_config = ConfigDict(
        title="Checkboxes Output",
    )

# Workflow Copilot Output
WorkflowCopilotOutput = Annotated[
    TextOutput | ButtonsOutput | MarkdownOutput | CodeOutput | WorkflowCardOutput | CheckboxesOutput,
    Field(discriminator="type"),
]

class WorkflowCopilotEvent(BaseModel):
    """
    Event model for the workflow copilot.
    """

    type: Literal["workflow_copilot"] = Field(
        default="workflow_copilot",
        description="Type of the workflow copilot event",
        title="Workflow Copilot Event Type",
    )

    payload: WorkflowCopilotOutput = Field(
        default=None,
        description="Payload of the workflow copilot event",
        title="Workflow Copilot Event Payload",
    )

    model_config = ConfigDict(
        title="Workflow Copilot Event",
    )
