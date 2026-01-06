"""Tests for command pattern and undo/redo."""

import pytest

from satisfactory_planner.core.models import Document, Building, Belt, BuildingType
from satisfactory_planner.core.commands import (
    CommandStack,
    PlaceBuildingCommand,
    DeleteItemsCommand,
    MoveBuildingsCommand,
    ConnectBeltCommand,
    SetClockSpeedCommand,
)


class TestCommandStack:
    """Tests for the command stack."""

    def test_execute_and_undo(self) -> None:
        """Commands can be executed and undone."""
        doc = Document()
        stack = CommandStack()

        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        cmd = PlaceBuildingCommand(document=doc, building=building)

        stack.execute(cmd)
        assert "b1" in doc.buildings

        stack.undo()
        assert "b1" not in doc.buildings

    def test_redo(self) -> None:
        """Undone commands can be redone."""
        doc = Document()
        stack = CommandStack()

        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        cmd = PlaceBuildingCommand(document=doc, building=building)

        stack.execute(cmd)
        stack.undo()
        assert "b1" not in doc.buildings

        stack.redo()
        assert "b1" in doc.buildings

    def test_execute_clears_redo(self) -> None:
        """Executing a new command clears the redo stack."""
        doc = Document()
        stack = CommandStack()

        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        b2 = Building(id="b2", building_type=BuildingType.CONSTRUCTOR, x=100, y=0)

        stack.execute(PlaceBuildingCommand(document=doc, building=b1))
        stack.undo()

        # Execute a new command
        stack.execute(PlaceBuildingCommand(document=doc, building=b2))

        # Redo should not bring back b1
        assert not stack.can_redo()


class TestMoveBuildingsCommand:
    """Tests for move command with merge support."""

    def test_move_building(self) -> None:
        """Can move a building."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)

        stack = CommandStack()
        cmd = MoveBuildingsCommand(document=doc, building_ids=["b1"], dx=50, dy=30)

        stack.execute(cmd)
        assert doc.buildings["b1"].x == 50
        assert doc.buildings["b1"].y == 30

        stack.undo()
        assert doc.buildings["b1"].x == 0
        assert doc.buildings["b1"].y == 0

    def test_move_merge(self) -> None:
        """Consecutive moves of same buildings merge."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)

        stack = CommandStack()

        # Simulate dragging in small increments
        stack.execute(MoveBuildingsCommand(document=doc, building_ids=["b1"], dx=10, dy=0))
        stack.execute(MoveBuildingsCommand(document=doc, building_ids=["b1"], dx=10, dy=0))
        stack.execute(MoveBuildingsCommand(document=doc, building_ids=["b1"], dx=10, dy=0))

        # Should have merged into one command
        assert len(stack.undo_stack) == 1
        assert doc.buildings["b1"].x == 30

        # Single undo should restore original position
        stack.undo()
        assert doc.buildings["b1"].x == 0


class TestDeleteItemsCommand:
    """Tests for delete command."""

    def test_delete_building(self) -> None:
        """Can delete buildings."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)

        stack = CommandStack()
        cmd = DeleteItemsCommand(document=doc, building_ids=["b1"], belt_ids=[])

        stack.execute(cmd)
        assert "b1" not in doc.buildings

        stack.undo()
        assert "b1" in doc.buildings

    def test_delete_belt(self) -> None:
        """Can delete belts."""
        doc = Document()
        belt = Belt(
            id="belt1", tier=1, source_building_id="a", source_port_index=0,
            dest_building_id="b", dest_port_index=0
        )
        doc.add_belt(belt)

        stack = CommandStack()
        cmd = DeleteItemsCommand(document=doc, building_ids=[], belt_ids=["belt1"])

        stack.execute(cmd)
        assert "belt1" not in doc.belts

        stack.undo()
        assert "belt1" in doc.belts


class TestSetClockSpeedCommand:
    """Tests for clock speed command."""

    def test_set_clock_speed(self) -> None:
        """Can set clock speed."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)

        stack = CommandStack()
        cmd = SetClockSpeedCommand(document=doc, building_id="b1", new_clock_speed=1.5)

        stack.execute(cmd)
        assert doc.buildings["b1"].clock_speed == 1.5

        stack.undo()
        assert doc.buildings["b1"].clock_speed == 1.0
