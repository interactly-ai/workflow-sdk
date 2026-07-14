import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 7 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_7.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_7.py
"""

import asyncio
import json
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import CompanionEdgeConfig, ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import LLMNodeRunInput, SayLLMNodeConfig, WorkerLLMNodeConfig
from interactly.configs import GlobalNodeConfig
from interactly.configs import NodesRunInputs
from interactly.configs import SayStaticMessageNodeConfig
from interactly.configs import PromptConfig, StaticMessagesConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import (
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
    EndRunNodeEvent,
    WorkerLLMNodeEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    openai_llm_config_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=50,
        temperature=0.5,
        do_not_split_sentences=True,
    )
    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=400,
        temperature=0.2,
        do_not_split_sentences=True,
    )
    worker_openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        temperature=0.0,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.g08oi9skt49t"
    )

    workflow_description = f"""
    This workflow represents a more comprehensive example that combines all the concepts from Examples 1-6 into a medical appointment scheduling and assessment system. 
    It demonstrates how multiple agent types, edge types, structured data extraction patterns, and complex conditional routing work together in a real-world healthcare scenario. 
    The workflow handles new patient intake, routine checkups, urgent care triage, and emergency redirection with appropriate scheduling and follow-up.

    See more details at {google_docs_md_link}

    Dynamic Variables you can use:
        {{
            # Clinic branding
            "clinic_name": "HealthFirst Medical Center",
            "clinic_address": "123 Wellness Way, Medical District",
            "greeting_phrase": "Welcome! I'm here to help you schedule your appointment.",
            
            # Appointment types
            "appointment_types": ["New Patient Visit", "Routine Checkup/Physical", "Urgent Care", "Follow-up Visit"],
            
            # Emergency
            "emergency_number": "911",
            
            # Scheduling slots (in real implementation, these would be dynamically fetched)
            "urgent_care_time_slots": ["10:30 AM", "2:00 PM", "4:15 PM"],
            "next_available_slots": ["Tomorrow at 9:00 AM", "Tomorrow at 2:30 PM", "Day after tomorrow at 11:00 AM"],
            "routine_available_slots": ["Next Monday 9:00 AM", "Next Wednesday 2:00 PM", "Next Friday 10:30 AM", "Following Monday 3:00 PM"],
            
            # Instructions
            "urgent_arrival_instruction": "15 minutes early to complete check-in",
            "standard_arrival_instruction": "10 minutes early for check-in",
            "routine_recommendation": "at least 2-3 weeks in advance for better availability",
            
            # Confirmation
            "confirmation_method": "via email and text message",
            "confirmation_closing": "We look forward to seeing you!",
            
            # Farewell
            "farewell_message": "Thank you for choosing HealthFirst Medical Center. Your appointment is confirmed. We look forward to caring for you. Have a wonderful day!",
        }}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 7: Comprehensive Medical Appointment & Assessment Workflow",
        description=workflow_description,
        llms_config=openai_llm_config,
        default_prompt_prefix=GLOBAL_PROMPT_PREFIX,
        default_prompt_suffix=GLOBAL_PROMPT_SUFFIX,
        # miscellaneous={"debug_mode": "true"},
        miscellaneous={
            "default_dynamic_variables": {
                # Clinic branding
                "clinic_name": "HealthFirst Medical Center",
                "clinic_address": "123 Wellness Way, Medical District",
                "greeting_phrase": "Welcome! I'm here to help you schedule your appointment.",
                # Appointment types
                "appointment_types": [
                    "New Patient Visit",
                    "Routine Checkup/Physical",
                    "Urgent Care",
                    "Follow-up Visit",
                ],
                # Emergency
                "emergency_number": "911",
                # Scheduling slots (in real implementation, these would be dynamically fetched)
                "urgent_care_time_slots": ["10:30 AM", "2:00 PM", "4:15 PM"],
                "next_available_slots": [
                    "Tomorrow at 9:00 AM",
                    "Tomorrow at 2:30 PM",
                    "Day after tomorrow at 11:00 AM",
                ],
                "routine_available_slots": [
                    "Next Monday 9:00 AM",
                    "Next Wednesday 2:00 PM",
                    "Next Friday 10:30 AM",
                    "Following Monday 3:00 PM",
                ],
                # Instructions
                "urgent_arrival_instruction": "15 minutes early to complete check-in",
                "standard_arrival_instruction": "10 minutes early for check-in",
                "routine_recommendation": "at least 2-3 weeks in advance for better availability",
                # Confirmation
                "confirmation_method": "via email and text message",
                "confirmation_closing": "We look forward to seeing you!",
                # Farewell
                "farewell_message": "Thank you for choosing HealthFirst Medical Center. Your appointment is confirmed. We look forward to caring for you. Have a wonderful day!",
            }
        },
    )

    ############# NODE CONFIGS BELOW #############

    # Node 1: Greeting Node
    GREETING_NODE_PROMPT = """
    Welcome the patient to {{clinic_name}} in a warm and professional manner.
    Use the greeting: {{greeting_phrase}}
    Let them know you'll help them schedule an appointment and complete a pre-visit health assessment.
    Keep it under 15 words.
    """
    greeting_node = SayLLMNodeConfig(
        name="Welcome & Introduction",
        description="Greets the patient and introduces the appointment scheduling and assessment process",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    # Node 2: Appointment Type Router (Say LLM with self-loop)
    APPOINTMENT_ROUTER_PROMPT = """
    You are an internal appointment routing agent for {{clinic_name}}.
    
    Your specific role is to understand what type of appointment the patient needs and route them accordingly.
    
    Ask the patient what brings them in today. Listen carefully and continue the conversation until you clearly understand their needs.
    
    The appointment types we support are: {{appointment_types}}
    
    Once you clearly understand their need, take the appropriate path to proceed.
    If their request doesn't match our appointment types, politely explain what we offer and ask them to clarify.
    """

    ROUTER_TO_NEW_PATIENT_CONDITION = """
    Trigger this to route to the new patient handling agent when the patient explicitly states they are a new patient or have never visited this clinic before.
    Examples: "I'm a new patient", "This is my first visit", "I've never been here before"
    """

    ROUTER_TO_ROUTINE_CONDITION = """
    Trigger this to route to the routine appointment handling agent when the patient wants a routine checkup, annual physical, wellness visit, or preventive care appointment.
    Examples: "I need my annual checkup", "Just a routine physical", "Wellness visit"
    """

    ROUTER_TO_URGENT_CONDITION = """
    Trigger this to route to the urgent care handling agent when the patient has urgent symptoms or acute issues that need prompt attention but are not emergencies.
    Examples: "I have a fever and cough", "My ankle is swollen", "Severe headache for 3 days"
    """

    appointment_router_node = SayLLMNodeConfig(
        name="Appointment Type Router",
        description="Conversational router that determines the type of appointment needed",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=APPOINTMENT_ROUTER_PROMPT),
    )

    # Node 3: New Patient Intake (Say LLM with companion Worker LLM)
    NEW_PATIENT_INTAKE_PROMPT = """
    You are a new patient intake agent for {{clinic_name}}.
    Your specific role is to collect essential information from new patients before their first appointment.

    You need to try and gather the following details:
    - Your full name
    - Date of birth
    - Insurance provider (or indicate if you're self-pay)
    - Primary reason for today's visit
    - Any known allergies
    - Current medications you're taking
    """

    new_patient_intake_node = SayLLMNodeConfig(
        name="New Patient Intake Interview",
        description="Conversational intake for new patients",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=NEW_PATIENT_INTAKE_PROMPT),
    )

    # Companion Worker LLM for structured extraction
    NEW_PATIENT_SCHEMA_AS_DICT = {
        "name": "NewPatientIntakeData",
        "description": "Extract structured new patient information of the user based on the chat history so far. If any information is missing, do not populate that field. Do not make assumptions. Only fill in what has been explicitly provided by the user.",
        "input_schema": {
            "title": "NewPatientData",
            "type": "object",
            "properties": {
                "full_name": {"title": "Full Name", "type": "string", "description": "Patient's complete legal name"},
                "date_of_birth": {
                    "title": "Date of Birth",
                    "type": "string",
                    "description": "Patient's date of birth in any format",
                },
                "insurance_provider": {
                    "title": "Insurance Provider",
                    "type": "string",
                    "description": "Name of insurance company or 'self-pay'",
                },
                "visit_reason": {
                    "title": "Visit Reason",
                    "type": "string",
                    "description": "Primary reason for the visit",
                },
                "allergies": {
                    "title": "Allergies",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of known allergies",
                },
                "current_medications": {
                    "title": "Current Medications",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of current medications",
                },
            },
            "required": [],
        },
    }

    new_patient_companion_worker = WorkerLLMNodeConfig(
        name="New Patient Data Extractor",
        description="Companion worker that extracts structured data from new patient intake",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=""),
        structured_output_schema=NEW_PATIENT_SCHEMA_AS_DICT,
        llms_config=worker_openai_llm_config,
    )

    # Node 4: Routine Checkup Pre-Assessment (Say LLM with companion Worker LLM)
    ROUTINE_ASSESSMENT_PROMPT = """
    You are a routine health assessment agent for {{clinic_name}}.
    Your specific role is to gather pre-visit health information from patients coming in for routine checkups.
    
    Please ask about:
    - Any health concerns or symptoms you're experiencing
    - Changes in your health since your last visit
    - Current medications and supplements
    - Your exercise and diet habits
    - Sleep quality and stress levels
    - Any family health history updates
    """

    routine_assessment_node = SayLLMNodeConfig(
        name="Routine Checkup Assessment",
        description="Pre-visit health assessment for routine appointments",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=ROUTINE_ASSESSMENT_PROMPT),
    )

    ROUTINE_ASSESSMENT_SCHEMA_AS_DICT = {
        "name": "RoutineAssessmentData",
        "description": "Extract structured routine health assessment information of the user based on the chat history so far. If any information is missing, do not populate that field. Do not make assumptions. Only fill in what has been explicitly provided by the user.",
        "input_schema": {
            "title": "RoutineHealthData",
            "type": "object",
            "properties": {
                "health_concerns": {
                    "title": "Health Concerns",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any current health concerns or symptoms",
                },
                "health_changes": {
                    "title": "Health Changes",
                    "type": "string",
                    "description": "Recent changes in health status",
                },
                "medications": {
                    "title": "Medications",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Current medications and supplements",
                },
                "exercise_frequency": {
                    "title": "Exercise Frequency",
                    "type": "string",
                    "description": "How often patient exercises",
                },
                "diet_quality": {
                    "title": "Diet Quality",
                    "type": "string",
                    "enum": ["excellent", "good", "fair", "poor"],
                    "description": "Self-reported diet quality",
                },
                "sleep_quality": {
                    "title": "Sleep Quality",
                    "type": "string",
                    "enum": ["excellent", "good", "fair", "poor"],
                    "description": "Sleep quality rating",
                },
                "stress_level": {
                    "title": "Stress Level",
                    "type": "string",
                    "enum": ["low", "moderate", "high", "very_high"],
                    "description": "Current stress level",
                },
                "overall_wellness_score": {
                    "title": "Overall Wellness Score",
                    "type": "integer",
                    "description": "Overall wellness score 1-100 based on patient responses",
                },
            },
            "required": [],
        },
    }

    routine_assessment_companion_worker = WorkerLLMNodeConfig(
        name="Routine Assessment Data Extractor",
        description="Companion worker for extracting structured health assessment data",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=""),
        structured_output_schema=ROUTINE_ASSESSMENT_SCHEMA_AS_DICT,
        llms_config=worker_openai_llm_config,
    )

    # Node 5: Urgent Care Triage (Say LLM with companion for symptom extraction)
    URGENT_TRIAGE_PROMPT = """
    You are an urgent care triage agent for {{clinic_name}}.
    Your specific role is to assess symptom severity and urgency for patients needing urgent care.
    
    IMPORTANT: If at any point they describe emergency symptoms (chest pain, difficulty breathing, severe bleeding, 
    loss of consciousness, stroke symptoms), you will immediately direct them to call {{emergency_number}} or go to the ER.

    Please ask the patient to describe:
    - Their main symptoms and when they started
    - Severity of symptoms (on a scale of 1-10)
    - Any recent injuries or accidents
    - Their temperature if they've taken it
    - Other relevant symptoms
    """

    urgent_triage_node = SayLLMNodeConfig(
        name="Urgent Care Triage",
        description="Triages urgent care needs and assesses symptom severity",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=URGENT_TRIAGE_PROMPT),
    )

    URGENT_TRIAGE_SCHEMA_AS_DICT = {
        "name": "UrgentTriageData",
        "description": "Extract urgent care symptom and triage information of the user based on the chat history so far. If any information is missing, do not populate that field. Do not make assumptions. Only fill in what has been explicitly provided by the user.",
        "input_schema": {
            "title": "UrgentCareData",
            "type": "object",
            "properties": {
                "primary_symptoms": {
                    "title": "Primary Symptoms",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main symptoms patient is experiencing",
                },
                "symptom_onset": {"title": "Symptom Onset", "type": "string", "description": "When symptoms started"},
                "severity_score": {
                    "title": "Severity Score",
                    "type": "integer",
                    "description": "Patient-reported severity on scale 1-10",
                },
                "has_injury": {
                    "title": "Has Injury",
                    "type": "boolean",
                    "description": "Whether there was an injury or accident",
                },
                "temperature": {
                    "title": "Temperature",
                    "type": "string",
                    "description": "Body temperature if measured",
                },
                "urgency_level": {
                    "title": "Urgency Level",
                    "type": "string",
                    "enum": ["emergency", "urgent", "semi_urgent", "routine"],
                    "description": "Assessed urgency level based on symptoms",
                },
                "triage_category": {
                    "title": "Triage Category",
                    "type": "string",
                    "description": "Clinical triage category",
                },
            },
            "required": [],
        },
    }

    urgent_triage_companion_worker = WorkerLLMNodeConfig(
        name="Urgent Triage Data Extractor",
        description="Companion worker for extracting structured triage data",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=""),
        structured_output_schema=URGENT_TRIAGE_SCHEMA_AS_DICT,
        llms_config=worker_openai_llm_config,
    )

    # Node 6: Emergency Redirect (Static Message - Global Node)
    EMERGENCY_REDIRECT_CONDITION = """
    Trigger this to route to the emergency services if the patient describes any emergency symptoms:
    - Chest pain or pressure
    - Difficulty breathing or shortness of breath
    - Severe bleeding that won't stop
    - Loss of consciousness or altered mental state
    - Signs of stroke (face drooping, arm weakness, speech difficulty)
    - Severe allergic reaction
    - Severe head injury
    - Suicidal thoughts or self-harm intentions
    
    This is a safety-critical decision - err on the side of caution.
    """

    emergency_redirect_node = SayStaticMessageNodeConfig(
        name="Emergency Redirect",
        description="Immediately redirects patients with emergency symptoms to emergency services",
        static_messages_config=StaticMessagesConfig(
            static_messages=[
                "🚨 STOP - This sounds like a medical emergency. Please call {{emergency_number}} immediately or go to your nearest emergency room. Do not wait for an appointment. Your safety is our top priority."
            ]
        ),
        global_node_config=GlobalNodeConfig(
            is_global=True, condition=ConditionConfig(condition_freeform=EMERGENCY_REDIRECT_CONDITION)
        ),
    )

    # Node 7: Schedule Same-Day Urgent (for high urgency)
    SCHEDULE_SAME_DAY_PROMPT = """
    You are an appointment scheduling agent for {{clinic_name}} for urgent care.
    Your specific role is to schedule same-day urgent care appointments for patients with high urgency needs.
    
    There is availability today at: {{urgent_care_time_slots}}
    
    Ask them which time works best for them.
    And tell them to please arrive {{urgent_arrival_instruction}}.

    Tell them that they will see one of our urgent care providers who will evaluate their symptoms.
    Ask them to bring their ID, insurance card, and a list of current medications.
    """

    schedule_same_day_node = SayLLMNodeConfig(
        name="Same-Day Urgent Scheduling",
        description="Schedules same-day urgent appointments for high-priority cases",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=SCHEDULE_SAME_DAY_PROMPT),
        llms_config=openai_llm_config,
    )

    # Node 8: Schedule Next Available (for semi-urgent)
    SCHEDULE_NEXT_AVAILABLE_PROMPT = """
    You are an appointment scheduling agent for {{clinic_name}} for semi-urgent care.
    Your specific role is to schedule the next available appointments for patients with semi-urgent needs.

    Tell them you can schedule them for our next available appointment.
    
    Tell that based on their needs, there are following available slots:
    {{next_available_slots}}
    
    Ask them which date and time works best for their schedule?
    Please ask them to plan to arrive {{standard_arrival_instruction}}.
    """

    schedule_next_available_node = SayLLMNodeConfig(
        name="Next Available Scheduling",
        description="Schedules next available appointments for semi-urgent cases",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=SCHEDULE_NEXT_AVAILABLE_PROMPT),
        llms_config=openai_llm_config,
    )

    # Node 9: Schedule Routine Appointment (for routine checkups)
    SCHEDULE_ROUTINE_PROMPT = """
    You are an appointment scheduling agent for {{clinic_name}} for routine checkup appointments.
    Your specific role is to help patients schedule their routine health checkup appointments.

    Tell them you recommend scheduling these appointments {{routine_recommendation}}.

    Available dates over the next few weeks:
    {{routine_available_slots}}
    
    Ask them what date and time would they prefer?
    """

    schedule_routine_node = SayLLMNodeConfig(
        name="Routine Appointment Scheduling",
        description="Schedules routine checkup appointments",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=SCHEDULE_ROUTINE_PROMPT),
        llms_config=openai_llm_config,
    )

    # Node 10: Appointment Confirmation & Summary
    CONFIRMATION_PROMPT = """
    You are an appointment confirmation agent for {{clinic_name}}.
    Your specific role is to confirm the appointment details with the patient and provide a summary of what to expect.
    
    📅 Appointment Summary:
    - Patient: [Name from collected data]
    - Type: [Appointment type]
    - Date & Time: [Scheduled time]
    - Location: {{clinic_name}}, {{clinic_address}}
    - Provider: [Will be assigned]
    
    What to bring:
    - Photo ID
    - Insurance card
    - List of current medications
    - Any relevant medical records
    
    They will receive a confirmation {{confirmation_method}} with:
    - Appointment details
    - Pre-visit instructions
    - Office location and parking information
    
    {{confirmation_closing}}
    
    And close with - Is there anything else you need help with regarding your appointment?
    """

    confirmation_node = SayLLMNodeConfig(
        name="Appointment Confirmation",
        description="Provides appointment confirmation and summary",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=CONFIRMATION_PROMPT),
        llms_config=openai_llm_config,
    )

    # Node 11: End Conversation (Global Node)
    END_CONVERSATION_CONDITION = """
    Trigger this to route to conversation ending agent when the patient clearly indicates they're done and have no more questions.
    Examples: "No, that's all", "I'm all set", "Thank you, goodbye", "No more questions"
    """

    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Ends the conversation with a farewell message",
        static_messages_config=StaticMessagesConfig(static_messages=["{{farewell_message}}"]),
        global_node_config=GlobalNodeConfig(
            is_global=True, condition=ConditionConfig(condition_freeform=END_CONVERSATION_CONDITION)
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    # Direct Edge: Greeting to Router
    greeting_to_router_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=appointment_router_node.logical_id,
        name="Start Appointment Process",
        description="After greeting, route to appointment type router",
    )

    # Conditional Edge: Router to New Patient Intake (freeform condition)
    router_to_new_patient_edge = ConditionalEdgeConfig(
        source_node_logical_id=appointment_router_node.logical_id,
        destination_node_logical_id=new_patient_intake_node.logical_id,
        name="Route to New Patient",
        description="Routes new patients to intake process",
        condition=ConditionConfig(condition_freeform=ROUTER_TO_NEW_PATIENT_CONDITION),
    )

    # Conditional Edge: Router to Routine Assessment (freeform condition)
    router_to_routine_edge = ConditionalEdgeConfig(
        source_node_logical_id=appointment_router_node.logical_id,
        destination_node_logical_id=routine_assessment_node.logical_id,
        name="Route to Routine",
        description="Routes patients needing routine checkups to health assessment",
        condition=ConditionConfig(condition_freeform=ROUTER_TO_ROUTINE_CONDITION),
    )

    # Conditional Edge: Router to Urgent Triage (freeform condition)
    router_to_urgent_edge = ConditionalEdgeConfig(
        source_node_logical_id=appointment_router_node.logical_id,
        destination_node_logical_id=urgent_triage_node.logical_id,
        name="Route to Urgent Care",
        description="Routes patients with urgent symptoms to triage",
        condition=ConditionConfig(condition_freeform=ROUTER_TO_URGENT_CONDITION),
    )

    # Companion Edge: New Patient Intake with Companion Worker
    new_patient_companion_edge = CompanionEdgeConfig(
        source_node_logical_id=new_patient_intake_node.logical_id,
        destination_node_logical_id=new_patient_companion_worker.logical_id,
        name="New Patient Data Extraction",
        description="Companion edge for extracting structured new patient data",
    )

    # Companion Edge: Routine Assessment with Companion Worker
    routine_companion_edge = CompanionEdgeConfig(
        source_node_logical_id=routine_assessment_node.logical_id,
        destination_node_logical_id=routine_assessment_companion_worker.logical_id,
        name="Routine Assessment Data Extraction",
        description="Companion edge for extracting structured assessment data",
    )

    # Companion Edge: Urgent Triage with Companion Worker
    urgent_companion_edge = CompanionEdgeConfig(
        source_node_logical_id=urgent_triage_node.logical_id,
        destination_node_logical_id=urgent_triage_companion_worker.logical_id,
        name="Urgent Triage Data Extraction",
        description="Companion edge for extracting structured triage data",
    )

    # Conditional Edge: New Patient to Routine Scheduling (expression-based)
    # After new patient intake is complete, schedule them for routine appointment
    NEW_PATIENT_TO_SCHEDULING_EXPRESSION = "isNonEmpty([[full_name]]) AND isNonEmpty([[visit_reason]])"

    new_patient_to_scheduling_edge = ConditionalEdgeConfig(
        source_node_logical_id=new_patient_intake_node.logical_id,
        destination_node_logical_id=schedule_routine_node.logical_id,
        name="Complete New Patient to Scheduling",
        description="After collecting new patient info, proceed to schedule routine appointment",
        condition=ConditionConfig(condition_expression=NEW_PATIENT_TO_SCHEDULING_EXPRESSION),
    )

    # Conditional Edge: Routine Assessment to Scheduling (expression-based)
    # High wellness score (>= 80) goes to routine scheduling
    ROUTINE_HIGH_WELLNESS_EXPRESSION = "isPresent([[overall_wellness_score]]) AND ([[overall_wellness_score]] >= 80)"

    routine_high_wellness_edge = ConditionalEdgeConfig(
        source_node_logical_id=routine_assessment_node.logical_id,
        destination_node_logical_id=schedule_routine_node.logical_id,
        name="High Wellness to Routine",
        description="Patients with high wellness scores get routine scheduling",
        condition=ConditionConfig(condition_expression=ROUTINE_HIGH_WELLNESS_EXPRESSION),
    )

    # Conditional Edge: Routine Assessment to Next Available (expression-based)
    # Lower wellness score (< 80 but >= 50) or moderate concerns
    ROUTINE_MODERATE_WELLNESS_EXPRESSION = "isPresent([[overall_wellness_score]]) AND ([[overall_wellness_score]] < 80) AND ([[overall_wellness_score]] >= 50)"

    routine_moderate_wellness_edge = ConditionalEdgeConfig(
        source_node_logical_id=routine_assessment_node.logical_id,
        destination_node_logical_id=schedule_next_available_node.logical_id,
        name="Moderate Wellness to Next Available",
        description="Patients with moderate wellness get earlier appointments",
        condition=ConditionConfig(condition_expression=ROUTINE_MODERATE_WELLNESS_EXPRESSION),
    )

    # Conditional Edge: Routine Assessment to Same Day (expression-based)
    # Very low wellness score (< 50) or high stress needs same-day
    ROUTINE_LOW_WELLNESS_EXPRESSION = "isPresent([[overall_wellness_score]]) AND ([[overall_wellness_score]] < 50)"

    routine_low_wellness_edge = ConditionalEdgeConfig(
        source_node_logical_id=routine_assessment_node.logical_id,
        destination_node_logical_id=schedule_same_day_node.logical_id,
        name="Low Wellness to Same Day",
        description="Patients with concerning wellness scores get same-day appointments",
        condition=ConditionConfig(condition_expression=ROUTINE_LOW_WELLNESS_EXPRESSION),
    )

    # Conditional Edge: Urgent Triage to Same Day (expression-based)
    # Urgent or semi-urgent cases go to same-day
    URGENT_TO_SAME_DAY_EXPRESSION = (
        "isPresent([[urgency_level]]) AND ([[urgency_level]] == 'urgent' OR [[urgency_level]] == 'semi_urgent')"
    )

    urgent_to_same_day_edge = ConditionalEdgeConfig(
        source_node_logical_id=urgent_triage_node.logical_id,
        destination_node_logical_id=schedule_same_day_node.logical_id,
        name="Urgent to Same Day",
        description="Urgent cases get same-day appointments",
        condition=ConditionConfig(condition_expression=URGENT_TO_SAME_DAY_EXPRESSION),
    )

    # Conditional Edge: Urgent Triage to Next Available (expression-based)
    # Routine urgency goes to next available
    URGENT_TO_NEXT_EXPRESSION = "isPresent([[urgency_level]]) AND [[urgency_level]] == 'routine'"

    urgent_to_next_edge = ConditionalEdgeConfig(
        source_node_logical_id=urgent_triage_node.logical_id,
        destination_node_logical_id=schedule_next_available_node.logical_id,
        name="Routine Urgency to Next Available",
        description="Lower urgency cases get next available appointments",
        condition=ConditionConfig(condition_expression=URGENT_TO_NEXT_EXPRESSION),
    )

    TO_CONFIRMATION_AGENT_CONDITION = """
    Trigger this to route to the appointment confirmation agent after scheduling is complete.
    If the patient has confirmed their appointment time and details, proceed to confirmation agent.
    If the patient just wants confirmation without scheduling changes, also proceed to confirmation agent.
    """
    # All scheduling nodes to Confirmation
    same_day_to_confirmation_edge = ConditionalEdgeConfig(
        source_node_logical_id=schedule_same_day_node.logical_id,
        destination_node_logical_id=confirmation_node.logical_id,
        name="Same Day to Confirmation",
        description="After same-day scheduling, confirm appointment",
        condition=ConditionConfig(condition_freeform=TO_CONFIRMATION_AGENT_CONDITION),
    )

    next_available_to_confirmation_edge = ConditionalEdgeConfig(
        source_node_logical_id=schedule_next_available_node.logical_id,
        destination_node_logical_id=confirmation_node.logical_id,
        name="Next Available to Confirmation",
        description="After next available scheduling, confirm appointment",
        condition=ConditionConfig(condition_freeform=TO_CONFIRMATION_AGENT_CONDITION),
    )

    routine_schedule_to_confirmation_edge = ConditionalEdgeConfig(
        source_node_logical_id=schedule_routine_node.logical_id,
        destination_node_logical_id=confirmation_node.logical_id,
        name="Routine to Confirmation",
        description="After routine scheduling, confirm appointment",
        condition=ConditionConfig(condition_freeform=TO_CONFIRMATION_AGENT_CONDITION),
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            appointment_router_node,
            new_patient_intake_node,
            new_patient_companion_worker,
            routine_assessment_node,
            routine_assessment_companion_worker,
            urgent_triage_node,
            urgent_triage_companion_worker,
            emergency_redirect_node,
            schedule_same_day_node,
            schedule_next_available_node,
            schedule_routine_node,
            confirmation_node,
            end_conversation_node,
        ],
        edge_configs=[
            # Direct edges
            greeting_to_router_edge,
            same_day_to_confirmation_edge,
            next_available_to_confirmation_edge,
            routine_schedule_to_confirmation_edge,
            # Conditional edges from router (freeform conditions)
            router_to_new_patient_edge,
            router_to_routine_edge,
            router_to_urgent_edge,
            # Companion edges
            new_patient_companion_edge,
            routine_companion_edge,
            urgent_companion_edge,
            # Conditional edges with expression-based conditions
            new_patient_to_scheduling_edge,
            routine_high_wellness_edge,
            routine_moderate_wellness_edge,
            routine_low_wellness_edge,
            urgent_to_same_day_edge,
            urgent_to_next_edge,
        ],
    )

    dynamic_variables = {
        # Clinic branding
        "clinic_name": "HealthFirst Medical Center",
        "clinic_address": "123 Wellness Way, Medical District",
        "greeting_phrase": "Welcome! I'm here to help you schedule your appointment.",
        # Appointment types
        "appointment_types": ["New Patient Visit", "Routine Checkup/Physical", "Urgent Care", "Follow-up Visit"],
        # Emergency
        "emergency_number": "911",
        # Scheduling slots (in real implementation, these would be dynamically fetched)
        "urgent_care_time_slots": ["10:30 AM", "2:00 PM", "4:15 PM"],
        "next_available_slots": ["Tomorrow at 9:00 AM", "Tomorrow at 2:30 PM", "Day after tomorrow at 11:00 AM"],
        "routine_available_slots": [
            "Next Monday 9:00 AM",
            "Next Wednesday 2:00 PM",
            "Next Friday 10:30 AM",
            "Following Monday 3:00 PM",
        ],
        # Instructions
        "urgent_arrival_instruction": "15 minutes early to complete check-in",
        "standard_arrival_instruction": "10 minutes early for check-in",
        "routine_recommendation": "at least 2-3 weeks in advance for better availability",
        # Confirmation
        "confirmation_method": "via email and text message",
        "confirmation_closing": "We look forward to seeing you!",
        # Farewell
        "farewell_message": "Thank you for choosing HealthFirst Medical Center. Your appointment is confirmed. We look forward to caring for you. Have a wonderful day!",
    }

    print(
        f"Built workflow config with {len(workflow_config_full.node_configs)} nodes and {len(workflow_config_full.edge_configs)} edges"
    )
    print(f"\nDynamic variables: \n{json.dumps(dynamic_variables, indent=2)}\n")
    return workflow_config_full, dynamic_variables


