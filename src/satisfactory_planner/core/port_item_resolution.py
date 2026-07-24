"""Pure model-graph traversal for resolving item identity at a building's ports.

This is deliberately independent of FlowGraph/flow_builder and the LP solver:
it only walks Building/Belt/Scene data, so it can answer what item is
probably flowing through a port even when the document has fatal errors,
an inconsistent recipe assignment, or no recipe set at all on the building
being inspected. This makes it cheap enough to call on every properties-panel
refresh, and correct even in contradictory setups.

Example of why a single shared graph doesn't work here: if a Smelter is set
to Copper Ore and feeds a Constructor set to Iron Plate, there is no valid
global resolution (recipe mismatch) - but the Constructor's dropdown should
still show Copper-Ore-consuming recipes first, and the Smelter's dropdown
should still show Copper-Ingot-consuming recipes first. Each focused
building gets its own local resolution, computed as if that building itself
had no recipe or item assigned - neighbors are resolved from their own fixed
identity (Source/Sink/Miner item_id, or a recipe's port assignment) or, if
they are a plain pass-through (Splitter/Merger/Port), by recursing further
outward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from satisfactory_planner.core.models import (
    LOGISTICS_PASSTHROUGH_TYPES,
    Building,
    BuildingType,
    ItemId,
)

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Recipe, RecipeId, Scene


def resolve_neighbor_port_items(
    scene: Scene,
    recipes: dict[RecipeId, Recipe],
    building: Building,
) -> tuple[list[set[ItemId]], list[set[ItemId]]]:
    """Resolve item IDs flowing into/out of a building's connected ports.

    Returns (input_candidates, output_candidates): one entry per *connected*
    input/output port (unconnected ports are omitted), each entry being the
    set of item IDs that could be flowing through that specific port, based
    purely on what's on the other end of its belt (recursing through
    Splitters/Mergers/Ports as needed). The building itself is always
    treated as if it had no recipe or item assigned - only neighbors are
    resolved, so this works even before a recipe is chosen for it, and even
    if the rest of the document has fatal errors elsewhere.

    Each port's candidates are disjunctive (the port will carry exactly one
    of them, we just don't know which yet) - callers must NOT merge these
    sets across ports and check subset/superset, since that conflates "one
    of these" with "all of these". Instead, check each port's set against a
    candidate recipe independently (e.g. non-empty intersection).
    """
    input_candidates: list[set[ItemId]] = []
    output_candidates: list[set[ItemId]] = []

    for i in range(building.num_inputs):
        belt = scene.get_belt_at_port(building.id, i, is_output=False)
        if belt is None:
            continue
        items = _resolve_source_items(
            scene, recipes, belt.source_building_id, belt.source_port_index, set()
        )
        input_candidates.append(items)

    for i in range(building.num_outputs):
        belt = scene.get_belt_at_port(building.id, i, is_output=True)
        if belt is None:
            continue
        items = _resolve_dest_items(
            scene, recipes, belt.dest_building_id, belt.dest_port_index, set()
        )
        output_candidates.append(items)

    return input_candidates, output_candidates


def _resolve_source_items(
    scene: Scene,
    recipes: dict[RecipeId, Recipe],
    building_id: str,
    port_index: int,
    visited: set[tuple[str, int, bool]],
) -> set[ItemId]:
    """Resolve the item(s) available at an output port (the source of a belt)."""
    key = (building_id, port_index, True)
    if key in visited:
        return set()
    visited.add(key)

    neighbor = scene.buildings.get(building_id)
    if neighbor is None:
        return set()

    if neighbor.building_type in (BuildingType.SOURCE, BuildingType.MINER):
        return {neighbor.item_id} if neighbor.item_id else set()

    if neighbor.building_type not in LOGISTICS_PASSTHROUGH_TYPES:
        if neighbor.recipe_id is None:
            return set()
        recipe = recipes.get(neighbor.recipe_id)
        if recipe is None or port_index >= len(recipe.outputs):
            return set()
        # Output port position is fixed by the recipe - unlike inputs, there's
        # no free-assignment ambiguity to narrow via siblings.
        return {recipe.outputs[port_index].item_id}

    result: set[ItemId] = set()
    for i in range(neighbor.num_inputs):
        belt = scene.get_belt_at_port(neighbor.id, i, is_output=False)
        if belt is None:
            continue
        result |= _resolve_source_items(
            scene, recipes, belt.source_building_id, belt.source_port_index, visited
        )
    for i in range(neighbor.num_outputs):
        if i == port_index:
            continue
        belt = scene.get_belt_at_port(neighbor.id, i, is_output=True)
        if belt is None:
            continue
        result |= _resolve_dest_items(
            scene, recipes, belt.dest_building_id, belt.dest_port_index, visited
        )

    return result


def _resolve_dest_items(
    scene: Scene,
    recipes: dict[RecipeId, Recipe],
    building_id: str,
    port_index: int,
    visited: set[tuple[str, int, bool]],
) -> set[ItemId]:
    """Resolve the item(s) expected at an input port (the dest of a belt)."""
    key = (building_id, port_index, False)
    if key in visited:
        return set()
    visited.add(key)

    neighbor = scene.buildings.get(building_id)
    if neighbor is None:
        return set()

    if neighbor.building_type == BuildingType.SINK:
        return {neighbor.item_id} if neighbor.item_id else set()

    if neighbor.building_type not in LOGISTICS_PASSTHROUGH_TYPES:
        if neighbor.recipe_id is None:
            return set()
        recipe = recipes.get(neighbor.recipe_id)
        if recipe is None:
            return set()
        candidates = {inp.item_id for inp in recipe.inputs}
        # A recipe's distinct inputs must be satisfied by distinct belts. If a
        # sibling input port is unambiguously (single-candidate) resolved to
        # a specific item, that item can't also be *this* port's item - drop
        # it from the candidate set. E.g. Assembler(Reinforced Iron Plate)
        # needs {Iron Plate, Screw}; if one input already unambiguously
        # carries Iron Plate, the other input's only remaining candidate is
        # Screw.
        for i in range(neighbor.num_inputs):
            if i == port_index:
                continue
            sibling_belt = scene.get_belt_at_port(neighbor.id, i, is_output=False)
            if sibling_belt is None:
                continue
            sibling_items = _resolve_source_items(
                scene,
                recipes,
                sibling_belt.source_building_id,
                sibling_belt.source_port_index,
                visited,
            )
            if len(sibling_items) == 1:
                candidates -= sibling_items
        return candidates

    result: set[ItemId] = set()
    for i in range(neighbor.num_outputs):
        belt = scene.get_belt_at_port(neighbor.id, i, is_output=True)
        if belt is None:
            continue
        result |= _resolve_dest_items(
            scene, recipes, belt.dest_building_id, belt.dest_port_index, visited
        )
    for i in range(neighbor.num_inputs):
        if i == port_index:
            continue
        belt = scene.get_belt_at_port(neighbor.id, i, is_output=False)
        if belt is None:
            continue
        result |= _resolve_source_items(
            scene, recipes, belt.source_building_id, belt.source_port_index, visited
        )

    return result
