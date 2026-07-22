"""Underflow detection with causal chain backtracking.

Detects when demand exceeds supply and builds a causal chain
showing WHY the underflow occurred.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from satisfactory_planner.core.flow_models import NodeType
from satisfactory_planner.core.flow_solver import Warning, WarningType

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_lp_solver import SolvedModel


def detect_underflow(model: SolvedModel) -> list[Warning]:
    """Detect underflow warnings with causal chains.

    An underflow occurs when a node's input receives less than demanded.
    We backchain to find the root cause.

    Important: We must distinguish input-limited from output-limited.
    If a building's outputs are reduced because downstream can't consume,
    the LP proportionally reduces inputs too. We shouldn't report that
    as input underflow - it's output-limited (downstream bottleneck).

    We use the LP dual values (via efficiencies) to determine the TRUE
    limiting factor and skip underflow warnings when output-limited.
    """
    if not model.success:
        return []

    from satisfactory_planner.core.flow_models import LimitingFactor

    warnings: list[Warning] = []

    # First, detect sink underflow (sink has min_rate but not getting enough)
    for node_id, node in model.graph.nodes.items():
        if node.node_type != NodeType.SINK:
            continue

        incoming = model.graph.get_incoming_edges(node_id)
        if not incoming:
            continue

        # Check if sink has a min_rate set and is not being satisfied
        for input_port in node.inputs:
            if input_port.rate <= 0 or input_port.rate >= 99999:  # No min set
                continue

            actual_flow = sum(model.flows.get(e.id, 0.0) for e in incoming)
            if actual_flow < input_port.rate - 0.01:
                warnings.append(
                    Warning(
                        type=WarningType.RESOURCE_UNDERFLOW,
                        message=f"Sink wants {input_port.rate:.1f}/min but only receiving {actual_flow:.1f}/min",
                        item_key=node_id,
                        severity=(input_port.rate - actual_flow) / input_port.rate,
                    )
                )

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
            for input_port in node.inputs:
                if input_port.rate > 0:
                    warnings.append(
                        Warning(
                            type=WarningType.INPUT_MISSING,
                            message=f"{input_port.item_name} input missing.",
                            item_key=node_id,
                            severity=1.0,
                        )
                    )
            continue

        # Build a set of items that have belts connected (regardless of flow)
        # AND a map of item_name -> total incoming flow for that item
        # (Satisfactory allows any belt ordering, so we match by item type not port index)
        items_with_belts: set[str] = set()
        incoming_by_item: dict[str, float] = {}
        for edge in incoming:
            if edge.item_name:
                items_with_belts.add(edge.item_name)
                flow = model.flows.get(edge.id, 0.0)
                incoming_by_item[edge.item_name] = incoming_by_item.get(edge.item_name, 0.0) + flow

        # Get efficiency info from LP to determine the true limiting factor
        efficiency = model.efficiencies.get(node_id)

        # Track truly missing inputs (no belt connected at all)
        truly_missing_inputs: list[str] = []

        for input_port in node.inputs:
            if input_port.rate <= 0 or not input_port.item_name:
                continue

            if input_port.item_name not in items_with_belts:
                # No belt at all for this item - this is ALWAYS a problem
                truly_missing_inputs.append(input_port.item_name)

        # Report truly missing inputs (no belt connected) - always a problem
        # Zero flow with a belt connected is NOT "input missing" - it's an upstream issue
        for item_name in truly_missing_inputs:
            warnings.append(
                Warning(
                    type=WarningType.INPUT_MISSING,
                    message=f"{item_name} input not connected.",
                    item_key=node_id,
                    severity=1.0,
                )
            )

        # Report underflow based on LP's limiting factor analysis
        if efficiency and efficiency.limiting_factor == LimitingFactor.INPUT_STARVED:
            # LP identified INPUT_STARVED - use its accurate info for the warning
            warnings.append(
                Warning(
                    type=WarningType.RESOURCE_UNDERFLOW,
                    message=efficiency.limiting_details,
                    item_key=node_id,
                    severity=1.0 - efficiency.duty_cycle,
                )
            )

    return warnings
