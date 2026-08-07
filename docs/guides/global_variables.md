# Global Variables

Define team-scoped variables that are injected into workflow state at runtime. Variables can be plain values or secrets (encrypted at rest).

## Setup

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # await client.global_variables.<...>
```

The `async with` block opens the client and cleanly closes it on exit. Every example
below assumes an open `client` from this block. (Prefer synchronous code? See
[Synchronous alternative](#synchronous-alternative) at the end.)

## Create a global variable

Create a single variable.

```python
variable = await client.global_variables.create(
    name="api_key_openai",
    value="sk-...",
    description="OpenAI API key",
    category="credentials",
    is_secret=True,  # encrypted at rest
)

print(f"Created: {variable.id}")
```

**Parameters:**
- `name`: Unique variable name. Used in workflows as `{{global.api_key_openai}}`.
- `value`: Variable value (optional). Will be encrypted if `is_secret=True`.
- `description`: Human-readable description (optional).
- `category`: Freeform category label for grouping (optional).
- `is_secret`: When `True`, the value is encrypted at rest and redacted in API responses (default `False`).

**Returns:**
A `GlobalVariable` object with `id`, `name`, `value` (or redacted), and metadata.

## Bulk create variables

Create multiple variables in one request. Build each item with the typed
`GlobalVariableCreateParams` for autocomplete and assignment-time validation:

```python
from interactly import GlobalVariableCreateParams

variables_list = [
    GlobalVariableCreateParams(
        name="openai_api_key",
        value="sk-...",
        is_secret=True,
        category="credentials",
    ),
    GlobalVariableCreateParams(
        name="slack_webhook_url",
        value="https://hooks.slack.com/...",
        is_secret=True,
        category="integrations",
    ),
    GlobalVariableCreateParams(
        name="app_name",
        value="MyApp",
        is_secret=False,
        category="metadata",
    ),
]

created = await client.global_variables.bulk_create(variables=variables_list)

print(f"Created {len(created)} variables")
for var in created:
    print(f"  {var.name}")
```

**Dict form (also supported).** `bulk_create` also accepts plain `dict` items — the escape
hatch when the `[configs]` extra isn't installed. No code change beyond dropping the typed
class; you just lose autocomplete and assignment-time validation:

```python
variables_list = [
    {"name": "openai_api_key", "value": "sk-...", "is_secret": True, "category": "credentials"},
    {"name": "slack_webhook_url", "value": "https://hooks.slack.com/...", "is_secret": True, "category": "integrations"},
    {"name": "app_name", "value": "MyApp", "is_secret": False, "category": "metadata"},
]

created = await client.global_variables.bulk_create(variables=variables_list)
```

**Parameters:**
- `variables`: List of variable items (`GlobalVariableCreateParams` or plain dicts), each with `name` and optionally `value`, `description`, `category`, `is_secret`.

**Returns:**
A list of successfully created `GlobalVariable` objects.

**Raises:**
`ValueError` if the server reports per-item errors. The exception message includes the reported failures.

## List global variables

```python
page = await client.global_variables.list(
    page=1,
    size=20,
    search="openai",  # optional: fuzzy name filter
    category="credentials",  # optional: filter by category
)

async for var in page:
    print(f"{var.name}: {var.description}")

# Iterate through all pages
for var in await page.list_all():
    print(var.id)
```

**Parameters:**
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).
- `search`: Fuzzy name filter (optional).
- `category`: Filter by category label (optional).

**Returns:**
An `AsyncPage` of `GlobalVariable` objects (a `SyncPage` with the synchronous client).

## Get a single variable

```python
variable = await client.global_variables.get("variable_id_123")

print(f"Name: {variable.name}")
print(f"Value: {variable.value}")  # Redacted if is_secret=True
```

**Parameters:**
- `variable_id`: ObjectId of the variable.

**Returns:**
A `GlobalVariable` object.

**Raises:**
`NotFoundError` if the variable does not exist.

## Update a variable

Partially update a global variable. Only provided fields are changed.

```python
updated = await client.global_variables.update(
    "variable_id_123",
    value="new_value",
    description="Updated description",
    is_secret=True,
)

