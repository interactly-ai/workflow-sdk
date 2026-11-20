"""A Decisions step: typed questions answered by a model, each answer a runtime variable."""

import re
from enum import Enum
from typing import List, Literal, NamedTuple, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from interactly_configs.llm import OpenAILLMConfig, OPENAIModel
from interactly_configs.nodes.analysis.analysis_llm import (
    AnalysisLLMOrGroupConfig,
    AnalysisWorkerLLMNodeConfig,
)
from interactly_configs.nodes.node import (
    BaseNodeConfig,
    GlobalNodeConfig,
    NodeCategory,
    NodeType,
    SelfLoopConfig,
)
from interactly_configs.prompt import PromptConfig

# The key the questions ride under on the worker's output schema; a chat model ignores it.
DECISIONS_QUESTIONS_KEY = "x_decisions_questions"
# Written by the step beside its answers: "model" when a model answered, "failed" when none did.
DECISION_SOURCE_VARIABLE = "decision_source"
DECISION_ERROR_VARIABLE = "decision_error"
MAX_QUESTIONS = 400  # the Decisions API's limit
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def answer_variables(questions) -> List[str]:
    """Every variable a run can write for these questions."""
    return [question.name + suffix for question in questions for suffix in ("", *_WRITTEN_BESIDE[question.type])]


class DecisionsStepProblem(NamedTuple):
    code: str
    message: str
    node_logical_id: str
    node_name: Optional[str]
    edge_logical_id: Optional[str] = None


def decisions_step_problems(node_configs, edge_configs) -> List[DecisionsStepProblem]:
    """What a workflow asks of its Decisions steps that they cannot do: ask nothing, be a global node, run in a loop,
    be a guardrail node, or choose a route.

    A Decisions step is given no tools on any model, and a freeform edge and a global node's way back are tools.
    """
    steps = {node.logical_id: node for node in node_configs if getattr(node, "type", None) == NodeType.DECISIONS.value}
    names = {node.logical_id: node.name for node in node_configs}
    problems = []
    for step in steps.values():
        if not step.questions:
            message = f"Decisions step {step.name}: it has no questions. Add at least one."
            problems.append(DecisionsStepProblem("decisions_no_questions", message, step.logical_id, step.name))
        marked = getattr(step, "global_node_config", None)
        if marked is not None and marked.is_global:
            message = (
                f"Decisions step {step.name}: it is marked as a global node. A Decisions step cannot be one. "
                "Reach it through an edge."
            )
            problems.append(DecisionsStepProblem("decisions_global_node", message, step.logical_id, step.name))
        elif marked is not None and marked.reverse_conditional_edge:
            message = (
                f"Decisions step {step.name}: it has a reverse conditional edge, a global node's way back. "
                "A Decisions step cannot have one. Remove it, and route on its answers with an expression edge."
            )
            problems.append(DecisionsStepProblem("decisions_global_node", message, step.logical_id, step.name))
        loop = getattr(step, "self_loop_config", None)
        if loop is not None and loop.enabled:
            message = (
                f"Decisions step {step.name}: it runs in a loop (Self Loop is on). A Decisions step runs once each "
                "time it is reached. Turn Self Loop off."
            )
            problems.append(DecisionsStepProblem("decisions_self_loop", message, step.logical_id, step.name))
        if getattr(step, "is_guardrail_node", False):
            message = (
                f"Decisions step {step.name}: it is marked as a guardrail node. A Decisions step cannot be one. "
                "Unmark it."
            )
            problems.append(DecisionsStepProblem("decisions_guardrail_node", message, step.logical_id, step.name))
    for edge in edge_configs:
        step = steps.get(getattr(edge, "source_node_logical_id", None))
        freeform = getattr(getattr(edge, "condition", None), "condition_freeform", None)
        if step is None or not freeform or getattr(edge, "disabled", False):
            continue
        destination = names.get(edge.destination_node_logical_id) or edge.destination_node_logical_id
        message = (
            f"Decisions step {step.name}: the edge to {destination} has a freeform condition. "
            "A Decisions step cannot choose a route. Use an expression on its answers."
        )
        problems.append(
            DecisionsStepProblem("decisions_freeform_edge", message, step.logical_id, step.name, edge.logical_id)
        )
    return problems


def decisions_step_rejection(node_configs, edge_configs=()) -> Optional[str]:
    """The message to refuse a save with, or None when the Decisions steps can run as drawn.

    For every place a workflow, a node or an edge is saved. Saved as drawn, the step's runtime refuses to build,
    and then every run of the workflow fails at its start, not only that step.
    """
    return " ".join(problem.message for problem in decisions_step_problems(node_configs, edge_configs)) or None


