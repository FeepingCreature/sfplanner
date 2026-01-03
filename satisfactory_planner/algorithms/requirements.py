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
    
    # Track what we still need to produce
    # item_name -> rate needed
    needed: dict[str, float] = dict(targets)
    
    # Track what's been allocated
    # item_name -> [(node_id, rate)]
    production: dict[str, list[tuple[str, float]]] = defaultdict(list)
    
    # Process items in order, adding recipes as needed
    while needed:
        item, rate = needed.popitem()
        
        if rate <= 0:
            continue
            
        # If this is a source item, add it as a source
        if item in sources:
            graph.add_source(item, rate)
            production[item].append(("__source__", rate))
            continue
        
        # Find a recipe that produces this item
        recipes = registry.recipes_producing(item)
        if not recipes:
            # No recipe found - treat as a source
            graph.add_source(item, rate)
            production[item].append(("__source__", rate))
            continue
        
        # Use the first recipe (could be smarter about selection)
        recipe = recipes[0]
        
        # How many buildings do we need?
        output_rate = recipe.outputs[item]
        count = rate / output_rate
        
        # Create production node
        node = ProductionNode(
            id=f"{recipe.name}_{len(graph.nodes)}",
            recipe=recipe,
            count=count,
        )
        graph.add_node(node)
        
        # Track that this node produces this item
        actual_output = output_rate * count
        production[item].append((node.id, actual_output))
        
        # Add to sinks if this is a target
        if item in targets:
            graph.add_sink(item, rate)
        
        # Add required inputs to needed
        for input_item, input_rate in recipe.inputs.items():
            total_input_needed = input_rate * count
            if input_item in needed:
                needed[input_item] += total_input_needed
            else:
                needed[input_item] = total_input_needed
    
    # Now create edges between nodes
    # This is a simplified version - connects producers to consumers
    _create_edges(graph, registry)
    
    return graph


def _create_edges(graph: ProductionGraph, registry: RecipeRegistry) -> None:
    """Create edges connecting production nodes."""
    
    # For each node, find where its inputs come from
    for node in graph.nodes.values():
        for input_item, input_rate in node.effective_inputs.items():
            # Find nodes that produce this item
            producers = []
            for other_node in graph.nodes.values():
                if input_item in other_node.effective_outputs:
                    producers.append(other_node)
            
            if not producers:
                # Input comes from source
                continue
            
            # Simple allocation: take from first producer that has capacity
            remaining = input_rate
            for producer in producers:
                if remaining <= 0:
                    break
                    
                available = producer.effective_outputs.get(input_item, 0)
                # Check how much is already allocated
                already_used = sum(
                    e.rate for e in graph.edges 
                    if e.source_id == producer.id and e.item == input_item
                )
                can_provide = available - already_used
                
                if can_provide > 0:
                    take = min(remaining, can_provide)
                    graph.add_edge(ProductionEdge(
                        source_id=producer.id,
                        target_id=node.id,
                        item=input_item,
                        rate=take,
                    ))
                    remaining -= take
