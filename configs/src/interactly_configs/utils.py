import re

from interactly_configs.workflow import WorkflowConfig, WorkflowConfigFullyHydrated

_WORKFLOW_SETTINGS_MISC_KEY_DYNAMIC_VARIABLES = "default_dynamic_variables"

def derive_dynamic_variables(workflow_config: WorkflowConfig | WorkflowConfigFullyHydrated | None) -> dict:
    """
    Derives and returns the dynamic variables used in the workflow from the node and edge configurations.

    Parses variable expressions and creates nested structures:
    - {{location.continent}} -> {"location": {"continent": ""}}
    - {{topics[1]}} -> {"topics": ["", ""]}
    - {{items[2].name}} -> {"items": [{"name": ""}, {"name": ""}, {"name": ""}]}
    """
    if not workflow_config:
        return {}

    workflow_full = WorkflowConfigFullyHydrated()
    if isinstance(workflow_config, WorkflowConfig):
        workflow_full.workflow_config = workflow_config
    elif isinstance(workflow_config, WorkflowConfigFullyHydrated):
        workflow_full = workflow_config
    else:
        raise ValueError(
            f"Invalid workflow configuration type provided. Type: {type(workflow_config)} Value: {workflow_config}"
        )

    dynamic_vars_set = set()

    # Pattern to match variables in double curly braces
    pattern = r"\{\{([^}]+)\}\}"

    # Check workflow level configuration
    workflow_json = workflow_full.workflow_config.model_dump_json()
    matches = re.findall(pattern, workflow_json)
    dynamic_vars_set.update(var.strip() for var in matches)

    # Check node configurations
    for node_config in workflow_full.node_configs:
        node_json = node_config.model_dump_json()
        matches = re.findall(pattern, node_json)
        dynamic_vars_set.update(var.strip() for var in matches)

    # Check edge configurations
    for edge_config in workflow_full.edge_configs:
        edge_json = edge_config.model_dump_json()
        matches = re.findall(pattern, edge_json)
        dynamic_vars_set.update(var.strip() for var in matches)

    # Parse variable expressions and build nested structures
    empty_dynamic_variables = _build_dynamic_variables_structure(dynamic_vars_set)

    if _WORKFLOW_SETTINGS_MISC_KEY_DYNAMIC_VARIABLES not in workflow_full.workflow_config.miscellaneous:
        return empty_dynamic_variables

    # Merge with existing default dynamic variables
    existing_defaults = workflow_full.workflow_config.miscellaneous[_WORKFLOW_SETTINGS_MISC_KEY_DYNAMIC_VARIABLES]
    for key, value in existing_defaults.items():
        empty_dynamic_variables[key] = value
    return empty_dynamic_variables

def _build_dynamic_variables_structure(variable_expressions: set) -> dict:
    """
    Build nested dict/list structures from variable expressions.

    Examples:
        - "location.continent" -> {"location": {"continent": ""}}
        - "topics[1]" -> {"topics": ["", ""]}
        - "items[2].name" -> {"items": [{"name": ""}, {"name": ""}, {"name": ""}]}
        - "location.continent | upcase" -> {"location": {"continent": ""}} (filter removed)
    """
    result = {}

    for expr in variable_expressions:
        # Remove Liquid filters (e.g., "| upcase", "| join: ', '")
        expr_clean = re.split(r"\s*\|", expr)[0].strip()

        # Parse the expression and update the result structure
        _parse_and_merge_variable(expr_clean, result)

    return result

def _parse_and_merge_variable(expr: str, result: dict) -> None:
    """
    Parse a variable expression and merge it into the result dictionary.

    Handles:
        - Simple variables: "name" -> result["name"] = ""
        - Nested objects: "user.name" -> result["user"] = {"name": ""}
        - Arrays: "items[2]" -> result["items"] = ["", "", ""]
        - Combined: "items[1].name" -> result["items"] = [{"name": ""}, {"name": ""}]
    """
    # Tokenize the expression into parts
    # Example: "items[2].name" -> ["items", "[2]", "name"]
    tokens = _tokenize_expression(expr)

    if not tokens:
        return

    # Start from the root
    _merge_tokens_into_result(tokens, result)

def _tokenize_expression(expr: str) -> list:
    """
    Tokenize a variable expression into parts.

    Examples:
        - "name" -> ["name"]
        - "user.name" -> ["user", "name"]
        - "items[2]" -> ["items", "[2]"]
        - "items[2].name" -> ["items", "[2]", "name"]
    """
    tokens = []
    current_token = ""
    i = 0

    while i < len(expr):
        char = expr[i]

        if char == ".":
            if current_token:
                tokens.append(current_token)
                current_token = ""
        elif char == "[":
            if current_token:
                tokens.append(current_token)
                current_token = ""
            # Find the closing bracket
            j = i + 1
            while j < len(expr) and expr[j] != "]":
                j += 1
            if j < len(expr):
                tokens.append(expr[i : j + 1])  # Include brackets
                i = j
                current_token = ""
        else:
            current_token += char

        i += 1

    if current_token:
        tokens.append(current_token)

    return tokens

def _merge_tokens_into_result(tokens: list, result: dict) -> None:
    """
    Merge tokenized expression into the result dictionary.

    This function handles merging logic when the same root variable
    is accessed in different ways (e.g., items[0] and items[2].name)
    """
    if not tokens:
        return

    current = result

    for i, token in enumerate(tokens):
        is_last = i == len(tokens) - 1

        # Check if token is an array access like "[2]"
        if token.startswith("[") and token.endswith("]"):
            # This shouldn't be the first token
            continue

        # Check if next token is an array access
        has_array_access = i + 1 < len(tokens) and tokens[i + 1].startswith("[") and tokens[i + 1].endswith("]")

        if has_array_access:
            # Extract the index
            index_str = tokens[i + 1][1:-1]  # Remove brackets
            try:
                max_index = int(index_str)
            except ValueError:
                max_index = 0

            # Determine what goes in the array
            if i + 2 < len(tokens):
                # There are more tokens after the array access
                # We need to create an array of objects
                remaining_tokens = tokens[i + 2 :]

                # Create or update array
                if token not in current:
                    current[token] = []

                # Ensure array has enough elements
                while len(current[token]) <= max_index:
                    current[token].append({})

                # Merge remaining tokens into each object in the array
                for j in range(max_index + 1):
                    if not isinstance(current[token][j], dict):
                        current[token][j] = {}
                    _merge_tokens_into_result(remaining_tokens, current[token][j])

                return  # We're done processing
            else:
                # Array of simple values
                if token not in current:
                    current[token] = []

                # Ensure array has enough elements
                while len(current[token]) <= max_index:
                    current[token].append("")

                return  # We're done processing
        else:
            # Regular property access
            if is_last:
                # Leaf node
                if token not in current:
                    current[token] = ""
                # If it already exists as dict/list, don't overwrite
            else:
                # Intermediate node - should be a dict
                if token not in current:
                    current[token] = {}
                elif not isinstance(current[token], dict):
                    # Conflict: was set as string/list, but now needs to be dict
                    # Convert to dict
                    current[token] = {}

                current = current[token]
