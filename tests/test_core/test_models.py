"""Tests for core data models."""

import pytest

from satisfactory_planner.core.models import (
    BELT_CAPACITIES,
    Belt,
    Building,
    BuildingType,
    Document,
    ItemRate,
    Recipe,
    generate_id,
)


class TestBuilding:
    """Tests for Building model."""

    def test_building_dimensions(self) -> None:
        """Buildings have correct dimensions based on type."""
        building = Building(
            id="test",
            building_type=BuildingType.CONSTRUCTOR,
            x=0,
            y=0,
        )
        assert building.width == 80
        assert building.height == 60

    def test_building_ports(self) -> None:
        """Buildings have correct number of ports."""
        constructor = Building(
            id="test",
            building_type=BuildingType.CONSTRUCTOR,
            x=0,
            y=0,
        )
        assert constructor.num_inputs == 1
        assert constructor.num_outputs == 1

        assembler = Building(
            id="test",
            building_type=BuildingType.ASSEMBLER,
            x=0,
            y=0,
        )
        assert assembler.num_inputs == 2
        assert assembler.num_outputs == 1

        splitter = Building(
            id="test",
            building_type=BuildingType.SPLITTER,
            x=0,
            y=0,
        )
        assert splitter.num_inputs == 1
        assert splitter.num_outputs == 3

    def test_port_positions(self) -> None:
        """Port positions are calculated correctly."""
        building = Building(
            id="test",
            building_type=BuildingType.CONSTRUCTOR,
            x=100,
            y=100,
        )

        # Input port on left side
        input_pos = building.input_port_pos(0)
        assert input_pos[0] == 100  # x = building.x (left edge)
        assert input_pos[1] == 130  # y = centered vertically

        # Output port on right side
        output_pos = building.output_port_pos(0)
        assert output_pos[0] == 180  # x = building.x + width
        assert output_pos[1] == 130  # y = centered vertically


class TestBelt:
    """Tests for Belt model."""

    def test_belt_capacity(self) -> None:
        """Belts have correct capacity based on tier."""
        for tier in range(1, 7):
            belt = Belt(
                id="test",
                tier=tier,
                source_building_id="a",
                source_port_index=0,
                dest_building_id="b",
                dest_port_index=0,
            )
            assert belt.capacity == BELT_CAPACITIES[tier]


class TestDocument:
    """Tests for Document model."""

    def test_add_remove_building(self) -> None:
        """Can add and remove buildings."""
        doc = Document()
        building = Building(
            id="b1",
            building_type=BuildingType.CONSTRUCTOR,
            x=0,
            y=0,
        )

        doc.add_building(building)
        assert "b1" in doc.buildings
        assert doc.buildings["b1"] == building

        removed = doc.remove_building("b1")
        assert removed == building
        assert "b1" not in doc.buildings

    def test_add_remove_belt(self) -> None:
        """Can add and remove belts."""
        doc = Document()
        belt = Belt(
            id="belt1",
            tier=1,
            source_building_id="a",
            source_port_index=0,
            dest_building_id="b",
            dest_port_index=0,
        )

        doc.add_belt(belt)
        assert "belt1" in doc.belts

        removed = doc.remove_belt("belt1")
        assert removed == belt
        assert "belt1" not in doc.belts

    def test_get_belts_for_building(self) -> None:
        """Can find belts connected to a building."""
        doc = Document()

        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        b2 = Building(id="b2", building_type=BuildingType.CONSTRUCTOR, x=100, y=0)
        b3 = Building(id="b3", building_type=BuildingType.CONSTRUCTOR, x=200, y=0)

        doc.add_building(b1)
        doc.add_building(b2)
        doc.add_building(b3)

        belt1 = Belt(id="belt1", tier=1, source_building_id="b1", source_port_index=0,
                     dest_building_id="b2", dest_port_index=0)
        belt2 = Belt(id="belt2", tier=1, source_building_id="b2", source_port_index=0,
                     dest_building_id="b3", dest_port_index=0)

        doc.add_belt(belt1)
        doc.add_belt(belt2)

        # b1 is connected to belt1
        b1_belts = doc.get_belts_for_building("b1")
        assert len(b1_belts) == 1
        assert b1_belts[0].id == "belt1"

        # b2 is connected to both belts
        b2_belts = doc.get_belts_for_building("b2")
        assert len(b2_belts) == 2


class TestRecipe:
    """Tests for Recipe model."""

    def test_recipe_scaling(self) -> None:
        """Recipe rates scale with clock speed."""
        recipe = Recipe(
            id="test",
            name="Test Recipe",
            building_type=BuildingType.CONSTRUCTOR,
            inputs=[ItemRate("iron_ingot", 30)],
            outputs=[ItemRate("iron_plate", 20)],
            power_mw=4.0,
            crafting_time=6.0,
        )

        # 200% clock speed
        scaled = recipe.scaled(2.0)
        assert scaled.inputs[0].rate == 60
        assert scaled.outputs[0].rate == 40
        assert scaled.crafting_time == 3.0
        # Power scales with clock_speed^1.6
        assert scaled.power_mw == pytest.approx(4.0 * (2.0 ** 1.6), rel=0.01)


class TestGenerateId:
    """Tests for ID generation."""

    def test_unique_ids(self) -> None:
        """Generated IDs are unique."""
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100