class DecisionQuestionType(str, Enum):
    YES_NO = "yes_no"
    CHOICE = "choice"
    SCORE = "score"


# What an answer on a Decisions API writes beside each type's answer (parse_answers writes them).
_WRITTEN_BESIDE = {
    DecisionQuestionType.YES_NO: ("_probability",),
    DecisionQuestionType.CHOICE: ("_confidence",),
    DecisionQuestionType.SCORE: ("_score", "_confidence"),
}
# A question of any type, in this step or another, may write one, so no question's name may end in any of them.
_RESERVED_SUFFIXES = tuple(sorted({suffix for suffixes in _WRITTEN_BESIDE.values() for suffix in suffixes}))


class DecisionChoice(BaseModel):
    value: str = Field(description="The value stored when this choice is picked.", title="Value", min_length=1)
    description: Optional[str] = Field(
        default=None, description="When to pick this choice. The model reads it.", title="Description"
    )


class DecisionLevel(BaseModel):
    label: str = Field(description="The value stored when the answer lands on this level.", title="Label", min_length=1)
    description: Optional[str] = Field(
        default=None, description="What this level means. The model reads it.", title="Description"
    )


class DecisionQuestion(BaseModel):
    name: str = Field(description="The runtime variable the answer is written to.", title="Name")
    type: DecisionQuestionType = Field(
        default=DecisionQuestionType.YES_NO,
        description="yes_no gives true or false, choice gives one of the choices, score gives one of the levels.",
        title="Type",
    )
    instructions: str = Field(
        description="What is being asked, in one or two plain sentences.",
        title="Instructions",
        min_length=1,
    )
    choices: List[DecisionChoice] = Field(
        default_factory=list, description="For a choice question: at least two choices.", title="Choices"
    )
    threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="For a yes_no question: the probability at or above which the answer is true.",
        title="Threshold",
    )
    levels: List[DecisionLevel] = Field(
        default_factory=list,
        description="For a score question: two to ten levels, ordered from lowest to highest.",
        title="Levels",
    )

    @field_validator("name")
    @classmethod
    def _name_is_a_variable(cls, name: str) -> str:
        if not _NAME.match(name):
            raise ValueError(
                f"'{name}' is not a variable name: letters, digits and underscores, not starting with a digit"
            )
        if name.endswith(_RESERVED_SUFFIXES) or name in (DECISION_SOURCE_VARIABLE, DECISION_ERROR_VARIABLE):
            raise ValueError(f"'{name}' is reserved for what the step writes beside its answers")
        return name

    @model_validator(mode="after")
    def _choices_fit_the_type(self):
        if self.type == DecisionQuestionType.CHOICE:
            values = [choice.value for choice in self.choices]
            if len(values) < 2:
                raise ValueError(f"'{self.name}' is a choice question and needs at least two choices")
            if len(set(values)) != len(values):
                raise ValueError(f"'{self.name}' has the same choice twice")
        if self.type == DecisionQuestionType.SCORE:
            labels = [level.label for level in self.levels]
            if not 2 <= len(labels) <= 10:
                raise ValueError(f"'{self.name}' is a score question and needs two to ten levels, lowest first")
            if len(set(labels)) != len(labels):
                raise ValueError(f"'{self.name}' has the same level twice")
        return self

    def json_schema(self) -> dict:
        """The question as a JSON Schema property, for a chat model."""
        if self.type == DecisionQuestionType.YES_NO:
            return {"type": "boolean", "description": self.instructions}
        if self.type == DecisionQuestionType.SCORE:
            options = [(level.label, level.description) for level in self.levels]
            # every level, in order: the order is what the levels mean, described or not
            lines = [f"{label}: {description}" if description else label for label, description in options]
            description = self.instructions + "\nLevels, lowest to highest:\n" + "\n".join(lines)
        else:
            options = [(choice.value, choice.description) for choice in self.choices]
            described = [f"{value}: {description}" for value, description in options if description]
            description = self.instructions + ("\n" + "\n".join(described) if described else "")
        return {"type": "string", "enum": [value for value, _ in options], "description": description}


class DecisionsWorkerLLMNodeConfig(AnalysisWorkerLLMNodeConfig):
    """The worker a Decisions step runs as. Built at run time only; never stored or shown in a form."""

    questions: List[DecisionQuestion] = Field(
        default_factory=list,
        description="The step's questions",
        title="Questions",
    )


