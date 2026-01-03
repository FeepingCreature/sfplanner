"""Generate physical network with splitters and mergers."""

import random
import math
from typing import Optional
from collections import defaultdict

from ..models.production import ProductionGraph, ProductionNode, ProductionEdge
from ..models.network import NetworkGraph, NetworkNode, NetworkEdge, NodeType


def generate_network(
    production: ProductionGraph,
    randomize: bool = True,
) -> NetworkGraph:
    """
    Generate a physical network from a production graph.
    
    This adds splitters and mergers as needed to connect recipe nodes.
    
    Args:
        production: The abstract production graph
        randomize: If True, make random choices in topology generation
    
    Returns:
        NetworkGraph with recipe nodes, splitters, mergers, and connections
    """
    network = NetworkGraph()
    
    # Create network nodes for each production node
    prod_to_net: dict[str, str] = {}  # production node id -> network node id
    
    for prod_node in production.nodes.values():
        net_node = network.create_node(
            NodeType.RECIPE,
            label=f"{prod_node.recipe.name} x{prod_node.count:.1f}",
            production_node_id=prod_node.id,
        )
        prod_to_net[prod_node.id] = net_node.id
    
    # Create source nodes
    source_nodes: dict[str, str] = {}  # item -> network node id
    for item, rate in production.sources.items():
        net_node = network.create_node(
            NodeType.SOURCE,
            label=f"Source: {item}",
            item=item,
            rate=rate,
        )
        source_nodes[item] = net_node.id
    
    # Create sink nodes
    sink_nodes: dict[str, str] = {}  # item -> network node id
    for item, rate in production.sinks.items():
        net_node = network.create_node(
            NodeType.SINK,
            label=f"Output: {item}",
            item=item,
            rate=rate,
        )
        sink_nodes[item] = net_node.id
    
    # Group edges by source and target for splitter/merger generation
    # source_id -> [(target_id, item, rate)]
    outgoing: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    # target_id -> [(source_id, item, rate)]
    incoming: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    
    for edge in production.edges:
        outgoing[edge.source_id].append((edge.target_id, edge.item, edge.rate))
        incoming[edge.target_id].append((edge.source_id, edge.item, edge.rate))
    
    # Process each connection, adding splitters/mergers as needed
    for edge in production.edges:
        source_net_id = prod_to_net[edge.source_id]
        target_net_id = prod_to_net[edge.target_id]
        
        # Check if we need splitters (source has multiple outputs of this item)
        source_outputs = [e for e in outgoing[edge.source_id] if e[1] == edge.item]
        
        # Check if we need mergers (target has multiple inputs of this item)
        target_inputs = [e for e in incoming[edge.target_id] if e[1] == edge.item]
        
        if len(source_outputs) > 1:
            # Need splitters - find or create splitter chain for this source/item
            splitter_out = _get_or_create_splitter_output(
                network, source_net_id, edge.item, edge.rate, randomize
            )
            source_net_id = splitter_out
        
        if len(target_inputs) > 1:
            # Need mergers - find or create merger chain for this target/item
            merger_in = _get_or_create_merger_input(
                network, target_net_id, edge.item, edge.rate, randomize
            )
            target_net_id = merger_in
        
        # Connect (possibly through splitters/mergers)
        network.connect(source_net_id, target_net_id, edge.item, edge.rate)
    
    # Connect sources to their consumers
    for item, source_id in source_nodes.items():
        # Find recipe nodes that need this item
        for prod_node in production.nodes.values():
            if item in prod_node.recipe.inputs:
                needed = prod_node.effective_inputs[item]
                target_id = prod_to_net[prod_node.id]
                network.connect(source_id, target_id, item, needed)
    
    # Connect producers to sinks
    for item, sink_id in sink_nodes.items():
        # Find recipe nodes that produce this item for final output
        for prod_node in production.nodes.values():
            if item in prod_node.recipe.outputs:
                # Check if any output goes to sink
                produced = prod_node.effective_outputs[item]
                # Subtract what goes to other nodes
                used = sum(
                    e.rate for e in production.edges 
                    if e.source_id == prod_node.id and e.item == item
                )
                to_sink = produced - used
                if to_sink > 0:
                    source_id = prod_to_net[prod_node.id]
                    network.connect(source_id, sink_id, item, to_sink)
    
    return network


def _get_or_create_splitter_output(
    network: NetworkGraph,
    source_id: str,
    item: str,
    rate: float,
    randomize: bool,
) -> str:
    """
    Get an available splitter output for a source, creating splitters as needed.
    
    Returns the node ID to connect from.
    """
    # Check existing splitters connected to source
    existing_splitters = [
        network.get_node(e.target_id) 
        for e in network.edges_from(source_id)
        if network.get_node(e.target_id).node_type == NodeType.SPLITTER
    ]
    
    for splitter in existing_splitters:
        # Each splitter can have up to 3 outputs
        if network.out_degree(splitter.id) < 3:
            return splitter.id
    
    # Need to create a new splitter
    # If source already has 1 direct output, we should insert a splitter
    direct_outputs = network.out_degree(source_id)
    
    if direct_outputs == 0:
        # First output - connect directly, splitter will be added later if needed
        return source_id
    
    # Create a splitter and connect it
    splitter = network.create_node(
        NodeType.SPLITTER,
        label=f"Splitter ({item})",
        item=item,
    )
    
    # If randomize, sometimes chain splitters differently
    if randomize and random.random() < 0.3 and existing_splitters:
        # Connect to an existing splitter instead of source
        parent = random.choice(existing_splitters)
        network.connect(parent.id, splitter.id, item, rate)
    else:
        network.connect(source_id, splitter.id, item, rate)
    
    return splitter.id


def _get_or_create_merger_input(
    network: NetworkGraph,
    target_id: str,
    item: str,
    rate: float,
    randomize: bool,
) -> str:
    """
    Get an available merger input for a target, creating mergers as needed.
    
    Returns the node ID to connect to.
    """
    # Check existing mergers connected to target
    existing_mergers = [
        network.get_node(e.source_id)
        for e in network.edges_to(target_id)
        if network.get_node(e.source_id).node_type == NodeType.MERGER
    ]
    
    for merger in existing_mergers:
        # Each merger can have up to 3 inputs
        if network.in_degree(merger.id) < 3:
            return merger.id
    
    # Need to create a new merger
    direct_inputs = network.in_degree(target_id)
    
    if direct_inputs == 0:
        # First input - connect directly
        return target_id
    
    # Create a merger and connect it
    merger = network.create_node(
        NodeType.MERGER,
        label=f"Merger ({item})",
        item=item,
    )
    
    # Connect merger to target
    network.connect(merger.id, target_id, item, rate)
    
    return merger.id
