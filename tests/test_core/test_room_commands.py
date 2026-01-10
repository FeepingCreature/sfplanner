"""Tests for room-related commands."""

from unittest.mock import Mock

from satisfactory_planner.core.models import (
    Belt,
    Building,
    BuildingType,
    Document,
    Room,
    RoomPlacement,
    generate_id,
)
from satisfactory_planner.ui.commands import (
    CommandStack,
    CreateRoomCommand,
    DelinkRoomCommand,
    PlaceBlueprintCommand,
)
from satisfactory_planner.ui.commands.room_commands import _generate_crossing_belt_ids


def make_mock_canvas() -> Mock:
    """Create a mock canvas for testing commands."""
    canvas = Mock()
    canvas.add_building_item = Mock()
    canvas.remove_building_item = Mock()
    canvas.add_belt_item = Mock()
    canvas.remove_belt_item = Mock()
    canvas.add_room_item = Mock()
    canvas.remove_room_item = Mock()
    canvas.refresh_building = Mock()
    canvas.refresh_belts_for_building = Mock()
    canvas.notify_mutation = Mock()
    return canvas


class TestCreateRoomCommand:
    """Tests for creating rooms from selected buildings."""

    def test_create_room_moves_buildings(self) -> None:
        """Buildings are moved into the room with relative coordinates."""
        doc = Document()
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=100, y=100)
        b2 = Building(id="b2", building_type=BuildingType.ASSEMBLER, x=200, y=150)
        doc.add_building(b1)
        doc.add_building(b2)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = CreateRoomCommand(
            parent_scene_room_id=None,
            rect=(80, 80, 200, 150),  # x, y, width, height
            building_ids=("b1", "b2"),
            belt_ids=(),
            original_crossing_belts=(),
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=(),
        )

        stack.execute(cmd)

        # Buildings should be removed from document
        assert "b1" not in doc.buildings
        assert "b2" not in doc.buildings

        # Room should be created
        assert cmd.created_room_id in doc.rooms
        room = doc.rooms[cmd.created_room_id]

        # Buildings should be in room with relative coordinates
        assert "b1" in room.buildings
        assert "b2" in room.buildings
        assert room.buildings["b1"].x == 20  # 100 - 80
        assert room.buildings["b1"].y == 20  # 100 - 80
        assert room.buildings["b2"].x == 120  # 200 - 80
        assert room.buildings["b2"].y == 70  # 150 - 80

        # Placement should exist
        assert cmd.created_placement_id in doc.room_placements

    def test_create_room_moves_belts(self) -> None:
        """Internal belts are moved into the room."""
        doc = Document()
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=100, y=100)
        b2 = Building(id="b2", building_type=BuildingType.ASSEMBLER, x=200, y=100)
        belt = Belt(
            id="belt1",
            tier=1,
            source_building_id="b1",
            source_port_index=0,
            dest_building_id="b2",
            dest_port_index=0,
        )
        doc.add_building(b1)
        doc.add_building(b2)
        doc.add_belt(belt)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = CreateRoomCommand(
            parent_scene_room_id=None,
            rect=(80, 80, 200, 100),
            building_ids=("b1", "b2"),
            belt_ids=("belt1",),
            original_crossing_belts=(),
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=(),
        )

        stack.execute(cmd)

        # Belt should be removed from document
        assert "belt1" not in doc.belts

        # Belt should be in room
        room = doc.rooms[cmd.created_room_id]
        assert "belt1" in room.belts

    def test_create_room_undo(self) -> None:
        """Undo restores buildings and belts to parent scene."""
        doc = Document()
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=100, y=100)
        belt = Belt(
            id="belt1",
            tier=1,
            source_building_id="b1",
            source_port_index=0,
            dest_building_id="b2",
            dest_port_index=0,
        )
        doc.add_building(b1)
        doc.add_belt(belt)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = CreateRoomCommand(
            parent_scene_room_id=None,
            rect=(80, 80, 100, 100),
            building_ids=("b1",),
            belt_ids=("belt1",),
            original_crossing_belts=(),
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=(),
        )

        stack.execute(cmd)
        stack.undo()

        # Buildings and belts restored to document
        assert "b1" in doc.buildings
        assert "belt1" in doc.belts

        # Building has original coordinates
        assert doc.buildings["b1"].x == 100
        assert doc.buildings["b1"].y == 100

        # Room and placement removed
        assert cmd.created_room_id not in doc.rooms
        assert cmd.created_placement_id not in doc.room_placements

    def test_create_room_redo(self) -> None:
        """Redo uses same IDs as original execute."""
        doc = Document()
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=100, y=100)
        doc.add_building(b1)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = CreateRoomCommand(
            parent_scene_room_id=None,
            rect=(80, 80, 100, 100),
            building_ids=("b1",),
            belt_ids=(),
            original_crossing_belts=(),
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=(),
        )

        stack.execute(cmd)
        room_id = cmd.created_room_id
        placement_id = cmd.created_placement_id

        stack.undo()
        stack.redo()

        # Same IDs should be used
        assert room_id in doc.rooms
        assert placement_id in doc.room_placements

    def test_place_building_then_room_undo_redo(self) -> None:
        """Full flow: place building, create room around it, undo room, redo room."""
        from satisfactory_planner.ui.commands import PlaceBuildingCommand

        doc = Document()
        canvas = make_mock_canvas()
        stack = CommandStack(doc)

        # Step 1: Place a building
        building = Building(
            id="b1",
            building_type=BuildingType.CONSTRUCTOR,
            x=100,
            y=100,
            rotation=0,
        )
        place_cmd = PlaceBuildingCommand(
            scene_room_id=None,
            building=building,
            canvas=canvas,
        )
        stack.execute(place_cmd)
        building_id = building.id

        # Verify building exists
        assert building_id in doc.buildings
        assert doc.buildings[building_id].x == 100
        assert doc.buildings[building_id].y == 100

        # Step 2: Create room around the building
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

        # Building should be in room now
        assert building_id not in doc.buildings
        assert room_cmd.created_room_id in doc.rooms
        room = doc.rooms[room_cmd.created_room_id]
        assert building_id in room.buildings
        assert room.buildings[building_id].x == 20  # 100 - 80
        assert room.buildings[building_id].y == 20  # 100 - 80

        # Step 3: Undo room creation
        stack.undo()

        # Building should be back in document with original coords
        assert building_id in doc.buildings
        assert doc.buildings[building_id].x == 100
        assert doc.buildings[building_id].y == 100
        assert room_cmd.created_room_id not in doc.rooms

        # Step 4: Redo room creation
        stack.redo()

        # Building should be in room again
        assert building_id not in doc.buildings
        assert room_cmd.created_room_id in doc.rooms
        room = doc.rooms[room_cmd.created_room_id]
        assert building_id in room.buildings
        assert room.buildings[building_id].x == 20
        assert room.buildings[building_id].y == 20

        # Verify canvas state: room item should exist and have the building
        assert room_cmd.created_placement_id in canvas.add_room_item.call_args_list[-1][0][0].id
        # The room passed to add_room_item should have the building
        last_call = canvas.add_room_item.call_args_list[-1]
        passed_room = last_call[0][1]  # second positional arg is room
        assert building_id in passed_room.buildings, (
            f"Room passed to add_room_item missing building. Room has: {list(passed_room.buildings.keys())}"
        )

    def test_create_room_with_crossing_belt_creates_port(self) -> None:
        """Crossing belts create ports at room boundary."""
        doc = Document()
        # b1 inside room, b2 outside
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=100, y=100)
        b2 = Building(id="b2", building_type=BuildingType.ASSEMBLER, x=300, y=100)
        crossing_belt = Belt(
            id="crossing",
            tier=1,
            source_building_id="b1",
            source_port_index=0,
            dest_building_id="b2",
            dest_port_index=0,
        )
        doc.add_building(b1)
        doc.add_building(b2)
        doc.add_belt(crossing_belt)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = CreateRoomCommand(
            parent_scene_room_id=None,
            rect=(80, 80, 150, 100),  # Only includes b1
            building_ids=("b1",),
            belt_ids=(),
            original_crossing_belts=(crossing_belt,),
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=_generate_crossing_belt_ids((crossing_belt,)),
        )

        stack.execute(cmd)

        # Original crossing belt removed from document
        assert "crossing" not in doc.belts

        # Room should have a PORT_OUT and internal belt
        room = doc.rooms[cmd.created_room_id]
        ports = [b for b in room.buildings.values() if b.building_type == BuildingType.PORT_OUT]
        assert len(ports) == 1

        # Internal belt should connect b1 to port
        internal_belts = [b for b in room.belts.values() if b.source_building_id == "b1"]
        assert len(internal_belts) == 1
        assert internal_belts[0].dest_building_id == ports[0].id


