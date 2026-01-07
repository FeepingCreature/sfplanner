#!/usr/bin/env python3
"""Flow simulation spike - entry point."""

from models import FlowEdge, FlowGraph, FlowNode, FlowPort, NodeType
from recipes import BELT_CAPACITIES, ITEMS, RECIPES


def main() -> None:
    """Entry point for flow simulation spike."""
    print("Flow Simulation Spike")
    print("=" * 40)

    print(f"\nLoaded {len(ITEMS)} items:")
    for item in ITEMS.values():
        fluid_tag = " (fluid)" if item.is_fluid else ""
        print(f"  - {item.name}{fluid_tag}")

    print(f"\nLoaded {len(RECIPES)} recipes:")
    for recipe in RECIPES.values():
        inputs = ", ".join(f"{i.rate}/min {i.item_id}" for i in recipe.inputs)
        outputs = ", ".join(f"{o.rate}/min {o.item_id}" for o in recipe.outputs)
        print(f"  - {recipe.name} ({recipe.building_type.value})")
        print(f"      {inputs} → {outputs}")

    # Example: Build a simple flow graph
    # Iron Ore (Miner) -> Iron Ingot (Smelter)
    print("\n" + "=" * 40)
    print("Example: Simple Iron Ingot production line")

    graph = FlowGraph()

    # Miner producing 30 iron ore/min
    miner = FlowNode(
        id="miner_1",
        node_type=NodeType.MINER,
        outputs=[FlowPort(item_id="Iron Ore", rate=30.0)],
    )
    graph.add_node(miner)

    # Smelter consuming iron ore, producing iron ingots
    recipe = RECIPES["Iron Ingot"]
    smelter = FlowNode(
        id="smelter_1",
        node_type=NodeType.PRODUCER,
        recipe_id="Iron Ingot",
        inputs=[FlowPort(item_id=inp.item_id, rate=inp.rate) for inp in recipe.inputs],
        outputs=[FlowPort(item_id=out.item_id, rate=out.rate) for out in recipe.outputs],
    )
    graph.add_node(smelter)

    # Belt connecting them (Mk.1 = 60/min capacity)
    belt = FlowEdge(
        id="belt_1",
        source_node_id="miner_1",
        source_port_index=0,
        dest_node_id="smelter_1",
        dest_port_index=0,
        capacity=BELT_CAPACITIES[1],
        item_id="Iron Ore",
    )
    graph.add_edge(belt)

    print(f"  Graph has {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"  Sources: {[n.id for n in graph.get_sources()]}")
    print(f"  Sinks: {[n.id for n in graph.get_sinks()]}")

    # Show edge info
    for edge in graph.edges.values():
        src = graph.nodes[edge.source_node_id]
        dst = graph.nodes[edge.dest_node_id]
        print(f"  Edge: {src.id} -> {dst.id} ({edge.item_id}, capacity={edge.capacity}/min)")


if __name__ == "__main__":
    main()
