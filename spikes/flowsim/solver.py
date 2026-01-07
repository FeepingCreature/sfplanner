"""LP-based flow solver.

Solves for steady-state flow rates using linear programming.
"""

from dataclasses import dataclass, field

import numpy as np
from models import BuildingEfficiency, FlowGraph, FlowNode, LimitingFactor, NodeType
from scipy.optimize import linprog


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


def _get_downstream_demand(node: "FlowNode", port_index: int) -> float | None:
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
            # For each output, flow = output rate
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    equality_rows.append(row)
                    equality_rhs.append(node.outputs[i].rate)

        elif node.node_type == NodeType.PRODUCER:
            # Producer: outputs are LIMITED by downstream demand (inequality)
            # Inputs are proportional to outputs (recipe ratio)
            #
            # This lets the LP figure out the actual throughput based on:
            # - What downstream can consume
            # - What upstream can supply
            # We then compute duty cycle = actual / intended

            # Each output is limited by downstream demand
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    dest_node = graph.nodes[out_edge.dest_node_id]
                    demand = _get_downstream_demand(dest_node, out_edge.dest_port_index)
                    if demand is not None:
                        # Output can't exceed what downstream wants
                        row = [0.0] * n_edges
                        row[edge_to_idx[out_edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(demand)

                    # Output also can't exceed production capacity
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    inequality_rows.append(row)
                    inequality_rhs.append(node.outputs[i].rate)

            # If no inputs connected, treat as a source (like a miner)
            # This handles smelters where we don't model the ore input
            if not incoming:
                # No input constraints - outputs just flow at capacity
                # (already constrained by output capacity above)
                pass
            else:
                # Inputs are limited by what upstream can provide
                for i, in_edge in enumerate(incoming):
                    if i < len(node.inputs):
                        # Input can't exceed what we need at full speed
                        row = [0.0] * n_edges
                        row[edge_to_idx[in_edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(node.inputs[i].rate)

                # Recipe ratio constraint: inputs and outputs are proportional
                # If we have input rate r_in and output rate r_out, then:
                # actual_in / r_in = actual_out / r_out (same efficiency)
                if outgoing and node.inputs and node.outputs:
                    # Use first input and first output as reference
                    ref_in_rate = node.inputs[0].rate
                    ref_out_rate = node.outputs[0].rate
                    if ref_in_rate > 0 and ref_out_rate > 0:
                        ref_in_edge = incoming[0]
                        ref_out_edge = outgoing[0]
                        # actual_in / ref_in_rate = actual_out / ref_out_rate
                        # actual_in * ref_out_rate = actual_out * ref_in_rate
                        row = [0.0] * n_edges
                        row[edge_to_idx[ref_in_edge.id]] = ref_out_rate
                        row[edge_to_idx[ref_out_edge.id]] = -ref_in_rate
                        equality_rows.append(row)
                        equality_rhs.append(0.0)

        elif node.node_type == NodeType.SPLITTER:
            # Splitter: sum of outputs <= input (conservation)
            # Each output is limited by downstream demand (handled via inequalities)
            # LP maximizes flow, so it naturally fills hungry outputs first
            if incoming and outgoing:
                # Conservation: sum(outputs) <= sum(inputs)
                # We use inequality here because outputs might not consume all input
                row = [0.0] * n_edges
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = 1.0
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = -1.0
                inequality_rows.append(row)
                inequality_rhs.append(0.0)

                # Each output is limited by what downstream can consume
                # This is computed by following the edge to its dest node
                for out_edge in outgoing:
                    dest_node = graph.nodes[out_edge.dest_node_id]
                    demand = _get_downstream_demand(dest_node, out_edge.dest_port_index)
                    if demand is not None:
                        row = [0.0] * n_edges
                        row[edge_to_idx[out_edge.id]] = 1.0
                        inequality_rows.append(row)
                        inequality_rhs.append(demand)

        elif node.node_type == NodeType.MERGER:
            # Merger: output = sum of inputs
            if incoming and outgoing:
                row = [0.0] * n_edges
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = -1.0
                equality_rows.append(row)
                equality_rhs.append(0.0)

        elif node.node_type in (NodeType.SINK, NodeType.PORT_OUT):
            # Sinks just consume whatever comes in, no constraint needed
            pass

        elif node.node_type == NodeType.PORT_IN:
            # External input: output = specified rate
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    equality_rows.append(row)
                    equality_rhs.append(node.outputs[i].rate)

    # Convert to numpy arrays
    if equality_rows:
        A_eq = np.array(equality_rows)
        b_eq = np.array(equality_rhs)
    else:
        A_eq = None
        b_eq = None

    if inequality_rows:
        A_ub = np.array(inequality_rows)
        b_ub = np.array(inequality_rhs)
    else:
        A_ub = None
        b_ub = None

    # Objective: maximize total flow (minimize negative flow)
    # c @ x is minimized, so use -1 for each flow
    c = np.array([-1.0] * n_edges)

    # Bounds: all flows >= 0
    bounds = [(0, None) for _ in range(n_edges)]

    # Solve
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    if not result.success:
        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=f"LP solver failed: {result.message}",
        )

    # Extract flows
    flows = {edge_ids[i]: max(0.0, result.x[i]) for i in range(n_edges)}

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

        # Get intended and actual rates
        # Prefer output flow, but fall back to input flow for end-of-chain buildings
        outgoing = graph.get_outgoing_edges(node_id)
        incoming = graph.get_incoming_edges(node_id)

        if outgoing and node.outputs:
            # Use output flow
            intended_rate = node.outputs[0].rate
            actual_rate = flows.get(outgoing[0].id, 0.0)
        elif incoming and node.inputs:
            # No outputs connected - compute from input flow
            intended_rate = node.inputs[0].rate
            actual_rate = flows.get(incoming[0].id, 0.0)
        else:
            # No connections at all
            continue

        # Compute duty cycle
        duty_cycle = actual_rate / intended_rate if intended_rate > 0 else 1.0

        # Determine limiting factor
        limiting_factor, limiting_details = _find_limiting_factor(graph, flows, node, duty_cycle)

        efficiencies[node_id] = BuildingEfficiency(
            building_id=node.building_id or node_id,
            node_id=node_id,
            intended_rate=intended_rate,
            actual_rate=actual_rate,
            duty_cycle=min(1.0, duty_cycle),  # Cap at 100%
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

    # Check if input-starved: actual input < needed input
    for i, in_edge in enumerate(incoming):
        if i < len(node.inputs):
            actual_input = flows.get(in_edge.id, 0.0)
            # If we're getting less than we need at full speed,
            # check if upstream is the bottleneck
            if actual_input < node.inputs[i].rate - 0.01:
                # Check if the belt itself is the limit
                edge = graph.edges[in_edge.id]
                if actual_input >= edge.capacity - 0.01:
                    return (
                        LimitingFactor.BELT_CAPACITY,
                        f"Input belt {in_edge.id} at capacity ({edge.capacity}/min)",
                    )
                # Otherwise, upstream isn't producing enough
                return (
                    LimitingFactor.INPUT_STARVED,
                    f"Input {node.inputs[i].item_id}: getting {actual_input:.1f}, need {node.inputs[i].rate:.1f}/min",
                )

    # Check if downstream-limited: output < capacity but we could produce more
    for i, out_edge in enumerate(outgoing):
        if i < len(node.outputs):
            actual_output = flows.get(out_edge.id, 0.0)
            if actual_output < node.outputs[i].rate - 0.01:
                # Check if belt is the limit
                edge = graph.edges[out_edge.id]
                if actual_output >= edge.capacity - 0.01:
                    return (
                        LimitingFactor.BELT_CAPACITY,
                        f"Output belt {out_edge.id} at capacity ({edge.capacity}/min)",
                    )
                # Otherwise, downstream doesn't need more
                return (
                    LimitingFactor.DOWNSTREAM,
                    f"Downstream only consumes {actual_output:.1f}/min",
                )

    return LimitingFactor.NONE, "Unknown"
