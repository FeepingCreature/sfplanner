"""Flow graph models for item flow simulation.

These are separate from the visual models (Building, Belt) - they represent
the abstract flow of items through the factory for LP solving.
"""

from dataclasses import dataclass, field
from enum import Enum, auto

# Flow simulation constants
INFINITE_RATE = 100000.0  # "Unlimited" rate for sources/sinks
FLOW_TOLERANCE = 0.01  # Tolerance for flow rate comparisons
BOTTLENECK_TOLERANCE = 0.1  # Tolerance for bottleneck detection


class NodeType(Enum):
    """Types of nodes in the flow graph."""

    # Sources
    MINER = auto()  # Produces items from resource node
    PORT_IN = auto()  # External input to a room

    # Sinks
    PORT_OUT = auto()  # External output from a room
    SINK = auto()  # Awesome sink, or unconnected output

    # Production (both consume and produce)
    PRODUCER = auto()  # Smelter, Constructor, Assembler, etc.

    # Logistics
    SPLITTER = auto()  # 1 input -> 3 outputs
    MERGER = auto()  # 3 inputs -> 1 output


@dataclass
class FlowPort:
    """A single input or output port on a flow node."""

    item_id: str | None  # Item type (None if not yet determined)
    rate: float  # Desired rate (items/min)
    actual_rate: float = 0.0  # Actual flow rate after simulation


@dataclass
class FlowNode:
    """A node in the flow graph.

    Each node represents something that produces, consumes, or routes items.
    """

    id: str
    node_type: NodeType
    building_id: str | None = None  # Reference back to visual Building

    # Recipe info (for PRODUCER nodes)
    recipe_id: str | None = None
    clock_speed: float = 1.0

    # Ports - what items flow in/out
    inputs: list[FlowPort] = field(default_factory=list)
    outputs: list[FlowPort] = field(default_factory=list)

    # Computed state
    efficiency: float = 1.0  # 0.0-1.0, how much of capacity is used
    is_starved: bool = False  # Not getting enough inputs
    is_blocked: bool = False  # Can't output (downstream full)


@dataclass
class FlowEdge:
    """An edge in the flow graph (represents a belt or pipe)."""

    id: str
    source_node_id: str
    source_port_index: int
    dest_node_id: str
    dest_port_index: int
    capacity: float  # items/min (from belt tier)

    # Optional fields with defaults
    belt_id: str | None = None  # Reference back to visual Belt
    is_fluid: bool = False
    item_id: str | None = None  # Item type (inferred from source)
    flow_rate: float = 0.0  # Actual flow (computed)
    is_overcapacity: bool = False  # Computed state


@dataclass
class FlowGraph:
    """The complete flow graph for simulation."""

    nodes: dict[str, FlowNode] = field(default_factory=dict)
    edges: dict[str, FlowEdge] = field(default_factory=dict)

    def add_node(self, node: FlowNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node

    def add_edge(self, edge: FlowEdge) -> None:
        """Add an edge to the graph."""
        self.edges[edge.id] = edge

    def get_incoming_edges(self, node_id: str) -> list[FlowEdge]:
        """Get all edges flowing into a node."""
        return [e for e in self.edges.values() if e.dest_node_id == node_id]

    def get_outgoing_edges(self, node_id: str) -> list[FlowEdge]:
        """Get all edges flowing out of a node."""
        return [e for e in self.edges.values() if e.source_node_id == node_id]

    def get_sources(self) -> list[FlowNode]:
        """Get all source nodes (no inputs or only external inputs)."""
        sources = []
        for node in self.nodes.values():
            if node.node_type in (NodeType.MINER, NodeType.PORT_IN) or not node.inputs:
                sources.append(node)
        return sources

    def get_sinks(self) -> list[FlowNode]:
        """Get all sink nodes (no outputs or only external outputs)."""
        sinks = []
        for node in self.nodes.values():
            if node.node_type in (NodeType.PORT_OUT, NodeType.SINK) or not node.outputs:
                sinks.append(node)
        return sinks


class LimitingFactor(Enum):
    """Why a building isn't running at 100%."""

    NONE = auto()  # Running at full capacity
    DOWNSTREAM = auto()  # Downstream can't consume output
    INPUT_STARVED = auto()  # Not enough input supply
    BELT_CAPACITY = auto()  # Belt can't carry enough


@dataclass
class BuildingEfficiency:
    """Efficiency state for a single building."""

    building_id: str
    node_id: str
    intended_rate: float  # What user designed for (output rate * clock)
    actual_rate: float  # What LP computed
    duty_cycle: float  # actual / intended (0.0 - 1.0)
    limiting_factor: LimitingFactor
    limiting_details: str = ""  # Human-readable explanation
