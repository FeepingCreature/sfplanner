"""Production graph - abstract representation of what we're building."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto
import uuid

from .recipe import Recipe


@dataclass
class ProductionNode:
    """
    A node in the production graph.
    
    Represents a building running a recipe at a certain scale.
    """
    id: str
    recipe: Recipe
    count: float  # Number of buildings (can be fractional for planning)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
    
    @property
    def effective_inputs(self) -> dict[str, float]:
        """Total input rates for this node."""
        return {k: v * self.count for k, v in self.recipe.inputs.items()}
    
    @property
    def effective_outputs(self) -> dict[str, float]:
        """Total output rates for this node."""
        return {k: v * self.count for k, v in self.recipe.outputs.items()}


@dataclass
class ProductionEdge:
    """
    An edge in the production graph.
    
    Represents flow of an item from one node to another.
    """
    source_id: str
    target_id: str
    item: str
    rate: float  # items/min


class ProductionGraph:
    """
    High-level production graph.
    
    This represents the abstract production requirements:
    - Which recipes are used and how many buildings
    - How items flow between production nodes
    
    This does NOT include splitters/mergers - that's the NetworkGraph.
    """
    
    def __init__(self):
        self.nodes: dict[str, ProductionNode] = {}
        self.edges: list[ProductionEdge] = []
        # Source nodes (raw inputs to the factory)
        self.sources: dict[str, float] = {}  # item_name -> rate
        # Sink nodes (final outputs from the factory)
        self.sinks: dict[str, float] = {}  # item_name -> rate
    
    def add_node(self, node: ProductionNode) -> None:
        """Add a production node."""
        self.nodes[node.id] = node
    
    def add_edge(self, edge: ProductionEdge) -> None:
        """Add a production edge."""
        self.edges.append(edge)
    
    def add_source(self, item: str, rate: float) -> None:
        """Add or update a source (raw input)."""
        self.sources[item] = self.sources.get(item, 0) + rate
    
    def add_sink(self, item: str, rate: float) -> None:
        """Add or update a sink (final output)."""
        self.sinks[item] = self.sinks.get(item, 0) + rate
    
    def get_node(self, node_id: str) -> Optional[ProductionNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def clear(self) -> None:
        """Clear the graph."""
        self.nodes.clear()
        self.edges.clear()
        self.sources.clear()
        self.sinks.clear()
    
    def edges_from(self, node_id: str) -> list[ProductionEdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source_id == node_id]
    
    def edges_to(self, node_id: str) -> list[ProductionEdge]:
        """Get all edges terminating at a node."""
        return [e for e in self.edges if e.target_id == node_id]
