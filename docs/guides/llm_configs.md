# LLM Configs

Save named LLM configurations at the team level, then reference them by name or ID in node and workflow configs. This guide shows how to create, manage, and test saved LLM configs.

The examples below use the asynchronous `AsyncWorkflowClient`. Every call is awaited, and the client is driven inside an `async with` block so it is closed cleanly on exit. All snippets assume you are inside:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # snippets below
```

A synchronous `WorkflowClient` mirrors the same API — see [Synchronous alternative](#synchronous-alternative) at the end.

## Why save LLM configs?

Saving LLM configs as named team assets allows you to:
- **Centralize credentials** — store API keys once instead of in every node
- **Enforce consistency** — all nodes referencing "GPT-4 Fast" use the same model and settings
- **Rotate vendors** — switch providers team-wide by updating one config
- **Avoid config duplication** — reference configs by name instead of inlining full settings

## Create a saved LLM config

Define a single-provider or group config and save it. Lead with a typed config from `interactly.configs` (requires `pip install interactly[configs]`):

```python
from interactly.configs import OpenAILLMConfig, OPENAIModel

llm_config = await client.llm_configs.create(
    name="GPT-4 Chat",
    config=OpenAILLMConfig(
        model=OPENAIModel.GPT_4,
        temperature=0.7,
        max_tokens=2000,
    ),
    description="Fast model for structured tasks",
    is_default=False,
)

print(f"Saved config ID: {llm_config.id}")
print(f"Name: {llm_config.name}")
```

**Dict form (also supported).** If you haven't installed the `[configs]` extra, pass a plain dict instead — the SDK serializes it the same way:

```python
llm_config = await client.llm_configs.create(
    name="GPT-4 Chat",
    config={
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000,
    },
    description="Fast model for structured tasks",
    is_default=False,
)
```

### Choosing a provider

Seven config classes, one per provider plus two specials:

| Class | Provider |
|---|---|
| `OpenAILLMConfig` | OpenAI |
| `AzureOpenAILLMConfig` | Azure OpenAI — values are **deployment** names, not vendor model names |
| `GoogleLLMConfig` | Google (Gemini) |
| `AnthropicLLMConfig` | Anthropic (Claude) |
| `BedrockLLMConfig` | Amazon Bedrock — serverless open-weight models |
| `CustomLLMConfig` | Any OpenAI-compatible endpoint |
| `WorkflowDefaultLLMConfig` | "Use whatever the workflow is configured with" |
| `NoLLMConfig` | Explicitly no LLM |

Amazon Bedrock authenticates in one of three ways, in this order of precedence:

```python
from interactly.configs import BedrockLLMConfig, BEDROCKModel

BedrockLLMConfig(
    model=BEDROCKModel.GLM_4_7_FLASH,   # the default: cheap, fast, routes edges reliably
    region="us-east-1",                 # defaults to us-east-1
    api_key="...",                      # a Bedrock long-term bearer token — wins if set
    # or an access-key pair:
    aws_access_key_id="AKIA...",
    aws_secret_access_key="...",
    # or leave all three empty to use the platform default / IAM role
)
```

Bedrock model availability is **region- and account-dependent**; `aws bedrock list-foundation-models`
tells you what your account can actually call.

### Provider quirks that cause 400s

These are properties of the models, not of the SDK, and each one produces a provider-side error that
is easier to avoid than to debug. The values are exported so you can check before sending:

```python
import interactly_configs as ic

ic.MODELS_WITHOUT_LOW_REASONING_EFFORT   # {gpt-5.4-pro, gpt-5.2-pro}
ic.ADAPTIVE_THINKING_MODELS              # claude-opus-5, claude-sonnet-5, claude-fable-5, opus-4-7, opus-4-8
ic.ALWAYS_THINKING_ANTHROPIC_MODELS      # {claude-fable-5}
ic.ALWAYS_THINKING_GOOGLE_MODELS         # gemini-3.6-flash and the two floating aliases
```

- **The "pro" OpenAI variants reject low reasoning effort.** `gpt-5.4-pro` and `gpt-5.2-pro` accept
  only `medium`, `high`, `xhigh` — and `reasoning_effort` defaults to `low`, so every call would fail
  out of the box. `ic.resolve_reasoning_effort(model, effort)` clamps a value up to the lowest the
  model accepts:

  ```python
  ic.resolve_reasoning_effort("gpt-5.4-pro", "low")   # -> "medium"
  ic.resolve_reasoning_effort("gpt-5", "low")         # -> "low"  (unchanged)
  ```

- **Adaptive-thinking Claude models reject `temperature`**, and reject the legacy
  `thinking={"type": "enabled", "budget_tokens": N}` shape. They also count thinking tokens against
  `max_tokens`, so the usual 4096 fallback truncates sooner — `ic.DEFAULT_ADAPTIVE_THINKING_MAX_TOKENS`
  (8192) is the more sensible floor.

- **Some models cannot switch thinking off.** `claude-fable-5` and the always-thinking Gemini models
  reject a zero thinking budget. `claude-fable-5` additionally requires 30-day data retention, so it
  is unavailable under zero-data-retention agreements.

- **`gpt-4`, `gpt-4o`, `gpt-4o-mini` and `gpt-3.5-turbo` are deprecated** — OpenAI shuts them down on
  2026-10-23. They remain selectable so stored workflows keep deserialising; prefer the 5.x models for
  anything new.

Models the server has retired are **removed from the enums**, so a value that no longer exists fails
at import rather than as a runtime 404.

### Marking as default

Set `is_default=True` to mark this config as the team's default:

```python
from interactly.configs import OpenAILLMConfig, OPENAIModel

