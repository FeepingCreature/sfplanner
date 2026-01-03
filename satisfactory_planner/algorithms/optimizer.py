"""Joint optimization of network topology and layout."""

import random
from typing import Optional, Callable
from dataclasses import dataclass

from ..models.production import ProductionGraph
from ..models.network import NetworkGraph
from .splitter_gen import generate_network
from .layout import compute_layout, count_crossings, total_edge_length, count_node_collisions


@dataclass
class OptimizationResult:
    """Result of optimization."""
    network: NetworkGraph
    crossings: int
    edge_length: float
    score: float
    iterations: int


def optimize_layout(
    production: ProductionGraph,
    max_iterations: int = 5000,
    stagnation_limit: int = 300,
    progress_callback: Optional[Callable[[int, float], None]] = None,
) -> OptimizationResult:
    """
    Optimize network topology and layout jointly.
    
    Two-phase approach:
    1. Phase 1: Minimize crossings + node collisions (find best topology)
    2. Phase 2: Minimize edge length while maintaining crossing count
    
    Args:
        production: The production graph to realize
        max_iterations: Maximum number of random networks to try
        stagnation_limit: Stop if no improvement for this many iterations
        progress_callback: Called with (iteration, best_score) for progress updates
    
    Returns:
        OptimizationResult with the best network found
    """
    # ===== PHASE 1: Minimize crossings and collisions =====
    best_network: Optional[NetworkGraph] = None
    best_crossings = float('inf')
    best_collisions = float('inf')
    
    stagnation_count = 0
    phase1_iterations = max_iterations // 2
    
    for i in range(phase1_iterations):
        # Generate a random network topology
        network = generate_network(production, randomize=True)
        
        # Layout the network
        compute_layout(network)
        
        # Score by crossings + collisions only
        crossings = count_crossings(network)
        collisions = count_node_collisions(network)
        total_bad = crossings + collisions
        
        if total_bad < best_crossings + best_collisions:
            best_network = network
            best_crossings = crossings
            best_collisions = collisions
            stagnation_count = 0
        else:
            stagnation_count += 1
        
        if progress_callback:
            progress_callback(i, best_crossings + best_collisions)
        
        # Early termination
        if stagnation_count >= stagnation_limit:
            break
        
        # Perfect - no crossings or collisions
        if best_crossings == 0 and best_collisions == 0:
            break
    
    phase1_end = i + 1
    target_crossings = best_crossings
    target_collisions = best_collisions
    
    # ===== PHASE 2: Minimize length while maintaining crossing count =====
    best_length = total_edge_length(best_network) if best_network else float('inf')
    stagnation_count = 0
    phase2_iterations = max_iterations - phase1_end
    
    for i in range(phase2_iterations):
        # Generate a random network topology
        network = generate_network(production, randomize=True)
        
        # Layout the network
        compute_layout(network)
        
        # Check crossings/collisions constraint
        crossings = count_crossings(network)
        collisions = count_node_collisions(network)
        
        # Only consider if doesn't exceed our best crossing count
        if crossings + collisions > target_crossings + target_collisions:
            stagnation_count += 1
            if progress_callback:
                progress_callback(phase1_end + i, best_length)
            if stagnation_count >= stagnation_limit:
                break
            continue
        
        # If better crossings, always take it
        if crossings + collisions < target_crossings + target_collisions:
            target_crossings = crossings
            target_collisions = collisions
            best_network = network
            best_crossings = crossings
            best_collisions = collisions
            best_length = total_edge_length(network)
            stagnation_count = 0
        else:
            # Same crossings - check length
            edge_length = total_edge_length(network)
            
            if edge_length < best_length:
                best_network = network
                best_length = edge_length
                stagnation_count = 0
            else:
                stagnation_count += 1
        
        if progress_callback:
            progress_callback(phase1_end + i, best_length)
        
        if stagnation_count >= stagnation_limit:
            break
    
    total_iterations = phase1_end + i + 1
    
    # ===== PHASE 3: Local search polish =====
    if best_network is None:
        best_network = NetworkGraph()
    else:
        best_network = local_search_improvement(
            best_network,
            iterations=200,
            max_crossings=target_crossings,
            max_collisions=target_collisions,
        )
        best_crossings = count_crossings(best_network)
        best_collisions = count_node_collisions(best_network)
        best_length = total_edge_length(best_network)
    
    return OptimizationResult(
        network=best_network,
        crossings=best_crossings + best_collisions,  # Report combined
        edge_length=best_length,
        score=float(best_crossings + best_collisions),
        iterations=total_iterations,
    )


