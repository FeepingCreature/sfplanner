"""Graph layout algorithms."""

import math
from collections import defaultdict
from typing import Optional

from ..models.network import NetworkGraph, NetworkNode, NodeType


# Layout constants
NODE_WIDTH = 120
NODE_HEIGHT = 60
LAYER_SPACING = 250  # Horizontal spacing between layers
NODE_SPACING = 150   # Vertical spacing between nodes in a layer


def compute_layout(network: NetworkGraph, iterations: int = 50) -> NetworkGraph:
    """
    Compute node positions for the network using a layered layout.
    
    Uses Sugiyama-style layout:
    1. Assign nodes to layers (x-coordinate)
    2. Order nodes within layers to minimize crossings (y-coordinate)
    3. Position nodes
    
    Args:
        network: The network to layout (modified in place)
        iterations: Number of crossing minimization iterations
    
    Returns:
        The same network with positions set
    """
    if not network.nodes:
        return network
    
    # Step 1: Assign layers
    layers = _assign_layers(network)
    
    # Step 2: Order nodes within layers
    layer_order = _minimize_crossings(network, layers, iterations)
    
    # Step 3: Assign positions
    _assign_positions(network, layer_order)
    
    return network


def _assign_layers(network: NetworkGraph) -> dict[str, int]:
    """Assign each node to a layer based on longest path from sources."""
    layers: dict[str, int] = {}
    
    # Find source nodes (no incoming edges)
    sources = [
        nid for nid in network.nodes 
        if network.in_degree(nid) == 0
    ]
    
    # If no sources, pick arbitrary starting point
    if not sources:
        sources = [next(iter(network.nodes))]
    
    # BFS to assign layers
    queue = [(s, 0) for s in sources]
    
    while queue:
        node_id, layer = queue.pop(0)
        
        # Take the maximum layer for each node
        if node_id in layers:
            if layer > layers[node_id]:
                layers[node_id] = layer
            else:
                continue  # Already processed with higher or equal layer
        else:
            layers[node_id] = layer
        
        # Process successors
        for succ in network.successors(node_id):
            queue.append((succ, layer + 1))
    
    # Handle any disconnected nodes
    for node_id in network.nodes:
        if node_id not in layers:
            layers[node_id] = 0
    
    return layers


def _minimize_crossings(
    network: NetworkGraph, 
    layers: dict[str, int],
    iterations: int,
) -> list[list[str]]:
    """
    Order nodes within layers to minimize edge crossings.
    
    Uses the barycenter heuristic: position each node at the average
    position of its neighbors.
    """
    # Group nodes by layer
    max_layer = max(layers.values()) if layers else 0
    layer_nodes: list[list[str]] = [[] for _ in range(max_layer + 1)]
    
    for node_id, layer in layers.items():
        layer_nodes[layer].append(node_id)
    
    # Initialize with arbitrary order
    for layer in layer_nodes:
        layer.sort()  # Consistent initial order
    
    # Iterate to improve
    for _ in range(iterations):
        # Forward pass
        for i in range(1, len(layer_nodes)):
            _order_layer_by_barycenter(network, layer_nodes, i, forward=True)
        
        # Backward pass
        for i in range(len(layer_nodes) - 2, -1, -1):
            _order_layer_by_barycenter(network, layer_nodes, i, forward=False)
    
    return layer_nodes


def _order_layer_by_barycenter(
    network: NetworkGraph,
    layer_nodes: list[list[str]],
    layer_idx: int,
    forward: bool,
) -> None:
    """Order nodes in a layer by barycenter of connected nodes in adjacent layer."""
    layer = layer_nodes[layer_idx]
    
    if forward:
        # Look at predecessors
        adj_layer = layer_nodes[layer_idx - 1] if layer_idx > 0 else []
    else:
        # Look at successors
        adj_layer = layer_nodes[layer_idx + 1] if layer_idx < len(layer_nodes) - 1 else []
    
    if not adj_layer:
        return
    
    # Position lookup for adjacent layer
    adj_positions = {nid: i for i, nid in enumerate(adj_layer)}
    
    # Calculate barycenter for each node in current layer
    barycenters: dict[str, float] = {}
    
    for node_id in layer:
        if forward:
            neighbors = network.predecessors(node_id)
        else:
            neighbors = network.successors(node_id)
        
        positions = [adj_positions[n] for n in neighbors if n in adj_positions]
        
        if positions:
            barycenters[node_id] = sum(positions) / len(positions)
        else:
            # Keep current position
            barycenters[node_id] = layer.index(node_id)
    
    # Sort by barycenter
    layer.sort(key=lambda nid: barycenters[nid])


