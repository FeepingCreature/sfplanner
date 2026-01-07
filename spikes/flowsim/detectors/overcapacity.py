"""Belt overcapacity detection.

Detects belts where ideal flow exceeds belt capacity.
Filters to show only the FIRST bottleneck in each chain.
"""

from models import Warning, WarningType
from solver import SolvedModel


def detect_overcapacity(model: SolvedModel) -> list[Warning]:
    """Detect belt overcapacity warnings.

    Returns warnings only for belts that are the FIRST bottleneck
    in their flow chain (upstream belts are not overcapacity).
    """
    if not model.success:
        return []

    # First pass: find all overcapacity belts
    overcap_edges: set[str] = set()
    for edge_id, flow in model.flows.items():
        edge = model.graph.edges[edge_id]
        if flow > edge.capacity:
            overcap_edges.add(edge_id)

    if not overcap_edges:
        return []

    # Second pass: filter out belts that have an upstream overcapacity belt
    # "Upstream" means: following the flow backwards through the graph
    filtered_overcap: set[str] = set()

    for edge_id in overcap_edges:
        if not _has_upstream_overcapacity(model, edge_id, overcap_edges):
            filtered_overcap.add(edge_id)

    # Generate warnings for filtered set
    warnings: list[Warning] = []
    for edge_id in filtered_overcap:
        edge = model.graph.edges[edge_id]
        flow = model.flows[edge_id]
        warnings.append(
            Warning(
                warning_type=WarningType.BELT_OVERCAPACITY,
                message=f"Belt {edge_id}: flow {flow:.1f}/min exceeds capacity {edge.capacity}/min",
                element_id=edge_id,
                severity=(flow - edge.capacity) / edge.capacity,  # Relative severity
            )
        )

    return warnings


def _has_upstream_overcapacity(
    model: SolvedModel, edge_id: str, overcap_edges: set[str], visited: set[str] | None = None
) -> bool:
    """Check if there's an overcapacity belt upstream of this edge.

    Walks backwards through the graph following the same item type.
    """
    if visited is None:
        visited = set()

    if edge_id in visited:
        return False  # Cycle detection
    visited.add(edge_id)

    edge = model.graph.edges[edge_id]
    source_node = model.graph.nodes[edge.source_node_id]

    # Get incoming edges to the source node
    incoming = model.graph.get_incoming_edges(source_node.id)

    for in_edge in incoming:
        # Only follow edges with the same item type
        if in_edge.item_id == edge.item_id or in_edge.item_id is None or edge.item_id is None:
            if in_edge.id in overcap_edges:
                return True
            if _has_upstream_overcapacity(model, in_edge.id, overcap_edges, visited):
                return True

    return False