class TestDelinkRoomCommand:
    """Tests for delinking room placements."""

    def test_delink_creates_copy(self) -> None:
        """Delink creates an independent copy of the room."""
        doc = Document()
        room = Room(id="room1", name="Test Room", width=200, height=150)
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=50, y=50)
        room.add_building(b1)
        doc.rooms[room.id] = room

        # Create two placements of same room
        p1 = RoomPlacement(id="p1", room_id="room1", x=0, y=0)
        p2 = RoomPlacement(id="p2", room_id="room1", x=300, y=0)
        doc.room_placements[p1.id] = p1
        doc.room_placements[p2.id] = p2
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = DelinkRoomCommand(
            placement_id="p2",
            canvas=canvas,
            old_room_id="room1",
            new_room_id=generate_id(),
        )

        stack.execute(cmd)

        # p2 should now point to a different room
        assert doc.room_placements["p2"].room_id != "room1"
        new_room_id = doc.room_placements["p2"].room_id

        # New room should exist with copied content
        assert new_room_id in doc.rooms
        new_room = doc.rooms[new_room_id]
        assert len(new_room.buildings) == 1
        assert new_room.name == "Copy of Test Room"

        # Original room unchanged
        assert "room1" in doc.rooms
        assert doc.room_placements["p1"].room_id == "room1"

    def test_delink_undo(self) -> None:
        """Undo restores original room reference."""
        doc = Document()
        room = Room(id="room1", name="Test Room", width=200, height=150)
        doc.rooms[room.id] = room

        p1 = RoomPlacement(id="p1", room_id="room1", x=0, y=0)
        p2 = RoomPlacement(id="p2", room_id="room1", x=300, y=0)
        doc.room_placements[p1.id] = p1
        doc.room_placements[p2.id] = p2
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = DelinkRoomCommand(
            placement_id="p2",
            canvas=canvas,
            old_room_id="room1",
            new_room_id=generate_id(),
        )

        stack.execute(cmd)
        new_room_id = doc.room_placements["p2"].room_id

        stack.undo()

        # p2 should point back to original room
        assert doc.room_placements["p2"].room_id == "room1"

        # Copied room should be removed
        assert new_room_id not in doc.rooms

    def test_delink_single_placement_noop(self) -> None:
        """Delink does nothing if room has only one placement."""
        doc = Document()
        room = Room(id="room1", name="Test Room", width=200, height=150)
        doc.rooms[room.id] = room

        p1 = RoomPlacement(id="p1", room_id="room1", x=0, y=0)
        doc.room_placements[p1.id] = p1
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = DelinkRoomCommand(
            placement_id="p1",
            canvas=canvas,
            old_room_id="room1",
            new_room_id=generate_id(),
        )

        stack.execute(cmd)

        # Should still point to same room (nothing to delink from)
        assert doc.room_placements["p1"].room_id == "room1"
        # No new rooms created
        assert len(doc.rooms) == 1


