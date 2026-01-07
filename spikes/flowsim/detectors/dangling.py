"""Dangling port detection.

Detects unconnected ports and reports them as info-level warnings.
These aren't errors - the solver handles them gracefully - but the user
should know we've made assumptions about their intent.
"""

from models import FlowGraph, NodeType, Warning, WarningType


def detect_dangling_ports(graph: FlowGraph) -> list[Warning]:
    """Detect unconnected input/output ports on production buildings.

    Returns info-level warnings explaining what assumptions were made:
    - Unconnected inputs: "Treated as infinite source"
    - Unconnected outputs: "Treated as sink (items discarded)"

    Splitters/mergers with open ports are handled by spare_capacity detector.
    Miners have no inputs. Sinks have no outputs. So we only check PRODUCER nodes.
    """
    warnings: list[Warning] = []

    for node_id, node in graph.nodes.items():
        if node.node_type != NodeType.PRODUCER:
            continue

        # Check for unconnected inputs
        incoming = graph.get_incoming_edges(node_id)
        connected_input_indices = {e.dest_port_index for e in incoming}

        unconnected_inputs: list[str] = []
        for i, input_port in enumerate(node.inputs):
            if i not in connected_input_indices and input_port.item_id:
                unconnected_inputs.append(input_port.item_id)

        if unconnected_inputs and not incoming:
            # NO inputs connected - treating entire building as a source
            items = ", ".join(unconnected_inputs)
            warnings.append(
                Warning(
                    warning_type=WarningType.LEFTOVER_ITEMS,  # Reusing for info
                    message=f"{node_id}: No inputs connected. Assuming infinite supply of {items}.",
                    element_id=node_id,
                    severity=0.1,  # Very low - just info
                )
            )
        elif unconnected_inputs:
            # SOME inputs connected but not all - this is more suspicious
            items = ", ".join(unconnected_inputs)
            warnings.append(
                Warning(
                    warning_type=WarningType.RESOURCE_UNDERFLOW,
                    message=f"{node_id}: Missing input(s): {items}. Building will not function correctly.",
                    element_id=node_id,
                    severity=0.8,
                )
            )

        # Check for unconnected outputs
        outgoing = graph.get_outgoing_edges(node_id)
        connected_output_indices = {e.source_port_index for e in outgoing}

        unconnected_outputs: list[str] = []
        for i, output_port in enumerate(node.outputs):
            if i not in connected_output_indices and output_port.item_id:
                unconnected_outputs.append(output_port.item_id)

        if unconnected_outputs and not outgoing:
            # NO outputs connected - treating as sink
            items = ", ".join(unconnected_outputs)
            warnings.append(
                Warning(
                    warning_type=WarningType.LEFTOVER_ITEMS,
                    message=f"{node_id}: No outputs connected. Production of {items} will be sunk.",
                    element_id=node_id,
                    severity=0.1,  # Just info
                )
            )
        elif unconnected_outputs:
            # SOME outputs connected but not all
            items = ", ".join(unconnected_outputs)
            warnings.append(
                Warning(
                    warning_type=WarningType.LEFTOVER_ITEMS,
                    message=f"{node_id}: Unconnected output(s): {items}. Items will be sunk.",
                    element_id=node_id,
                    severity=0.3,
                )
            )

    return warnings
