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
    Recipe nodes are constrained to have exactly ONE belt per item in/out.
    Any fan-in/fan-out uses splitters and mergers.
    
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
            label=f"{prod_node.recipe.name} x{prod_node.count:.2f}",
            production_node_id=prod_node.id,
        )
        prod_to_net[prod_node.id] = net_node.id
    
    # Create source nodes - one per item (they can have multiple outputs via splitters)
    source_nodes: dict[str, str] = {}  # item -> network node id
    for item, rate in production.sources.items():
        net_node = network.create_node(
            NodeType.SOURCE,
            label=f"Source: {item}",
            item=item,
            rate=rate,
        )
        source_nodes[item] = net_node.id
    
    # Create sink nodes - one per item
    sink_nodes: dict[str, str] = {}  # item -> network node id
    for item, rate in production.sinks.items():
        net_node = network.create_node(
            NodeType.SINK,
            label=f"Output: {item}",
            item=item,
            rate=rate,
        )
        sink_nodes[item] = net_node.id
    
    # Track connections per recipe node per item
    # (node_id, item, 'in'/'out') -> splitter/merger node id or None
    recipe_ports: dict[tuple[str, str, str], Optional[str]] = {}
    
    # Group production edges by item for processing
    edges_by_item: dict[str, list[ProductionEdge]] = defaultdict(list)
    for edge in production.edges:
        edges_by_item[edge.item].append(edge)
    
    # Process edges grouped by item
    for item, edges in edges_by_item.items():
        # Group by source (for splitters) and target (for mergers)
        by_source: dict[str, list[ProductionEdge]] = defaultdict(list)
        by_target: dict[str, list[ProductionEdge]] = defaultdict(list)
        
        for edge in edges:
            by_source[edge.source_id].append(edge)
            by_target[edge.target_id].append(edge)
        
        # Create splitter trees for sources with multiple outputs
        source_output_nodes: dict[str, list[str]] = {}  # prod_id -> list of output node ids
        
        for source_id, source_edges in by_source.items():
            net_source_id = prod_to_net[source_id]
            total_rate = sum(e.rate for e in source_edges)
            
            if len(source_edges) == 1:
                # Single output - direct connection (but still need to go through port tracking)
                source_output_nodes[source_id] = [net_source_id]
            else:
                # Multiple outputs - need splitter tree
                outputs = _create_splitter_tree(
                    network, net_source_id, item, total_rate, 
                    len(source_edges), randomize
                )
                source_output_nodes[source_id] = outputs
        
        # Create merger trees for targets with multiple inputs
        target_input_nodes: dict[str, list[str]] = {}  # prod_id -> list of input node ids
        
        for target_id, target_edges in by_target.items():
            net_target_id = prod_to_net[target_id]
            total_rate = sum(e.rate for e in target_edges)
            
            if len(target_edges) == 1:
                # Single input - direct connection
                target_input_nodes[target_id] = [net_target_id]
            else:
                # Multiple inputs - need merger tree
                inputs = _create_merger_tree(
                    network, net_target_id, item, total_rate,
                    len(target_edges), randomize
                )
                target_input_nodes[target_id] = inputs
        
        # Now connect source outputs to target inputs
        for source_id, source_edges in by_source.items():
            outputs = source_output_nodes[source_id]
            output_idx = 0
            
            for edge in source_edges:
                target_id = edge.target_id
                inputs = target_input_nodes[target_id]
                
                # Get the next available output and input
                from_node = outputs[min(output_idx, len(outputs) - 1)]
                
                # Find unused input for this target
                to_node = None
                for inp in inputs:
                    # Check if already connected
                    existing = [e for e in network.edges_to(inp) if e.item == item]
                    if not existing or network.get_node(inp).node_type in (NodeType.MERGER,):
                        if network.get_node(inp).node_type == NodeType.MERGER:
                            if network.in_degree(inp) < 3:
                                to_node = inp
                                break
                        else:
                            to_node = inp
                            break
                
                if to_node is None:
                    to_node = inputs[0]  # Fallback
                
                network.connect(from_node, to_node, item, edge.rate)
                output_idx += 1
    
    # Connect sources to consumers
    for item, source_net_id in source_nodes.items():
        # Find all recipe nodes that need this item as input
        consumers = []
        for prod_node in production.nodes.values():
            if item in prod_node.recipe.inputs:
                consumers.append((prod_to_net[prod_node.id], prod_node.effective_inputs[item]))
        
        if not consumers:
            continue
        
        if len(consumers) == 1:
            # Direct connection
            target_id, rate = consumers[0]
            network.connect(source_net_id, target_id, item, rate)
        else:
            # Need splitter tree
            total_rate = sum(r for _, r in consumers)
            outputs = _create_splitter_tree(
                network, source_net_id, item, total_rate, len(consumers), randomize
            )
            for (target_id, rate), out_node in zip(consumers, outputs):
                network.connect(out_node, target_id, item, rate)
    
    # Connect producers to sinks
    for item, sink_net_id in sink_nodes.items():
        # Find all recipe nodes that produce this item for output
        producers = []
        for prod_node in production.nodes.values():
            if item in prod_node.recipe.outputs:
                produced = prod_node.effective_outputs[item]
                # Subtract what goes to other nodes
                used = sum(
                    e.rate for e in production.edges 
                    if e.source_id == prod_node.id and e.item == item
                )
                to_sink = produced - used
                if to_sink > 1e-9:
                    producers.append((prod_to_net[prod_node.id], to_sink))
        
        if not producers:
            continue
        
        if len(producers) == 1:
            # Direct connection
            source_id, rate = producers[0]
            network.connect(source_id, sink_net_id, item, rate)
        else:
            # Need merger tree
            total_rate = sum(r for _, r in producers)
            inputs = _create_merger_tree(
                network, sink_net_id, item, total_rate, len(producers), randomize
            )
            for (source_id, rate), in_node in zip(producers, inputs):
                network.connect(source_id, in_node, item, rate)
    
    return network