class TestPlaceBlueprintCommand:
    """Tests for placing blueprints."""

    def test_place_new_blueprint(self) -> None:
        """Placing a new blueprint adds room and placement."""
        doc = Document()
        room = Room(id="bp1", name="Blueprint", width=200, height=150)
        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=50, y=50)
        room.add_building(b1)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = PlaceBlueprintCommand(
            source_room=room,
            x=100,
            y=100,
            canvas=canvas,
            created_placement_id=generate_id(),
            room_will_be_added=True,
        )

        stack.execute(cmd)

        # Room should be added to document
        assert "bp1" in doc.rooms

        # Placement should be created
        assert cmd.created_placement_id in doc.room_placements
        placement = doc.room_placements[cmd.created_placement_id]
        assert placement.room_id == "bp1"
        assert placement.x == 100
        assert placement.y == 100

    def test_place_existing_blueprint_creates_linked(self) -> None:
        """Placing an existing room creates a linked placement."""
        doc = Document()
        room = Room(id="bp1", name="Blueprint", width=200, height=150)
        doc.rooms[room.id] = room

        # First placement already exists
        p1 = RoomPlacement(id="p1", room_id="bp1", x=0, y=0)
        doc.room_placements[p1.id] = p1
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = PlaceBlueprintCommand(
            source_room=room,
            x=300,
            y=0,
            canvas=canvas,
            created_placement_id=generate_id(),
            room_will_be_added=False,  # Room already exists
        )

        stack.execute(cmd)

        # Should have two placements of same room
        placements = doc.get_placements_for_room("bp1")
        assert len(placements) == 2

        # Room should not be duplicated
        assert len(doc.rooms) == 1

    def test_place_blueprint_undo(self) -> None:
        """Undo removes placement and room if it was added."""
        doc = Document()
        room = Room(id="bp1", name="Blueprint", width=200, height=150)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = PlaceBlueprintCommand(
            source_room=room,
            x=100,
            y=100,
            canvas=canvas,
            created_placement_id=generate_id(),
            room_will_be_added=True,
        )

        stack.execute(cmd)
        stack.undo()

        # Room and placement should be removed
        assert "bp1" not in doc.rooms
        assert cmd.created_placement_id not in doc.room_placements

    def test_place_blueprint_undo_keeps_existing_room(self) -> None:
        """Undo doesn't remove room if it already existed."""
        doc = Document()
        room = Room(id="bp1", name="Blueprint", width=200, height=150)
        doc.rooms[room.id] = room
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = PlaceBlueprintCommand(
            source_room=room,
            x=100,
            y=100,
            canvas=canvas,
            created_placement_id=generate_id(),
            room_will_be_added=False,  # Room already exists
        )

        stack.execute(cmd)
        stack.undo()

        # Room should still exist (it was pre-existing)
        assert "bp1" in doc.rooms
        # Placement should be removed
        assert cmd.created_placement_id not in doc.room_placements

    def test_place_blueprint_redo(self) -> None:
        """Redo uses same placement ID."""
        doc = Document()
        room = Room(id="bp1", name="Blueprint", width=200, height=150)
        canvas = make_mock_canvas()

        stack = CommandStack(doc)
        cmd = PlaceBlueprintCommand(
            source_room=room,
            x=100,
            y=100,
            canvas=canvas,
            created_placement_id=generate_id(),
            room_will_be_added=True,
        )

        stack.execute(cmd)
        placement_id = cmd.created_placement_id

        stack.undo()
        stack.redo()

        # Same placement ID should be used
        assert placement_id in doc.room_placements
