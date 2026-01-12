"""LP-based flow solver.

Solves for steady-state flow rates using linear programming.
Uses pylinprog (pure Python simplex) instead of scipy for smaller package size.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from satisfactory_planner.core.flow_models import (
    BOTTLENECK_TOLERANCE,
    FLOW_TOLERANCE,
    INFINITE_RATE,
    BuildingEfficiency,
    FlowEdge,
    FlowGraph,
    FlowNode,
    LimitingFactor,
    NodeType,
)
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.linprog import RESOLUTION_SOLVED, linsolve

logger = logging.getLogger(__name__)


@dataclass
class SolvedModel:
    """Result of solving flow rates."""

    graph: FlowGraph
    flows: dict[ItemKey, float] = field(default_factory=dict)  # edge_id → flow rate
    efficiencies: dict[ItemKey, BuildingEfficiency] = field(
        default_factory=dict
    )  # node_id → efficiency
    success: bool = True
    message: str = ""
    # Two-pass results for bottleneck detection
    theoretical_flows: dict[ItemKey, float] = field(default_factory=dict)
    bottlenecks: dict[ItemKey, tuple[float, float]] = field(
        default_factory=dict
    )  # edge_id → (theoretical, actual)


def _get_downstream_demand(node: FlowNode, item_name: str | None) -> float | None:
    """Get the demand of a node for a specific item.

    For producers, this is the recipe input rate for that item.
    Satisfactory allows any belt ordering on inputs, so we match by item type.
    For splitters/mergers, we return None (no fixed demand).
    """
    if node.node_type == NodeType.PRODUCER:
        if item_name:
            # Find the input port that matches this item
            for inp in node.inputs:
                if inp.item_name == item_name:
                    return inp.rate
        # Fallback: if no item match, return first input rate
        if node.inputs:
            return node.inputs[0].rate
    elif node.node_type == NodeType.SINK:
        # Sinks consume everything, no limit
        return None
    # Splitters/mergers don't have fixed demand
    return None


def solve_flows(graph: FlowGraph) -> SolvedModel:
    """Solve for steady-state flow rates using LP.

    Two-pass approach:
    1. Solve WITHOUT belt limits → theoretical max throughput
    2. Solve WITH belt limits → actual throughput
    3. Compare to identify belt bottlenecks

    The LP formulation:
    - Variables: one flow rate per edge
    - Constraints: flow conservation at each node, splitter fairness
    - Objective: maximize total flow (to fill the factory)

    Fairness: Splitter outputs are constrained to be equal. This ensures
    the LP distributes flow evenly and surfaces downstream bottlenecks
    instead of silently starving one branch to avoid them.
    """
    if not graph.edges:
        # No edges = no flows to solve
        return SolvedModel(graph=graph, flows={})

    # Two-pass solve: first without belt limits, then with
    theoretical_result = _solve_lp(graph, use_belt_limits=False)
    if not theoretical_result[0]:
        # If theoretical solve fails, return the error
        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=theoretical_result[2],
        )

    actual_result = _solve_lp(graph, use_belt_limits=True)
    if not actual_result[0]:
        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=actual_result[2],
        )

    theoretical_flows = theoretical_result[1]
    actual_flows = actual_result[1]

    # Identify belt bottlenecks: where theoretical > actual
    bottlenecks: dict[ItemKey, tuple[float, float]] = {}
    for edge_id, edge in graph.edges.items():
        theo = theoretical_flows.get(edge_id, 0.0)
        actual = actual_flows.get(edge_id, 0.0)
        # A belt is a bottleneck if:
        # 1. Theoretical flow exceeds actual
        # 2. Actual flow is at or near belt capacity
        if theo > actual + BOTTLENECK_TOLERANCE and actual >= edge.capacity - BOTTLENECK_TOLERANCE:
            bottlenecks[edge_id] = (theo, actual)

    # Write DOT file for visualization (disabled for now)
    # _write_dot_file(graph, actual_flows, theoretical_flows, bottlenecks)

    # Compute efficiencies using actual flows
    efficiencies = _compute_efficiencies(graph, actual_flows)

    return SolvedModel(
        graph=graph,
        flows=actual_flows,
        efficiencies=efficiencies,
        success=True,
        theoretical_flows=theoretical_flows,
        bottlenecks=bottlenecks,
    )


def _write_dot_file(
    graph: FlowGraph,
    flows: dict[ItemKey, float],
    theoretical_flows: dict[ItemKey, float],
    bottlenecks: dict[ItemKey, tuple[float, float]],
    suffix: str = "",
) -> None:
    """Write the flow graph to a DOT file for visualization."""
    dot_path = Path.home() / f"flow_graph{suffix}.dot"

    lines = [
        "digraph FlowGraph {",
        "  rankdir=LR;",
        '  node [shape=record, fontname="Courier", fontsize=10];',
        '  edge [fontname="Courier", fontsize=9];',
        "",
    ]

    # Node colors by type
    node_colors = {
        NodeType.MINER: "#90EE90",  # Light green
        NodeType.PRODUCER: "#87CEEB",  # Light blue
        NodeType.SPLITTER: "#FFD700",  # Gold
        NodeType.MERGER: "#FFA500",  # Orange
        NodeType.SINK: "#FF6B6B",  # Light red
        NodeType.PORT_IN: "#DDA0DD",  # Plum
        NodeType.PORT_OUT: "#DDA0DD",  # Plum
    }

    # Nodes with full details
    for node_id, node in graph.nodes.items():
        color = node_colors.get(node.node_type, "#FFFFFF")
        safe_id = str(node_id).replace("-", "_").replace(":", "_").replace("(", "").replace(")", "")

        # Build port details
        in_ports = []
        for i, p in enumerate(node.inputs):
            rate_str = f"{p.rate:.0f}" if p.rate < 10000 else "∞"
            in_ports.append(f"IN{i}: {p.item_name or '?'}@{rate_str}")

        out_ports = []
        for i, p in enumerate(node.outputs):
            rate_str = f"{p.rate:.0f}" if p.rate < 10000 else "∞"
            out_ports.append(f"OUT{i}: {p.item_name or '?'}@{rate_str}")

        # Recipe info for producers
        recipe_str = ""
        if node.recipe_id:
            recipe_str = f"\\nrecipe: {node.recipe_id}"
        if node.clock_speed != 1.0:
            recipe_str += f"\\nclock: {node.clock_speed:.0%}"

        # Build label
        node_id_str = str(node_id)
        label_parts = [f"{node.node_type.name}\\n{node_id_str[:12]}...{recipe_str}"]
        if in_ports:
            label_parts.append("| {" + " | ".join(in_ports) + "}")
        if out_ports:
            label_parts.append("| {" + " | ".join(out_ports) + "}")

        label = "{" + "".join(label_parts) + "}"
        lines.append(f'  "{safe_id}" [label="{label}", style=filled, fillcolor="{color}"];')

    lines.append("")

    # Edges with flow info
    for edge_id, edge in graph.edges.items():
        src_safe = (
            str(edge.source_node_id)
            .replace("-", "_")
            .replace(":", "_")
            .replace("(", "")
            .replace(")", "")
        )
        dst_safe = (
            str(edge.dest_node_id)
            .replace("-", "_")
            .replace(":", "_")
            .replace("(", "")
            .replace(")", "")
        )

        actual = flows.get(edge_id, 0.0)
        theoretical = theoretical_flows.get(edge_id, actual)
        cap = edge.capacity

        # Color based on status
        if edge_id in bottlenecks:
            color = "red"
            penwidth = "3"
        elif actual >= cap * 0.9:
            color = "darkgreen"
            penwidth = "2"
        elif actual < cap * 0.5 and actual > 0:
            color = "orange"
            penwidth = "1.5"
        else:
            color = "black"
            penwidth = "1"

        # Label with all the info
        label_parts = [
            f"{edge.item_name or '?'}",
            f"actual: {actual:.1f}/min",
            f"cap: {cap}/min",
        ]
        if theoretical != actual:
            label_parts.append(f"theo: {theoretical:.1f}")
        if edge_id in bottlenecks:
            label_parts.append("⚠ BOTTLENECK")

        label = "\\n".join(label_parts)

        lines.append(
            f'  "{src_safe}" -> "{dst_safe}" '
            f'[label="{label}", color="{color}", penwidth="{penwidth}"];'
        )

    lines.append("}")

    dot_path.write_text("\n".join(lines))
    logger.info(f"Wrote flow graph to {dot_path}")
    logger.info(f"  View with: dot -Tpng {dot_path} -o ~/flow_graph.png && open ~/flow_graph.png")


def _solve_lp(graph: FlowGraph, use_belt_limits: bool) -> tuple[bool, dict[ItemKey, float], str]:
    """Run the LP solver.

    Args:
        graph: The flow graph to solve
        use_belt_limits: If True, apply belt capacity constraints

    Returns:
        (success, flows, error_message)
    """
    # Create edge index mapping
    edge_ids = list(graph.edges.keys())
    edge_to_idx = {eid: i for i, eid in enumerate(edge_ids)}
    n_edges = len(edge_ids)

    # We'll build equality constraints: A_eq @ x = b_eq
    # And inequality constraints: A_ub @ x <= b_ub
    equality_rows: list[list[float]] = []
    equality_rhs: list[float] = []
    inequality_rows: list[list[float]] = []
    inequality_rhs: list[float] = []

    for node_id, node in graph.nodes.items():
        incoming = graph.get_incoming_edges(node_id)
        outgoing = graph.get_outgoing_edges(node_id)

        if node.node_type == NodeType.MINER:
            # Miner/Source: no inputs, output <= production rate (can produce less if not needed)
            # The port rate comes from max_rate for Source, or tier-based rate for Miner
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    inequality_rows.append(row)
                    inequality_rhs.append(node.outputs[i].rate)

        elif node.node_type == NodeType.PRODUCER:
            # Producer: outputs are LIMITED by downstream demand (inequality)
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    dest_node = graph.nodes[out_edge.dest_node_id]
                    demand = _get_downstream_demand(dest_node, out_edge.item_name)
                    if demand is not None:
                        row = [0.0] * n_edges
                        row[edge_to_idx[out_edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(demand)

                    # Output also can't exceed production capacity
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    inequality_rows.append(row)
                    inequality_rhs.append(node.outputs[i].rate)

            if not incoming:
                # No input constraints - treat as source
                pass
            else:
                # Build map of item_name -> total incoming flow for that item
                # (Satisfactory allows any belt ordering on inputs)
                incoming_by_item: dict[str | None, list[FlowEdge]] = {}
                for edge in incoming:
                    incoming_by_item.setdefault(edge.item_name, []).append(edge)

                # For each required input item, constrain the sum of belts carrying it
                for input_port in node.inputs:
                    item_edges = incoming_by_item.get(input_port.item_name, [])
                    if item_edges:
                        # Sum of all belts for this item <= required rate
                        row = [0.0] * n_edges
                        for edge in item_edges:
                            row[edge_to_idx[edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(input_port.rate)
                    elif input_port.item_name:
                        # Missing input - force outputs to zero
                        # (This item has no belt, so building can't run)
                        for out_edge in outgoing:
                            row = [0.0] * n_edges
                            row[edge_to_idx[out_edge.id]] = 1.0
                            inequality_rows.append(row)
                            inequality_rhs.append(0.0)

                # Recipe ratio constraints: tie EACH input to the first output
                # This ensures all inputs are consumed proportionally
                if outgoing and node.outputs:
                    ref_out_rate = node.outputs[0].rate
                    ref_out_edge = outgoing[0]

                    for input_port in node.inputs:
                        input_edges = incoming_by_item.get(input_port.item_name, [])
                        if input_edges and ref_out_rate > 0 and input_port.rate > 0:
                            # Constraint: sum(input_flows) * out_rate = output_flow * in_rate
                            row = [0.0] * n_edges
                            for edge in input_edges:
                                row[edge_to_idx[edge.id]] = ref_out_rate
                            row[edge_to_idx[ref_out_edge.id]] = -input_port.rate
                            equality_rows.append(row)
                            equality_rhs.append(0.0)

                    # Also tie additional outputs to first output (for multi-output recipes)
                    # Constraint: output_i_flow * ref_rate = ref_output_flow * output_i_rate
                    for i, out_edge in enumerate(outgoing[1:], 1):
                        if i < len(node.outputs) and node.outputs[i].rate > 0:
                            row = [0.0] * n_edges
                            row[edge_to_idx[out_edge.id]] = ref_out_rate
                            row[edge_to_idx[ref_out_edge.id]] = -node.outputs[i].rate
                            equality_rows.append(row)
                            equality_rhs.append(0.0)

        elif node.node_type == NodeType.SPLITTER:
            if incoming and outgoing:
                # Conservation: sum(outputs) = sum(inputs) (equality for full flow-through)
                row = [0.0] * n_edges
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = 1.0
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = -1.0
                equality_rows.append(row)
                equality_rhs.append(0.0)

                # Each output is limited by downstream demand (or belt capacity)
                # We DON'T force equal outputs - that breaks tree layouts
                # Instead, we let the LP optimize flow based on actual demand
                for out_edge in outgoing:
                    dest_node = graph.nodes[out_edge.dest_node_id]
                    demand = _get_downstream_demand(dest_node, out_edge.item_name)
                    if demand is not None:
                        row = [0.0] * n_edges
                        row[edge_to_idx[out_edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(demand)

        elif node.node_type == NodeType.MERGER:
            if incoming and outgoing:
                row = [0.0] * n_edges
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = -1.0
                equality_rows.append(row)
                equality_rhs.append(0.0)

        elif node.node_type == NodeType.SINK:
            # Sink inputs are limited by the port rate (which comes from max_rate)
            for i, in_edge in enumerate(incoming):
                if i < len(node.inputs) and node.inputs[i].rate < INFINITE_RATE - 1:
                    row = [0.0] * n_edges
                    row[edge_to_idx[in_edge.id]] = 1.0
                    inequality_rows.append(row)
                    inequality_rhs.append(node.inputs[i].rate)

        elif node.node_type == NodeType.PORT_IN:
            # PORT_IN: receives from external belt, passes to internal
            if incoming and outgoing:
                # Pass-through: sum(inputs) = sum(outputs)
                row = [0.0] * n_edges
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = -1.0
                equality_rows.append(row)
                equality_rhs.append(0.0)
            elif not incoming and outgoing:
                # No external connection - outputs must be 0
                # Use inequality <= 0 combined with non-negativity to force = 0
                for out_edge in outgoing:
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    inequality_rows.append(row)
                    inequality_rhs.append(0.0)

        elif node.node_type == NodeType.PORT_OUT:
            # PORT_OUT: receives from internal, passes to external belt
            if incoming and outgoing:
                # Pass-through: sum(inputs) = sum(outputs)
                row = [0.0] * n_edges
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = -1.0
                equality_rows.append(row)
                equality_rhs.append(0.0)
            elif incoming and not outgoing:
                # No external connection - inputs must be 0
                # Use inequality <= 0 combined with non-negativity to force = 0
                for in_edge in incoming:
                    row = [0.0] * n_edges
                    row[edge_to_idx[in_edge.id]] = 1.0
                    inequality_rows.append(row)
                    inequality_rhs.append(0.0)

    # Objective: maximize total flow (minimize negative flow)
    c = [-1.0] * n_edges

    # All variables are non-negative (flow rates >= 0)
    nonneg_vars = list(range(n_edges))

    # Add upper bounds for edges
    for edge_id, edge in graph.edges.items():
        idx = edge_to_idx[edge_id]
        if use_belt_limits:
            # Use actual belt capacity
            upper_bound = edge.capacity if edge.capacity > 0 else 10000.0
        else:
            # No belt limits - use very high capacity for "theoretical" solve
            upper_bound = INFINITE_RATE
        row = [0.0] * n_edges
        row[idx] = 1.0
        inequality_rows.append(row)
        inequality_rhs.append(upper_bound)

    # Solve using pylinprog (vendored, untyped)
    resolution, solution = linsolve(  # type: ignore[no-untyped-call]
        c,
        ineq_left=inequality_rows,
        ineq_right=inequality_rhs,
        eq_left=equality_rows,
        eq_right=equality_rhs,
        nonneg_variables=nonneg_vars,
    )

    if resolution != RESOLUTION_SOLVED:
        # Provide more helpful error messages
        from satisfactory_planner.core.linprog import (
            RESOLUTION_INCOMPATIBLE,
            RESOLUTION_UNBOUNDED,
        )

        if resolution == RESOLUTION_UNBOUNDED:
            msg = "Flow analysis failed: No constraints limit the flow (check for disconnected outputs)"
        elif resolution == RESOLUTION_INCOMPATIBLE:
            # Build diagnostic info about the constraints
            diag_lines = ["Flow analysis failed: Conflicting constraints"]
            diag_lines.append("")
            diag_lines.append("Nodes in graph:")
            for _node_id, node in graph.nodes.items():
                node_in = [f"{p.item_name}@{p.rate}/min" for p in node.inputs]
                node_out = [f"{p.item_name}@{p.rate}/min" for p in node.outputs]
                diag_lines.append(f"  {node.node_type.name}: in={node_in} out={node_out}")
            msg = "\n".join(diag_lines)
        else:
            msg = f"Flow analysis failed: {resolution}"

        return (False, {}, msg)

    # Extract flows
    flows = {edge_ids[i]: max(0.0, solution[i]) for i in range(n_edges)}
    return (True, flows, "")


def _compute_efficiencies(
    graph: FlowGraph, flows: dict[ItemKey, float]
) -> dict[ItemKey, BuildingEfficiency]:
    """Compute duty cycle and limiting factor for each producer.

    Efficiency is the minimum ratio across all inputs and outputs.
    If any input is constrained, that limits the building's efficiency.
    """
    efficiencies: dict[ItemKey, BuildingEfficiency] = {}

    for node_id, node in graph.nodes.items():
        if node.node_type != NodeType.PRODUCER:
            continue

        outgoing = graph.get_outgoing_edges(node_id)
        incoming = graph.get_incoming_edges(node_id)

        # Calculate efficiency as min ratio across all inputs and outputs
        # Satisfactory allows any belt ordering, so we match by item type
        min_ratio = 1.0
        intended_rate = 0.0
        actual_rate = 0.0

        # Build map of item_name -> total incoming flow
        incoming_by_item: dict[str | None, float] = {}
        for edge in incoming:
            item = edge.item_name
            incoming_by_item[item] = incoming_by_item.get(item, 0.0) + flows.get(edge.id, 0.0)

        # Check each required input
        for input_port in node.inputs:
            if input_port.rate > 0:
                actual_input = incoming_by_item.get(input_port.item_name, 0.0)
                ratio = actual_input / input_port.rate
                if ratio < min_ratio:
                    min_ratio = ratio
                    intended_rate = input_port.rate
                    actual_rate = actual_input

        # Also check outputs (in case downstream is the limit)
        for i, output_port in enumerate(node.outputs):
            if output_port.rate > 0 and i < len(outgoing):
                actual_output = flows.get(outgoing[i].id, 0.0)
                ratio = actual_output / output_port.rate
                if ratio < min_ratio:
                    min_ratio = ratio
                    intended_rate = output_port.rate
                    actual_rate = actual_output

        # If we found no rates, skip this node
        if intended_rate == 0.0 and actual_rate == 0.0:
            continue

        duty_cycle = min_ratio
        limiting_factor, limiting_details = _find_limiting_factor(graph, flows, node, duty_cycle)

        efficiencies[node_id] = BuildingEfficiency(
            building_id=node.building_id or node_id,
            node_id=node_id,
            intended_rate=intended_rate,
            actual_rate=actual_rate,
            duty_cycle=min(1.0, duty_cycle),
            limiting_factor=limiting_factor,
            limiting_details=limiting_details,
        )

    return efficiencies


def _find_limiting_factor(
    graph: FlowGraph,
    flows: dict[ItemKey, float],
    node: FlowNode,
    duty_cycle: float,
) -> tuple[LimitingFactor, str]:
    """Determine why a producer isn't at 100% duty cycle."""
    if duty_cycle >= 0.999:
        return LimitingFactor.NONE, "Running at full capacity"

    incoming = graph.get_incoming_edges(node.id)
    outgoing = graph.get_outgoing_edges(node.id)

    # Build map of item_name -> total incoming flow and edges
    incoming_by_item: dict[str | None, tuple[float, list[FlowEdge]]] = {}
    for edge in incoming:
        item = edge.item_name
        current = incoming_by_item.get(item, (0.0, []))
        incoming_by_item[item] = (current[0] + flows.get(edge.id, 0.0), current[1] + [edge])

    # Check if input-starved (match by item type, not port index)
    for input_port in node.inputs:
        item_data = incoming_by_item.get(input_port.item_name)
        if item_data:
            actual_input, edges = item_data
            if actual_input < input_port.rate - FLOW_TOLERANCE:
                # Check if any feeding belt is at capacity
                for edge in edges:
                    edge_flow = flows.get(edge.id, 0.0)
                    if edge_flow >= edge.capacity - FLOW_TOLERANCE:
                        return (
                            LimitingFactor.BELT_CAPACITY,
                            f"{input_port.item_name} belt at capacity ({edge.capacity}/min)",
                        )
                return (
                    LimitingFactor.INPUT_STARVED,
                    f"{input_port.item_name}: getting {actual_input:.1f}, need {input_port.rate:.1f}/min",
                )
        elif input_port.rate > 0:
            # No belt for this input at all
            return (
                LimitingFactor.INPUT_STARVED,
                f"{input_port.item_name}: no input connected",
            )

    # Check if downstream-limited
    for i, out_edge in enumerate(outgoing):
        if i < len(node.outputs):
            actual_output = flows.get(out_edge.id, 0.0)
            if actual_output < node.outputs[i].rate - FLOW_TOLERANCE:
                edge = graph.edges[out_edge.id]
                if actual_output >= edge.capacity - FLOW_TOLERANCE:
                    return (
                        LimitingFactor.BELT_CAPACITY,
                        f"Output belt at capacity ({edge.capacity}/min)",
                    )
                return (
                    LimitingFactor.DOWNSTREAM,
                    f"Downstream only consumes {actual_output:.1f}/min",
                )

    return LimitingFactor.NONE, "Unknown"
