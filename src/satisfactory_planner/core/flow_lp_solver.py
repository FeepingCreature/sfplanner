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
    FlowGraph,
    FlowNode,
    LimitingFactor,
    NodeType,
)
from satisfactory_planner.core.linprog import RESOLUTION_SOLVED, linsolve

logger = logging.getLogger(__name__)


@dataclass
class SolvedModel:
    """Result of solving flow rates."""

    graph: FlowGraph
    flows: dict[str, float] = field(default_factory=dict)  # edge_id → flow rate
    efficiencies: dict[str, BuildingEfficiency] = field(
        default_factory=dict
    )  # node_id → efficiency
    success: bool = True
    message: str = ""
    # Two-pass results for bottleneck detection
    theoretical_flows: dict[str, float] = field(default_factory=dict)
    bottlenecks: dict[str, tuple[float, float]] = field(
        default_factory=dict
    )  # edge_id → (theoretical, actual)


def _get_downstream_demand(node: FlowNode, port_index: int) -> float | None:
    """Get the demand of a node's input port.

    For producers, this is the recipe input rate.
    For splitters/mergers, we return None (no fixed demand).
    """
    if node.node_type == NodeType.PRODUCER:
        if port_index < len(node.inputs):
            return node.inputs[port_index].rate
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
    bottlenecks: dict[str, tuple[float, float]] = {}
    for edge_id, edge in graph.edges.items():
        theo = theoretical_flows.get(edge_id, 0.0)
        actual = actual_flows.get(edge_id, 0.0)
        # A belt is a bottleneck if:
        # 1. Theoretical flow exceeds actual
        # 2. Actual flow is at or near belt capacity
        if theo > actual + BOTTLENECK_TOLERANCE and actual >= edge.capacity - BOTTLENECK_TOLERANCE:
            bottlenecks[edge_id] = (theo, actual)

    # Write DOT file for visualization
    _write_dot_file(graph, actual_flows, theoretical_flows, bottlenecks)

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
    flows: dict[str, float],
    theoretical_flows: dict[str, float],
    bottlenecks: dict[str, tuple[float, float]],
    suffix: str = "",
) -> None:
    """Write the flow graph to a DOT file for visualization."""
    dot_path = Path.home() / f"flow_graph{suffix}.dot"

    lines = [
        "digraph FlowGraph {",
        "  rankdir=LR;",
        "  node [shape=record, fontname=\"Courier\", fontsize=10];",
        "  edge [fontname=\"Courier\", fontsize=9];",
        "",
    ]

    # Node colors by type
    node_colors = {
        NodeType.MINER: "#90EE90",      # Light green
        NodeType.PRODUCER: "#87CEEB",   # Light blue
        NodeType.SPLITTER: "#FFD700",   # Gold
        NodeType.MERGER: "#FFA500",     # Orange
        NodeType.SINK: "#FF6B6B",       # Light red
        NodeType.PORT_IN: "#DDA0DD",    # Plum
        NodeType.PORT_OUT: "#DDA0DD",   # Plum
    }

    # Nodes with full details
    for node_id, node in graph.nodes.items():
        color = node_colors.get(node.node_type, "#FFFFFF")
        safe_id = node_id.replace("-", "_").replace(":", "_")

        # Build port details
        in_ports = []
        for i, p in enumerate(node.inputs):
            rate_str = f"{p.rate:.0f}" if p.rate < 10000 else "∞"
            in_ports.append(f"IN{i}: {p.item_id or '?'}@{rate_str}")

        out_ports = []
        for i, p in enumerate(node.outputs):
            rate_str = f"{p.rate:.0f}" if p.rate < 10000 else "∞"
            out_ports.append(f"OUT{i}: {p.item_id or '?'}@{rate_str}")

        # Recipe info for producers
        recipe_str = ""
        if node.recipe_id:
            recipe_str = f"\\nrecipe: {node.recipe_id}"
        if node.clock_speed != 1.0:
            recipe_str += f"\\nclock: {node.clock_speed:.0%}"

        # Build label
        label_parts = [f"{node.node_type.name}\\n{node_id[:12]}...{recipe_str}"]
        if in_ports:
            label_parts.append("| {" + " | ".join(in_ports) + "}")
        if out_ports:
            label_parts.append("| {" + " | ".join(out_ports) + "}")

        label = "{" + "".join(label_parts) + "}"
        lines.append(f'  "{safe_id}" [label="{label}", style=filled, fillcolor="{color}"];')

    lines.append("")

    # Edges with flow info
    for edge_id, edge in graph.edges.items():
        src_safe = edge.source_node_id.replace("-", "_").replace(":", "_")
        dst_safe = edge.dest_node_id.replace("-", "_").replace(":", "_")

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
            f"{edge.item_id or '?'}",
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


