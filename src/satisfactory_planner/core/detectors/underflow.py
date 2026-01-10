"""Underflow detection with causal chain backtracking.

Detects when demand exceeds supply and builds a causal chain
showing WHY the underflow occurred.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from satisfactory_planner.core.flow_models import NodeType
from satisfactory_planner.core.flow_solver import Warning, WarningType
from satisfactory_planner.core.item_key import ItemKey

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_lp_solver import SolvedModel


def detect_underflow(model: SolvedModel) -> list[Warning]:
    """Detect underflow warnings with causal chains.

    An underflow occurs when a node's input receives less than demanded.
    We backchain to find the root cause.
    """
    if not model.success:
        return []

    warnings: list[Warning] = []

    for node_id, node in model.graph.nodes.items():
        if node.node_type != NodeType.PRODUCER:
            continue

        incoming = model.graph.get_incoming_edges(node_id)
        outgoing = model.graph.get_outgoing_edges(node_id)

        if not incoming and outgoing:
            # Has outputs but no inputs - treat as source
            continue
        if not incoming and not outgoing:
            # Orphaned building
            for i, input_port in enumerate(node.inputs):
                if input_port.rate > 0:
                    warnings.append(
                        Warning(
                            type=WarningType.RESOURCE_UNDERFLOW,
                            message=f"{node_id}: input {i} ({input_port.item_id}) not connected",
                            item_key=node_id,
                            severity=1.0,
                        )
                    )
            continue

        for i, input_port in enumerate(node.inputs):
            if input_port.rate <= 0:
                continue

            # Find the edge feeding this input
            feeding_edge = None
            for edge in incoming:
                if edge.dest_port_index == i:
                    feeding_edge = edge
                    break

            if feeding_edge is None:
                warnings.append(
                    Warning(
                        type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"{node_id}: input {i} ({input_port.item_id}) not connected",
                        item_key=node_id,
                        severity=1.0,
                    )
                )
                continue

            actual_flow = model.flows.get(feeding_edge.id, 0.0)
            demanded = input_port.rate

            if actual_flow < demanded - 0.01:
                caused_by = _build_causal_chain(model, feeding_edge.id, demanded)
                warnings.append(
                    Warning(
                        type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"{node_id}: {input_port.item_id} {actual_flow:.1f} < {demanded:.1f}/min demanded",
                        item_key=node_id,
                        severity=(demanded - actual_flow) / demanded,
                        caused_by=caused_by,
                    )
                )

    return warnings


def _build_causal_chain(
    model: SolvedModel,
    edge_id: ItemKey,
    demanded: float,
    visited: set[ItemKey] | None = None,
) -> list[Warning]:
    """Build causal chain showing why flow is insufficient."""
    if visited is None:
        visited = set()

    if edge_id in visited:
        return []
    visited.add(edge_id)

    causes: list[Warning] = []
    edge = model.graph.edges[edge_id]
    actual_flow = model.flows.get(edge_id, 0.0)

    # Check if this belt is the bottleneck
    if actual_flow >= edge.capacity - 0.01:
        item_key = edge.belt_id if edge.belt_id else edge_id
        causes.append(
            Warning(
                type=WarningType.BELT_OVERCAPACITY,
                message=f"Belt {edge_id} at capacity ({edge.capacity}/min)",
                item_key=item_key,
                severity=1.0,
            )
        )
        return causes

    # Otherwise, look upstream
    source_node = model.graph.nodes[edge.source_node_id]

    if source_node.node_type == NodeType.PRODUCER:
        for output in source_node.outputs:
            if output.item_id == edge.item_id and output.rate < demanded:
                causes.append(
                    Warning(
                        type=WarningType.PRODUCTION_UNDERFLOW,
                        message=f"{source_node.id} produces {output.rate:.1f}/min, need {demanded:.1f}/min",
                        item_key=source_node.id,
                        severity=(demanded - output.rate) / demanded,
                    )
                )

    elif source_node.node_type == NodeType.MINER:
        for output in source_node.outputs:
            if output.rate < demanded:
                causes.append(
                    Warning(
                        type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"Miner {source_node.id} outputs {output.rate:.1f}/min, need {demanded:.1f}/min",
                        item_key=source_node.id,
                        severity=(demanded - output.rate) / demanded,
                    )
                )

    elif source_node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
        incoming = model.graph.get_incoming_edges(source_node.id)
        for in_edge in incoming:
            causes.extend(_build_causal_chain(model, in_edge.id, demanded, visited))

    return causes