async def main():
    workflow_config_full, dynamic_variables = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow_config_full, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    prev_time = time.time()
    elapseds = []
    chat_history = []
    structured_outputs = []  # To collect structured outputs from worker nodes

    while True:
        print(
            "============================================================================================================================================="
        )
        print(
            "\n\n======================================= Chat History ==================================================================================="
        )
        print(
            "============================================================================================================================================="
        )

        for msg in chat_history:
            print(msg)

        # Display collected structured outputs
        if structured_outputs:
            print("\n" + "=" * 50 + " STRUCTURED OUTPUTS " + "=" * 50)
            for i, output in enumerate(structured_outputs):
                print(f"\nStructured Output #{i+1}:")
                print(json.dumps(output, indent=2))
            print("=" * 120)

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

            # WorkerLLMNodeEvent fires each time a Worker LLM node runs.
            # Log it so that learners can see when each worker companion is active.
            if isinstance(event, WorkerLLMNodeEvent):
                node_name = event.origin_node_name
                print(f"\n\U0001f916 WORKER LLM NODE EVENT from {node_name}")

            # Capture structured output from Worker LLM nodes
            if (
                isinstance(event, EndRunNodeEvent)
                and hasattr(event.run_output, "structured_output")
                and event.run_output.structured_output
            ):
                node_name = event.origin_node_name
                structured_output = event.run_output.structured_output
                structured_outputs.append(structured_output)
                print(f"\n📋 STRUCTURED OUTPUT CAPTURED from {node_name}:")
                print(json.dumps(structured_output, indent=2))

            if loop_count > 100:  # Add a limit to avoid runaway loops
                print("Quitting because of potential infinite loop")
                break

    # Print performance statistics
    if elapseds:
        elapseds.sort()
        n = len(elapseds)
        median_first_token_time = elapseds[n // 2] if n % 2 == 1 else (elapseds[n // 2 - 1] + elapseds[n // 2]) / 2
        average_first_token_time = sum(elapseds) / n
        percentile_90_first_token_time = elapseds[int(n * 0.9)]
        percentile_99_first_token_time = elapseds[int(n * 0.99)]
        print(f"\nTotal samples: {n}")
        print(f"All samples (sorted): {elapseds}")
        print(
            f"Elapsed First Token Time (ms): Median: {median_first_token_time:.2f}, Average: {average_first_token_time:.2f}, 90th Percentile: {percentile_90_first_token_time:.2f}, 99th Percentile: {percentile_99_first_token_time:.2f}"
        )

    # Print final structured outputs summary
    if structured_outputs:
        print("\n" + "=" * 50 + " FINAL STRUCTURED OUTPUTS SUMMARY " + "=" * 50)
        for i, output in enumerate(structured_outputs):
            print(f"\nStructured Output #{i+1}:")
            print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
