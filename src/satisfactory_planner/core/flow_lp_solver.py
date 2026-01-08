"""LP-based flow solver.

Solves for steady-state flow rates using linear programming.
Uses pylinprog (pure Python simplex) instead of scipy for smaller package size.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from satisfactory_planner.core.flow_models import (
    BuildingEfficiency,
    FlowGraph,
    FlowNode,
    LimitingFactor,
    NodeType,
)
from satisfactory_planner.core.linprog import RESOLUTION_SOLVED, linsolve


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

    We solve WITHOUT belt capacity constraints to get "ideal" flows.
    Capacity checking happens in the warning detection phase.

    The LP formulation:
    - Variables: one flow rate per edge
    - Constraints: flow conservation at each node
    - Objective: maximize total flow (to fill the factory)
    """
    if not graph.edges:
        # No edges = no flows to solve
        return SolvedModel(graph=graph, flows={})

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
            # Miner: no inputs, output = production rate
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    equality_rows.append(row)
                    equality_rhs.append(node.outputs[i].rate)

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
                # Conservation: sum(outputs) <= sum(inputs)
                row = [0.0] * n_edges
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = 1.0
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = -1.0
                inequality_rows.append(row)
                inequality_rhs.append(0.0)

                # Each output is limited by downstream demand
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

        elif node.node_type in (NodeType.SINK, NodeType.PORT_OUT):
            # Sinks just consume whatever comes in
            pass

        elif node.node_type == NodeType.PORT_IN:
            # External input: output = specified rate
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    equality_rows.append(row)
                    equality_rhs.append(node.outputs[i].rate)

    # Objective: maximize total flow (minimize negative flow)
    c = [-1.0] * n_edges

    # All variables are non-negative (flow rates >= 0)
    nonneg_vars = list(range(n_edges))

    # Add upper bounds to prevent unbounded solutions
    # Each edge is bounded by its belt capacity (or a large default)
    for edge_id, edge in graph.edges.items():
        idx = edge_to_idx[edge_id]
        # Use belt capacity as upper bound, or 10000 as fallback
        upper_bound = edge.capacity if edge.capacity > 0 else 10000.0
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
            msg = "Flow analysis failed: Conflicting constraints (check recipe ratios)"
        else:
            msg = f"Flow analysis failed: {resolution}"

        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=msg,
        )

    # Extract flows
    flows = {edge_ids[i]: max(0.0, solution[i]) for i in range(n_edges)}

    # Compute duty cycles for all producer nodes
    efficiencies = _compute_efficiencies(graph, flows)

    return SolvedModel(graph=graph, flows=flows, efficiencies=efficiencies, success=True)


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
            if actual_input < node.inputs[i].rate - 0.01:
                edge = graph.edges[in_edge.id]
                if actual_input >= edge.capacity - 0.01:
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
            if actual_output < node.outputs[i].rate - 0.01:
                edge = graph.edges[out_edge.id]
                if actual_output >= edge.capacity - 0.01:
                    return (
                        LimitingFactor.BELT_CAPACITY,
                        f"Output belt {out_edge.id} at capacity ({edge.capacity}/min)",
                    )
                return (
                    LimitingFactor.DOWNSTREAM,
                    f"Downstream only consumes {actual_output:.1f}/min",
                )

    return LimitingFactor.NONE, "Unknown"