llm_config = await client.llm_configs.create(
    name="Production LLM",
    config=OpenAILLMConfig(model=OPENAIModel.GPT_4),
    is_default=True,
    override_default=True,  # Replaces existing default if one exists
)
```

**Dict form (also supported):**

```python
llm_config = await client.llm_configs.create(
    name="Production LLM",
    config={"provider": "openai", "model": "gpt-4"},
    is_default=True,
    override_default=True,
)
```

## List saved configs

Paginate through your team's saved LLM configs. `list()` returns an `AsyncPage`, which you iterate with `async for`:

```python
page = await client.llm_configs.list(
    page=1,
    size=20,
    search="gpt",  # Optional fuzzy filter
)

async for config in page:
    print(f"{config.name} ({'default' if config.is_default else 'custom'})")
    print(f"  Config: {config.config}")

if page.has_next_page:
    next_page = await page.next_page()
```

To collect every page into one list, use `await page.list_all()`.

## Get a saved config

Retrieve a config by ID:

```python
llm_config = await client.llm_configs.get(llm_config_id="<config_id>")

print(f"Name: {llm_config.name}")
print(f"Provider: {llm_config.config.get('provider')}")
print(f"Model: {llm_config.config.get('model')}")
```

The `config` field is a dict (or typed `LLMOrGroupConfig` if `interactly[configs]` is installed).

## Get the team default

Fetch the team's default LLM config (useful when onboarding new workflows):

```python
default_config = await client.llm_configs.get_default()

print(f"Team default: {default_config.name}")
```

Raises `NotFoundError` if no default has been set.

## Update a saved config

Modify only the fields you supply:

```python
from interactly.configs import OpenAILLMConfig, OPENAIModel

llm_config = await client.llm_configs.update(
    llm_config_id="<config_id>",
    name="GPT-4 Production",
    config=OpenAILLMConfig(
        model=OPENAIModel.GPT_4_1,
        temperature=0.5,
    ),
)
```

**Dict form (also supported):**

```python
llm_config = await client.llm_configs.update(
    llm_config_id="<config_id>",
    name="GPT-4 Production",
    config={"provider": "openai", "model": "gpt-4.1", "temperature": 0.5},
)
```

To change the default:

```python
llm_config = await client.llm_configs.update(
    llm_config_id="<config_id>",
    is_default=True,
    override_default=True,
)
```

## Delete a saved config

Remove a config (nodes referencing it by ID will fail until reconfigured):

```python
await client.llm_configs.delete(llm_config_id="<config_id>")
```

## Test a saved config

Exercise a saved config against a system prompt and optional messages before deploying:

```python
result = await client.llm_configs.test(
    llm_config_id="<config_id>",
    system_prompt="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "What is 2+2?"},
    ],
)

print(f"Success: {result.success}")
if result.success:
    print(f"Response: {result.response}")
    print(f"Tokens: {result.total_tokens}")
else:
    print(f"Error: {result.error}")
```

The `messages` parameter is optional and defaults to an empty conversation.

### Test with inline override

Test an unsaved (inline) config to validate before persisting. Lead with a typed config:

```python
from interactly.configs import OpenAILLMConfig, OPENAIModel

result = await client.llm_configs.test_inline(
    system_prompt="You are a medical coder.",
    config=OpenAILLMConfig(
        model=OPENAIModel.GPT_4,
        temperature=0.1,
    ),
    messages=[
        {"role": "user", "content": "Code this diagnosis: Type 2 diabetes"},
    ],
)

print(f"Success: {result.success}")
if result.success:
    print(f"Response: {result.response}")
