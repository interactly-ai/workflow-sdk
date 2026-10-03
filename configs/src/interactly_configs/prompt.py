"""Prompt and message configuration models."""

from typing import List, Optional

from pydantic import BaseModel, Field

from interactly_configs.llm_group import SelectionMode


class PromptConfig(BaseModel):
    """LLM system prompt configuration."""

    prompt: Optional[str] = Field(
        default=None,
        description="System prompt for the LLM",
        title="System Prompt",
    )


class StaticMessagesConfig(BaseModel):
    """A list of pre-configured messages — one is selected and emitted."""

    # `default=[]`, not `default_factory=list`: identical at runtime (Pydantic v2 deep-copies a mutable
    # default per instance), but only the literal is published in the JSON Schema. See
    # `BaseToolConfig.variable_arguments`.
    static_messages: List[str] = Field(
        default=[],
        description="List of pre-configured messages from which one will be emitted",
        title="Static Messages",
    )
    static_messages_selection_mode: Optional[SelectionMode] = Field(
        default=SelectionMode.RANDOM,
        description="Selection mode for static messages",
        title="Static Messages Selection Mode",
    )


class DynamicMessagesConfig(BaseModel):
    """Configuration for LLM-generated in-flight messages (e.g. on a conditional edge)."""

    dynamic_message_prompt: Optional[str] = Field(
        default=None,
        description=(
            "A prompt describing what the LLM should say when this conditional edge is taken. "
            "The LLM will be asked to fill in a value based on this prompt, and the result will "
            "be emitted as an assistant response."
        ),
        title="Dynamic Message Prompt",
    )