def _solve_lp(graph: FlowGraph, use_belt_limits: bool) -> tuple[bool, dict[str, float], str]:
    """Run the LP solver.

    Args:
        graph: The flow graph to solve
        use_belt_limits: If True, apply belt capacity constraints

    Returns:
        (success, flows, error_message)
    """
    logger.debug(f"LP SOLVE (belt_limits={use_belt_limits})")

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
                    demand = _get_downstream_demand(dest_node, out_edge.dest_port_index)
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
                # Inputs are limited by what upstream can provide
                for i, in_edge in enumerate(incoming):
                    if i < len(node.inputs):
                        row = [0.0] * n_edges
                        row[edge_to_idx[in_edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(node.inputs[i].rate)

                # Recipe ratio constraint
                if outgoing and node.inputs and node.outputs:
                    ref_in_rate = node.inputs[0].rate
                    ref_out_rate = node.outputs[0].rate
                    if ref_in_rate > 0 and ref_out_rate > 0:
                        ref_in_edge = incoming[0]
                        ref_out_edge = outgoing[0]
                        row = [0.0] * n_edges
                        row[edge_to_idx[ref_in_edge.id]] = ref_out_rate
                        row[edge_to_idx[ref_out_edge.id]] = -ref_in_rate
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
                    demand = _get_downstream_demand(dest_node, out_edge.dest_port_index)
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

        elif node.node_type in (NodeType.PORT_IN, NodeType.PORT_OUT) and incoming and outgoing:
            # Ports are pass-through: sum(inputs) = sum(outputs)
            row = [0.0] * n_edges
            for in_edge in incoming:
                row[edge_to_idx[in_edge.id]] = 1.0
            for out_edge in outgoing:
                row[edge_to_idx[out_edge.id]] = -1.0
            equality_rows.append(row)
            equality_rhs.append(0.0)

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

    # Log constraint summary
    logger.debug(f"  {len(inequality_rows)} inequality constraints, {len(equality_rows)} equality constraints")

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
                node_in = [f"{p.item_id}@{p.rate}/min" for p in node.inputs]
                node_out = [f"{p.item_id}@{p.rate}/min" for p in node.outputs]
                diag_lines.append(f"  {node.node_type.name}: in={node_in} out={node_out}")
            msg = "\n".join(diag_lines)
        else:
            msg = f"Flow analysis failed: {resolution}"

        return (False, {}, msg)

    # Extract flows
    flows = {edge_ids[i]: max(0.0, solution[i]) for i in range(n_edges)}
    return (True, flows, "")


def _compute_efficiencies(
    graph: FlowGraph, flows: dict[str, float]
) -> dict[str, BuildingEfficiency]:
    """Compute duty cycle and limiting factor for each producer."""
    efficiencies: dict[str, BuildingEfficiency] = {}

    for node_id, node in graph.nodes.items():
        if node.node_type != NodeType.PRODUCER:
            continue

        outgoing = graph.get_outgoing_edges(node_id)
        incoming = graph.get_incoming_edges(node_id)

        if outgoing and node.outputs:
            intended_rate = node.outputs[0].rate
            actual_rate = flows.get(outgoing[0].id, 0.0)
        elif incoming and node.inputs:
            intended_rate = node.inputs[0].rate
            actual_rate = flows.get(incoming[0].id, 0.0)
        else:
            continue

        duty_cycle = actual_rate / intended_rate if intended_rate > 0 else 1.0
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
    flows: dict[str, float],
    node: FlowNode,
    duty_cycle: float,
) -> tuple[LimitingFactor, str]:
    """Determine why a producer isn't at 100% duty cycle."""
    if duty_cycle >= 0.999:
        return LimitingFactor.NONE, "Running at full capacity"

    incoming = graph.get_incoming_edges(node.id)
    outgoing = graph.get_outgoing_edges(node.id)

    # Check if input-starved
    for i, in_edge in enumerate(incoming):
        if i < len(node.inputs):
            actual_input = flows.get(in_edge.id, 0.0)
            if actual_input < node.inputs[i].rate - FLOW_TOLERANCE:
                edge = graph.edges[in_edge.id]
                if actual_input >= edge.capacity - FLOW_TOLERANCE:
                    return (
                        LimitingFactor.BELT_CAPACITY,
                        f"Input belt {in_edge.id} at capacity ({edge.capacity}/min)",
                    )
                return (
                    LimitingFactor.INPUT_STARVED,
                    f"Input {node.inputs[i].item_id}: getting {actual_input:.1f}, need {node.inputs[i].rate:.1f}/min",
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
                        f"Output belt {out_edge.id} at capacity ({edge.capacity}/min)",
                    )
                return (
                    LimitingFactor.DOWNSTREAM,
                    f"Downstream only consumes {actual_output:.1f}/min",
                )

    return LimitingFactor.NONE, "Unknown"