def _create_splitter_tree(
    network: NetworkGraph,
    source_id: str,
    item: str,
    total_rate: float,
    num_outputs: int,
    randomize: bool,
) -> list[str]:
    """
    Create a tree of splitters to provide num_outputs from source_id.
    
    Returns list of node IDs to connect from (one per output needed).
    """
    if num_outputs <= 1:
        return [source_id]
    
    # Each splitter takes 1 input and provides 3 outputs.
    # We need to build a tree where leaves are our outputs.
    # Strategy: build splitters until we have enough leaf slots.
    
    # Start with source as the only available slot
    # available_slots tracks (node_id, is_splitter) - if is_splitter, can use up to 3 times
    leaf_nodes: list[str] = [source_id]  # Nodes that can be outputs
    
    while len(leaf_nodes) < num_outputs:
        # Pick a leaf to expand into a splitter
        if randomize:
            idx = random.randint(0, len(leaf_nodes) - 1)
        else:
            idx = 0
        
        parent_id = leaf_nodes.pop(idx)
        
        # Create a splitter fed by this parent
        splitter = network.create_node(
            NodeType.SPLITTER,
            label=f"Splitter ({item})",
            item=item,
        )
        network.connect(parent_id, splitter.id, item, total_rate)
        
        # This splitter provides 3 new leaf slots
        leaf_nodes.append(splitter.id)
        leaf_nodes.append(splitter.id)
        leaf_nodes.append(splitter.id)
    
    # Return exactly num_outputs leaves
    if randomize:
        random.shuffle(leaf_nodes)
    return leaf_nodes[:num_outputs]


def _create_merger_tree(
    network: NetworkGraph,
    target_id: str,
    item: str,
    total_rate: float,
    num_inputs: int,
    randomize: bool,
) -> list[str]:
    """
    Create a tree of mergers to accept num_inputs into target_id.
    
    Returns list of node IDs to connect to (one per input needed).
    """
    if num_inputs <= 1:
        return [target_id]
    
    # Similar to splitter tree but reversed.
    # Each merger takes 3 inputs and provides 1 output.
    
    leaf_nodes: list[str] = [target_id]
    
    while len(leaf_nodes) < num_inputs:
        if randomize:
            idx = random.randint(0, len(leaf_nodes) - 1)
        else:
            idx = 0
        
        child_id = leaf_nodes.pop(idx)
        
        # Create a merger that feeds into this child
        merger = network.create_node(
            NodeType.MERGER,
            label=f"Merger ({item})",
            item=item,
        )
        network.connect(merger.id, child_id, item, total_rate)
        
        # This merger provides 3 new input slots
        leaf_nodes.append(merger.id)
        leaf_nodes.append(merger.id)
        leaf_nodes.append(merger.id)
    
    if randomize:
        random.shuffle(leaf_nodes)
    return leaf_nodes[:num_inputs]
