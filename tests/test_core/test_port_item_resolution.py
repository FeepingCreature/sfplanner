"""Tests for pure model-graph item resolution at building ports."""

from __future__ import annotations

from satisfactory_planner.core.models import (
    Belt,
    Building,
    BuildingType,
    Document,
    ItemId,
    ItemRate,
    Recipe,
    RecipeId,
)
from satisfactory_planner.core.port_item_resolution import resolve_neighbor_port_items

IRON_PLATE = ItemId("iron-plate")
IRON_ROD = ItemId("iron-rod")
SCREW = ItemId("screw")
REINFORCED_IRON_PLATE = ItemId("reinforced-iron-plate")

RECIPE_IRON_PLATE = Recipe(
    id=RecipeId("recipe-iron-plate"),
    name="Iron Plate",
    building_type=BuildingType.CONSTRUCTOR,
    inputs=[ItemRate(IRON_ROD, 30)],
    outputs=[ItemRate(IRON_PLATE, 20)],
    power_mw=4.0,
    crafting_time=6.0,
)

RECIPE_SCREW = Recipe(
    id=RecipeId("recipe-screw"),
    name="Screw",
    building_type=BuildingType.CONSTRUCTOR,
    inputs=[ItemRate(IRON_ROD, 10)],
    outputs=[ItemRate(SCREW, 40)],
    power_mw=4.0,
    crafting_time=6.0,
)

RECIPE_REINFORCED_IRON_PLATE = Recipe(
    id=RecipeId("recipe-reinforced-iron-plate"),
    name="Reinforced Iron Plate",
    building_type=BuildingType.ASSEMBLER,
    inputs=[ItemRate(IRON_PLATE, 30), ItemRate(SCREW, 60)],
    outputs=[ItemRate(REINFORCED_IRON_PLATE, 5)],
    power_mw=15.0,
    crafting_time=12.0,
)

RECIPES: dict[RecipeId, Recipe] = {
    RECIPE_IRON_PLATE.id: RECIPE_IRON_PLATE,
    RECIPE_SCREW.id: RECIPE_SCREW,
    RECIPE_REINFORCED_IRON_PLATE.id: RECIPE_REINFORCED_IRON_PLATE,
}


def make_belt(belt_id: str, source_id: str, source_port: int, dest_id: str, dest_port: int) -> Belt:
    return Belt(
        id=belt_id,
        tier=1,
        source_building_id=source_id,
        source_port_index=source_port,
        dest_building_id=dest_id,
        dest_port_index=dest_port,
    )


class TestSiblingInputNarrowing:
    # Reported bug: A->C produces Iron Plate, B->C has no recipe, C makes
    # Reinforced Iron Plate (needs Iron Plate + Screw). B's dropdown should
    # suggest Screw specifically, not both, because Iron Plate is already
    # unambiguously claimed by A on C's other input.

    def test_b_suggests_screw_not_both(self) -> None:
        doc = Document()
        a = Building(
            id="a",
            building_type=BuildingType.CONSTRUCTOR,
            x=0,
            y=0,
            recipe_id=RECIPE_IRON_PLATE.id,
        )
        b = Building(id="b", building_type=BuildingType.CONSTRUCTOR, x=0, y=100, recipe_id=None)
        c = Building(
            id="c",
            building_type=BuildingType.ASSEMBLER,
            x=200,
            y=50,
            recipe_id=RECIPE_REINFORCED_IRON_PLATE.id,
        )
        doc.add_building(a)
        doc.add_building(b)
        doc.add_building(c)
        doc.add_belt(make_belt("belt-a-c", "a", 0, "c", 0))
        doc.add_belt(make_belt("belt-b-c", "b", 0, "c", 1))

        _inputs, outputs = resolve_neighbor_port_items(doc, RECIPES, b)

        assert outputs == {SCREW}

    def test_order_independent_a_on_port_1(self) -> None:
        # Same scenario, but A is wired to C's port 1 and B to port 0 - the
        # narrowing must not depend on port ordering.
        doc = Document()
        a = Building(
            id="a",
            building_type=BuildingType.CONSTRUCTOR,
            x=0,
            y=0,
            recipe_id=RECIPE_IRON_PLATE.id,
        )
        b = Building(id="b", building_type=BuildingType.CONSTRUCTOR, x=0, y=100, recipe_id=None)
        c = Building(
            id="c",
            building_type=BuildingType.ASSEMBLER,
            x=200,
            y=50,
            recipe_id=RECIPE_REINFORCED_IRON_PLATE.id,
        )
        doc.add_building(a)
        doc.add_building(b)
        doc.add_building(c)
        doc.add_belt(make_belt("belt-a-c", "a", 0, "c", 1))
        doc.add_belt(make_belt("belt-b-c", "b", 0, "c", 0))

        _inputs, outputs = resolve_neighbor_port_items(doc, RECIPES, b)

        assert outputs == {SCREW}

    def test_neither_input_connected_yields_both_candidates(self) -> None:
        # If B is the only one connected (A's input is not wired), both Iron
        # Plate and Screw remain valid candidates - no sibling to narrow.
        doc = Document()
        b = Building(id="b", building_type=BuildingType.CONSTRUCTOR, x=0, y=100, recipe_id=None)
        c = Building(
            id="c",
            building_type=BuildingType.ASSEMBLER,
            x=200,
            y=50,
            recipe_id=RECIPE_REINFORCED_IRON_PLATE.id,
        )
        doc.add_building(b)
        doc.add_building(c)
        doc.add_belt(make_belt("belt-b-c", "b", 0, "c", 0))

        _inputs, outputs = resolve_neighbor_port_items(doc, RECIPES, b)

        assert outputs == {IRON_PLATE, SCREW}


