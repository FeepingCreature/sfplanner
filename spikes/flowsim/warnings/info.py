"""Info-level warnings: spare capacity, consumption verification."""

from models import NodeType, Warning, WarningType
from solver import SolvedModel


def detect_spare_capacity(model: SolvedModel) -> list[Warning]:
    """Detect splitters with unused output capacity.

    If a splitter has open (unconnected) outputs and its input
    isn't fully consumed, report the spare capacity as info.
    """
    if not model.success:
        return []

    warnings: list[Warning] = []

    for node_id, node in model.graph.nodes.items():
        if node.node_type != NodeType.SPLITTER:
            continue

        # Get connected inputs and outputs
        incoming = model.graph.get_incoming_edges(node_id)
        outgoing = model.graph.get_outgoing_edges(node_id)

        if not incoming:
            continue

        # Calculate total input flow
        total_input = sum(model.flows.get(e.id, 0.0) for e in incoming)

        # Calculate total output flow (to connected outputs)
        total_output = sum(model.flows.get(e.id, 0.0) for e in outgoing)

        # Spare capacity = input that isn't being routed to outputs
        spare = total_input - total_output

        # Also check: splitter has 3 outputs, how many are connected?
        n_connected = len(outgoing)
        n_open = 3 - n_connected

        if n_open > 0 and spare > 0.01:
            # There's spare capacity on open outputs
            warnings.append(
                Warning(
                    warning_type=WarningType.LEFTOVER_ITEMS,
                    message=f"Splitter {node_id}: {spare:.1f}/min spare capacity on {n_open} open output(s)",
                    element_id=node_id,
                    severity=0.3,  # Low severity - just info
                )
            )

    return warnings
