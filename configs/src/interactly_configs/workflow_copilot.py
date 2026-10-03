from enum import Enum
from typing import Annotated, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCopilotStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"

class WorkflowCopilotCommand(str, Enum):
    DATA = "data"
    #: Close the socket and leave the conversation where it is. The stored session survives, so the
    #: next connection resumes it.
    STOP = "stop"
    #: Forget the conversation so far and begin a new one under a fresh session id. A reconnect resumes
    #: rather than resets, so this is the only way for a user to start clean.
    NEW_CHAT = "new_chat"
    #: End the conversation for good: the server deletes the stored session so nothing can resume it,
    #: then closes with code 4041. Distinct from STOP, which only hangs up.
    FINISH = "finish"

class WorkflowCopilotOutputType(str, Enum):
    TEXT = "text"
    BUTTONS = "buttons"
    MARKDOWN = "markdown"
    CODE = "code"
    WORKFLOW_CARD = "workflowCard"
    CHECKBOXES = "checkboxes"
    PROPOSAL = "proposal"

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

    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Identifies a conversation across reconnects. Send back the id from a previous connection "
            "to resume it; omit it to start a new one. Scoped to the caller's team, so an id from "
            "elsewhere resumes nothing."
        ),
        title="Session ID",
    )

    page_context: Optional[dict] = Field(
        default=None,
        description=(
            "What the user is looking at: page type, route, and the identifier of the entity on "
            "screen. Validated and bounded server-side, and treated as untrusted description rather "
            "than as any kind of permission. Safe to send every turn - the server decides when it is "
            "worth showing the model."
        ),
        title="Page Context",
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


class ProposedChangeItem(BaseModel):
    """One line of a proposed diff.

    ``status`` uses the same vocabulary as the version-comparison view — ``added`` / ``removed`` /
    ``modified`` — so a proposal reads the same way as a version diff.
    """

    status: str = Field(description="added, removed or modified")
    kind: str = Field(description="What changed: node, edge or workflow")
    logical_id: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)

    model_config = ConfigDict(title="Proposed Change Item")


class ProposalGraph(BaseModel):
    """Enough of a workflow to draw it, and no more.

    Node and edge shapes are deliberately flat and small rather than whole configs: this travels on every
    turn that proposes something, and a narrow panel draws names and connections. The full configuration
    is reachable through the workflow APIs.
    """

    nodes: List[dict] = Field(default_factory=list, description="logical_id, name, type, status")
    edges: List[dict] = Field(default_factory=list, description="logical_id, source, destination, status")

    model_config = ConfigDict(title="Proposal Graph")


class ProposalOutput(BaseOutput):
    """A change the copilot has worked out but not made.

    **Nothing has been written when this is sent.** The client renders it for a person to accept or
    decline, and accepting is a separate request from that person. That is what keeps the copilot's own
    tools read-only while still letting it suggest edits.

    ``proposal_id`` is a lookup key and nothing else. Accepting sends back the id alone, so the change
    applied is by definition the change that was shown, not something the client reassembled.
    """

    type: Literal["proposal"] = Field(
        default=WorkflowCopilotOutputType.PROPOSAL.value,
        description="Type of the workflow copilot output",
        title="Workflow Copilot Output Type",
    )

    proposal_id: str = Field(description="Opaque handle the user's acceptance refers to")
    entity: str = Field(default="workflow", description="What kind of thing would change")
    workflow_id: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None, description="One sentence describing the change")
    changes: List[ProposedChangeItem] = Field(default_factory=list)
    expires_in_seconds: Optional[int] = Field(default=None)
    #: Present when the change can be drawn. Absent is normal, not an error — a rename has no useful graph.
    graph: Optional[ProposalGraph] = Field(default=None)

    model_config = ConfigDict(title="Proposal Output")

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
    TextOutput
    | ButtonsOutput
    | MarkdownOutput
    | CodeOutput
    | WorkflowCardOutput
    | CheckboxesOutput
    | ProposalOutput,
    Field(discriminator="type"),
]


class WorkflowCopilotTurnDoneEvent(BaseModel):
    """Sent once when a turn has finished, so a client knows to stop waiting.

    **A separate top-level event rather than another ``WorkflowCopilotOutput`` variant, on purpose.** A
    turn's answer arrives as several ``WorkflowCopilotEvent`` messages, one per assistant chunk, and
    nothing in that envelope can say "that was the last one". Without this, a client guesses with an idle
    timeout, which is both slow and wrong: a long tool-calling turn looks finished, and a finished turn
    keeps a spinner up.

    It is not a payload type inside ``WorkflowCopilotEvent`` because clients render an unknown payload
    type as a chat bubble, so users would see a literal "done" message until every client had updated. A
    new top-level ``type`` is ignored by clients that do not know it.

    Carries no content: it is a control signal about the turn, not something to display.
    """

    type: Literal["workflow_copilot_done"] = Field(
        default="workflow_copilot_done",
        description="Type of the workflow copilot event",
        title="Workflow Copilot Event Type",
    )

    request_id: Optional[str] = Field(
        default=None,
        description="Identifies the turn that just finished, so a client can match it to the question it asked",
        title="Request ID",
    )

    outcome: Optional[str] = Field(
        default=None,
        description="How the turn ended: 'ok', 'empty' when the model produced no answer, or 'error'",
        title="Turn Outcome",
    )

    model_config = ConfigDict(
        title="Workflow Copilot Turn Done Event",
    )

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