class TestFixedIdentityNeighbors:
    def test_source_output_side(self) -> None:
        doc = Document()
        source = Building(id="src", building_type=BuildingType.SOURCE, x=0, y=0, item_id=IRON_ROD)
        constructor = Building(
            id="con", building_type=BuildingType.CONSTRUCTOR, x=100, y=0, recipe_id=None
        )
        doc.add_building(source)
        doc.add_building(constructor)
        doc.add_belt(make_belt("belt", "src", 0, "con", 0))

        inputs, _outputs = resolve_neighbor_port_items(doc, RECIPES, constructor)

        assert inputs == {IRON_ROD}

    def test_sink_input_side(self) -> None:
        doc = Document()
        constructor = Building(
            id="con", building_type=BuildingType.CONSTRUCTOR, x=0, y=0, recipe_id=None
        )
        sink = Building(id="sink", building_type=BuildingType.SINK, x=100, y=0, item_id=SCREW)
        doc.add_building(constructor)
        doc.add_building(sink)
        doc.add_belt(make_belt("belt", "con", 0, "sink", 0))

        _inputs, outputs = resolve_neighbor_port_items(doc, RECIPES, constructor)

        assert outputs == {SCREW}


class TestPassthroughRecursion:
    def test_splitter_recurses_to_recipe_output(self) -> None:
        # Constructor's input comes via a Splitter fed by an Iron Plate
        # producer - the Splitter itself has no identity, so we recurse
        # through it to find the real source.
        doc = Document()
        producer = Building(
            id="prod",
            building_type=BuildingType.CONSTRUCTOR,
            x=0,
            y=0,
            recipe_id=RECIPE_IRON_PLATE.id,
        )
        splitter = Building(id="split", building_type=BuildingType.SPLITTER, x=100, y=0)
        consumer = Building(
            id="cons", building_type=BuildingType.CONSTRUCTOR, x=200, y=0, recipe_id=None
        )
        doc.add_building(producer)
        doc.add_building(splitter)
        doc.add_building(consumer)
        doc.add_belt(make_belt("b1", "prod", 0, "split", 0))
        doc.add_belt(make_belt("b2", "split", 1, "cons", 0))

        inputs, _outputs = resolve_neighbor_port_items(doc, RECIPES, consumer)

        assert inputs == {IRON_PLATE}


class TestNoConnections:
    def test_unconnected_building_returns_empty_sets(self) -> None:
        doc = Document()
        lone = Building(id="lone", building_type=BuildingType.CONSTRUCTOR, x=0, y=0, recipe_id=None)
        doc.add_building(lone)

        inputs, outputs = resolve_neighbor_port_items(doc, RECIPES, lone)

        assert inputs == set()
        assert outputs == set()
