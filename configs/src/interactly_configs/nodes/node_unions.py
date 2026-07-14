from typing import Annotated, Union

from pydantic import BaseModel, Field

from interactly_configs.nodes.athena.appointments_create import (
    AthenaAppointmentsCreateNodeConfig,
    AthenaAppointmentsCreateNodeRunInput,
    AthenaAppointmentsCreateNodeRunOutput,
)
from interactly_configs.nodes.athena.patients_create import (
    AthenaPatientsCreateNodeConfig,
    AthenaPatientsCreateNodeRunInput,
    AthenaPatientsCreateNodeRunOutput,
)
from interactly_configs.nodes.athena.patients_search import (
    AthenaPatientsSearchNodeConfig,
    AthenaPatientsSearchNodeRunInput,
    AthenaPatientsSearchNodeRunOutput,
)
from interactly_configs.nodes.athena.patients_update import (
    AthenaPatientsUpdateNodeConfig,
    AthenaPatientsUpdateNodeRunInput,
    AthenaPatientsUpdateNodeRunOutput,
)
from interactly_configs.nodes.communications.sms import (
    SendSMSNodeConfig,
    SendSMSNodeRunInput,
    SendSMSNodeRunOutput,
)
from interactly_configs.nodes.data_transformation.deduplicate import (
    DeduplicateNodeConfig,
    DeduplicateNodeRunInput,
    DeduplicateNodeRunOutput,
)
from interactly_configs.nodes.data_transformation.field_extractor import (
    FieldExtractorNodeConfig,
    FieldExtractorNodeRunInput,
    FieldExtractorNodeRunOutput,
)
from interactly_configs.nodes.conversations.end_conversation import (
    EndConversationNodeConfig,
    EndConversationNodeRunInput,
    EndConversationNodeRunOutput,
)
from interactly_configs.nodes.conversations.start_conversation import (
    StartConversationNodeConfig,
    StartConversationNodeRunInput,
    StartConversationNodeRunOutput,
)
from interactly_configs.nodes.google_workspace.google_docs import (
    GoogleDocsNodeConfig,
    GoogleDocsNodeRunInput,
    GoogleDocsNodeRunOutput,
)
from interactly_configs.nodes.llm.llm import (
    LLMNodeRunInput,
    SayLLMNodeConfig,
    SayLLMNodeRunOutput,
    WorkerLLMNodeConfig,
    WorkerLLMNodeRunOutput,
)
from interactly_configs.nodes.node import BaseNodeRunInput, NodeType
from interactly_configs.nodes.rest_api.http_request import (
    HttpRequestNodeConfig,
    HttpRequestNodeRunInput,
    HttpRequestNodeRunOutput,
)
from interactly_configs.nodes.static_messages.static_message import (
    SayStaticMessageNodeConfig,
    SayStaticMessageNodeRunInput,
    SayStaticMessageNodeRunOutput,
)
from interactly_configs.nodes.super_nodes.super_node import (
    SuperNodeConfig,
    SuperNodeRunInput,
    SuperNodeRunOutput,
)
from interactly_configs.nodes.tool.tool_node import (
    ToolNodeConfig,
    ToolNodeRunInput,
    ToolNodeRunOutput,
)
from interactly_configs.nodes.workflows.workflow_run_evaluator import (
    WorkflowRunEvalLLMNodeConfig,
    WorkflowRunEvalLLMNodeRunInput,
    WorkflowRunEvalLLMNodeRunOutput,
)
from interactly_configs.nodes.workflows.workflow_run_fetch import (
    WorkflowRunFetchNodeConfig,
    WorkflowRunFetchNodeRunInput,
    WorkflowRunFetchNodeRunOutput,
)

