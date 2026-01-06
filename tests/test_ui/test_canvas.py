"""Tests for the factory canvas."""

import pytest
from PySide6.QtCore import Qt, QPointF

from satisfactory_planner.core.models import Document, BuildingType
from satisfactory_planner.core.commands import CommandStack
from satisfactory_planner.ui.canvas import FactoryCanvas


class TestFactoryCanvas:
    """Tests for FactoryCanvas."""

    def test_canvas_creation(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Canvas can be created."""
        doc = Document()
        stack = CommandStack()
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        assert canvas.document is doc
        assert canvas.command_stack is stack

    def test_place_building(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Can place a building on the canvas."""
        doc = Document()
        stack = CommandStack()
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Enter placement mode
        canvas.set_placement_mode(BuildingType.CONSTRUCTOR)
        assert canvas._placement_mode == BuildingType.CONSTRUCTOR

        # Simulate click to place
        canvas._place_building(BuildingType.CONSTRUCTOR, 100, 100)

        # Building should be added to document
        assert len(doc.buildings) == 1
        building = list(doc.buildings.values())[0]
        assert building.building_type == BuildingType.CONSTRUCTOR
        assert building.x == 100
        assert building.y == 100

    def test_delete_selection(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Can delete selected buildings."""
        doc = Document()
        stack = CommandStack()
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Place a building
        canvas._place_building(BuildingType.CONSTRUCTOR, 100, 100)
        assert len(doc.buildings) == 1

        building_id = list(doc.buildings.keys())[0]

        # Select the building item
        item = canvas._building_items[building_id]
        item.setSelected(True)

        # Delete
        canvas.delete_selection()
        assert len(doc.buildings) == 0

    def test_grid_snap(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Grid snapping works."""
        doc = Document()
        stack = CommandStack()
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
        stack = CommandStack()
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        canvas._grid_snap = False

        pos = canvas._snap_to_grid(QPointF(25, 33))
        assert pos.x() == 25
        assert pos.y() == 33

    def test_belt_connection(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Can connect buildings with a belt."""
        doc = Document()
        stack = CommandStack()
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Place two buildings
        canvas._place_building(BuildingType.CONSTRUCTOR, 0, 0)
        canvas._place_building(BuildingType.CONSTRUCTOR, 200, 0)

        b1_id = list(doc.buildings.keys())[0]
        b2_id = list(doc.buildings.keys())[1]

        # Start and complete connection
        canvas.start_belt_connection(b1_id, 0)
        assert canvas._is_connecting

        canvas.complete_belt_connection(b2_id, 0)
        assert not canvas._is_connecting

        # Belt should exist
        assert len(doc.belts) == 1
        belt = list(doc.belts.values())[0]
        assert belt.source_building_id == b1_id
        assert belt.dest_building_id == b2_id
