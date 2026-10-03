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
- **Enforce consistency** — all nodes referencing "Fast Chat" use the same model and settings
- **Rotate vendors** — switch providers team-wide by updating one config
- **Avoid config duplication** — reference configs by name instead of inlining full settings

## Create a saved LLM config

Define a single-provider or group config and save it. Lead with a typed config from `interactly.configs` (requires `pip install interactly[configs]`):

```python
from interactly.configs import OpenAILLMConfig, OPENAIModel

llm_config = await client.llm_configs.create(
    name="Fast Chat",
    config=OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_MINI,
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
    name="Fast Chat",
    config={
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "temperature": 0.7,
        "max_tokens": 2000,
    },
    description="Fast model for structured tasks",
    is_default=False,
)
```

### Choosing a provider

One config class per provider, plus two specials:

| Class | Provider |
|---|---|
| `OpenAILLMConfig` | OpenAI |
| `AzureOpenAILLMConfig` | Azure OpenAI — values are **deployment** names, not vendor model names |
| `GoogleLLMConfig` | Google (Gemini) — on the public Gemini API or Vertex AI, see [Backends](#backends-direct-api-or-vertex-ai) |
| `AnthropicLLMConfig` | Anthropic (Claude) — on api.anthropic.com or Vertex AI |
| `BedrockLLMConfig` | Amazon Bedrock — serverless open-weight models |
| `XAILLMConfig` | xAI Grok, served through Vertex AI |
| `GemmaLLMConfig` | Google Gemma (open weights), served through Vertex AI |
| `GLMLLMConfig` | Z.ai GLM, served through Vertex AI |
| `DeepSeekLLMConfig` | DeepSeek, served through Vertex AI |
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

### Providers served through Vertex AI

Grok, Gemma, GLM and DeepSeek are reached through Google Vertex AI with the platform's Google Cloud
credentials. **None of them takes an API key**, and usage is billed to the platform's Google Cloud project:

```python
from interactly.configs import DeepSeekLLMConfig, GemmaLLMConfig, GLMLLMConfig, XAILLMConfig, XAIModel

XAILLMConfig(model=XAIModel.GROK_4_1_FAST_NON_REASONING)   # Grok; the default is grok-4.6
GemmaLLMConfig()                                           # gemma-4-26b-a4b-it-maas
GLMLLMConfig(enable_thinking=True, max_tokens=1000)        # thinking needs room — see below
DeepSeekLLMConfig()                                        # deepseek-v3.2-maas
```

- **Global endpoint only.** All four are served only by Vertex's global endpoint. Leave `vertex_location`
  blank (or `"global"`); any other region is rejected. `vertex_project` defaults to the platform's
  project.
- **Thinking is off by default** on Gemma, GLM and DeepSeek (`enable_thinking=False`). Thinking costs
  roughly 13–17× the output tokens on a simple question, which on a voice call the caller hears as
  silence. With thinking on, give the node a generous `max_tokens`: GLM spends its whole budget
  reasoning first, and came back empty at 64 and 256 tokens.
- **Grok has no thinking switch.** Its 4.20 and 4.1-fast lines ship as `-reasoning` /
  `-non-reasoning` pairs instead. The non-reasoning variants are the cheaper, lower-latency choice for
  voice nodes.
- **DeepSeek routes conditional edges less reliably** than the other providers here: in measured runs it
  called the navigation tool 1 time in 5 when the tool's argument had not already been stated, preferring
  to ask a clarifying question. Use it for say and worker nodes, or make sure the edge tool needs no
  argument the caller has not given.

### Backends: direct API or Vertex AI

Claude and Gemini models can each be served two ways. The choice is about credentials and billing, not
about the model:

```python
from interactly.configs import (
    AnthropicBackend,
    AnthropicLLMConfig,
    ANTHROPICModel,
    GoogleBackend,
    GoogleLLMConfig,
    GOOGLEModel,
)

# Claude on Vertex AI: no Anthropic key, billed to the Google Cloud project.
AnthropicLLMConfig(model=ANTHROPICModel.CLAUDE_SONNET_4_6, backend=AnthropicBackend.VERTEX)

# Gemini pinned to Vertex, even when the team has its own Gemini key.
GoogleLLMConfig(model=GOOGLEModel.GEMINI_3_8_FLASH, backend=GoogleBackend.VERTEX)
```

- **`AnthropicLLMConfig.backend`** defaults to `direct` (api.anthropic.com with an Anthropic key). On
  `vertex`, only some models are available; check before choosing one:

  ```python
  import interactly_configs as ic

  ic.vertex_selectable_anthropic_models()   # carried by Vertex, minus those withheld (claude-opus-5)
  ```

  A model outside that set is rejected by the server rather than redirected. `vertex_project` and
  `vertex_location` default to the platform's; `global` serves every model.
- **`GoogleLLMConfig.backend`** is unset by default, which keeps the server's own rule: a team-scoped
  Gemini key means the public Gemini API, no key means Vertex. That rule cannot express "Vertex
  regardless", because the team's key is applied before the model is called. Set
  `backend=GoogleBackend.VERTEX` to pin Vertex, or `AI_STUDIO` to pin the public API.

### Gemini thinking levels

The Gemini 3 models take a thinking **level** rather than a token budget:

```python
from interactly.configs import GeminiThinkingLevel, GoogleLLMConfig, GOOGLEModel

GoogleLLMConfig(model=GOOGLEModel.GEMINI_3_8_FLASH, thinking_level=GeminiThinkingLevel.LOW)
GoogleLLMConfig(model=GOOGLEModel.GEMINI_3_8_FLASH, thinking_level="low")   # any casing is accepted
```

Levels are `MINIMAL`, `LOW`, `MEDIUM` and `HIGH`, but each model offers its own subset: `MINIMAL` is
Flash-only, and `gemini-3.7-flash` starts at `LOW`. A level the model does not offer is **not rejected**:
the server uses the nearest level it does offer without thinking harder than you asked. Below the model's
range that is its cheapest level, so `MINIMAL` on `gemini-3.7-flash` runs as `LOW`. Above the range it is
the highest level the model offers.

### Provider quirks that cause 400s

These are properties of the models, not of the SDK, and each one produces a provider-side error that
is easier to avoid than to debug. The values are exported so you can check before sending:

```python
import interactly_configs as ic

ic.MODELS_WITHOUT_LOW_REASONING_EFFORT   # {gpt-5.4-pro, gpt-5.2-pro}
ic.ADAPTIVE_THINKING_MODELS              # claude-opus-5, claude-sonnet-5, claude-fable-5, opus-4-7, opus-4-8
ic.ALWAYS_THINKING_ANTHROPIC_MODELS      # {claude-fable-5}
ic.ALWAYS_THINKING_GOOGLE_MODELS         # gemini-3.8/3.7/3.6-flash, 3.1-pro-preview, the two aliases
ic.REJECTS_TRAILING_MODEL_TURN_GOOGLE_MODELS  # Gemini models that reject a request ending on a model turn
ic.AUDIO_INPUT_OPENAI_MODELS             # {gpt-audio-1.5, gpt-audio-mini}
ic.VISION_BEDROCK_MODELS                 # the Bedrock models that accept images
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

- **Only some models take audio.** `gpt-audio-1.5` and `gpt-audio-mini` accept audio input, on the Chat
  Completions API, as wav or mp3. For a model behind a `CustomLLMConfig` gateway, say so with
  `supports_audio_input=True`; it is off by default, because audio sent to a model that cannot take it
  fails the request.

Models the server has retired are **removed from the enums**, so a value that no longer exists fails
at import rather than as a runtime 404. Most recently: `gpt-5.2-chat-latest`, `gpt-5.3-chat-latest` and
`claude-opus-4-1-20250805`.

### Marking as default

Set `is_default=True` to mark this config as the team's default:

```python
from interactly.configs import OpenAILLMConfig, OPENAIModel

llm_config = await client.llm_configs.create(
    name="Production LLM",
    config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4_MINI),
    is_default=True,
    override_default=True,  # Replaces existing default if one exists
)
```

**Dict form (also supported):**

```python
llm_config = await client.llm_configs.create(
    name="Production LLM",
    config={"provider": "openai", "model": "gpt-5.4-mini"},
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
    search="chat",  # Optional fuzzy filter
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

Whether you see the stored `api_key` depends on your role. **Admins and super-admins are shown the real
key**; every other role gets it redacted.

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
    name="Production Chat",
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
    name="Production Chat",
    config={"provider": "openai", "model": "gpt-4.1", "temperature": 0.5},
)
```

### Keeping the stored API key

`config` replaces the stored config **as a whole**. That matters for the key: with an admin or super-admin
token, the server reads a config with no `api_key` as "remove the stored key", because an admin is shown
the key and could only have cleared it on purpose. A config built fresh in code, like the one above, has
no key.

So `update` guards it by default. When `config` leaves `api_key` unset, `update` reads the stored config
first and carries its key across, group members' keys included (matched by `logical_id`). That costs one
extra request. It never carries a key onto a config of a different provider: switching a saved config from
OpenAI to Anthropic does not hand the OpenAI key to Anthropic.

To remove a stored key on purpose, opt out and send the config as given:

```python
await client.llm_configs.update(
    llm_config_id="<config_id>",
    config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4_MINI),
    preserve_api_key=False,   # with an admin token, this deletes the stored key
)
```

For a non-admin token nothing changes either way: the server never shows them the key, and preserves it
for them itself.

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
        {"role": "human", "content": "What is 2+2?"},
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
        model=OPENAIModel.GPT_5_4_MINI,
        temperature=0.1,
    ),
    messages=[
        {"role": "human", "content": "Code this diagnosis: Type 2 diabetes"},
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
        "model": "gpt-5.4-mini",
        "temperature": 0.1,
    },
    messages=[
        {"role": "human", "content": "Code this diagnosis: Type 2 diabetes"},
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

Point a node (or a whole workflow) at a saved config with **`attachable_llm_config_id`**:

```python
from interactly.configs import PromptConfig, SayLLMNodeConfig, WorkflowConfig