NodeConfig = Annotated[
    Union[
        # System nodes
        WorkerLLMNodeConfig,
        SayLLMNodeConfig,  # LLM nodes
        SayStaticMessageNodeConfig,  # Static message nodes
        SuperNodeConfig,  # Super nodes
        WorkflowRunFetchNodeConfig,  # Workflow Run Fetch nodes
        WorkflowRunEvalLLMNodeConfig,  # Evaluator nodes
        ToolNodeConfig,  # Tool nodes
        # Conversation nodes
        StartConversationNodeConfig,
        EndConversationNodeConfig,
        # Communication nodes
        SendSMSNodeConfig,
        # Google Workspace nodes
        GoogleDocsNodeConfig,
        # REST API nodes
        HttpRequestNodeConfig,
        # Athena Nodes
        AthenaPatientsSearchNodeConfig,
        AthenaPatientsCreateNodeConfig,
        AthenaPatientsUpdateNodeConfig,
        AthenaAppointmentsCreateNodeConfig,
        # Data Transformation nodes
        DeduplicateNodeConfig,
        FieldExtractorNodeConfig,
    ],
    Field(discriminator="type"),
]

NodeRunInput = Annotated[
    Union[
        # System nodes
        BaseNodeRunInput,
        LLMNodeRunInput,  # LLM nodes
        SayStaticMessageNodeRunInput,  # Static message nodes
        SuperNodeRunInput,  # Super nodes
        WorkflowRunFetchNodeRunInput,  # Workflow Run Fetch nodes
        WorkflowRunEvalLLMNodeRunInput,  # Evaluator nodes
        ToolNodeRunInput,  # Tool nodes
        # Conversation nodes
        StartConversationNodeRunInput,
        EndConversationNodeRunInput,
        # Communication nodes
        SendSMSNodeRunInput,  # SMS nodes
        # Google Workspace nodes
        GoogleDocsNodeRunInput,  # Google Docs nodes
        # Rest API nodes
        HttpRequestNodeRunInput,
        # Athena nodes
        AthenaPatientsSearchNodeRunInput,
        AthenaPatientsCreateNodeRunInput,
        AthenaPatientsUpdateNodeRunInput,
        AthenaAppointmentsCreateNodeRunInput,
        # Data Transformation nodes
        DeduplicateNodeRunInput,
        FieldExtractorNodeRunInput,
    ],
    Field(discriminator="type"),
]

NodeRunOutput = Annotated[
    Union[
        # System nodes
        WorkerLLMNodeRunOutput,
        SayLLMNodeRunOutput,  # LLM nodes
        SayStaticMessageNodeRunOutput,  # Static message nodes
        SuperNodeRunOutput,  # Super nodes
        WorkflowRunFetchNodeRunOutput,  # Workflow Run Fetch nodes
        WorkflowRunEvalLLMNodeRunOutput,  # Evaluator nodes
        ToolNodeRunOutput,  # Tool nodes
        # Conversation nodes
        StartConversationNodeRunOutput,
        EndConversationNodeRunOutput,
        # Communication nodes
        SendSMSNodeRunOutput,  # SMS nodes
        # Google Workspace nodes
        GoogleDocsNodeRunOutput,  # Google Docs nodes
        # REST API nodes
        HttpRequestNodeRunOutput,
        # Athena nodes
        AthenaPatientsSearchNodeRunOutput,
        AthenaPatientsCreateNodeRunOutput,
        AthenaPatientsUpdateNodeRunOutput,
        AthenaAppointmentsCreateNodeRunOutput,
        # Data Transformation nodes
        DeduplicateNodeRunOutput,
        FieldExtractorNodeRunOutput,
    ],
    Field(discriminator="type"),
]

class NodesRunInputs(BaseModel):
    """
    Represents the run inputs for multiple nodes in a workflow.
    """

    node_run_inputs: list[NodeRunInput] = Field(
        default_factory=list,
        description="Mapping of node logical IDs to their respective run inputs",
        title="Node Run Inputs",
    )