class DecisionsNodeConfig(BaseNodeConfig):
    type: Literal["decisions"] = Field(
        default=NodeType.DECISIONS.value,
        description="Type of the node. Must be 'decisions'",
        title="Node Type",
    )
    # Grouped with the worker LLM node it runs as. Not Analysis: that palette group is for evaluation workflows only.
    primary_category: Optional[str] = Field(
        default=NodeCategory.SYSTEM.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.LLM.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    is_guardrail_node: bool = Field(
        default=False,
        description="A Decisions step is never a guardrail node.",
        title="Is Guardrail Node",
    )
    global_node_config: Optional[GlobalNodeConfig] = Field(
        default=None,
        description="A Decisions step is never a global node.",
        title="Global Node Configuration",
    )
    self_loop_config: Optional[SelfLoopConfig] = Field(
        default=None,
        description="A Decisions step runs once.",
        title="Self Loop",
    )
    main_response_config: Optional[PromptConfig] = Field(
        default=None,
        description="The rules the questions are answered by, sent as the system prompt. Keep it the same on every "
        "run so it is cached; put what changes in Input.",
        title="Prompt",
    )
    input_message: Optional[str] = Field(
        default=None,
        description="What to decide on, sent as the user message: for example the caller's latest words and the "
        "state of the request, through [[variables]].",
        title="Input",
    )
    questions: List[DecisionQuestion] = Field(
        default_factory=list,
        description="The questions. Each answer is written to the variable its name gives. Answered on a Decisions "
        "API, a yes_no answer also writes <name>_probability, a choice answer <name>_confidence, and a score answer "
        "<name>_score (its position between the levels, from 0) and <name>_confidence.",
        title="Questions",
    )
    attachable_llm_config_id: Optional[str] = Field(
        default=None,
        description="ID of the named LLM Configuration to use. If provided, overrides the inline configuration.",
        title="Named LLM Configuration",
    )
    llms_config: Optional[AnalysisLLMOrGroupConfig] = Field(
        default_factory=lambda: OpenAILLMConfig(model=OPENAIModel.GPT_6_LUNA),
        description="Any model, or a group of models. A chat model answers the questions as JSON. A decisions model "
        "answers on its vendor's Decisions API instead, with probabilities. A Decisions API request is given 2 "
        "seconds in all on a live conversation and 30 seconds off one, its retries included, unless the model's "
        "Request Timeout says otherwise.",
        title="LLM Configuration",
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

    model_config = ConfigDict(title="Decisions Node")

    @field_validator("questions")
    @classmethod
    def _questions_are_distinct(cls, questions: List[DecisionQuestion]) -> List[DecisionQuestion]:
        if len(questions) > MAX_QUESTIONS:
            raise ValueError(f"a Decisions step takes at most {MAX_QUESTIONS} questions, not {len(questions)}")
        names = [question.name for question in questions]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"question names must differ: {', '.join(repeated)}")
        return questions

    def output_schema(self) -> dict:
        """The answers as a JSON Schema a chat model can fill. The questions ride beside it, for a Decisions API."""
        return {
            "name": "Decisions",
            "description": "The answer to each question.",
            "input_schema": {
                "type": "object",
                "properties": {question.name: question.json_schema() for question in self.questions},
                "required": [question.name for question in self.questions],
            },
            DECISIONS_QUESTIONS_KEY: [question.model_dump(mode="json") for question in self.questions],
        }

    def to_worker_config(self) -> DecisionsWorkerLLMNodeConfig:
        """The worker LLM node this step runs as; same logical id, so edges and events are unchanged."""
        prompt = self.main_response_config.model_copy() if self.main_response_config else PromptConfig()
        return DecisionsWorkerLLMNodeConfig(
            logical_id=self.logical_id,
            name=self.name,
            description=self.description,
            workflow_id=self.workflow_id,
            version_number=self.version_number,
            disabled=self.disabled,
            miscellaneous=dict(self.miscellaneous or {}),
            input_message=self.input_message,
            isolated=True,
            is_start=self.is_start,
            main_response_config=prompt,
            attachable_llm_config_id=self.attachable_llm_config_id,
            llms_config=self.llms_config,
            # a Decisions step answers questions and is given no tools, on any model
            ignore_global_tools=True,
            structured_output_schema=self.output_schema(),
            questions=list(self.questions),
            wait_for_user_message=False,
            self_loop=False,
            ignore_default_prompt_prefix=self.ignore_default_prompt_prefix,
            ignore_default_prompt_suffix=self.ignore_default_prompt_suffix,
        )
