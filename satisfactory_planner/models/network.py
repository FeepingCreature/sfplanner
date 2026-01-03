"""Physical network graph including splitters and mergers."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto
import uuid


class NodeType(Enum):
    """Type of node in the physical network."""
    RECIPE = auto()      # A production building running a recipe
    SPLITTER = auto()    # 1 belt in, 3 belts out (splits evenly)
    MERGER = auto()      # 3 belts in, 1 belt out
    SOURCE = auto()      # Raw resource input
    SINK = auto()        # Final output


# Belt capacities in items/min
BELT_TIERS = {
    1: 60,
    2: 120,
    3: 180,
    4: 240,
    5: 300,
    6: 360,
}


def get_belt_tier_for_rate(rate: float) -> int:
    """Get the minimum belt tier needed for a given rate."""
    for tier, capacity in sorted(BELT_TIERS.items()):
        if capacity >= rate:
            return tier
    return 6  # Max tier if rate exceeds all


@dataclass
class NetworkNode:
    """A node in the physical network."""
    id: str
    node_type: NodeType
    label: str = ""
    # Position for layout (set by layout algorithm)
    x: float = 0.0
    y: float = 0.0
    # For RECIPE nodes, reference to the production node
    production_node_id: Optional[str] = None
    # For SOURCE/SINK, the item name
    item: Optional[str] = None
    # Rate for source/sink nodes
    rate: float = 0.0
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, NetworkNode):
            return self.id == other.id
        return False


@dataclass 
class NetworkEdge:
    """A belt connection in the physical network."""
    source_id: str
    target_id: str
    source_port: int = 0  # Which output port (0-2 for splitters)
    target_port: int = 0  # Which input port (0-2 for mergers)
    item: str = ""
    rate: float = 0.0
    
    @property
    def belt_tier(self) -> int:
        """Minimum belt tier needed for this edge."""
        return get_belt_tier_for_rate(self.rate)


class NetworkGraph:
    """
    Physical network graph.
    
    This includes recipe nodes, splitters, mergers, and belt connections.
    Used for layout optimization.
    """
    
    def __init__(self):
        self.nodes: dict[str, NetworkNode] = {}
        self.edges: list[NetworkEdge] = []
    
    def add_node(self, node: NetworkNode) -> NetworkNode:
        """Add a node to the network."""
        self.nodes[node.id] = node
        return node
    
    def create_node(self, node_type: NodeType, label: str = "", **kwargs) -> NetworkNode:
        """Create and add a new node."""
        node = NetworkNode(
            id=str(uuid.uuid4())[:8],
            node_type=node_type,
            label=label,
            **kwargs
        )
        return self.add_node(node)
    
    def add_edge(self, edge: NetworkEdge) -> NetworkEdge:
        """Add an edge to the network."""
        self.edges.append(edge)
        return edge
    
    def connect(self, source_id: str, target_id: str, item: str = "", 
                rate: float = 0.0, source_port: int = 0, target_port: int = 0) -> NetworkEdge:
        """Create and add an edge between two nodes."""
        edge = NetworkEdge(
            source_id=source_id,
            target_id=target_id,
            source_port=source_port,
            target_port=target_port,
            item=item,
            rate=rate,
        )
        return self.add_edge(edge)
    
    def get_node(self, node_id: str) -> Optional[NetworkNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def edges_from(self, node_id: str) -> list[NetworkEdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source_id == node_id]
    
    def edges_to(self, node_id: str) -> list[NetworkEdge]:
        """Get all edges terminating at a node."""
        return [e for e in self.edges if e.target_id == node_id]
    
    def in_degree(self, node_id: str) -> int:
        """Number of incoming edges."""
        return len(self.edges_to(node_id))
    
    def out_degree(self, node_id: str) -> int:
        """Number of outgoing edges."""
        return len(self.edges_from(node_id))
    
    def predecessors(self, node_id: str) -> list[str]:
        """Get IDs of all nodes with edges to this node."""
        return [e.source_id for e in self.edges_to(node_id)]
    
    def successors(self, node_id: str) -> list[str]:
        """Get IDs of all nodes with edges from this node."""
        return [e.target_id for e in self.edges_from(node_id)]
    
    def topological_order(self) -> list[str]:
        """Return nodes in topological order (sources first)."""
        in_degree = {nid: 0 for nid in self.nodes}
        for edge in self.edges:
            in_degree[edge.target_id] += 1
        
        # Start with nodes that have no incoming edges
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            for succ in self.successors(node_id):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)
        
        return result
    
    def clear(self) -> None:
        """Clear the network."""
        self.nodes.clear()
        self.edges.clear()
    
    def copy(self) -> 'NetworkGraph':
        """Create a deep copy of this network."""
        new_graph = NetworkGraph()
        for node in self.nodes.values():
            new_graph.nodes[node.id] = NetworkNode(
                id=node.id,
                node_type=node.node_type,
                label=node.label,
                x=node.x,
                y=node.y,
                production_node_id=node.production_node_id,
                item=node.item,
                rate=node.rate,
            )
        for edge in self.edges:
            new_graph.edges.append(NetworkEdge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                source_port=edge.source_port,
                target_port=edge.target_port,
                item=edge.item,
                rate=edge.rate,
            ))
        return new_graph
