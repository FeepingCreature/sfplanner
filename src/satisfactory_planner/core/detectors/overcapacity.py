"""Belt overcapacity detection.

Detects belts where ideal flow exceeds belt capacity.
Filters to show only the FIRST bottleneck in each chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from satisfactory_planner.core.flow_key import FlowKey
from satisfactory_planner.core.flow_solver import Warning, WarningType

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_lp_solver import SolvedModel


def detect_overcapacity(model: SolvedModel) -> list[Warning]:
    """Detect belt overcapacity warnings.

    Uses the two-pass solve results to identify belts where:
    - Theoretical flow (no belt limits) > Actual flow (with belt limits)
    - Actual flow is at belt capacity

    This correctly identifies "you forgot to upgrade this belt" situations.
    """
    if not model.success:
        return []

    warnings: list[Warning] = []

    # Use bottlenecks from two-pass solve if available
    if model.bottlenecks:
        for edge_id, (theoretical, actual) in model.bottlenecks.items():
            edge = model.graph.edges[edge_id]
            # Use element_id for UI references
            element_id = edge.belt_id.element_id if edge.belt_id else edge_id.element_id
            warnings.append(
                Warning(
                    type=WarningType.BELT_OVERCAPACITY,
                    message=(
                        f"Belt bottleneck: needs {theoretical:.0f}/min "
                        f"but belt capacity is {edge.capacity:.0f}/min "
                        f"(actual flow: {actual:.0f}/min)"
                    ),
                    element_id=element_id,
                    severity=min(1.0, (theoretical - actual) / actual) if actual > 0 else 1.0,
                )
            )
        return warnings

    # Fallback: old behavior for backward compatibility
    overcap_edges: set[FlowKey] = set()
    for edge_id, flow in model.flows.items():
        edge = model.graph.edges[edge_id]
        if flow > edge.capacity:
            overcap_edges.add(edge_id)

    if not overcap_edges:
        return []

    # Second pass: filter out belts that have an upstream overcapacity belt
    filtered_overcap: set[FlowKey] = set()

    for edge_id in overcap_edges:
        if not _has_upstream_overcapacity(model, edge_id, overcap_edges):
            filtered_overcap.add(edge_id)

    # Generate warnings for filtered set
    for edge_id in filtered_overcap:
        edge = model.graph.edges[edge_id]
        flow = model.flows[edge_id]
        warnings.append(
            Warning(
                type=WarningType.BELT_OVERCAPACITY,
                message=f"Belt {edge_id}: flow {flow:.1f}/min exceeds capacity {edge.capacity}/min",
                element_id=edge_id.element_id,
                severity=(flow - edge.capacity) / edge.capacity,
            )
        )

    return warnings


def _has_upstream_overcapacity(
    model: SolvedModel,
    edge_id: FlowKey,
    overcap_edges: set[FlowKey],
    visited: set[FlowKey] | None = None,
) -> bool:
    """Check if there's an overcapacity belt upstream of this edge."""
    if visited is None:
        visited = set()

    if edge_id in visited:
        return False
    visited.add(edge_id)

    edge = model.graph.edges[edge_id]
    source_node = model.graph.nodes[edge.source_node_id]

    incoming = model.graph.get_incoming_edges(source_node.id)

    for in_edge in incoming:
        if in_edge.item_id == edge.item_id or in_edge.item_id is None or edge.item_id is None:
            if in_edge.id in overcap_edges:
                return True
            if _has_upstream_overcapacity(model, in_edge.id, overcap_edges, visited):
                return True

    return False
