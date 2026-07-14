"""Interactly node configuration models.

Re-exports all public symbols from the nodes subpackage for convenience.
Users can import directly from submodules or from this package root.
"""

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    GlobalConditionEdgeEvaluationMethod,
    GlobalNodeConfig,
    NodeCategory,
    NodeType,
)
from interactly_configs.nodes.node_unions import (
    NodeConfig,
    NodeRunInput,
    NodeRunOutput,
    NodesRunInputs,
)

__all__ = [
    "NodeType",
    "NodeCategory",
    "GlobalConditionEdgeEvaluationMethod",
    "GlobalNodeConfig",
    "BaseNodeConfig",
    "BaseNodeRunInput",
    "BaseNodeRunOutput",
    "NodeConfig",
    "NodeRunInput",
    "NodeRunOutput",
    "NodesRunInputs",
]

from interactly_configs.nodes.node_unions import NodeMetadataRetriever

def get_node_config_class(node_type: str | NodeType) -> type[BaseNodeConfig] | None:
    """Get the node configuration class associated with a node type."""
    if isinstance(node_type, str):
        try:
            node_type = NodeType(node_type)
        except ValueError:
            return None
    return NodeMetadataRetriever.get_type_to_config_class_map().get(node_type)

__all__.append("get_node_config_class")