def _assign_positions(network: NetworkGraph, layer_order: list[list[str]]) -> None:
    """Assign x, y coordinates to nodes based on layer assignment and order."""
    for layer_idx, layer in enumerate(layer_order):
        x = layer_idx * LAYER_SPACING
        
        # Center the layer vertically
        total_height = len(layer) * NODE_SPACING
        start_y = -total_height / 2
        
        for node_idx, node_id in enumerate(layer):
            node = network.get_node(node_id)
            if node:
                node.x = x
                node.y = start_y + node_idx * NODE_SPACING


def count_crossings(network: NetworkGraph) -> int:
    """
    Count the number of edge crossings in the current layout.
    
    Two edges cross if their source nodes are in different vertical order
    than their target nodes.
    """
    crossings = 0
    edges = network.edges
    
    for i, e1 in enumerate(edges):
        for e2 in edges[i + 1:]:
            if _edges_cross(network, e1, e2):
                crossings += 1
    
    return crossings


def _edges_cross(network: NetworkGraph, e1, e2) -> bool:
    """Check if two edges cross."""
    n1_src = network.get_node(e1.source_id)
    n1_tgt = network.get_node(e1.target_id)
    n2_src = network.get_node(e2.source_id)
    n2_tgt = network.get_node(e2.target_id)
    
    if not all([n1_src, n1_tgt, n2_src, n2_tgt]):
        return False
    
    # Check if edges are between same layers
    if n1_src.x != n2_src.x or n1_tgt.x != n2_tgt.x:
        return False
    
    # Check if they cross
    src_order = (n1_src.y < n2_src.y)
    tgt_order = (n1_tgt.y < n2_tgt.y)
    
    return src_order != tgt_order


def total_edge_length(network: NetworkGraph) -> float:
    """Calculate the total length of all edges."""
    total = 0.0
    
    for edge in network.edges:
        src = network.get_node(edge.source_id)
        tgt = network.get_node(edge.target_id)
        
        if src and tgt:
            dx = tgt.x - src.x
            dy = tgt.y - src.y
            total += math.sqrt(dx * dx + dy * dy)
    
    return total


def count_node_collisions(network: NetworkGraph) -> int:
    """
    Count edges that pass through recipe nodes.
    
    Recipe nodes are physical buildings - belts shouldn't route through them.
    """
    collisions = 0
    
    # Get all recipe nodes (they take up physical space)
    recipe_nodes = [n for n in network.nodes.values() if n.node_type == NodeType.RECIPE]
    
    for edge in network.edges:
        src = network.get_node(edge.source_id)
        tgt = network.get_node(edge.target_id)
        
        if not src or not tgt:
            continue
        
        # Check if edge passes through any recipe node
        for node in recipe_nodes:
            # Skip if this node is source or target of the edge
            if node.id == edge.source_id or node.id == edge.target_id:
                continue
            
            if _edge_intersects_node(src, tgt, node):
                collisions += 1
    
    return collisions


def _edge_intersects_node(src: NetworkNode, tgt: NetworkNode, node: NetworkNode) -> bool:
    """Check if an edge from src to tgt passes through node's bounding box."""
    # Node bounding box (with some padding)
    padding = 10
    node_left = node.x - NODE_WIDTH / 2 - padding
    node_right = node.x + NODE_WIDTH / 2 + padding
    node_top = node.y - NODE_HEIGHT / 2 - padding
    node_bottom = node.y + NODE_HEIGHT / 2 + padding
    
    # Check if node is horizontally between src and tgt
    min_x = min(src.x, tgt.x)
    max_x = max(src.x, tgt.x)
    
    if node.x < min_x or node.x > max_x:
        return False
    
    # Interpolate y position of edge at node.x
    if abs(tgt.x - src.x) < 1e-9:
        # Vertical edge - check if node is between
        min_y = min(src.y, tgt.y)
        max_y = max(src.y, tgt.y)
        return node_top < max_y and node_bottom > min_y
    
    t = (node.x - src.x) / (tgt.x - src.x)
    edge_y = src.y + t * (tgt.y - src.y)
    
    # Check if edge y is within node's vertical bounds
    return node_top <= edge_y <= node_bottom