print(f"Updated: {updated.name}")
```

**Parameters:**
- `variable_id`: ObjectId of the variable.
- `name`: New unique name (optional).
- `value`: New value (optional).
- `description`: New description (optional).
- `category`: New category label (optional).
- `is_secret`: Toggle encryption (optional).

**Returns:**
The updated `GlobalVariable` object.

## Delete a variable

```python
await client.global_variables.delete("variable_id_123")
print("Variable deleted")
```

**Parameters:**
- `variable_id`: ObjectId of the variable to delete.

**Returns:**
`None` on success.

## Resolve all variables

Resolve all team global variables into a plain `{name: value}` dict. Secret values are decrypted server-side. This endpoint is typically used by execution services to inject variables into workflow state.

```python
resolved = await client.global_variables.resolve()

print(f"Available variables: {list(resolved.keys())}")
print(f"app_name: {resolved.get('app_name')}")
```

**Returns:**
A plain dict mapping each variable name to its resolved (and decrypted, for secrets) value.

## Using variables in workflows

Once created, global variables are available in workflow definitions using the `{{global.<name>}}` syntax:

```json
{
  "name": "My Workflow",
  "nodes": [
    {
      "type": "llm",
      "prompt": "Use the API key: {{global.openai_api_key}}"
    },
    {
      "type": "rest_api",
      "url": "https://api.example.com/send",
      "headers": {
        "Authorization": "Bearer {{global.slack_webhook_url}}"
      }
    }
  ]
}
```

At runtime, the variable name is replaced with the resolved value from your team's global variables.

## Key concepts

### Team-scoped

Global variables are team-scoped. All workflows in your team can access them. There is no per-user or per-workflow scoping.

### Encryption

When `is_secret=True`:
- The value is encrypted at rest in the database.
- API responses redact the value (show `"***"` or similar).
- Only the execution engine can decrypt and use the value.
- The `resolve()` endpoint decrypts values server-side.

Use `is_secret=True` for API keys, tokens, passwords, and other sensitive data.

### System-provided variables (`is_system`)

Two variables are provided automatically for every team and appear in `list()` and `resolve()`
alongside your own:

| Name | Contents |
|---|---|
| `interactly_api_base_url` | Public API base URL for this environment. |
| `interactly_api_token` | Your team's API key, for calling Interactly APIs from a tool. Returned **masked**. |

They carry `is_system=True`, category `"System"`, and a synthetic id of the form `system:<name>`.
They **cannot be created, updated, or deleted** — the write endpoints only ever touch your team's own
variables, and a name collision is refused.

```python
page = await client.global_variables.list()
mine = [v for v in page.items if not v.is_system]
```

Use them in a workflow exactly like any other: `{{global.interactly_api_base_url}}`. The token is
masked in every list/resolve response — the execution engine substitutes the real value at run time.
Filter them out whenever you render an editable list, or a user will try to edit one and get an
error.

### Naming conventions

Variable names must be valid for use in `{{global.<name>}}` syntax. Use lowercase letters, digits, and underscores:
- `openai_api_key` ✓
- `slack_webhook` ✓
- `APP_NAME` (valid but convention is lowercase)
- `my-variable` ✗ (hyphens not allowed in template syntax)

### Categories

The `category` field is freeform and used for grouping and filtering. Suggested categories:
- `credentials` (API keys, tokens)
- `integrations` (URLs, webhooks)
- `metadata` (app names, version strings)
- `config` (numeric thresholds, feature flags)

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

variable = client.global_variables.create(
    name="api_key_openai",
    value="sk-...",
    is_secret=True,
)

for var in client.global_variables.list(category="credentials"):
    print(var.name)

resolved = client.global_variables.resolve()
```

## See also

- [Workflows guide](workflows_and_versions.md) — using variables in workflow definitions
- [Global Variables API reference](../api_async.md) — endpoint documentation

## Gotchas

- **System variables are read-only.** `is_system=True` rows cannot be updated or deleted, and
  `interactly_api_token` is always masked in responses.

- Variable names are case-sensitive. `api_key` and `API_KEY` are different variables.
- Once a variable is set as `is_secret=True`, its value is redacted in all API responses. You can update the value, but you cannot read it back.
- Deleting a variable breaks any workflows that reference it. Such references return `null` or error at runtime, depending on your workflow's design.
- The `{{global.<name>}}` syntax is substituted during workflow execution. Typos or undefined variable names are not validated at workflow creation time; they fail at runtime.
- Bulk create is atomic per-item but not transactional. If some items fail, successfully created items are kept, and you must retry or clean up failed items manually.
