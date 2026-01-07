"""Underflow detection with causal chain backtracking.

Detects when demand exceeds supply and builds a causal chain
showing WHY the underflow occurred.
"""

from models import NodeType, Warning, WarningType
from solver import SolvedModel


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

        # Check each input port
        incoming = model.graph.get_incoming_edges(node_id)

        # If NO inputs are connected, check if it has outputs
        # - Has outputs but no inputs = treat as source (like a miner feeding downstream)
        # - Has no outputs AND no inputs = orphaned building, should warn
        outgoing = model.graph.get_outgoing_edges(node_id)
        if not incoming and outgoing:
            # Has outputs, treat as source - skip input checking
            continue
        if not incoming and not outgoing:
            # Orphaned building - warn about all missing inputs
            for i, input_port in enumerate(node.inputs):
                if input_port.rate > 0:
                    warnings.append(
                        Warning(
                            warning_type=WarningType.RESOURCE_UNDERFLOW,
                            message=f"{node_id}: input {i} ({input_port.item_id}) not connected",
                            element_id=node_id,
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
                # No belt connected to this specific input, but others are connected
                warnings.append(
                    Warning(
                        warning_type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"{node_id}: input {i} ({input_port.item_id}) not connected",
                        element_id=node_id,
                        severity=1.0,
                    )
                )
                continue

            actual_flow = model.flows.get(feeding_edge.id, 0.0)
            demanded = input_port.rate

            if actual_flow < demanded - 0.01:  # Small tolerance
                # Underflow detected - build causal chain
                caused_by = _build_causal_chain(model, feeding_edge.id, demanded)
                warnings.append(
                    Warning(
                        warning_type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"{node_id}: {input_port.item_id} {actual_flow:.1f} < {demanded:.1f}/min demanded",
                        element_id=node_id,
                        severity=(demanded - actual_flow) / demanded,
                        caused_by=caused_by,
                    )
                )

    return warnings


def _build_causal_chain(
    model: SolvedModel, edge_id: str, demanded: float, visited: set[str] | None = None
) -> list[Warning]:
    """Build causal chain showing why flow is insufficient.

    Walks upstream to find the root cause of underflow.
    """
    if visited is None:
        visited = set()

    if edge_id in visited:
        return []  # Cycle
    visited.add(edge_id)

    causes: list[Warning] = []
    edge = model.graph.edges[edge_id]
    actual_flow = model.flows.get(edge_id, 0.0)

    # Check if this belt is the bottleneck (overcapacity)
    if actual_flow >= edge.capacity - 0.01:
        causes.append(
            Warning(
                warning_type=WarningType.BELT_OVERCAPACITY,
                message=f"Belt {edge_id} at capacity ({edge.capacity}/min)",
                element_id=edge_id,
                severity=1.0,
            )
        )
        return causes

    # Otherwise, look upstream
    source_node = model.graph.nodes[edge.source_node_id]

    if source_node.node_type == NodeType.PRODUCER:
        # Check if the producer is underproducing
        for output in source_node.outputs:
            if output.item_id == edge.item_id and output.rate < demanded:
                causes.append(
                    Warning(
                        warning_type=WarningType.PRODUCTION_UNDERFLOW,
                        message=f"{source_node.id} produces {output.rate:.1f}/min, need {demanded:.1f}/min",
                        element_id=source_node.id,
                        severity=(demanded - output.rate) / demanded,
                    )
                )

    elif source_node.node_type == NodeType.MINER:
        # Miner can't produce enough
        for output in source_node.outputs:
            if output.rate < demanded:
                causes.append(
                    Warning(
                        warning_type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"Miner {source_node.id} outputs {output.rate:.1f}/min, need {demanded:.1f}/min",
                        element_id=source_node.id,
                        severity=(demanded - output.rate) / demanded,
                    )
                )

    elif source_node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
        # Look at inputs to splitter/merger
        incoming = model.graph.get_incoming_edges(source_node.id)
        for in_edge in incoming:
            causes.extend(_build_causal_chain(model, in_edge.id, demanded, visited))

    return causes
