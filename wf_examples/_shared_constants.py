# _shared_constants.py
#
# Shared prompt boilerplate used across the example progressions (2–23).
#
# These constants are *literal placeholder strings* that the Interactly server
# resolves at LLM inference time via its managed-prompt machinery. Because
# prompt registration and resolution happen on the server, the examples only
# need to embed the placeholder strings.
#
# The resolved prompt text is configured on the server; replace it with your
# own brand guidelines when adapting these examples.

GLOBAL_PROMPT_PREFIX = "<<<managed_prompt:global_workflow_prefix>>>"
GLOBAL_PROMPT_SUFFIX = "<<<managed_prompt:global_workflow_suffix>>>"
