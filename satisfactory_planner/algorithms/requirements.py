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
    
    Algorithm:
    1. Work backwards from targets to calculate total demand for each item
    2. Create building nodes to meet that demand
    3. Connect buildings with edges based on item flow
    
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
    
    # Step 1: Calculate total demand for each item (recursive backtracking)
    item_demand: dict[str, float] = {}
    item_recipe: dict[str, Recipe] = {}  # Cache which recipe we use for each item
    
    def get_demand(item: str, rate: float) -> None:
        """Recursively calculate demand for an item and its inputs."""
        # Accumulate demand
        item_demand[item] = item_demand.get(item, 0.0) + rate
        
        # If it's a source, stop here
        if item in sources:
            return
        
        # Find recipe (use cached if available)
        if item not in item_recipe:
            recipes = registry.recipes_producing(item)
            if not recipes:
                # No recipe - treat as source
                return
            item_recipe[item] = recipes[0]
        
        recipe = item_recipe[item]
        output_rate = recipe.outputs[item]
        buildings_needed = rate / output_rate
        
        # Recurse for inputs
        for input_item, input_rate in recipe.inputs.items():
            get_demand(input_item, input_rate * buildings_needed)
    
    # Calculate demand starting from targets
    for item, rate in targets.items():
        get_demand(item, rate)
    
    # Step 2: Create building nodes for each item with a recipe
    # item -> list of (node_id, output_rate) for buildings producing this item
    item_producers: dict[str, list[tuple[str, float]]] = defaultdict(list)
    
    # item -> list of (node_id, input_rate) for buildings consuming this item  
    item_consumers: dict[str, list[tuple[str, float]]] = defaultdict(list)
    
    for item, demand in item_demand.items():
        # Add as sink if it's a target
        if item in targets:
            graph.add_sink(item, targets[item])
            # The sink consumes this item
            item_consumers[item].append((None, targets[item]))  # None = sink
        
        # If no recipe, it's a source
        if item not in item_recipe:
            graph.add_source(item, demand)
            continue
        
        recipe = item_recipe[item]
        output_rate = recipe.outputs[item]
        total_buildings = demand / output_rate
        num_buildings = max(1, math.ceil(total_buildings))
        
        for i in range(num_buildings):
            # Last building may be fractional
            if i == num_buildings - 1:
                building_count = total_buildings - i
            else:
                building_count = 1.0
            
            if building_count <= 1e-9:
                continue
            
            node = ProductionNode(
                id=f"{recipe.name}_{len(graph.nodes)}",
                recipe=recipe,
                count=building_count,
            )
            graph.add_node(node)
            
            # Track production
            for out_item, out_rate in recipe.outputs.items():
                actual_rate = out_rate * building_count
                item_producers[out_item].append((node.id, actual_rate))
            
            # Track consumption
            for in_item, in_rate in recipe.inputs.items():
                actual_rate = in_rate * building_count
                item_consumers[in_item].append((node.id, actual_rate))
    
    # Step 3: Create edges connecting producers to consumers
    for item in item_demand:
        producers = item_producers.get(item, [])
        consumers = item_consumers.get(item, [])
        
        if not producers or not consumers:
            continue
        
        # Match producers to consumers by rate
        # Simple greedy allocation
        producer_idx = 0
        producer_id, producer_avail = producers[producer_idx]
        
        for consumer_id, consumer_need in consumers:
            remaining = consumer_need
            
            while remaining > 1e-9 and producer_idx < len(producers):
                producer_id, _ = producers[producer_idx]
                
                # How much can this producer give?
                give = min(remaining, producer_avail)
                
                if give > 1e-9 and consumer_id is not None:
                    graph.add_edge(ProductionEdge(
                        source_id=producer_id,
                        target_id=consumer_id,
                        item=item,
                        rate=give,
                    ))
                
                remaining -= give
                producer_avail -= give
                
                # Move to next producer if this one is exhausted
                if producer_avail <= 1e-9:
                    producer_idx += 1
                    if producer_idx < len(producers):
                        producer_id, producer_avail = producers[producer_idx]
    
    return graph
