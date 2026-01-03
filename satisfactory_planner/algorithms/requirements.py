"""Calculate production requirements from target outputs."""

from typing import Optional
from collections import defaultdict
import math
import logging

from ..models.recipe import Recipe, RecipeRegistry
from ..models.production import ProductionGraph, ProductionNode, ProductionEdge

logger = logging.getLogger(__name__)


def calculate_requirements(
    registry: RecipeRegistry,
    targets: dict[str, float],  # item_name -> items/min desired
    sources: Optional[set[str]] = None,  # items that are raw inputs (don't need recipes)
) -> ProductionGraph:
    """
    Calculate the production graph needed to achieve target outputs.
    
    Two-phase approach:
    1. Aggregate total demand for each item, create properly-sized buildings
    2. Create edges connecting producers to consumers
    
    Each building is represented as a separate node (count=1 for full buildings,
    fractional for the last partial building if needed).
    
    Args:
        registry: Recipe registry to look up recipes
        targets: Desired output rates (item_name -> items/min)
        sources: Set of item names that are raw inputs (optional)
    
    Returns:
        ProductionGraph with nodes and edges representing the factory
    """
    if sources is None:
        sources = set()
    
    graph = ProductionGraph()
    
    # Phase 1: Calculate total demand for each item and determine buildings needed
    # item -> total rate needed
    total_demand: dict[str, float] = defaultdict(float)
    
    # item -> [(consumer_node_id or None for sink, rate)]
    demand_breakdown: dict[str, list[tuple[Optional[str], float]]] = defaultdict(list)
    
    # Start with targets
    for item, rate in targets.items():
        total_demand[item] += rate
        demand_breakdown[item].append((None, rate))  # None = goes to sink
        graph.add_sink(item, rate)
    
    # item -> list of (node_id, rate) for nodes that produce this item
    producers: dict[str, list[tuple[str, float]]] = defaultdict(list)
    
    # Phase 1a: First pass - aggregate ALL demand recursively without creating nodes
    # This ensures we know the full demand for each item before creating buildings
    items_to_process = list(targets.keys())
    full_demand: dict[str, float] = defaultdict(float)
    
    # Initialize with target demands
    for item, rate in targets.items():
        full_demand[item] = rate
    
    # Process in waves to handle dependencies correctly
    processed_for_inputs: set[str] = set()
    
    while items_to_process:
        item = items_to_process.pop(0)
        if item in processed_for_inputs:
            continue
        processed_for_inputs.add(item)
        
        # If this is a source, skip
        if item in sources:
            continue
        
        # Find recipe
        recipes = registry.recipes_producing(item)
        if not recipes:
            continue
        
        recipe = recipes[0]
        output_rate = recipe.outputs[item]
        count_needed = full_demand[item] / output_rate
        
        # Add input demands
        for input_item, input_rate in recipe.inputs.items():
            input_needed = input_rate * count_needed
            full_demand[input_item] += input_needed
            if input_item not in processed_for_inputs:
                items_to_process.append(input_item)
    
    logger.debug(f"Phase 1a: Full demand calculated: {dict(full_demand)}")
    
    # Phase 1b: Now create buildings based on FULL demand
    # Reset demand_breakdown to only track actual building connections
    demand_breakdown.clear()
    
    # Re-add sinks
    for item, rate in targets.items():
        demand_breakdown[item].append((None, rate))
    
    for item in processed_for_inputs:
        rate_needed = full_demand[item]
        if rate_needed <= 1e-9:
            continue
        
        # If this is a source item, add it as a source
        if item in sources:
            graph.add_source(item, rate_needed)
            continue
        
        # Find a recipe that produces this item
        recipes = registry.recipes_producing(item)
        if not recipes:
            # No recipe found - treat as a source
            graph.add_source(item, rate_needed)
            continue
        
        # Use the first recipe
        recipe = recipes[0]
        
        # How many buildings do we need total for this item?
        output_rate = recipe.outputs[item]
        total_count = rate_needed / output_rate
        
        # Create individual building nodes (count=1 each, last may be fractional)
        num_buildings = int(math.ceil(total_count))
        
        for building_idx in range(num_buildings):
            # Last building might be partial (fractional)
            if building_idx == num_buildings - 1:
                building_count = total_count - building_idx
            else:
                building_count = 1.0
            
            node = ProductionNode(
                id=f"{recipe.name}_{len(graph.nodes)}",
                recipe=recipe,
                count=building_count,
            )
            graph.add_node(node)
            
            # Track what this building produces
            for out_item, out_rate in recipe.outputs.items():
                actual_output = out_rate * building_count
                producers[out_item].append((node.id, actual_output))
            
            # Track what this building needs (for edge creation)
            for input_item, input_rate in recipe.inputs.items():
                input_needed = input_rate * building_count
                demand_breakdown[input_item].append((node.id, input_needed))
    
    # Phase 2: Create edges connecting producers to consumers
    logger.debug(f"Phase 2: Creating edges. Demand breakdown: {list(demand_breakdown.keys())}")
    logger.debug(f"Producers: {list(producers.keys())}")
    
    for item, consumers in demand_breakdown.items():
        item_producers = producers.get(item, [])
        if not item_producers:
            # Comes from source, no internal edges needed
            logger.debug(f"Item '{item}' has no producers - treating as source")
            continue
        
        logger.debug(f"Item '{item}': {len(item_producers)} producers -> {len(consumers)} consumers")
        
        # Sort producers by node id for consistent allocation
        item_producers = sorted(item_producers, key=lambda x: x[0])
        
        # Allocate production to consumers
        producer_idx = 0
        producer_remaining = item_producers[producer_idx][1] if item_producers else 0
        
        for consumer_id, rate_needed in consumers:
            remaining = rate_needed
            
            while remaining > 1e-9 and producer_idx < len(item_producers):
                producer_id, _ = item_producers[producer_idx]
                
                take = min(remaining, producer_remaining)
                
                if consumer_id is not None and take > 1e-9:
                    # Create edge from producer to consumer
                    graph.add_edge(ProductionEdge(
                        source_id=producer_id,
                        target_id=consumer_id,
                        item=item,
                        rate=take,
                    ))
                
                remaining -= take
                producer_remaining -= take
                
                if producer_remaining <= 1e-9:
                    producer_idx += 1
                    if producer_idx < len(item_producers):
                        producer_remaining = item_producers[producer_idx][1]
    
    # Validation: check for disconnected nodes
    for node_id, node in graph.nodes.items():
        incoming = graph.edges_to(node_id)
        outgoing = graph.edges_from(node_id)
        
        # Check if node has inputs but no incoming edges
        if node.recipe.inputs and not incoming:
            logger.warning(
                f"Node '{node_id}' ({node.recipe.name}) requires inputs "
                f"{list(node.recipe.inputs.keys())} but has no incoming edges!"
            )
        
        # Check if node has outputs but no outgoing edges (and isn't feeding a sink)
        if node.recipe.outputs and not outgoing:
            # Check if any of its outputs go to sinks
            node_outputs = set(node.recipe.outputs.keys())
            sink_items = set(graph.sinks.keys())
            if not node_outputs & sink_items:
                logger.warning(
                    f"Node '{node_id}' ({node.recipe.name}) produces "
                    f"{list(node.recipe.outputs.keys())} but has no outgoing edges!"
                )
    
    return graph
