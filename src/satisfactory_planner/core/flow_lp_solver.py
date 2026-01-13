"""LP-based flow solver.

Solves for steady-state flow rates using linear programming.
Uses pylinprog (pure Python simplex) instead of scipy for smaller package size.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from satisfactory_planner.core.constraint_optimizer import ConstraintSystem
from satisfactory_planner.core.flow_models import (
    BOTTLENECK_TOLERANCE,
    INFINITE_RATE,
    BuildingEfficiency,
    FlowEdge,
    FlowGraph,
    FlowNode,
    LimitingFactor,
    NodeType,
)
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.linprog import RESOLUTION_SOLVED, LPResult, linsolve

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConstraintSource:
    """Identifies the source of an LP constraint for bottleneck tracing."""

    kind: str  # "production_rate", "downstream_demand", "belt_capacity", "input_limit"
    edge_id: ItemKey  # The edge this constraint applies to
    node_id: ItemKey | None = None  # The node that owns this constraint (if applicable)
    description: str = ""  # Human-readable description


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
    # Binding constraint sources from LP duals
    binding_sources: dict[ConstraintSource, float] = field(
        default_factory=dict
    )  # source → dual value


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
    theo_success, theo_flows, theo_msg, _ = _solve_lp(graph, use_belt_limits=False)
    if not theo_success:
        # If theoretical solve fails, return the error
        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=theo_msg,
        )

    actual_success, actual_flows, actual_msg, binding_sources = _solve_lp(
        graph, use_belt_limits=True
    )
    if not actual_success:
        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=actual_msg,
        )

    theoretical_flows = theo_flows

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

    # Compute efficiencies using actual flows and binding constraint info
    efficiencies = _compute_efficiencies(graph, actual_flows, binding_sources)

    return SolvedModel(
        graph=graph,
        flows=actual_flows,
        efficiencies=efficiencies,
        success=True,
        theoretical_flows=theoretical_flows,
        bottlenecks=bottlenecks,
        binding_sources=binding_sources,
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


def _solve_lp(
    graph: FlowGraph, use_belt_limits: bool
) -> tuple[bool, dict[ItemKey, float], str, dict[ConstraintSource, float]]:
    """Run the LP solver.

    Args:
        graph: The flow graph to solve
        use_belt_limits: If True, apply belt capacity constraints

    Returns:
        (success, flows, error_message, binding_sources)
    """
    # Create edge index mapping
    edge_ids = list(graph.edges.keys())
    edge_to_idx = {eid: i for i, eid in enumerate(edge_ids)}
    n_edges = len(edge_ids)

    # Use constraint optimizer for symbolic simplification
    cs: ConstraintSystem[ConstraintSource] = ConstraintSystem(n_vars=n_edges)
    cs.objective = [-1.0] * n_edges  # maximize total flow

    for node_id, node in graph.nodes.items():
        incoming = graph.get_incoming_edges(node_id)
        outgoing = graph.get_outgoing_edges(node_id)

        if node.node_type == NodeType.MINER:
            # Miner/Source: no inputs, output <= production rate
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    cs.add_inequality(
                        {edge_to_idx[out_edge.id]: 1.0},
                        node.outputs[i].rate,
                        source=ConstraintSource(
                            kind="production_rate",
                            edge_id=out_edge.id,
                            node_id=node_id,
                            description=f"Miner output rate {node.outputs[i].rate}/min",
                        ),
                    )

        elif node.node_type == NodeType.PRODUCER:
            # Producer: outputs are LIMITED by downstream demand (inequality)
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    dest_node = graph.nodes[out_edge.dest_node_id]
                    demand = _get_downstream_demand(dest_node, out_edge.item_name)
                    if demand is not None:
                        cs.add_inequality(
                            {edge_to_idx[out_edge.id]: 1.0},
                            demand,
                            source=ConstraintSource(
                                kind="downstream_demand",
                                edge_id=out_edge.id,
                                node_id=out_edge.dest_node_id,
                                description=f"Downstream demand {demand}/min",
                            ),
                        )

                    # Output also can't exceed production capacity
                    cs.add_inequality(
                        {edge_to_idx[out_edge.id]: 1.0},
                        node.outputs[i].rate,
                        source=ConstraintSource(
                            kind="production_rate",
                            edge_id=out_edge.id,
                            node_id=node_id,
                            description=f"Production rate {node.outputs[i].rate}/min",
                        ),
                    )

            if incoming:
                # Build map of item_name -> total incoming flow for that item
                incoming_by_item: dict[str | None, list[FlowEdge]] = {}
                for edge in incoming:
                    incoming_by_item.setdefault(edge.item_name, []).append(edge)

                # For each required input item, constrain the sum of belts carrying it
                for input_port in node.inputs:
                    item_edges = incoming_by_item.get(input_port.item_name, [])
                    if item_edges:
                        # Sum of all belts for this item <= required rate
                        coeffs = {edge_to_idx[e.id]: 1.0 for e in item_edges}
                        # Use first edge as representative for source tracking
                        cs.add_inequality(
                            coeffs,
                            input_port.rate,
                            source=ConstraintSource(
                                kind="input_limit",
                                edge_id=item_edges[0].id,
                                node_id=node_id,
                                description=f"Input limit {input_port.rate}/min for {input_port.item_name}",
                            ),
                        )
                    elif input_port.item_name:
                        # Missing input - force outputs to zero
                        for out_edge in outgoing:
                            cs.add_inequality({edge_to_idx[out_edge.id]: 1.0}, 0.0)

                # Recipe ratio constraints: tie EACH input to the first output
                if outgoing and node.outputs:
                    ref_out_rate = node.outputs[0].rate
                    ref_out_edge = outgoing[0]

                    for input_port in node.inputs:
                        input_edges = incoming_by_item.get(input_port.item_name, [])
                        if input_edges and ref_out_rate > 0 and input_port.rate > 0:
                            # sum(input_flows) * out_rate = output_flow * in_rate
                            ratio_coeffs: dict[int, float] = {}
                            for edge in input_edges:
                                ratio_coeffs[edge_to_idx[edge.id]] = ref_out_rate
                            ratio_coeffs[edge_to_idx[ref_out_edge.id]] = -input_port.rate
                            cs.add_equality(ratio_coeffs, 0.0)

                    # Tie additional outputs to first output (multi-output recipes)
                    for i, out_edge in enumerate(outgoing[1:], 1):
                        if i < len(node.outputs) and node.outputs[i].rate > 0:
                            cs.add_equality(
                                {
                                    edge_to_idx[out_edge.id]: ref_out_rate,
                                    edge_to_idx[ref_out_edge.id]: -node.outputs[i].rate,
                                },
                                0.0,
                            )

        elif node.node_type == NodeType.SPLITTER:
            if incoming and outgoing:
                # Conservation: sum(outputs) = sum(inputs)
                coeffs = {}
                for out_edge in outgoing:
                    coeffs[edge_to_idx[out_edge.id]] = 1.0
                for in_edge in incoming:
                    coeffs[edge_to_idx[in_edge.id]] = -1.0
                cs.add_equality(coeffs, 0.0)

                # Each output is limited by downstream demand
                for out_edge in outgoing:
                    dest_node = graph.nodes[out_edge.dest_node_id]
                    demand = _get_downstream_demand(dest_node, out_edge.item_name)
                    if demand is not None:
                        cs.add_inequality(
                            {edge_to_idx[out_edge.id]: 1.0},
                            demand,
                            source=ConstraintSource(
                                kind="downstream_demand",
                                edge_id=out_edge.id,
                                node_id=out_edge.dest_node_id,
                                description=f"Downstream demand {demand}/min",
                            ),
                        )

        elif node.node_type == NodeType.MERGER:
            if incoming and outgoing:
                # Conservation: sum(inputs) = sum(outputs)
                coeffs = {}
                for in_edge in incoming:
                    coeffs[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    coeffs[edge_to_idx[out_edge.id]] = -1.0
                cs.add_equality(coeffs, 0.0)

        elif node.node_type == NodeType.SINK:
            # Sink inputs are limited by the port rate
            for i, in_edge in enumerate(incoming):
                if i < len(node.inputs) and node.inputs[i].rate < INFINITE_RATE - 1:
                    cs.add_inequality(
                        {edge_to_idx[in_edge.id]: 1.0},
                        node.inputs[i].rate,
                        source=ConstraintSource(
                            kind="downstream_demand",
                            edge_id=in_edge.id,
                            node_id=node_id,
                            description=f"Sink capacity {node.inputs[i].rate}/min",
                        ),
                    )

        elif node.node_type == NodeType.PORT_IN:
            # PORT_IN: receives from external belt, passes to internal
            if incoming and outgoing:
                # Pass-through: sum(inputs) = sum(outputs)
                coeffs = {}
                for in_edge in incoming:
                    coeffs[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    coeffs[edge_to_idx[out_edge.id]] = -1.0
                cs.add_equality(coeffs, 0.0)
            elif not incoming and outgoing:
                # No external connection - outputs must be 0
                for out_edge in outgoing:
                    cs.add_inequality({edge_to_idx[out_edge.id]: 1.0}, 0.0)

        elif node.node_type == NodeType.PORT_OUT:
            # PORT_OUT: receives from internal, passes to external belt
            if incoming and outgoing:
                # Pass-through: sum(inputs) = sum(outputs)
                coeffs = {}
                for in_edge in incoming:
                    coeffs[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    coeffs[edge_to_idx[out_edge.id]] = -1.0
                cs.add_equality(coeffs, 0.0)
            elif incoming and not outgoing:
                # No external connection - inputs must be 0
                for in_edge in incoming:
                    cs.add_inequality({edge_to_idx[in_edge.id]: 1.0}, 0.0)

    # Add upper bounds for edges (belt capacity or infinite)
    for edge_id, edge in graph.edges.items():
        idx = edge_to_idx[edge_id]
        if use_belt_limits:
            upper_bound = edge.capacity if edge.capacity > 0 else 10000.0
            cs.add_inequality(
                {idx: 1.0},
                upper_bound,
                source=ConstraintSource(
                    kind="belt_capacity",
                    edge_id=edge_id,
                    description=f"Belt capacity {upper_bound}/min",
                ),
            )
        else:
            upper_bound = INFINITE_RATE
            cs.add_inequality({idx: 1.0}, upper_bound)  # No source - not a real constraint

    # Optimize the constraint system before solving
    cs.optimize()

    # Get the reduced system
    active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective = cs.get_reduced_system()

    # If no active variables, return zero flows
    if not active_vars:
        return (True, dict.fromkeys(edge_ids, 0.0), "", {})

    # Solve using pylinprog with dual extraction
    result = linsolve(
        objective,
        ineq_left=ineq_matrix,
        ineq_right=ineq_rhs,
        eq_left=eq_matrix,
        eq_right=eq_rhs,
        nonneg_variables=list(range(len(active_vars))),
        return_duals=True,
    )
    assert isinstance(result, LPResult)
    resolution = result.resolution
    reduced_solution = result.solution

    if resolution != RESOLUTION_SOLVED:
        from satisfactory_planner.core.linprog import (
            RESOLUTION_INCOMPATIBLE,
            RESOLUTION_UNBOUNDED,
        )

        if resolution == RESOLUTION_UNBOUNDED:
            msg = "Flow analysis failed: No constraints limit the flow (check for disconnected outputs)"
        elif resolution == RESOLUTION_INCOMPATIBLE:
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

        return (False, {}, msg, {})

    # Expand reduced solution back to full variable space
    assert reduced_solution is not None
    full_solution = cs.expand_solution(reduced_solution, active_vars)

    # Extract binding constraint sources (only when using belt limits - the "real" solve)
    binding_sources: dict[ConstraintSource, float] = {}
    if use_belt_limits and result.ineq_duals:
        binding_sources = cs.get_binding_sources(reduced_solution, active_vars, result.ineq_duals)

    # Extract flows
    flows = {edge_ids[i]: max(0.0, full_solution[i]) for i in range(n_edges)}
    return (True, flows, "", binding_sources)


def _compute_efficiencies(
    graph: FlowGraph,
    flows: dict[ItemKey, float],
    binding_sources: dict[ConstraintSource, float] | None = None,
) -> dict[ItemKey, BuildingEfficiency]:
    """Compute duty cycle and limiting factor for each producer.

    Efficiency is the minimum ratio across all applicable inputs and outputs.
    Buildings with no inputs (miners/sources) only consider outputs.
    We track the MOST limiting factor (lowest ratio), not just the first.
    """
    efficiencies: dict[ItemKey, BuildingEfficiency] = {}

    for node_id, node in graph.nodes.items():
        if node.node_type != NodeType.PRODUCER:
            continue

        outgoing = graph.get_outgoing_edges(node_id)
        incoming = graph.get_incoming_edges(node_id)

        # Calculate efficiency as min ratio across applicable factors
        # Track the most limiting one (lowest ratio)
        min_ratio: float | None = None
        limiting_intended = 0.0
        limiting_actual = 0.0

        def update_min(actual: float, intended: float) -> None:
            """Update min_ratio if this factor is more limiting."""
            nonlocal min_ratio, limiting_intended, limiting_actual
            if intended <= 0:
                return
            ratio = actual / intended
            if min_ratio is None or ratio < min_ratio:
                min_ratio = ratio
                limiting_intended = intended
                limiting_actual = actual

        # Only check inputs if building has incoming edges
        # Buildings with missing inputs get a separate warning, efficiency is about
        # how well the building runs given what it HAS connected
        if incoming:
            # Build map of item_name -> total incoming flow
            incoming_by_item: dict[str | None, float] = {}
            for edge in incoming:
                item = edge.item_name
                incoming_by_item[item] = incoming_by_item.get(item, 0.0) + flows.get(edge.id, 0.0)

            # Check each required input that has a belt connected
            for input_port in node.inputs:
                if input_port.item_name in incoming_by_item:
                    actual_input = incoming_by_item[input_port.item_name]
                    update_min(actual_input, input_port.rate)

        # Check outputs (always applicable)
        for i, output_port in enumerate(node.outputs):
            if i < len(outgoing):
                actual_output = flows.get(outgoing[i].id, 0.0)
                update_min(actual_output, output_port.rate)

        # If we found no applicable rates, skip this node
        if min_ratio is None:
            continue

        duty_cycle = min_ratio
        limiting_factor, limiting_details = _find_limiting_factor(
            graph, flows, node, duty_cycle, binding_sources
        )

        efficiencies[node_id] = BuildingEfficiency(
            building_id=node.building_id or node_id,
            node_id=node_id,
            intended_rate=limiting_intended,
            actual_rate=limiting_actual,
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
    binding_sources: dict[ConstraintSource, float] | None = None,
) -> tuple[LimitingFactor, str]:
    """Determine why a producer isn't at 100% duty cycle.

    Uses LP dual values (shadow prices) to identify the TRUE limiting constraint.
    This avoids the problem where output limits cause proportionally reduced inputs
    (due to recipe ratios), making it look like an input problem when it's really
    an output problem.

    A constraint with a positive dual is "binding" - it's actually limiting flow.

    When no binding constraint is found on direct edges (e.g., there's a splitter
    between the source and this node), we walk upstream through the graph to find
    the actual binding constraint.
    """
    if duty_cycle >= 0.999:
        return LimitingFactor.NONE, "Running at full capacity"

    if not binding_sources:
        return LimitingFactor.NONE, "Unknown (no constraint info)"

    incoming = graph.get_incoming_edges(node.id)
    outgoing = graph.get_outgoing_edges(node.id)

    # Build lookup of binding constraints by edge_id for efficient access
    binding_by_edge: dict[ItemKey, tuple[ConstraintSource, float]] = {}
    for source, dual in binding_sources.items():
        if dual > 0:
            binding_by_edge[source.edge_id] = (source, dual)

    # Check outgoing edges for downstream/belt constraints
    for edge in outgoing:
        if edge.id in binding_by_edge:
            source, _ = binding_by_edge[edge.id]
            if source.kind == "belt_capacity":
                return LimitingFactor.BELT_CAPACITY, source.description
            elif source.kind == "downstream_demand":
                return LimitingFactor.DOWNSTREAM, source.description

    # Check incoming edges for direct input constraints
    for edge in incoming:
        if edge.id in binding_by_edge:
            source, _ = binding_by_edge[edge.id]
            if source.kind == "production_rate":
                item_name = edge.item_name or "input"
                return (
                    LimitingFactor.INPUT_STARVED,
                    f"{item_name} limited by upstream ({source.description})",
                )
            elif source.kind == "input_limit":
                return LimitingFactor.INPUT_STARVED, source.description

    # No direct binding constraint found - walk upstream through splitters/mergers
    # to find the actual binding constraint (BFS)
    result = _find_upstream_binding_constraint(graph, incoming, binding_by_edge)
    if result:
        return result

    return LimitingFactor.NONE, "Unknown (no matching constraint)"


def _find_upstream_binding_constraint(
    graph: FlowGraph,
    starting_edges: list[FlowEdge],
    binding_by_edge: dict[ItemKey, tuple[ConstraintSource, float]],
) -> tuple[LimitingFactor, str] | None:
    """Walk upstream through splitters/mergers to find binding constraints.

    Stops when we hit a producer/miner (those have their own efficiency) or find
    a binding constraint.
    """
    from collections import deque

    visited: set[ItemKey] = set()
    queue: deque[FlowEdge] = deque(starting_edges)

    while queue:
        edge = queue.popleft()
        if edge.id in visited:
            continue
        visited.add(edge.id)

        # Check if this edge has a binding constraint
        if edge.id in binding_by_edge:
            source, _ = binding_by_edge[edge.id]
            if source.kind == "production_rate":
                item_name = edge.item_name or "input"
                return (
                    LimitingFactor.INPUT_STARVED,
                    f"{item_name} limited by upstream ({source.description})",
                )
            elif source.kind == "belt_capacity":
                return LimitingFactor.BELT_CAPACITY, source.description

        # Get the source node of this edge
        source_node = graph.nodes.get(edge.source_node_id)
        if not source_node:
            continue

        # Stop at producers/miners - they have their own constraints
        if source_node.node_type in (NodeType.PRODUCER, NodeType.MINER):
            continue

        # For splitters/mergers, continue walking upstream
        if source_node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
            upstream_edges = graph.get_incoming_edges(source_node.id)
            for upstream_edge in upstream_edges:
                if upstream_edge.id not in visited:
                    queue.append(upstream_edge)

    return None
