"""An LLM analysis step: one prompt, one model or LLM group, one output variable."""

from typing import Annotated, Literal, Optional, Union

from pydantic import ConfigDict, Field

from interactly_configs.llm import LLMConfig, UnknownLLMConfig, WorkflowDefaultLLMConfig
from interactly_configs.llm_group import LLMGroupConfig
from interactly_configs.nodes.analysis.base import BaseAnalysisNodeConfig
from interactly_configs.nodes.llm.llm import WorkerLLMNodeConfig
from interactly_configs.nodes.node import NodeType
from interactly_configs.prompt import PromptConfig
from interactly_configs.unknown_types import unknown_type_serializer, unknown_type_validator

# A single model or a group with fallback; the backchannel variant only makes sense while a caller waits.
# Upstream's alias is the discriminated union alone; the two extra entries are the mirror's fallback for a provider
# newer than this package (see `LLMOrGroupConfig`).
AnalysisLLMOrGroupConfig = Annotated[
    Union[LLMConfig, LLMGroupConfig],
    Field(discriminator="type"),
    unknown_type_validator(UnknownLLMConfig),
    unknown_type_serializer(UnknownLLMConfig),
]


class AnalysisWorkerLLMNodeConfig(WorkerLLMNodeConfig):
    """The worker an Analysis LLM step runs as. Built at run time only; never stored or shown in a form."""

    input_message: Optional[str] = Field(
        default=None,
        description="The step's Input, sent as its one user turn so caller speech never sits in the system prompt",
        title="Input",
    )
    isolated: bool = Field(
        default=True,
        description="Leave earlier steps' results out of the request",
        title="Isolated",
    )


class AnalysisLLMNodeConfig(BaseAnalysisNodeConfig):
    type: Literal["analysis_llm"] = Field(
        default=NodeType.ANALYSIS_LLM.value,
        description="Type of the node. Must be 'analysis_llm'",
        title="Node Type",
    )
    main_response_config: Optional[PromptConfig] = Field(
        default=None,
        description=(
            "What to analyse and how: the instructions, sent as the system prompt. Put the call itself in Input."
        ),
        title="Prompt",
    )
    attachable_llm_config_id: Optional[str] = Field(
        default=None,
        description="ID of the named LLM Configuration to use. If provided, overrides the inline configuration.",
        title="Named LLM Configuration",
    )
    llms_config: Optional[AnalysisLLMOrGroupConfig] = Field(
        default=WorkflowDefaultLLMConfig(),
        description="One model, or a group of models tried in order.",
        title="LLM Configuration",
    )
    input_message: Optional[str] = Field(
        default=None,
        description=(
            "What to analyse, sent as the user message: the call, never instructions. Conversation Fetch provides "
            "[[transcript]] (with tool calls when Include Tool Activity is on), [[tool_activity]], "
            "[[assistant_system_prompt]], [[call]], "
            "[[call_duration_seconds]], [[call_context]], [[input_dynamic_variables]], [[current_time]], "
            "[[timezone]], [[dnd_expiration_days]] and [[phi_messages]]."
        ),
        title="Input",
    )
    output_variable: str = Field(
        default="analysis_result",
        description="Runtime variable the result is written to. Store Analysis maps it to an analysis field.",
        title="Output Variable",
    )
    structured_output_schema: Optional[dict] = Field(
        default=None,
        description=(
            "Leave empty for a text result. For a JSON result give a JSON schema object, e.g. "
            '{"type": "object", "properties": {"intent": {"type": "string"}}, "required": ["intent"]}.'
        ),
        title="JSON Output Schema",
    )

    include_earlier_steps: bool = Field(
        default=False,
        description=(
            "Also send the earlier steps' outputs as chat history. Off (the default), the step sends only its "
            "prompt and Input, like each section of the prompt-based analysis; read an earlier result through "
            "its output variable instead (e.g. [[summary]])."
        ),
        title="Include Earlier Steps",
    )
    ignore_default_prompt_prefix: bool = Field(
        default=False,
        description="If true, the workflow's default_prompt_prefix will not be prepended to this node's prompt.",
        title="Ignore Default Prompt Prefix",
    )
    ignore_default_prompt_suffix: bool = Field(
        default=False,
        description="If true, the workflow's default_prompt_suffix will not be appended to this node's prompt.",
        title="Ignore Default Prompt Suffix",
    )

    model_config = ConfigDict(title="Analysis LLM Node")

    def output_schema(self) -> dict:
        """Single-property schema so the result lands in ``output_variable`` whatever its shape."""
        name = self.output_variable
        if self.structured_output_schema:
            inner = dict(self.structured_output_schema.get("input_schema", self.structured_output_schema))
            inner.setdefault("type", "object")
            description = self.structured_output_schema.get("description") or f"The {name} result."
        else:
            inner = {"type": "string"}
            description = f"The {name} result as plain text."
        inner.setdefault("description", description)
        return {
            "name": "AnalysisResult",
            "description": description,
            "input_schema": {"type": "object", "properties": {name: inner}, "required": [name]},
        }

    def to_worker_config(self) -> AnalysisWorkerLLMNodeConfig:
        """The worker LLM node this step runs as; same logical id, so edges and events are unchanged."""
        prompt = self.main_response_config.model_copy() if self.main_response_config else PromptConfig()
        return AnalysisWorkerLLMNodeConfig(
            logical_id=self.logical_id,
            name=self.name,
            description=self.description,
            workflow_id=self.workflow_id,
            version_number=self.version_number,
            disabled=self.disabled,
            miscellaneous=dict(self.miscellaneous or {}),
            input_message=self.input_message,
            isolated=not self.include_earlier_steps,
            is_start=self.is_start,
            main_response_config=prompt,
            attachable_llm_config_id=self.attachable_llm_config_id,
            llms_config=self.llms_config,
            structured_output_schema=self.output_schema(),
            wait_for_user_message=False,
            self_loop=False,
            ignore_default_prompt_prefix=self.ignore_default_prompt_prefix,
            ignore_default_prompt_suffix=self.ignore_default_prompt_suffix,
        )