```

**Dict form (also supported):**

```python
result = await client.llm_configs.test_inline(
    system_prompt="You are a medical coder.",
    config={
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.1,
    },
    messages=[
        {"role": "user", "content": "Code this diagnosis: Type 2 diabetes"},
    ],
)
```

## Get the schema

Retrieve the JSON Schema for an `LLMOrGroupConfig` (for validation or editor rendering):

```python
schema = await client.llm_configs.schema()
print(schema)  # {"type": "object", "properties": {...}}
```

## Reference a saved config in a node

Once saved, reference a config by ID or name in a node's LLM config:

```python
from interactly.configs import SayLLMNodeConfig

node = SayLLMNodeConfig(
    name="Respond to Customer",
    description="Use the team's standard LLM",
    main_response_config={"prompt": "Answer the customer question..."},
    # Reference by ID (preferred)
    llms_config={
        "named_llm_config_id": "<config_id>",
    },
    # OR reference by name (requires unique team-wide name)
    # llms_config={
    #     "named_llm_config_name": "GPT-4 Chat",
    # },
)
```

At runtime, the node resolves the named config and uses its settings.

## Test result details

The `LLMConfigTestResult` includes:

| Field | Notes |
|---|---|
| `success` | Boolean indicating if the test passed |
| `response` | The model's text response (if successful) |
| `error` | Error message (if failed) |
| `provider` | Provider name (e.g., "openai") |
| `model` | Model identifier (e.g., "gpt-4") |
| `prompt_tokens` | Input tokens consumed |
| `completion_tokens` | Output tokens generated |
| `total_tokens` | Sum of above |
| `latency_ms` | Request latency in milliseconds |
| `winning_member` | For group configs: which member won the "fast follower" race |
| `backchannel_response` | For group configs: the backchannel response |
| `backchannel_member` | For group configs: info about the backchannel member |

## Group configs

If you save an LLM group config (multiple fallback providers), test results include group-specific fields. Lead with the typed `LLMGroupConfig`, whose `llms` field takes an ordered list of typed provider configs:

```python
from interactly.configs import (
    LLMGroupConfig,
    OpenAILLMConfig,
    AnthropicLLMConfig,
    OPENAIModel,
    ANTHROPICModel,
)

group_config = LLMGroupConfig(
    llms=[
        OpenAILLMConfig(model=OPENAIModel.GPT_4),
        AnthropicLLMConfig(model=ANTHROPICModel.CLAUDE_SONNET_4_6),
    ],
)

result = await client.llm_configs.test_inline(
    system_prompt="Test prompt",
    config=group_config,
)

print(f"Winning member: {result.winning_member}")  # Fast provider won
print(f"Backchannel response: {result.backchannel_response}")  # Fallback sent this
```

**Dict form (also supported):**

```python
group_config = {
    "type": "llm_group",
    "llms": [
        {"type": "openai_llm", "provider": "openai", "model": "gpt-4"},
        {"type": "anthropic_llm", "provider": "anthropic", "model": "claude-sonnet-4-6"},
    ],
}

result = await client.llm_configs.test_inline(
    system_prompt="Test prompt",
    config=group_config,
)
```

For a group that combines a main model with a fast backchannel responder, use `LLMGroupWithBackchannelConfig` (with `main_llm_config` and `backchannel_llm_config` group members).

## Key options

| Option | Default | Notes |
|---|---|---|
| `is_default` | False | Mark as team default |
| `override_default` | False | Allows replacing existing default |
| `search` | None | Fuzzy filter by name (list) |
| `page` | 1 | Page number (list) |
| `size` | 20 | Items per page (list) |

## Gotchas

1. **Secrets are redacted** — when you fetch a saved config, the `api_key` is always redacted by the server for security.
2. **Named references must be unique** — if multiple configs share the same name, use `named_llm_config_id` instead.
3. **Test inline requires the secret** — `test_inline()` needs a full config with `api_key` if not using a vendor credential stored on the server.
4. **Override conflicts** — if you set `is_default=True` without `override_default=True` and a default already exists, the operation will fail.

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient
from interactly.configs import OpenAILLMConfig, OPENAIModel

client = WorkflowClient()

llm_config = client.llm_configs.create(
    name="GPT-4 Chat",
    config=OpenAILLMConfig(model=OPENAIModel.GPT_4, temperature=0.7),
)

page = client.llm_configs.list(search="gpt")
for config in page:
    print(config.name)
```

## See also

- [API reference](../api_async.md) — full method signatures
- [Configs guide](../configs.md) — typed LLM config classes
- [Node config](../configs.md#llm-nodes) — how nodes reference saved configs
</content>
</invoke>
