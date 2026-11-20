"""Stores chosen runtime variables as the conversation's analysis fields."""

from typing import Dict, Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.analysis.base import ANALYSIS_SECTION_KEYS, BaseAnalysisNodeConfig
from interactly_configs.nodes.node import BaseNodeRunInput, BaseNodeRunOutput, NodeType

_MAP_HINT = "Variable to store, e.g. [[summary_text]]. Leave empty to skip."


class StoreAnalysisNodeConfig(BaseAnalysisNodeConfig):
    type: Literal["store_analysis"] = Field(
        default=NodeType.STORE_ANALYSIS.value,
        description="Type of the node. Must be 'store_analysis'",
        title="Node Type",
    )
    summary: Optional[str] = Field(
        default=None,
        description=_MAP_HINT,
        title="Summary",
    )
    success_evaluation: Optional[str] = Field(
        default=None,
        description=_MAP_HINT,
        title="Success Evaluation",
    )
    structured_data: Optional[str] = Field(
        default=None,
        description=_MAP_HINT + " Must hold a JSON object.",
        title="Structured Data",
    )
    dnd: Optional[str] = Field(
        default=None,
        description=_MAP_HINT + " Expects {status, reason, until}, as the DND preset produces.",
        title="Do Not Disturb",
    )
    callback: Optional[str] = Field(
        default=None,
        description=_MAP_HINT + " Expects {status, reason, when: [{startAt, endAt}]}, as the Callback preset produces.",
        title="Callback",
    )
    outcome: Optional[str] = Field(
        default=None,
        description=_MAP_HINT,
        title="Outcome",
    )
    masked_messages: Optional[str] = Field(
        default=None,
        description=_MAP_HINT
        + " Masks PHI in the stored transcript: expects {messages: [{turn_id, text}]}, as the PHI Mask preset produces.",
        title="Masked Messages",
    )
    extras: Optional[Dict[str, str]] = Field(
        default=None,
        description='Any other fields to store: field name -> variable, e.g. {"sentiment": "[[sentiment]]"}.',
        title="Extra Fields",
    )

    model_config = ConfigDict(title="Store Analysis Node")

    def mappings(self) -> Dict[str, str]:
        """Section key -> variable reference, standard sections first; extras keep their own names."""
        mapped = {key: getattr(self, key) for key in ANALYSIS_SECTION_KEYS if getattr(self, key)}
        return {**mapped, **(self.extras or {})}


class StoreAnalysisNodeRunInput(BaseNodeRunInput):
    type: Literal["store_analysis"] = Field(
        default="store_analysis", description="Discriminator field which must always be 'store_analysis'"
    )


class StoreAnalysisNodeRunOutput(BaseNodeRunOutput):
    type: Literal["store_analysis"] = Field(
        default="store_analysis", description="Discriminator field which must always be 'store_analysis'"
    )
    stored: list = Field(
        default_factory=list, description="Fields stored, or that would be in a dry run", title="Stored"
    )
    skipped: dict = Field(default_factory=dict, description="Field -> why it was not stored", title="Skipped")
    dry_run: bool = Field(default=False, description="True outside post-call analysis", title="Dry Run")
    masking: Optional[str] = Field(
        default=None, description="Masked messages: checked, rejected, completed or failed", title="Masking"
    )
