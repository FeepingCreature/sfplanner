"""LP-based flow solver.

Solves for steady-state flow rates using linear programming.
"""

from dataclasses import dataclass, field

import numpy as np
from models import FlowGraph, NodeType
from scipy.optimize import linprog


@dataclass
class SolvedModel:
    """Result of solving flow rates."""

    graph: FlowGraph
    flows: dict[str, float] = field(default_factory=dict)  # edge_id → flow rate
    success: bool = True
    message: str = ""


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
    # Each constraint is flow conservation at a node
    equality_rows: list[list[float]] = []
    equality_rhs: list[float] = []

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
            # Producer: consumes inputs, produces outputs at recipe ratio
            # If we have N inputs at rates r1, r2, ... and outputs at rates o1, o2, ...
            # The building runs at efficiency = min(input_i / demand_i)
            # This is non-linear, so we approximate:
            # - Assume building runs at full speed if inputs are available
            # - Set output flow = output rate (demand-driven)

            # For now: set each output to its rated capacity
            # This is "demand-driven" - we want the building to run full speed
            for i, out_edge in enumerate(outgoing):
                if i < len(node.outputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[out_edge.id]] = 1.0
                    equality_rows.append(row)
                    equality_rhs.append(node.outputs[i].rate)

            # Input consumption follows from output (recipe ratio)
            # For each input, flow should equal input rate
            for i, in_edge in enumerate(incoming):
                if i < len(node.inputs):
                    row = [0.0] * n_edges
                    row[edge_to_idx[in_edge.id]] = 1.0
                    equality_rows.append(row)
                    equality_rhs.append(node.inputs[i].rate)

        elif node.node_type == NodeType.SPLITTER:
            # Splitter: sum of outputs = input
            # For equal split: each output = input / num_connected_outputs
            if incoming and outgoing:
                # Conservation: input = sum(outputs)
                row = [0.0] * n_edges
                for in_edge in incoming:
                    row[edge_to_idx[in_edge.id]] = 1.0
                for out_edge in outgoing:
                    row[edge_to_idx[out_edge.id]] = -1.0
                equality_rows.append(row)
                equality_rhs.append(0.0)

                # Equal split: each output = input / n
                n_outputs = len(outgoing)
                if n_outputs > 1:
                    # All outputs equal to each other
                    for i in range(1, n_outputs):
                        row = [0.0] * n_edges
                        row[edge_to_idx[outgoing[0].id]] = 1.0
                        row[edge_to_idx[outgoing[i].id]] = -1.0
                        equality_rows.append(row)
                        equality_rhs.append(0.0)

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

    # Objective: maximize total flow (minimize negative flow)
    # c @ x is minimized, so use -1 for each flow
    c = np.array([-1.0] * n_edges)

    # Bounds: all flows >= 0
    bounds = [(0, None) for _ in range(n_edges)]

    # Solve
    result = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    if not result.success:
        return SolvedModel(
            graph=graph,
            flows={},
            success=False,
            message=f"LP solver failed: {result.message}",
        )

    # Extract flows
    flows = {edge_ids[i]: max(0.0, result.x[i]) for i in range(n_edges)}

    return SolvedModel(graph=graph, flows=flows, success=True)