def local_search_improvement(
    network: NetworkGraph,
    iterations: int = 500,
    max_crossings: int = 0,
    max_collisions: int = 0,
) -> NetworkGraph:
    """
    Improve a network layout through local search.
    
    Tries swapping adjacent nodes within layers to reduce edge length
    while not exceeding the max crossings/collisions constraint.
    """
    layers = _get_layers(network)
    
    current_crossings = count_crossings(network)
    current_collisions = count_node_collisions(network)
    current_length = total_edge_length(network)
    
    for iteration in range(iterations):
        improved = False
        
        # Phase 1: Try swapping adjacent pairs
        for layer in layers:
            if len(layer) < 2:
                continue
            
            for i in range(len(layer) - 1):
                # Swap
                layer[i], layer[i + 1] = layer[i + 1], layer[i]
                _apply_layer_positions(network, layers)
                
                new_crossings = count_crossings(network)
                new_collisions = count_node_collisions(network)
                new_length = total_edge_length(network)
                
                # Accept if: better crossings, OR same crossings + better length
                accept = False
                if new_crossings + new_collisions < current_crossings + current_collisions:
                    accept = True
                elif new_crossings + new_collisions == current_crossings + current_collisions:
                    if new_length < current_length - 1e-6:
                        accept = True
                
                if accept:
                    current_crossings = new_crossings
                    current_collisions = new_collisions
                    current_length = new_length
                    improved = True
                else:
                    # Swap back
                    layer[i], layer[i + 1] = layer[i + 1], layer[i]
        
        # Phase 2: Try moving nodes toward their neighbors
        for layer in layers:
            if len(layer) < 2:
                continue
            
            for i in range(len(layer)):
                node_id = layer[i]
                
                node = network.get_node(node_id)
                neighbors = network.predecessors(node_id) + network.successors(node_id)
                if not neighbors:
                    continue
                
                neighbor_ys = [network.get_node(n).y for n in neighbors if network.get_node(n)]
                if not neighbor_ys:
                    continue
                
                ideal_y = sum(neighbor_ys) / len(neighbor_ys)
                
                # Sort layer by distance from ideal position for this node
                layer_with_ideal = [(node_id, ideal_y) if nid == node_id else (nid, network.get_node(nid).y) 
                                    for nid in layer]
                layer_with_ideal.sort(key=lambda x: x[1])
                new_order = [nid for nid, _ in layer_with_ideal]
                
                if new_order != layer:
                    old_layer = layer.copy()
                    layer.clear()
                    layer.extend(new_order)
                    _apply_layer_positions(network, layers)
                    
                    new_crossings = count_crossings(network)
                    new_collisions = count_node_collisions(network)
                    new_length = total_edge_length(network)
                    
                    accept = False
                    if new_crossings + new_collisions < current_crossings + current_collisions:
                        accept = True
                    elif new_crossings + new_collisions == current_crossings + current_collisions:
                        if new_length < current_length - 1e-6:
                            accept = True
                    
                    if accept:
                        current_crossings = new_crossings
                        current_collisions = new_collisions
                        current_length = new_length
                        improved = True
                    else:
                        layer.clear()
                        layer.extend(old_layer)
        
        if not improved:
            break
    
    _apply_layer_positions(network, layers)
    return network


def _get_layers(network: NetworkGraph) -> list[list[str]]:
    """Extract layer structure from current positions."""
    # Group by x position
    x_to_nodes: dict[float, list[str]] = {}
    
    for node in network.nodes.values():
        if node.x not in x_to_nodes:
            x_to_nodes[node.x] = []
        x_to_nodes[node.x].append(node.id)
    
    # Sort by y within each layer
    for x in x_to_nodes:
        x_to_nodes[x].sort(key=lambda nid: network.get_node(nid).y)
    
    # Sort layers by x
    return [x_to_nodes[x] for x in sorted(x_to_nodes.keys())]


def _apply_layer_positions(network: NetworkGraph, layers: list[list[str]]) -> None:
    """Apply positions based on layer structure."""
    from .layout import LAYER_SPACING, NODE_SPACING
    
    for layer_idx, layer in enumerate(layers):
        x = layer_idx * LAYER_SPACING
        total_height = len(layer) * NODE_SPACING
        start_y = -total_height / 2
        
        for node_idx, node_id in enumerate(layer):
            node = network.get_node(node_id)
            if node:
                node.x = x
                node.y = start_y + node_idx * NODE_SPACING



