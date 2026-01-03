"""Joint optimization of network topology and layout."""

import random
from typing import Optional, Callable
from dataclasses import dataclass

from ..models.production import ProductionGraph
from ..models.network import NetworkGraph
from .splitter_gen import generate_network
from .layout import compute_layout, count_crossings, total_edge_length


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
    max_iterations: int = 300,
    crossing_weight: float = 1000.0,
    length_weight: float = 5.0,
    stagnation_limit: int = 50,
    progress_callback: Optional[Callable[[int, float], None]] = None,
) -> OptimizationResult:
    """
    Optimize network topology and layout jointly.
    
    Generates multiple random network topologies, layouts each,
    and returns the best one.
    
    Args:
        production: The production graph to realize
        max_iterations: Maximum number of random networks to try
        crossing_weight: Weight for crossing count in score
        length_weight: Weight for edge length in score
        stagnation_limit: Stop if no improvement for this many iterations
        progress_callback: Called with (iteration, best_score) for progress updates
    
    Returns:
        OptimizationResult with the best network found
    """
    best_network: Optional[NetworkGraph] = None
    best_score = float('inf')
    best_crossings = 0
    best_length = 0.0
    
    stagnation_count = 0
    
    for i in range(max_iterations):
        # Generate a random network topology
        network = generate_network(production, randomize=True)
        
        # Layout the network
        compute_layout(network)
        
        # Score it
        crossings = count_crossings(network)
        edge_length = total_edge_length(network)
        score = crossings * crossing_weight + edge_length * length_weight
        
        if score < best_score:
            best_network = network
            best_score = score
            best_crossings = crossings
            best_length = edge_length
            stagnation_count = 0
        else:
            stagnation_count += 1
        
        if progress_callback:
            progress_callback(i, best_score)
        
        # Early termination if stagnating
        if stagnation_count >= stagnation_limit:
            break
    
    # If no network was generated (empty production), create an empty one
    if best_network is None:
        best_network = NetworkGraph()
    else:
        # Apply local search to polish the best result
        best_network = local_search_improvement(
            best_network,
            iterations=100,
            crossing_weight=crossing_weight,
            length_weight=length_weight,
        )
        best_crossings = count_crossings(best_network)
        best_length = total_edge_length(best_network)
        best_score = best_crossings * crossing_weight + best_length * length_weight
    
    return OptimizationResult(
        network=best_network,
        crossings=best_crossings,
        edge_length=best_length,
        score=best_score,
        iterations=i + 1,
    )


def local_search_improvement(
    network: NetworkGraph,
    iterations: int = 100,
    crossing_weight: float = 1000.0,
    length_weight: float = 5.0,
) -> NetworkGraph:
    """
    Improve a network layout through local search.
    
    Tries swapping adjacent nodes within layers to reduce crossings,
    and also tries moving nodes to reduce edge lengths.
    """
    # Get current layer structure
    layers = _get_layers(network)
    
    best_score = _score_network(network, crossing_weight, length_weight)
    
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
                
                new_score = _score_network(network, crossing_weight, length_weight)
                
                if new_score < best_score:
                    best_score = new_score
                    improved = True
                else:
                    # Swap back
                    layer[i], layer[i + 1] = layer[i + 1], layer[i]
        
        # Phase 2: Try moving nodes to better positions within layer
        for layer in layers:
            if len(layer) < 2:
                continue
            
            for i in range(len(layer)):
                node_id = layer[i]
                
                # Calculate ideal position based on neighbors
                node = network.get_node(node_id)
                neighbors = network.predecessors(node_id) + network.successors(node_id)
                if not neighbors:
                    continue
                
                neighbor_ys = [network.get_node(n).y for n in neighbors if network.get_node(n)]
                if not neighbor_ys:
                    continue
                
                ideal_y = sum(neighbor_ys) / len(neighbor_ys)
                
                # Find best position in layer based on y-sort
                layer_with_ideal = [(node_id, ideal_y) if nid == node_id else (nid, network.get_node(nid).y) 
                                    for nid in layer]
                layer_with_ideal.sort(key=lambda x: x[1])
                new_order = [nid for nid, _ in layer_with_ideal]
                
                if new_order != layer:
                    old_layer = layer.copy()
                    layer.clear()
                    layer.extend(new_order)
                    _apply_layer_positions(network, layers)
                    
                    new_score = _score_network(network, crossing_weight, length_weight)
                    
                    if new_score < best_score:
                        best_score = new_score
                        improved = True
                    else:
                        # Revert
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


def _score_network(
    network: NetworkGraph,
    crossing_weight: float,
    length_weight: float,
) -> float:
    """Calculate score for a network."""
    crossings = count_crossings(network)
    edge_length = total_edge_length(network)
    return crossings * crossing_weight + edge_length * length_weight