class NodeMetadataRetriever:
    """
    Class to retrieve metadata for nodes based on their type.
    """

    @classmethod
    def get_type_to_default_config_map(cls) -> dict[NodeType, NodeConfig]:
        """
        Returns a mapping of node types to their respective configuration classes.
        """
        return {
            # System nodes
            NodeType.SAY_LLM: SayLLMNodeConfig(),
            NodeType.WORKER_LLM: WorkerLLMNodeConfig(),
            NodeType.SUPER_NODE: SuperNodeConfig(),
            NodeType.SAY_STATIC: SayStaticMessageNodeConfig(),
            NodeType.WORKFLOW_RUN_FETCH: WorkflowRunFetchNodeConfig(),
            NodeType.WORKFLOW_RUN_EVALUATOR: WorkflowRunEvalLLMNodeConfig(),
            NodeType.TOOL_NODE: ToolNodeConfig(),
            # Conversation nodes
            NodeType.START_CONVERSATION: StartConversationNodeConfig(),
            NodeType.END_CONVERSATION: EndConversationNodeConfig(),
            # Communication nodes
            NodeType.SEND_SMS: SendSMSNodeConfig(),
            # Google Workspace nodes
            NodeType.GOOGLE_DOCS: GoogleDocsNodeConfig(),
            # REST API nodes
            NodeType.HTTP_REQUEST: HttpRequestNodeConfig(),
            # Athena nodes
            NodeType.ATHENA_PATIENTS_SEARCH: AthenaPatientsSearchNodeConfig(),
            NodeType.ATHENA_PATIENTS_CREATE: AthenaPatientsCreateNodeConfig(),
            NodeType.ATHENA_PATIENTS_UPDATE: AthenaPatientsUpdateNodeConfig(),
            NodeType.ATHENA_APPOINTMENTS_CREATE: AthenaAppointmentsCreateNodeConfig(),
            # Data Transformation nodes
            NodeType.DEDUPLICATE: DeduplicateNodeConfig(),
            NodeType.FIELD_EXTRACTOR: FieldExtractorNodeConfig(),
        }

    @classmethod
    def get_type_to_config_class_map(cls) -> dict[NodeType, type[NodeConfig]]:
        """
        Returns a mapping of node types to their respective configuration classes.
        """
        return {
            # System nodes
            NodeType.SAY_LLM: SayLLMNodeConfig,
            NodeType.WORKER_LLM: WorkerLLMNodeConfig,
            NodeType.SUPER_NODE: SuperNodeConfig,
            NodeType.SAY_STATIC: SayStaticMessageNodeConfig,
            NodeType.WORKFLOW_RUN_FETCH: WorkflowRunFetchNodeConfig,
            NodeType.WORKFLOW_RUN_EVALUATOR: WorkflowRunEvalLLMNodeConfig,
            NodeType.TOOL_NODE: ToolNodeConfig,
            # Conversation nodes
            NodeType.START_CONVERSATION: StartConversationNodeConfig,
            NodeType.END_CONVERSATION: EndConversationNodeConfig,
            # Communication nodes
            NodeType.SEND_SMS: SendSMSNodeConfig,
            # Google Workspace nodes
            NodeType.GOOGLE_DOCS: GoogleDocsNodeConfig,
            # REST API nodes
            NodeType.HTTP_REQUEST: HttpRequestNodeConfig,
            # Athena nodes
            NodeType.ATHENA_PATIENTS_SEARCH: AthenaPatientsSearchNodeConfig,
            NodeType.ATHENA_PATIENTS_CREATE: AthenaPatientsCreateNodeConfig,
            NodeType.ATHENA_PATIENTS_UPDATE: AthenaPatientsUpdateNodeConfig,
            NodeType.ATHENA_APPOINTMENTS_CREATE: AthenaAppointmentsCreateNodeConfig,
            # Data Transformation nodes
            NodeType.DEDUPLICATE: DeduplicateNodeConfig,
            NodeType.FIELD_EXTRACTOR: FieldExtractorNodeConfig,
        }

    @classmethod
    def get_type_to_run_input_class_map(cls):
        """
        Returns a mapping of node types to their respective run-input classes.
        """
        return {
            # System nodes
            NodeType.SAY_LLM: LLMNodeRunInput,
            NodeType.WORKER_LLM: LLMNodeRunInput,
            NodeType.SUPER_NODE: SuperNodeRunInput,
            NodeType.SAY_STATIC: SayStaticMessageNodeRunInput,
            NodeType.WORKFLOW_RUN_FETCH: WorkflowRunFetchNodeRunInput,
            NodeType.WORKFLOW_RUN_EVALUATOR: WorkflowRunEvalLLMNodeRunInput,
            NodeType.TOOL_NODE: ToolNodeRunInput,
            # Conversation nodes
            NodeType.START_CONVERSATION: StartConversationNodeRunInput,
            NodeType.END_CONVERSATION: EndConversationNodeRunInput,
            # Communication nodes
            NodeType.SEND_SMS: SendSMSNodeRunInput,
            # Google Workspace nodes
            NodeType.GOOGLE_DOCS: GoogleDocsNodeRunInput,
            # REST API nodes
            NodeType.HTTP_REQUEST: HttpRequestNodeRunInput,
            # Athena nodes
            NodeType.ATHENA_PATIENTS_SEARCH: AthenaPatientsSearchNodeRunInput,
            NodeType.ATHENA_PATIENTS_CREATE: AthenaPatientsCreateNodeRunInput,
            NodeType.ATHENA_PATIENTS_UPDATE: AthenaPatientsUpdateNodeRunInput,
            NodeType.ATHENA_APPOINTMENTS_CREATE: AthenaAppointmentsCreateNodeRunInput,
            # Data Transformation nodes
            NodeType.DEDUPLICATE: DeduplicateNodeRunInput,
            NodeType.FIELD_EXTRACTOR: FieldExtractorNodeRunInput,
        }

    @classmethod
    def get_type_to_run_output_class_map(cls):
        """
        Returns a mapping of node types to their respective run-output classes.
        """
        return {
            # System nodes
            NodeType.SAY_LLM: SayLLMNodeRunOutput,
            NodeType.WORKER_LLM: WorkerLLMNodeRunOutput,
            NodeType.SUPER_NODE: SuperNodeRunOutput,
            NodeType.SAY_STATIC: SayStaticMessageNodeRunOutput,
            NodeType.WORKFLOW_RUN_FETCH: WorkflowRunFetchNodeRunOutput,
            NodeType.WORKFLOW_RUN_EVALUATOR: WorkflowRunEvalLLMNodeRunOutput,
            NodeType.TOOL_NODE: ToolNodeRunOutput,
            # Conversation nodes
            NodeType.START_CONVERSATION: StartConversationNodeRunOutput,
            NodeType.END_CONVERSATION: EndConversationNodeRunOutput,
            # Communication nodes
            NodeType.SEND_SMS: SendSMSNodeRunOutput,
            # Google Workspace nodes
            NodeType.GOOGLE_DOCS: GoogleDocsNodeRunOutput,
            # REST API nodes
            NodeType.HTTP_REQUEST: HttpRequestNodeRunOutput,
            # Athena nodes
            NodeType.ATHENA_PATIENTS_SEARCH: AthenaPatientsSearchNodeRunOutput,
            NodeType.ATHENA_PATIENTS_CREATE: AthenaPatientsCreateNodeRunOutput,
            NodeType.ATHENA_PATIENTS_UPDATE: AthenaPatientsUpdateNodeRunOutput,
            NodeType.ATHENA_APPOINTMENTS_CREATE: AthenaAppointmentsCreateNodeRunOutput,
            # Data Transformation nodes
            NodeType.DEDUPLICATE: DeduplicateNodeRunOutput,
            NodeType.FIELD_EXTRACTOR: FieldExtractorNodeRunOutput,
        }
