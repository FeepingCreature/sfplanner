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

    def test_room_redo_has_building_items(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """After redo, room item should have building items visible."""
        from satisfactory_planner.ui.commands import CreateRoomCommand
        from satisfactory_planner.ui.items.room_item import RoomItem

        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # Place a building
        building = Building(
            id=generate_id(),
            building_type=BuildingType.CONSTRUCTOR,
            x=100,
            y=100,
        )
        cmd = PlaceBuildingCommand(scene_room_id=None, building=building, canvas=canvas)
        stack.execute(cmd)
        building_id = building.id

        # Create room around building
        room_cmd = CreateRoomCommand(
            parent_scene_room_id=None,
            rect=(80, 80, 100, 100),
            building_ids=(building_id,),
            belt_ids=(),
            original_crossing_belts=(),
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=(),
        )
        stack.execute(room_cmd)

        # Verify room item exists and has building item
        room_item = canvas._room_items.get(room_cmd.created_placement_id)
        assert room_item is not None
        assert isinstance(room_item, RoomItem)
        assert building_id in room_item._building_items, "Building item missing after execute"

        # Undo
        stack.undo()

        # Redo
        stack.redo()

        # Verify room item still has building item after redo
        room_item_after = canvas._room_items.get(room_cmd.created_placement_id)
        assert room_item_after is not None
        assert isinstance(room_item_after, RoomItem)
        assert building_id in room_item_after._building_items, (
            f"Building item missing after redo. "
            f"Room has buildings: {list(room_item_after.room.buildings.keys())}, "
            f"RoomItem has items: {list(room_item_after._building_items.keys())}"
        )

        # Additional checks: building item should be in scene and visible
        building_item = room_item_after._building_items[building_id]
        assert building_item.scene() is not None, "Building item not in scene after redo"
        assert building_item.parentItem() is room_item_after, "Building item parent is wrong"
        assert building_item.isVisible(), "Building item not visible after redo"

    def test_copy_paste_preserves_building_fields(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Copy/paste must preserve ALL building fields (item_id, tier, rates...).

        Regression test for B2: paste() used to reconstruct Buildings from a
        hand-picked subset of fields, silently dropping item_id, tier,
        min_rate, max_rate, and port_index.
        """
        from satisfactory_planner.core.models import ItemId
        from satisfactory_planner.ui.canvas import ClipboardManager

        doc = Document()
        stack = CommandStack(doc)
        canvas = FactoryCanvas(doc, stack)
        qtbot.addWidget(canvas)

        # A fully-configured miner exercising the previously-dropped fields
        miner = Building(
            id=generate_id(),
            building_type=BuildingType.MINER,
            x=100,
            y=100,
            item_id=ItemId("Iron Ore"),
            tier=3,
            clock_speed=1.5,
            rotation=90,
        )
        stack.execute(PlaceBuildingCommand(scene_room_id=None, building=miner, canvas=canvas))

        # A source with min/max rates
        source = Building(
            id=generate_id(),
            building_type=BuildingType.SOURCE,
            x=300,
            y=100,
            item_id=ItemId("Copper Ore"),
            min_rate=5.0,
            max_rate=42.0,
        )
        stack.execute(PlaceBuildingCommand(scene_room_id=None, building=source, canvas=canvas))

        canvas._building_items[miner.id].setSelected(True)
        canvas._building_items[source.id].setSelected(True)

        clipboard = ClipboardManager(canvas)
        clipboard.copy_selection()
        clipboard.paste()

        originals = {miner.id, source.id}
        pasted = [b for b in doc.buildings.values() if b.id not in originals]
        assert len(pasted) == 2, f"Expected 2 pasted buildings, got {len(pasted)}"

        pasted_miner = next(b for b in pasted if b.building_type == BuildingType.MINER)
        assert pasted_miner.item_id == "Iron Ore"
        assert pasted_miner.tier == 3
        assert pasted_miner.clock_speed == 1.5
        assert pasted_miner.rotation == 90
        assert pasted_miner.x == miner.x + 50
        assert pasted_miner.y == miner.y + 50

        pasted_source = next(b for b in pasted if b.building_type == BuildingType.SOURCE)
        assert pasted_source.item_id == "Copper Ore"
        assert pasted_source.min_rate == 5.0
        assert pasted_source.max_rate == 42.0
