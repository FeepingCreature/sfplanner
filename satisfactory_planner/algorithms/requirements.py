"""Calculate production requirements from target outputs."""

from typing import Optional
from collections import defaultdict
import math

from ..models.recipe import Recipe, RecipeRegistry
from ..models.production import ProductionGraph, ProductionNode, ProductionEdge


def calculate_requirements(
    registry: RecipeRegistry,
    targets: dict[str, float],  # item_name -> items/min desired
    sources: Optional[set[str]] = None,  # items that are raw inputs (don't need recipes)
) -> ProductionGraph:
    """
    Calculate the production graph needed to achieve target outputs.
    
    Works backwards from desired outputs to required inputs.
    Each building is represented as a separate node (count=1 for full buildings,
    fractional for the last partial building if needed).
    Reuses existing production when multiple consumers need the same item.
    
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
    
    # Track available production capacity for each item
    # item_name -> [(node_id, available_rate)]
    available_production: dict[str, list[tuple[str, float]]] = defaultdict(list)
    
    # Track what we still need to produce, with the consumer that needs it
    # List of (item_name, rate_needed, consumer_node_id or None for sinks)
    needed: list[tuple[str, float, Optional[str]]] = [
        (item, rate, None) for item, rate in targets.items()
    ]
    
    # Add sinks for targets
    for item, rate in targets.items():
        graph.add_sink(item, rate)
    
    # Process items, adding recipes as needed
    while needed:
        item, rate, consumer_id = needed.pop(0)
        
        if rate <= 1e-9:  # Effectively zero
            continue
        
        # First, try to use existing production
        remaining = _allocate_from_available(
            graph, available_production, item, rate, consumer_id
        )
        
        if remaining <= 1e-9:
            continue
            
        # If this is a source item, add it as a source
        if item in sources:
            graph.add_source(item, remaining)
            continue
        
        # Find a recipe that produces this item
        recipes = registry.recipes_producing(item)
        if not recipes:
            # No recipe found - treat as a source
            graph.add_source(item, remaining)
            continue
        
        # Use the first recipe (could be smarter about selection)
        recipe = recipes[0]
        
        # How many buildings do we need?
        output_rate = recipe.outputs[item]
        total_count = remaining / output_rate
        
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
            
            # Calculate how much of each output this building produces
            for out_item, out_rate in recipe.outputs.items():
                actual_output = out_rate * building_count
                
                if out_item == item and remaining > 1e-9:
                    # This is what we needed - allocate to consumer
                    consumed = min(remaining, actual_output)
                    
                    if consumer_id is not None:
                        # Create edge to the consumer
                        graph.add_edge(ProductionEdge(
                            source_id=node.id,
                            target_id=consumer_id,
                            item=item,
                            rate=consumed,
                        ))
                    # else: goes to sink, no edge needed
                    
                    remaining -= consumed
                    excess = actual_output - consumed
                    if excess > 1e-9:
                        available_production[out_item].append((node.id, excess))
                else:
                    # By-product or excess - all available for other consumers
                    available_production[out_item].append((node.id, actual_output))
            
            # Add required inputs to needed (this node is the consumer)
            for input_item, input_rate in recipe.inputs.items():
                input_needed = input_rate * building_count
                needed.append((input_item, input_needed, node.id))
    
    return graph


def _allocate_from_available(
    graph: ProductionGraph,
    available_production: dict[str, list[tuple[str, float]]],
    item: str,
    needed: float,
    consumer_id: Optional[str],
) -> float:
    """
    Allocate from available production to a consumer, creating edges.
    
    Returns the remaining amount still needed after consuming available.
    """
    remaining = needed
    new_available = []
    
    for node_id, available in available_production.get(item, []):
        if remaining <= 1e-9:
            new_available.append((node_id, available))
            continue
        
        take = min(remaining, available)
        leftover = available - take
        
        if consumer_id is not None:
            # Create edge from producer to consumer
            graph.add_edge(ProductionEdge(
                source_id=node_id,
                target_id=consumer_id,
                item=item,
                rate=take,
            ))
        # else: goes to sink, no internal edge needed
        
        if leftover > 1e-9:
            new_available.append((node_id, leftover))
        
        remaining -= take
    
    available_production[item] = new_available
    return remaining
