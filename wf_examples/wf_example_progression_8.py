import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 8 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_8.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_8.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import LLMNodeRunInput, SayLLMNodeConfig
from interactly.configs import NodesRunInputs
from interactly.configs import SayStaticMessageNodeConfig
from interactly.configs import PromptConfig, StaticMessagesConfig
from interactly.configs import InlinePythonToolConfig, ToolsConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
def build_assistant_workflow():
    """
    Build a workflow that demonstrates the use of InlinePythonToolConfig for custom tool definitions.

    This workflow showcases how to:
    1. Define Python functions inline as tools without pre-registration
    2. Use custom calculations and data transformations
    3. Combine multiple inline tools in a single node
    4. Leverage tools for business logic execution
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
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.kdaq8eqjs24d"
    )

    workflow_description = f"""
    This workflow introduces Tools - a powerful feature that allows you to equip LLMs with Tools. 
    For illustration purposes, we leverage Inline Python tools - a concept where custom Python functions can be defined directly within your workflow configuration without pre-registration. 
    These tools enable agents to perform calculations, data transformations, and business logic execution on demand. 
    The example demonstrates an insurance calculator assistant that uses multiple inline tools to calculate premiums, deductibles, eligibility, and cost estimates based on user inputs.

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 8: Insurance Calculator with Inline Python Tools",
        description=workflow_description,
    )

    ############# TOOL CONFIGS BELOW #############

    # Define inline Python tools for insurance calculations
    insurance_calculator_tools = ToolsConfig(
        tools=[
            # Tool 1: Calculate monthly premium based on age and coverage amount
            InlinePythonToolConfig(
                name="calculate_monthly_premium",
                signature="Calculate the monthly insurance premium based on the customer's age, coverage amount, and plan type",
                args_schema={
                    "type": "object",
                    "properties": {
                        "age": {"type": "number", "description": "Age of the customer in years"},
                        "coverage_amount": {"type": "number", "description": "Desired coverage amount in dollars"},
                        "plan_type": {
                            "type": "string",
                            "description": "Type of insurance plan: 'basic', 'standard', or 'premium'",
                            "enum": ["basic", "standard", "premium"],
                        },
                    },
                    "required": ["age", "coverage_amount", "plan_type"],
                },
                code="""
def calculate_monthly_premium(age: float, coverage_amount: float, plan_type: str) -> float:
    '''Calculate monthly premium with age-based risk factor and plan multiplier'''
    # Base rate per $1000 of coverage
    base_rate = 0.5
    
    # Age-based risk factor
    if age < 30:
        age_factor = 0.8
    elif age < 45:
        age_factor = 1.0
    elif age < 60:
        age_factor = 1.3
    else:
        age_factor = 1.8
    
    # Plan type multiplier
    plan_multipliers = {
        "basic": 1.0,
        "standard": 1.5,
        "premium": 2.2
    }
    plan_factor = plan_multipliers.get(plan_type.lower(), 1.0)
    
    # Calculate monthly premium
    monthly_premium = (coverage_amount / 1000) * base_rate * age_factor * plan_factor
    
    return round(monthly_premium, 2)
""",
            ),
            # Tool 2: Calculate deductible amount based on plan
            InlinePythonToolConfig(
                name="get_deductible_info",
                signature="Get deductible information for a given insurance plan type",
                args_schema={
                    "type": "object",
                    "properties": {
                        "plan_type": {
                            "type": "string",
                            "description": "Type of insurance plan: 'basic', 'standard', or 'premium'",
                            "enum": ["basic", "standard", "premium"],
                        }
                    },
                    "required": ["plan_type"],
                },
                code="""
def get_deductible_info(plan_type: str) -> dict:
    '''Return deductible information for the specified plan type'''
    deductibles = {
        "basic": {
            "annual_deductible": 5000,
            "out_of_pocket_max": 8000,
            "copay_percentage": 30
        },
        "standard": {
            "annual_deductible": 2500,
            "out_of_pocket_max": 5000,
            "copay_percentage": 20
        },
        "premium": {
            "annual_deductible": 1000,
            "out_of_pocket_max": 3000,
            "copay_percentage": 10
        }
    }
    
    plan_info = deductibles.get(plan_type.lower())
    if plan_info:
        return {
            "plan_type": plan_type,
            "annual_deductible": f"${plan_info['annual_deductible']:,}",
            "out_of_pocket_max": f"${plan_info['out_of_pocket_max']:,}",
            "copay_percentage": f"{plan_info['copay_percentage']}%"
        }
    else:
        return {"error": "Invalid plan type"}
""",
            ),
            # Tool 3: Calculate coverage eligibility based on health factors
            InlinePythonToolConfig(
                name="check_coverage_eligibility",
                signature="Check if a customer is eligible for coverage based on age and pre-existing conditions",
                args_schema={
                    "type": "object",
                    "properties": {
                        "age": {"type": "number", "description": "Age of the customer in years"},
                        "has_preexisting_conditions": {
                            "type": "boolean",
                            "description": "Whether the customer has pre-existing conditions",
                        },
                        "requested_coverage": {"type": "number", "description": "Requested coverage amount in dollars"},
                    },
                    "required": ["age", "has_preexisting_conditions", "requested_coverage"],
                },
                code="""
def check_coverage_eligibility(age: float, has_preexisting_conditions: bool, requested_coverage: float) -> dict:
    '''Determine eligibility and any restrictions for insurance coverage'''
    # Age restrictions
    if age < 18:
        return {
            "eligible": False,
            "reason": "Applicant must be 18 years or older",
            "alternative": "Please apply through a parent or guardian"
        }
    
    if age > 75:
        return {
            "eligible": True,
            "reason": "Eligible with age restriction",
            "max_coverage": 500000,
            "note": "Maximum coverage capped at $500,000 for applicants over 75"
        }
    
    # Pre-existing conditions handling
    if has_preexisting_conditions:
        if requested_coverage > 1000000:
            return {
                "eligible": True,
                "reason": "Eligible with coverage limit",
                "max_coverage": 1000000,
                "waiting_period": "6 months",
                "note": "Coverage for pre-existing conditions subject to 6-month waiting period"
            }
        else:
            return {
                "eligible": True,
                "reason": "Eligible with waiting period",
                "waiting_period": "6 months",
                "note": "Coverage for pre-existing conditions subject to 6-month waiting period"
            }
    
    # Standard eligibility
    return {
        "eligible": True,
        "reason": "Fully eligible for coverage",
        "max_coverage": 5000000,
        "note": "No restrictions apply"
    }
""",
            ),
            # Tool 4: Estimate annual out-of-pocket costs
            InlinePythonToolConfig(
                name="estimate_annual_costs",
                signature="Estimate total annual costs including premiums and expected out-of-pocket expenses",
                args_schema={
                    "type": "object",
                    "properties": {
                        "monthly_premium": {"type": "number", "description": "Monthly premium amount in dollars"},
                        "expected_medical_expenses": {
                            "type": "number",
                            "description": "Expected annual medical expenses in dollars",
                        },
                        "plan_type": {
                            "type": "string",
                            "description": "Type of insurance plan: 'basic', 'standard', or 'premium'",
                            "enum": ["basic", "standard", "premium"],
                        },
                    },
                    "required": ["monthly_premium", "expected_medical_expenses", "plan_type"],
                },
                code="""
def estimate_annual_costs(monthly_premium: float, expected_medical_expenses: float, plan_type: str) -> dict:
    '''Calculate estimated annual costs including premiums and out-of-pocket expenses'''
    # Annual premium
    annual_premium = monthly_premium * 12
    
    # Deductible and copay info
    deductibles = {
        "basic": {"deductible": 5000, "copay_pct": 0.30},
        "standard": {"deductible": 2500, "copay_pct": 0.20},
        "premium": {"deductible": 1000, "copay_pct": 0.10}
    }
    
    plan_info = deductibles.get(plan_type.lower(), deductibles["basic"])
    
    # Calculate out-of-pocket costs
    if expected_medical_expenses <= plan_info["deductible"]:
        out_of_pocket = expected_medical_expenses
    else:
        remaining = expected_medical_expenses - plan_info["deductible"]
        copay_amount = remaining * plan_info["copay_pct"]
        out_of_pocket = plan_info["deductible"] + copay_amount
    
    total_annual_cost = annual_premium + out_of_pocket
    
    return {
        "annual_premium": f"${annual_premium:,.2f}",
        "estimated_out_of_pocket": f"${out_of_pocket:,.2f}",
        "total_estimated_annual_cost": f"${total_annual_cost:,.2f}",
        "plan_type": plan_type,
        "breakdown": {
            "monthly_premium": f"${monthly_premium:.2f}",
            "deductible": f"${plan_info['deductible']:,}",
            "copay_percentage": f"{int(plan_info['copay_pct'] * 100)}%"
        }
    }
""",
            ),
        ]
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_NODE_PROMPT = """
    Welcome the user warmly to the Insurance Calculator Assistant in less than 15 words. 
    Let them know you can help calculate premiums, check eligibility, and estimate costs.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Welcome node that greets the user and explains the calculator capabilities",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    INSURANCE_CALCULATOR_PROMPT = """
    You are "InsureCalc Assistant," a helpful AI tool for insurance calculations and quotes.

    ==================================================
    YOUR CAPABILITIES
    ==================================================
    You have access to the following calculation tools:

    1. **calculate_monthly_premium**: Calculate monthly premiums based on age, coverage amount, and plan type
    2. **get_deductible_info**: Get deductible details for different plan types
    3. **check_coverage_eligibility**: Verify eligibility and any coverage restrictions
    4. **estimate_annual_costs**: Estimate total annual costs including premiums and out-of-pocket expenses

    ==================================================
    PLAN TYPES
    ==================================================
    - **Basic**: Lower monthly premium, higher deductible ($5,000), 30% copay
    - **Standard**: Moderate premium, moderate deductible ($2,500), 20% copay
    - **Premium**: Higher monthly premium, low deductible ($1,000), 10% copay

    ==================================================
    YOUR ROLE
    ==================================================
    1. Listen to user questions about insurance costs, coverage, and eligibility
    2. Use the appropriate tools to perform calculations and lookups
    3. Present results clearly and explain what they mean
    4. Offer to run additional scenarios or comparisons
    5. Keep responses concise (2-3 sentences max) - this is a conversation

    ==================================================
    IMPORTANT GUIDELINES
    ==================================================
    - ALWAYS use the tools to calculate - never estimate or guess
    - Be proactive: if a user asks about premiums, also mention you can calculate total annual costs
    - Explain calculations in simple terms
    - Suggest comparing different plan types when relevant
    - If information is missing (e.g., age, coverage amount), politely ask for it
    - These are estimates only - remind users to contact an agent for final quotes
    - After answering, ask if they'd like to explore other scenarios

    ==================================================
    EXAMPLE INTERACTIONS
    ==================================================
    
    User: "How much would insurance cost for a 35-year-old wanting $500,000 coverage?"
    You: [Use calculate_monthly_premium for each plan type] "For $500,000 coverage at age 35: Basic plan is $325/month, Standard is $488/month, and Premium is $715/month. Would you like to see deductible details or annual cost estimates for any of these?"

    User: "What's the deductible for the standard plan?"
    You: [Use get_deductible_info] "The Standard plan has a $2,500 annual deductible, $5,000 out-of-pocket maximum, and 20% copay. Would you like me to estimate your total annual costs?"

    User: "Am I eligible for coverage? I'm 45 with a pre-existing condition."
    You: [Use check_coverage_eligibility with typical coverage amount] "You're eligible! However, coverage for pre-existing conditions has a 6-month waiting period. What coverage amount were you considering?"

    Remember: Keep it conversational, use tools for accuracy, and guide users through their options!
    """

    insurance_calculator_node = SayLLMNodeConfig(
        name="Insurance Calculator",
        description="Calculator assistant that uses inline Python tools to perform insurance calculations",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=INSURANCE_CALCULATOR_PROMPT),
        llms_config=openai_llm_config,
        tools_config=insurance_calculator_tools,
        max_consecutive_tool_calls=5,  # Allow multiple tool calls for comprehensive calculations
    )

    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Ends the conversation with a thank you message",
        static_messages_config=StaticMessagesConfig(
            static_messages=[
                "Thank you for using InsureCalc Assistant! For final quotes, please contact a licensed insurance agent. Have a great day!"
            ]
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    greeting_to_calculator_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=insurance_calculator_node.logical_id,
        name="Go to Calculator",
        description="After greeting, route to the insurance calculator for assistance.",
    )

    CALCULATOR_TO_END_CONVERSATION_EDGE_CONDITION = """
    Trigger this if the user indicates they want to end the conversation or says goodbye.
    Examples of such user inputs include:
    - "That's all I needed, thank you."
    - "Goodbye!"
    - "Thanks, I'll contact an agent now."
    - "No more questions, thanks!"
    """

    calculator_to_end_conversation_edge = ConditionalEdgeConfig(
        source_node_logical_id=insurance_calculator_node.logical_id,
        destination_node_logical_id=end_conversation_node.logical_id,
        name="End Conversation",
        description="Routes from the calculator to the end conversation node when user is done.",
        condition=ConditionConfig(condition_freeform=CALCULATOR_TO_END_CONVERSATION_EDGE_CONDITION),
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            insurance_calculator_node,
            end_conversation_node,
        ],
        edge_configs=[
            greeting_to_calculator_edge,
            calculator_to_end_conversation_edge,
        ],
    )

    dynamic_variables = {
        # Add any dynamic variables required for the workflow here
    }

    return workflow_config_full, dynamic_variables


async def main():
    """
    Main function to run the insurance calculator workflow demonstration.

    This demonstrates:
    1. How InlinePythonToolConfig allows defining custom Python functions as tools
    2. How LLMs can call these tools to perform calculations and data transformations
    3. How multiple tools can work together in a single workflow
    4. The power of inline tools for business logic without pre-registration
    """
    workflow_config_full, dynamic_variables = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow_config_full, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    prev_time = time.time()
    elapseds = []
    chat_history = []

    print("\n" + "=" * 100)
    print("EXAMPLE WORKFLOW 8: Insurance Calculator with Inline Python Tools")
    print("=" * 100)
    print("\nThis example demonstrates the use of InlinePythonToolConfig to define custom tools inline.")
    print("\nFeatures showcased:")
    print("  • Inline Python function definitions as tools")
    print("  • Custom calculations (premium, deductibles, eligibility)")
    print("  • Data transformations and business logic")
    print("  • Multiple tools working together")
    print("  • JSON schema for function arguments")
    print("\nTry asking:")
    print("  - 'How much would insurance cost for a 35-year-old wanting $500,000 coverage?'")
    print("  - 'What's the deductible for the premium plan?'")
    print("  - 'Am I eligible if I'm 45 with a pre-existing condition?'")
    print("  - 'Estimate my annual costs with $300/month premium and $3000 expected medical expenses on standard plan'")
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