node = SayLLMNodeConfig(
    name="Respond to Customer",
    main_response_config=PromptConfig(prompt="Answer the customer question..."),
    attachable_llm_config_id=llm_config.id,   # the saved config's id
)

# Or for every LLM node in the workflow that does not set its own:
WorkflowConfig(name="Support", attachable_llm_config_id=llm_config.id)
```

The server resolves the reference on every fully-hydrated fetch: it copies the saved config into the
node's `llms_config`, so an edit to the saved config takes effect without re-publishing the workflow. A
node's own reference wins over the workflow's. `named_llm_config_id` and `named_llm_config_name` on the
resolved config are filled in by the server to record where it came from; setting them yourself does not
create a reference, and there is no lookup by name.

A reference to a config that has been deleted, or belongs to another team, is logged and skipped: the
node keeps its inline `llms_config` (the workflow default unless you set one) and the call still runs.

## Test result details

The `LLMConfigTestResult` includes:

| Field | Notes |
|---|---|
| `success` | Boolean indicating if the test passed |
| `response` | The model's text response (if successful) |
| `error` | Error message (if failed) |
| `provider` | Provider name (e.g., "openai") |
| `model` | Model identifier (e.g., "gpt-5.4-mini") |
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
        OpenAILLMConfig(model=OPENAIModel.GPT_5_4_MINI),
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
        {"type": "openai_llm", "provider": "openai", "model": "gpt-5.4-mini"},
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
| `preserve_api_key` | True | Keep the stored key when an update's `config` has none (update) |
| `override_default` | False | Allows replacing existing default |
| `search` | None | Fuzzy filter by name (list) |
| `page` | 1 | Page number (list) |
| `size` | 20 | Items per page (list) |

## Gotchas

1. **Key visibility depends on role** — admins and super-admins are shown the stored `api_key`; every other role gets it redacted.
2. **An admin update without a key deletes it, unless the SDK keeps it** — leave `preserve_api_key` at its default unless removing the key is the point.
3. **Reference a saved config by id** — set `attachable_llm_config_id`; `named_llm_config_id` / `named_llm_config_name` are filled in by the server, and there is no lookup by name.
4. **Test inline requires the secret** — `test_inline()` needs a full config with `api_key` if not using a vendor credential stored on the server.
5. **Override conflicts** — if you set `is_default=True` without `override_default=True` and a default already exists, the operation will fail.
6. **Vertex-served providers are global-only** — a `vertex_location` other than `global` is rejected for Grok, Gemma, GLM and DeepSeek.

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient
from interactly.configs import OpenAILLMConfig, OPENAIModel

client = WorkflowClient()

llm_config = client.llm_configs.create(
    name="Fast Chat",
    config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4_MINI, temperature=0.7),
)

page = client.llm_configs.list(search="chat")
for config in page:
    print(config.name)
```

## See also

- [API reference](../api_async.md) — full method signatures
- [Configs guide](../configs.md) — typed LLM config classes
- [Node config](../configs.md#llm-nodes) — how nodes reference saved configs
</content>
</invoke>
