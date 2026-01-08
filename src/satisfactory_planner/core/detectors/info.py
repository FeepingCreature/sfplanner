"""Info-level warnings: spare capacity, consumption verification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from satisfactory_planner.core.flow_models import NodeType
from satisfactory_planner.core.flow_solver import Warning, WarningType

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_lp_solver import SolvedModel


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

        incoming = model.graph.get_incoming_edges(node_id)
        outgoing = model.graph.get_outgoing_edges(node_id)

        if not incoming:
            continue

        total_input = sum(model.flows.get(e.id, 0.0) for e in incoming)
        total_output = sum(model.flows.get(e.id, 0.0) for e in outgoing)

        spare = total_input - total_output
        n_connected = len(outgoing)
        n_open = 3 - n_connected

        if n_open > 0 and spare > 0.01:
            warnings.append(
                Warning(
                    type=WarningType.LEFTOVER_ITEMS,
                    message=f"Splitter {node_id}: {spare:.1f}/min spare capacity on {n_open} open output(s)",
                    element_id=node_id,
                    severity=0.3,
                )
            )

    return warnings
