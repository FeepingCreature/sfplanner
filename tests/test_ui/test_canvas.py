"""Tests for the factory canvas."""

from PySide6.QtCore import QPointF

from satisfactory_planner.core.models import Belt, Building, BuildingType, Document, generate_id
from satisfactory_planner.ui.canvas import FactoryCanvas
from satisfactory_planner.ui.commands import CommandStack, ConnectBeltCommand, PlaceBuildingCommand


class TestFactoryCanvas:
    """Tests for FactoryCanvas."""

    def test_canvas_creation(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Canvas can be created."""
        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        assert canvas.document is doc
        assert canvas.command_stack is stack

    def test_place_building(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Can place a building on the canvas via command."""
        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Place building via command (the public API)
        building = Building(
            id=generate_id(),
            building_type=BuildingType.CONSTRUCTOR,
            x=100,
            y=100,
        )
        cmd = PlaceBuildingCommand(scene_room_id=None, building=building, canvas=canvas)
        stack.execute(cmd)

        # Building should be added to document
        assert len(doc.buildings) == 1
        placed = list(doc.buildings.values())[0]
        assert placed.building_type == BuildingType.CONSTRUCTOR
        assert placed.x == 100
        assert placed.y == 100

    def test_delete_selection(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Can delete selected buildings."""
        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Place a building via command
        building = Building(
            id=generate_id(),
            building_type=BuildingType.CONSTRUCTOR,
            x=100,
            y=100,
        )
        cmd = PlaceBuildingCommand(scene_room_id=None, building=building, canvas=canvas)
        stack.execute(cmd)
        assert len(doc.buildings) == 1

        building_id = building.id

        # Select the building item
        item = canvas._building_items[building_id]
        item.setSelected(True)

        # Delete
        canvas.delete_selection()
        assert len(doc.buildings) == 0

    def test_grid_snap(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Grid snapping works."""
        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        canvas._grid_snap = True
        canvas._grid_size = 20

        pos = canvas._snap_to_grid(QPointF(25, 33))
        assert pos.x() == 20
        assert pos.y() == 40

    def test_grid_snap_disabled(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Grid snapping can be disabled."""
        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        canvas._grid_snap = False

        pos = canvas._snap_to_grid(QPointF(25, 33))
        assert pos.x() == 25
        assert pos.y() == 33

    def test_belt_connection(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Can connect buildings with a belt."""
        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Place two buildings via commands
        b1 = Building(id=generate_id(), building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        b2 = Building(id=generate_id(), building_type=BuildingType.CONSTRUCTOR, x=200, y=0)
        stack.execute(PlaceBuildingCommand(scene_room_id=None, building=b1, canvas=canvas))
        stack.execute(PlaceBuildingCommand(scene_room_id=None, building=b2, canvas=canvas))

        # Connect via command
        belt = Belt(
            id=generate_id(),
            tier=1,
            source_building_id=b1.id,
            source_port_index=0,
            dest_building_id=b2.id,
            dest_port_index=0,
        )
        stack.execute(ConnectBeltCommand(scene_room_id=None, belt=belt, canvas=canvas))

        # Belt should exist
        assert len(doc.belts) == 1
        connected = list(doc.belts.values())[0]
        assert connected.source_building_id == b1.id
        assert connected.dest_building_id == b2.id
