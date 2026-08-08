import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 9 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_9.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_9.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import LLMNodeRunInput, SayLLMNodeConfig
from interactly.configs import GlobalNodeConfig
from interactly.configs import NodesRunInputs
from interactly.configs import SayStaticMessageNodeConfig
from interactly.configs import PromptConfig, StaticMessagesConfig
from interactly.configs import InlinePythonToolConfig, ToolsConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a patient triage workflow that demonstrates tool static messages and tool result runtime variables.

    This workflow showcases:
    1. Tool static messages - Providing user feedback while tools execute
    2. Tool result runtime variables - Storing tool results for use in downstream nodes
    3. Conditional branching based on tool results
    4. Using runtime variables in prompts of destination nodes
    """

    openai_llm_config_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=30,
        temperature=0.5,
        do_not_split_sentences=True,
    )
    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.s79l1rlsuisu"
    )

    workflow_description = f"""
    This workflow introduces two advanced features that enhance user experience and enable cross-node data flow: Tool Static Messages and Tool Result Runtime Variables. 
    Static messages provide user feedback during tool execution ("Analyzing your symptoms..."), while runtime variables store tool results for use in downstream agents. 
    The example demonstrates a patient triage workflow where symptom assessment results are stored and used by specialized care path agents.

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 9: Patient Triage with Tool Static Messages and Runtime Variables",
        description=workflow_description,
        llms_config=openai_llm_config,
        default_prompt_prefix=GLOBAL_PROMPT_PREFIX,
        default_prompt_suffix=GLOBAL_PROMPT_SUFFIX,
    )

    ############# TOOL CONFIGS BELOW #############

    # Define inline Python tools with static messages and result runtime variables
    patient_assessment_tools = ToolsConfig(
        tools=[
            # Tool 1: Assess patient symptoms with STATIC MESSAGES and RUNTIME VARIABLE
            InlinePythonToolConfig(
                name="assess_patient_symptoms",
                signature="Analyze patient symptoms and determine urgency level and recommended care path",
                args_schema={
                    "type": "object",
                    "properties": {
                        "symptoms": {"type": "string", "description": "Description of patient symptoms"},
                        "duration": {"type": "string", "description": "How long the symptoms have been present"},
                        "severity": {
                            "type": "string",
                            "description": "Patient's description of severity (mild, moderate, severe)",
                            "enum": ["mild", "moderate", "severe"],
                        },
                    },
                    "required": ["symptoms", "duration", "severity"],
                },
                # IMPORTANT: Static messages for user feedback during tool execution
                static_messages_config=StaticMessagesConfig(
                    static_messages=[
                        "Let me analyze your symptoms...",
                        "Evaluating your condition...",
                        "Assessing the urgency of your case...",
                    ]
                ),
                # IMPORTANT: Runtime variable to store the assessment result
                result_runtime_variable_name="patient_assessment_result",
                code="""
def assess_patient_symptoms(symptoms: str, duration: str, severity: str) -> dict:
    '''Assess symptoms and return urgency level with care recommendations'''
    symptoms_lower = symptoms.lower()
    
    # Define emergency keywords
    emergency_keywords = [
        "chest pain", "difficulty breathing", "severe bleeding", 
        "stroke", "unconscious", "seizure", "severe headache",
        "sudden vision loss", "severe abdominal pain"
    ]
    
    # Define urgent care keywords
    urgent_keywords = [
        "fever", "vomiting", "diarrhea", "sprain", "cut",
        "burn", "infection", "pain", "rash"
    ]
    
    # Check for emergency conditions
    is_emergency = any(keyword in symptoms_lower for keyword in emergency_keywords)
    is_urgent = any(keyword in symptoms_lower for keyword in urgent_keywords)
    
    if is_emergency or severity == "severe":
        return {
            "urgency_level": "EMERGENCY",
            "care_path": "emergency_room",
            "wait_time": "immediate",
            "recommendation": "Seek emergency care immediately - call 911 or go to nearest ER",
            "symptoms_summary": symptoms,
            "severity": severity,
            "duration": duration
        }
    elif is_urgent or severity == "moderate":
        return {
            "urgency_level": "URGENT",
            "care_path": "urgent_care",
            "wait_time": "within 24 hours",
            "recommendation": "Visit urgent care or schedule same-day appointment",
            "symptoms_summary": symptoms,
            "severity": severity,
            "duration": duration
        }
    else:
        return {
            "urgency_level": "ROUTINE",
            "care_path": "primary_care",
            "wait_time": "within 1-2 weeks",
            "recommendation": "Schedule routine appointment with your primary care provider",
            "symptoms_summary": symptoms,
            "severity": severity,
            "duration": duration
        }
""",
            ),
        ]
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_NODE_PROMPT = """
    Welcome the patient warmly in less than 15 words. 
    Let them know you're here to help assess their symptoms and guide them to the right care.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Welcome node that greets the patient and explains the triage process",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    TRIAGE_ASSESSMENT_PROMPT = """
    You are a compassionate Virtual Triage Agent helping patients get the right care.

    YOUR SPECIFIC ROLE:
    1. Gather information about patient symptoms in a conversational way
    2. Use the assess_patient_symptoms tool to determine urgency
    3. Provide clear guidance based on the assessment

    GATHERING INFORMATION:
    Ask about:
    - What symptoms they're experiencing
    - How long they've had these symptoms
    - How severe the symptoms are (mild, moderate, severe)

    IMPORTANT - TOOL USAGE:
    - Once you have symptoms, duration, and severity, ALWAYS call assess_patient_symptoms
    - The tool will show a "Let me analyze..." message while it works
    - Use the tool result to guide your response

    SAFETY:
    - If symptoms sound severe or life-threatening, immediately recommend emergency care
    - Never provide medical diagnoses or treatment advice
    - Always defer to the tool's assessment for urgency determination
    """

    triage_assessment_node = SayLLMNodeConfig(
        name="Triage Assessment",
        description="Initial triage node that assesses patient symptoms using tools with static messages",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=TRIAGE_ASSESSMENT_PROMPT),
        llms_config=openai_llm_config,
        tools_config=patient_assessment_tools,
        max_consecutive_tool_calls=3,
    )

    # EMERGENCY CARE NODE - uses runtime variable [[patient_assessment_result]]
    EMERGENCY_CARE_PROMPT = """
    You are an internal agent handling an EMERGENCY case, and specialized in providing immediate care instructions.
    
    You have been given the following assessment about the patient's condition:
    Urgency Level: [[patient_assessment_result.urgency_level]]
    Symptoms: [[patient_assessment_result.symptoms_summary]]
    Recommendation: [[patient_assessment_result.recommendation]]
    
    CRITICAL INSTRUCTIONS:
    1. Immediately emphasize the urgency
    2. Provide clear emergency instructions (call 911 or go to ER)
    3. Do NOT schedule appointments - this is an emergency
    4. Reassure the patient that emergency care is available 24/7
    """

    emergency_care_node = SayLLMNodeConfig(
        name="Emergency Care",
        description="Handles emergency cases with immediate care instructions - uses patient_assessment_result runtime variable",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=EMERGENCY_CARE_PROMPT),
        llms_config=openai_llm_config,
    )

    # URGENT CARE NODE - uses runtime variable [[patient_assessment_result]]
    URGENT_CARE_PROMPT = """
    You are an internal agent handling an URGENT care case, specialized in being supportive and efficient.
    
    You have been given the following assessment about the patient's condition:
    Urgency Level: [[patient_assessment_result.urgency_level]]
    Symptoms: [[patient_assessment_result.symptoms_summary]]
    Duration: [[patient_assessment_result.duration]]
    Recommendation: [[patient_assessment_result.recommendation]]
    
    YOUR TASKS:
    1. Acknowledge their symptoms with empathy
    2. Explain that urgent care is the right level of service
    
    Be supportive and help them get care quickly (within 24 hours).
    """

    urgent_care_node = SayLLMNodeConfig(
        name="Urgent Care",
        description="Handles urgent care cases and helps schedule same-day appointments - uses patient_assessment_result runtime variable",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=URGENT_CARE_PROMPT),
        llms_config=openai_llm_config,
        tools_config=patient_assessment_tools,
        max_consecutive_tool_calls=2,
    )

    # ROUTINE CARE NODE - uses runtime variable [[patient_assessment_result]]
    ROUTINE_CARE_PROMPT = """
    You are an internal agent handling a ROUTINE care case, specialized in being reassuring and helpful.
    
    Based on the assessment:
    Urgency Level: [[patient_assessment_result.urgency_level]]
    Symptoms: [[patient_assessment_result.symptoms_summary]]
    Recommendation: [[patient_assessment_result.recommendation]]
    
    YOUR TASKS:
    1. Reassure the patient that their symptoms don't require urgent attention
    2. Tell them to schedule a routine appointment with their primary care provider
    
    Be reassuring while still taking their concerns seriously.
    """

    routine_care_node = SayLLMNodeConfig(
        name="Routine Care",
        description="Handles routine care cases and schedules regular appointments - uses patient_assessment_result runtime variable",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=ROUTINE_CARE_PROMPT),
        llms_config=openai_llm_config,
        tools_config=patient_assessment_tools,
        max_consecutive_tool_calls=2,
    )

    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Ends the conversation with a caring message",
        static_messages_config=StaticMessagesConfig(
            static_messages=[
                "Thank you for using our Virtual Triage Assistant. Take care and feel better soon!",
                "We're here whenever you need us. Wishing you good health!",
            ]
        ),
        global_node_config=GlobalNodeConfig(
            is_global=True,
            condition=ConditionConfig(
                condition_freeform="""
                Trigger when the patient indicates they're done or says goodbye.
                Examples: "That's all, thanks", "Goodbye", "I'm all set", "Thank you"
                """
            ),
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    greeting_to_triage_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=triage_assessment_node.logical_id,
        name="Start Triage",
        description="After greeting, begin the triage assessment process",
    )

    # Conditional edge based on runtime variable [[patient_assessment_result.urgency_level]]
    TRIAGE_TO_EMERGENCY_CONDITION_EXPRESSION = "[[patient_assessment_result.urgency_level | upcase ]] == 'EMERGENCY'"

    triage_to_emergency_edge = ConditionalEdgeConfig(
        source_node_logical_id=triage_assessment_node.logical_id,
        destination_node_logical_id=emergency_care_node.logical_id,
        name="Emergency Care Path",
        description="Routes to emergency care for critical conditions",
        condition=ConditionConfig(
            condition_expression=TRIAGE_TO_EMERGENCY_CONDITION_EXPRESSION,
            # Static message shown while transitioning to emergency care
            static_messages_config=StaticMessagesConfig(static_messages=["Routing you to emergency care guidance..."]),
        ),
    )

    # Conditional edge for URGENT care path
    TRIAGE_TO_URGENT_CONDITION_EXPRESSION = "[[patient_assessment_result.urgency_level | upcase ]] == 'URGENT'"

    triage_to_urgent_edge = ConditionalEdgeConfig(
        source_node_logical_id=triage_assessment_node.logical_id,
        destination_node_logical_id=urgent_care_node.logical_id,
        name="Urgent Care Path",
        description="Routes to urgent care for time-sensitive conditions",
        condition=ConditionConfig(
            condition_expression=TRIAGE_TO_URGENT_CONDITION_EXPRESSION,
            # Static message shown while transitioning
            static_messages_config=StaticMessagesConfig(
                static_messages=["Connecting you to urgent care scheduling..."]
            ),
        ),
    )

    # Conditional edge for ROUTINE care path
    TRIAGE_TO_ROUTINE_CONDITION_EXPRESSION = "[[patient_assessment_result.urgency_level | upcase ]] == 'ROUTINE'"

    triage_to_routine_edge = ConditionalEdgeConfig(
        source_node_logical_id=triage_assessment_node.logical_id,
        destination_node_logical_id=routine_care_node.logical_id,
        name="Routine Care Path",
        description="Routes to routine care for non-urgent conditions",
        condition=ConditionConfig(
            condition_expression=TRIAGE_TO_ROUTINE_CONDITION_EXPRESSION,
            # Static message shown while transitioning
            static_messages_config=StaticMessagesConfig(static_messages=["Setting up routine care options for you..."]),
        ),
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            triage_assessment_node,
            emergency_care_node,
            urgent_care_node,
            routine_care_node,
            end_conversation_node,
        ],
        edge_configs=[
            greeting_to_triage_edge,
            triage_to_emergency_edge,
            triage_to_urgent_edge,
            triage_to_routine_edge,
        ],
    )

    return workflow_config_full


async def main():
    """
    Main function to run the patient triage workflow demonstration.

    This demonstrates:
    1. Tool static messages - User sees "Analyzing your symptoms..." while tool executes
    2. Tool result runtime variables - Assessment results stored and used in downstream nodes
    3. Conditional branching based on tool results (EMERGENCY, URGENT, ROUTINE paths)
    4. Runtime variables in prompts - Destination nodes access [[patient_assessment_result.urgency_level]]
    """
    workflow_config_full = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow_config_full.workflow_config.miscellaneous.get(
        "default_dynamic_variables", {}
    )
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow_config_full, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    prev_time = time.time()
    elapseds = []
    chat_history = []

    print("\n" + "=" * 100)
    print("EXAMPLE WORKFLOW 9: Patient Triage with Tool Static Messages and Runtime Variables")
    print("=" * 100)
    print("\nThis example demonstrates:")
    print("  • Tool static messages - Feedback while tools execute ('Analyzing symptoms...')")
    print("  • Tool result runtime variables - Storing tool results for downstream use")
    print("  • Conditional branching based on tool results (3 care paths)")
    print("  • Using runtime variables in destination node prompts [[patient_assessment_result]]")
    print("\nTry these scenarios:")
    print("  EMERGENCY: 'I have severe chest pain and difficulty breathing for 10 minutes'")
    print("  URGENT: 'I have a high fever and vomiting for 2 days, feels moderate'")
    print("  ROUTINE: 'I have a mild headache for a few days'")
    print("\nWatch for:")
    print("  - 'Let me analyze your symptoms...' message during tool execution")
    print("  - 'Routing you to emergency care...' message during edge transition")
    print("  - Destination nodes using the assessment results in their responses")
    print("\nType '<exit>' to quit\n")
    print("=" * 100 + "\n")

    while True:
        print("=" * 100)
        print("\n======================================= Chat History =======================================")
        print("=" * 100)

        for msg in chat_history:
            print(msg)
        user_input = input("User Input: ")
        chat_history.append(f"\n USER: {user_input} \n")
        prev_time = time.time()
        if user_input.strip() == "<exit>":
            break
        user_message = HumanMessage(content=user_input)
        workflow_input = WorkflowRunInput(
            thread_to_node_inputs={"0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[user_message])])},
            dynamic_variables=dynamic_variables,
        )

        loop_count = 0
        async for event in workflow_runtime.arun(workflow_input):
            loop_count += 1
            print(f"\nEvent received: {type(event)}\n{event.model_dump_json(indent=2)}\n")

            if isinstance(event, BusyWaitForUserMessageEvent):
                node_name = event.origin_node_name
                msg = f"\n NODE: {node_name} .. is waiting for user input... \n"
                chat_history.append(msg)

            if isinstance(event, AssistantResponseEvent):
                node_name = event.origin_node_name
                elapsed = time.time() - prev_time
                msg = f"\n ASSISTANT (in {elapsed:.2f} sec) ({node_name}): {event.content} \n"
                chat_history.append(msg)
                elapseds.append(elapsed)
                prev_time = time.time()

            if loop_count > 100:  # Add a limit to avoid runaway loops
                print("Quitting because of potential infinite loop")
                break

    # Print statistics
    if elapseds:
        elapseds.sort()
        n = len(elapseds)
        median_first_token_time = elapseds[n // 2] if n % 2 == 1 else (elapseds[n // 2 - 1] + elapseds[n // 2]) / 2
        average_first_token_time = sum(elapseds) / n
        percentile_90_first_token_time = elapseds[int(n * 0.9)] if n > 0 else 0
        percentile_99_first_token_time = elapseds[int(n * 0.99)] if n > 0 else 0
        print(f"\n{'='*100}")
        print("Response Time Statistics")
        print(f"{'='*100}")
        print(f"Total samples: {n}")
        print(f"All samples (sorted): {elapseds}")
        print(
            f"Elapsed Time (sec): Median: {median_first_token_time:.2f}, Average: {average_first_token_time:.2f}, "
            f"90th Percentile: {percentile_90_first_token_time:.2f}, 99th Percentile: {percentile_99_first_token_time:.2f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
