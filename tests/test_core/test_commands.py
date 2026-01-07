"""Tests for command pattern and undo/redo."""

from unittest.mock import Mock

from satisfactory_planner.core.models import Belt, Building, BuildingType, Document
from satisfactory_planner.ui.commands import (
    CommandStack,
    DeleteItemsCommand,
    MoveBuildingsCommand,
    PlaceBuildingCommand,
    SetClockSpeedCommand,
)


def make_mock_canvas() -> Mock:
    """Create a mock canvas for testing commands."""
    canvas = Mock()
    canvas.add_building_item = Mock()
    canvas.remove_building_item = Mock()
    canvas.add_belt_item = Mock()
    canvas.remove_belt_item = Mock()
    canvas.refresh_building = Mock()
    canvas.refresh_belts_for_building = Mock()
    canvas.notify_mutation = Mock()
    return canvas


class TestCommandStack:
    """Tests for the command stack."""

    def test_execute_and_undo(self) -> None:
        """Commands can be executed and undone."""
        doc = Document()
        stack = CommandStack()
        canvas = make_mock_canvas()

        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        cmd = PlaceBuildingCommand(document=doc, building=building, canvas=canvas)

        stack.execute(cmd)
        assert "b1" in doc.buildings

        stack.undo()
        assert "b1" not in doc.buildings

    def test_redo(self) -> None:
        """Undone commands can be redone."""
        doc = Document()
        stack = CommandStack()
        canvas = make_mock_canvas()

        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        cmd = PlaceBuildingCommand(document=doc, building=building, canvas=canvas)

        stack.execute(cmd)
        stack.undo()
        assert "b1" not in doc.buildings

        stack.redo()
        assert "b1" in doc.buildings

    def test_execute_clears_redo(self) -> None:
        """Executing a new command clears the redo stack."""
        doc = Document()
        stack = CommandStack()
        canvas = make_mock_canvas()

        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        b2 = Building(id="b2", building_type=BuildingType.CONSTRUCTOR, x=100, y=0)

        stack.execute(PlaceBuildingCommand(document=doc, building=b1, canvas=canvas))
        stack.undo()

        # Execute a new command
        stack.execute(PlaceBuildingCommand(document=doc, building=b2, canvas=canvas))

        # Redo should not bring back b1
        assert not stack.can_redo()


class TestMoveBuildingsCommand:
    """Tests for move command with merge support."""

    def test_move_building(self) -> None:
        """Can move a building."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)
        canvas = make_mock_canvas()

        stack = CommandStack()
        # positions tuple: (id, old_x, old_y, old_rot, new_x, new_y, new_rot)
        cmd = MoveBuildingsCommand(
            document=doc,
            canvas=canvas,
            positions=(("b1", 0, 0, 0, 50, 30, 0),),
        )

        stack.execute(cmd)
        assert doc.buildings["b1"].x == 50
        assert doc.buildings["b1"].y == 30

        stack.undo()
        assert doc.buildings["b1"].x == 0
        assert doc.buildings["b1"].y == 0

    def test_move_and_rotate_building(self) -> None:
        """Can move and rotate a building in one command."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)
        canvas = make_mock_canvas()

        stack = CommandStack()
        # Move and rotate 90 degrees
        cmd = MoveBuildingsCommand(
            document=doc,
            canvas=canvas,
            positions=(("b1", 0, 0, 0, 50, 30, 90),),
        )

        stack.execute(cmd)
        assert doc.buildings["b1"].x == 50
        assert doc.buildings["b1"].y == 30
        assert doc.buildings["b1"].rotation == 90

        stack.undo()
        assert doc.buildings["b1"].x == 0
        assert doc.buildings["b1"].y == 0
        assert doc.buildings["b1"].rotation == 0

    def test_move_merge(self) -> None:
        """Consecutive moves of same buildings merge."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)
        canvas = make_mock_canvas()

        stack = CommandStack()

        # Simulate dragging in small increments (id, old_x, old_y, old_rot, new_x, new_y, new_rot)
        stack.execute(
            MoveBuildingsCommand(document=doc, canvas=canvas, positions=(("b1", 0, 0, 0, 10, 0, 0),))
        )
        stack.execute(
            MoveBuildingsCommand(document=doc, canvas=canvas, positions=(("b1", 10, 0, 0, 20, 0, 0),))
        )
        stack.execute(
            MoveBuildingsCommand(document=doc, canvas=canvas, positions=(("b1", 20, 0, 0, 30, 0, 90),))
        )

        # Should have merged into one command
        assert len(stack.undo_stack) == 1
        assert doc.buildings["b1"].x == 30
        assert doc.buildings["b1"].rotation == 90

        # Single undo should restore original position and rotation
        stack.undo()
        assert doc.buildings["b1"].x == 0
        assert doc.buildings["b1"].rotation == 0


class TestDeleteItemsCommand:
    """Tests for delete command."""

    def test_delete_building(self) -> None:
        """Can delete buildings."""
        doc = Document()
        building = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        doc.add_building(building)
        canvas = make_mock_canvas()

        stack = CommandStack()
        cmd = DeleteItemsCommand(document=doc, buildings=(building,), belts=(), canvas=canvas)

        stack.execute(cmd)
        assert "b1" not in doc.buildings

        stack.undo()
        assert "b1" in doc.buildings

    def test_delete_belt(self) -> None:
        """Can delete belts."""
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
        canvas = make_mock_canvas()

        stack = CommandStack()
        cmd = DeleteItemsCommand(document=doc, buildings=(), belts=(belt,), canvas=canvas)

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
        canvas = make_mock_canvas()

        stack = CommandStack()
        cmd = SetClockSpeedCommand(
            document=doc,
            building_id="b1",
            old_clock_speed=1.0,
            new_clock_speed=1.5,
            canvas=canvas,
        )

        stack.execute(cmd)
        assert doc.buildings["b1"].clock_speed == 1.5

        stack.undo()
        assert doc.buildings["b1"].clock_speed == 1.0
