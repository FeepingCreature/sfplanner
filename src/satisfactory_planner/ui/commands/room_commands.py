"""Room-related commands: create room, delink, place blueprint."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from satisfactory_planner.core.models import PORT_EDGE_OFFSET
from satisfactory_planner.ui.commands.base import Command, get_scene

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Document, Room, RoomPlacement, Scene
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


def _shallow_copy_room_with_new_ids(room: Room) -> tuple[Room, dict[str, str]]:
    """Shallow copy a Room, regenerating IDs for buildings and belts only.

    This is a SHALLOW copy - nested room placements keep their original room_id,
    so linked rooms inside this room stay linked after delink.

    Returns the new room and a mapping of old_id -> new_id for buildings/belts.
    Belt references are updated to use new building IDs.
    """
    from satisfactory_planner.core.models import Room as RoomModel
    from satisfactory_planner.core.models import generate_id

    # Create ID mapping for buildings
    building_id_map: dict[str, str] = {}
    for old_id in room.buildings:
        building_id_map[old_id] = generate_id()

    # Create ID mapping for belts
    belt_id_map: dict[str, str] = {}
    for old_id in room.belts:
        belt_id_map[old_id] = generate_id()

    # Create new room (not deepcopy - we'll copy contents selectively)
    new_room = RoomModel(
        id=generate_id(),
        name=room.name,
        width=room.width,
        height=room.height,
    )

    # Copy buildings with new IDs
    for old_id, building in room.buildings.items():
        new_building = copy.deepcopy(building)
        new_id = building_id_map[old_id]
        new_building.id = new_id
        new_room.buildings[new_id] = new_building

    # Copy belts with new IDs and updated building references
    for old_id, belt in room.belts.items():
        new_belt = copy.deepcopy(belt)
        new_id = belt_id_map[old_id]
        new_belt.id = new_id
        # Update building references
        if new_belt.source_building_id in building_id_map:
            new_belt.source_building_id = building_id_map[new_belt.source_building_id]
        if new_belt.dest_building_id in building_id_map:
            new_belt.dest_building_id = building_id_map[new_belt.dest_building_id]
        new_room.belts[new_id] = new_belt

    # Nested rooms dict is NOT copied - stays empty
    # Nested room *placements* would be in parent document's room_placements
    # and they reference rooms by ID, so they stay linked automatically

    # Combine all ID mappings
    all_id_map = {**building_id_map, **belt_id_map}

    return new_room, all_id_map


@dataclass(frozen=True)
class CreateRoomCommand(Command):
    """Command to create a room from selected buildings.

    Moves buildings and belts into the new room, creating ports for crossing belts.

    Fully immutable - all IDs are pre-generated at construction time. This means
    execute/undo/redo always produce identical results with the same IDs.
    """

    parent_scene_room_id: str | None  # None = root document
    rect: tuple[float, float, float, float]  # x, y, width, height
    building_ids: tuple[str, ...]  # Buildings to move into room
    belt_ids: tuple[str, ...]  # Belts fully inside room
    original_crossing_belts: tuple[Belt, ...]  # Belts crossing boundary (captured at creation)
    canvas: FactoryCanvas

    # Pre-generated IDs - caller can supply or __post_init__ generates
    created_room_id: str = ""
    created_placement_id: str = ""

    # Pre-generated IDs for ports/belts created from crossing belts
    # Tuple of (original_belt_id, port_id, internal_belt_id, external_belt_id)
    # Generated in __post_init__ based on original_crossing_belts
    crossing_belt_port_ids: tuple[tuple[str, str, str, str], ...] = ()

    def __post_init__(self) -> None:
        """Generate all IDs needed for this command."""
        from satisfactory_planner.core.models import generate_id

        if not self.created_room_id:
            object.__setattr__(self, "created_room_id", generate_id())
        if not self.created_placement_id:
            object.__setattr__(self, "created_placement_id", generate_id())

        # Pre-generate IDs for each crossing belt: (original_belt_id, port_id, internal_belt_id, external_belt_id)
        if not self.crossing_belt_port_ids and self.original_crossing_belts:
            port_ids = tuple(
                (belt.id, generate_id(), generate_id(), generate_id())
                for belt in self.original_crossing_belts
            )
            object.__setattr__(self, "crossing_belt_port_ids", port_ids)

    def execute(self, document: Document) -> None:
        from satisfactory_planner.core import Room, RoomPlacement

        parent = get_scene(document, self.parent_scene_room_id)
        x, y, w, h = self.rect

        # Create the room
        room = Room(
            id=self.created_room_id,
            name=f"Room {len(document.rooms) + 1}",
            width=w,
            height=h,
        )

        # Move buildings into room (translate to room-relative coords)
        for building_id in self.building_ids:
            building = parent.remove_building(building_id)
            if building:
                building.x -= x
                building.y -= y
                room.add_building(building)
                # Remove from canvas (will be re-added as child of RoomItem)
                self.canvas.remove_building_item(building_id)

        # Move internal belts into room
        for belt_id in self.belt_ids:
            belt = parent.remove_belt(belt_id)
            if belt:
                room.add_belt(belt)
                self.canvas.remove_belt_item(belt_id)

        # Handle crossing belts (same logic for execute and redo - fully deterministic)
        self._handle_crossing_belts(document, parent, room, x, y)

        # Add room to document
        document.rooms[room.id] = room

        # Create placement
        placement = RoomPlacement(
            id=self.created_placement_id,
            room_id=room.id,
            x=x,
            y=y,
            parent_room_id=self.parent_scene_room_id,
        )
        document.room_placements[placement.id] = placement

        # Add room item to canvas
        self.canvas.add_room_item(placement, room)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        parent = get_scene(document, self.parent_scene_room_id)
        x, y, _w, _h = self.rect

        # Get the room
        room = document.rooms.get(self.created_room_id)
        if not room:
            logger.warning(f"CreateRoomCommand.undo: room {self.created_room_id} not found")
            return

        # Remove room item from canvas
        self.canvas.remove_room_item(self.created_placement_id)

        # Move buildings back to parent scene (restore absolute coords)
        for building_id in self.building_ids:
            building = room.remove_building(building_id)
            if building:
                building.x += x
                building.y += y
                parent.add_building(building)
                self.canvas.add_building_item(building)

        # Move belts back to parent scene
        for belt_id in self.belt_ids:
            belt = room.remove_belt(belt_id)
            if belt:
                parent.add_belt(belt)
                self.canvas.add_belt_item(belt)

        # Restore crossing belts and remove created ports
        self._undo_crossing_belts(document, parent, room)

        # Remove room and placement from document
        document.rooms.pop(self.created_room_id, None)
        document.room_placements.pop(self.created_placement_id, None)

        self.canvas.notify_mutation()

    def _handle_crossing_belts(
        self,
        document: Document,
        parent: Scene,
        room: Room,
        room_x: float,
        room_y: float,
    ) -> None:
        """Handle belts that cross the room boundary by creating ports.

        Uses pre-generated IDs from crossing_belt_port_ids - fully deterministic.
        Creates:
        - A port building inside the room (PORT_IN or PORT_OUT)
        - An internal belt connecting the port to the building inside the room
        - An external belt connecting the outside building to the port
        """
        from satisfactory_planner.core.models import Belt as BeltModel
        from satisfactory_planner.core.models import Building, BuildingType

        room_w = self.rect[2]

        for crossing_belt_id, port_id, internal_belt_id, external_belt_id in self.crossing_belt_port_ids:
            belt = parent.belts.get(crossing_belt_id)
            if not belt:
                continue

            # Determine direction: is source inside or outside?
            source_inside = belt.source_building_id in self.building_ids
            dest_inside = belt.dest_building_id in self.building_ids

            if source_inside and not dest_inside:
                # Output: source is inside room, create PORT_OUT
                source_building = room.buildings.get(belt.source_building_id)
                if not source_building:
                    continue

                port = Building(
                    id=port_id,
                    building_type=BuildingType.PORT_OUT,
                    x=room_w - PORT_EDGE_OFFSET,  # Right edge
                    y=source_building.y,
                    rotation=0,
                )
                room.add_building(port)

                # Belt inside room: from source to port
                inside_belt = BeltModel(
                    id=internal_belt_id,
                    tier=belt.tier,
                    source_building_id=belt.source_building_id,
                    source_port_index=belt.source_port_index,
                    dest_building_id=port_id,
                    dest_port_index=0,
                    item_id=belt.item_id,
                )
                room.add_belt(inside_belt)

                # External belt: from port to original destination (outside)
                external_belt = BeltModel(
                    id=external_belt_id,
                    tier=belt.tier,
                    source_building_id=port_id,
                    source_port_index=0,
                    dest_building_id=belt.dest_building_id,
                    dest_port_index=belt.dest_port_index,
                    item_id=belt.item_id,
                )
                parent.add_belt(external_belt)
                self.canvas.add_belt_item(external_belt)

            elif dest_inside and not source_inside:
                # Input: dest is inside room, create PORT_IN
                dest_building = room.buildings.get(belt.dest_building_id)
                if not dest_building:
                    continue

                port = Building(
                    id=port_id,
                    building_type=BuildingType.PORT_IN,
                    x=0,  # Left edge
                    y=dest_building.y,
                    rotation=0,
                )
                room.add_building(port)

                # Belt inside room: from port to destination
                inside_belt = BeltModel(
                    id=internal_belt_id,
                    tier=belt.tier,
                    source_building_id=port_id,
                    source_port_index=0,
                    dest_building_id=belt.dest_building_id,
                    dest_port_index=belt.dest_port_index,
                    item_id=belt.item_id,
                )
                room.add_belt(inside_belt)

                # External belt: from original source (outside) to port
                external_belt = BeltModel(
                    id=external_belt_id,
                    tier=belt.tier,
                    source_building_id=belt.source_building_id,
                    source_port_index=belt.source_port_index,
                    dest_building_id=port_id,
                    dest_port_index=0,
                    item_id=belt.item_id,
                )
                parent.add_belt(external_belt)
                self.canvas.add_belt_item(external_belt)

            # Remove original crossing belt from parent
            parent.remove_belt(crossing_belt_id)
            self.canvas.remove_belt_item(crossing_belt_id)

    def _undo_crossing_belts(
        self,
        document: Document,
        parent: Scene,
        room: Room,
    ) -> None:
        """Undo crossing belt handling - restore original belts, remove ports."""
        # Remove created ports, internal belts, and external belts
        for _crossing_belt_id, port_id, internal_belt_id, external_belt_id in self.crossing_belt_port_ids:
            # Remove internal belt from room
            room.remove_belt(internal_belt_id)
            # Remove port from room
            room.remove_building(port_id)
            # Remove external belt from parent scene
            parent.remove_belt(external_belt_id)
            self.canvas.remove_belt_item(external_belt_id)

        # Restore original belts (captured at command creation time)
        for belt in self.original_crossing_belts:
            parent.add_belt(belt)
            self.canvas.add_belt_item(belt)


@dataclass(frozen=True)
class DeleteRoomPlacementCommand(Command):
    """Command to delete a room placement.

    If this is the last placement for a room, also deletes the room and all
    its contents. Use DissolveRoomCommand to restore contents instead.
    """

    placement_id: str
    canvas: FactoryCanvas

    # Captured state for undo
    _placement: RoomPlacement | None = None
    _room: Room | None = None
    _was_last_placement: bool = False

    def execute(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(
                f"DeleteRoomPlacementCommand.execute: placement {self.placement_id} not found"
            )
            return

        room = document.rooms.get(placement.room_id)
        if not room:
            logger.warning(
                f"DeleteRoomPlacementCommand.execute: room {placement.room_id} not found"
            )
            return

        # Capture state for undo (use object.__setattr__ for frozen dataclass)
        object.__setattr__(self, "_placement", copy.deepcopy(placement))
        object.__setattr__(self, "_room", copy.deepcopy(room))

        # Check if this is the last placement
        placements = document.get_placements_for_room(placement.room_id)
        is_last = len(placements) <= 1
        object.__setattr__(self, "_was_last_placement", is_last)

        # Remove room item from canvas
        self.canvas.remove_room_item(self.placement_id)

        # Remove placement
        document.room_placements.pop(self.placement_id, None)

        if is_last:
            # Remove room from document (contents are deleted with it)
            document.rooms.pop(room.id, None)

        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        if not self._placement or not self._room:
            logger.warning("DeleteRoomPlacementCommand.undo: no captured state")
            return

        if self._was_last_placement:
            # Re-add the room
            room_copy = copy.deepcopy(self._room)
            document.rooms[room_copy.id] = room_copy

        # Re-add placement
        placement_copy = copy.deepcopy(self._placement)
        document.room_placements[placement_copy.id] = placement_copy

        # Re-add room item
        room = document.rooms.get(placement_copy.room_id)
        if room:
            self.canvas.add_room_item(placement_copy, room)

        self.canvas.notify_mutation()


@dataclass(frozen=True)
class DissolveRoomCommand(Command):
    """Command to dissolve a room, restoring its contents to the parent scene.

    Unlike delete, this preserves the buildings and belts by moving them back
    to the parent scene at the room's position.
    """

    placement_id: str
    canvas: FactoryCanvas

    # Captured state for undo
    _placement: RoomPlacement | None = None
    _room: Room | None = None

    def execute(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(f"DissolveRoomCommand.execute: placement {self.placement_id} not found")
            return

        room = document.rooms.get(placement.room_id)
        if not room:
            logger.warning(f"DissolveRoomCommand.execute: room {placement.room_id} not found")
            return

        # Capture state for undo
        object.__setattr__(self, "_placement", copy.deepcopy(placement))
        object.__setattr__(self, "_room", copy.deepcopy(room))

        # Remove room item from canvas
        self.canvas.remove_room_item(self.placement_id)

        # Remove placement
        document.room_placements.pop(self.placement_id, None)

        # Restore buildings and belts to parent scene
        parent = get_scene(document, placement.parent_room_id)

        for building in list(room.buildings.values()):
            # Translate back to absolute coords
            building.x += placement.x
            building.y += placement.y
            parent.add_building(building)
            self.canvas.add_building_item(building)

        for belt in list(room.belts.values()):
            parent.add_belt(belt)
            self.canvas.add_belt_item(belt)

        # Remove room from document
        document.rooms.pop(room.id, None)

        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        if not self._placement or not self._room:
            logger.warning("DissolveRoomCommand.undo: no captured state")
            return

        parent = get_scene(document, self._placement.parent_room_id)

        # Re-add the room
        room_copy = copy.deepcopy(self._room)
        document.rooms[room_copy.id] = room_copy

        # Remove restored buildings/belts from parent
        for building_id in self._room.buildings:
            if building_id in parent.buildings:
                parent.remove_building(building_id)
                self.canvas.remove_building_item(building_id)

        for belt_id in self._room.belts:
            if belt_id in parent.belts:
                parent.remove_belt(belt_id)
                self.canvas.remove_belt_item(belt_id)

        # Re-add placement
        placement_copy = copy.deepcopy(self._placement)
        document.room_placements[placement_copy.id] = placement_copy

        # Re-add room item
        room = document.rooms.get(placement_copy.room_id)
        if room:
            self.canvas.add_room_item(placement_copy, room)

        self.canvas.notify_mutation()


@dataclass(frozen=True)
class DelinkRoomCommand(Command):
    """Command to delink a room placement from its linked instances.

    Creates a deep copy of the Room with new IDs for all contents,
    and points the placement at the new independent room.
    """

    placement_id: str  # The placement being delinked
    canvas: FactoryCanvas

    # Captured at construction for undo
    old_room_id: str = ""
    # Generated at construction for deterministic redo
    new_room_id: str = ""

    def __post_init__(self) -> None:
        """Capture old room ID and pre-generate new room ID."""
        from satisfactory_planner.core.models import generate_id

        # Note: We can't look up placement here (no document access)
        # old_room_id must be set by caller or we set it in execute
        if not self.new_room_id:
            object.__setattr__(self, "new_room_id", generate_id())

    def execute(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(f"DelinkRoomCommand.execute: placement {self.placement_id} not found")
            return

        old_room = document.rooms.get(placement.room_id)
        if not old_room:
            logger.warning(f"DelinkRoomCommand.execute: room {placement.room_id} not found")
            return

        # Capture old_room_id if not already set
        if not self.old_room_id:
            object.__setattr__(self, "old_room_id", placement.room_id)

        # Check if this is the only placement - nothing to delink
        placements = document.get_placements_for_room(placement.room_id)
        if len(placements) <= 1:
            logger.info("DelinkRoomCommand.execute: room has only one placement, nothing to delink")
            return

        # Shallow copy the room with new IDs (nested rooms stay linked)
        new_room, _id_map = _shallow_copy_room_with_new_ids(old_room)

        # Override the generated ID with our pre-generated one (for deterministic redo)
        new_room.id = self.new_room_id

        # Windows-style naming: "Copy of X"
        new_room.name = f"Copy of {old_room.name}"

        # Add new room to document
        document.rooms[new_room.id] = new_room

        # Point this placement at the new room
        placement.room_id = new_room.id

        # Refresh the canvas
        self.canvas.remove_room_item(self.placement_id)
        self.canvas.add_room_item(placement, new_room)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(f"DelinkRoomCommand.undo: placement {self.placement_id} not found")
            return

        if not self.old_room_id:
            logger.warning("DelinkRoomCommand.undo: old_room_id not captured")
            return

        old_room = document.rooms.get(self.old_room_id)
        if not old_room:
            logger.warning(f"DelinkRoomCommand.undo: old room {self.old_room_id} not found")
            return

        # Remove the copied room
        document.rooms.pop(self.new_room_id, None)

        # Point placement back at original room
        placement.room_id = self.old_room_id

        # Refresh the canvas
        self.canvas.remove_room_item(self.placement_id)
        self.canvas.add_room_item(placement, old_room)
        self.canvas.notify_mutation()


@dataclass(frozen=True)
class PlaceBlueprintCommand(Command):
    """Command to place a blueprint (room from library) on the canvas.

    If the room ID already exists in the document, creates a linked placement.
    If it doesn't exist, adds the room and creates a placement.
    This allows blueprints to maintain linkage with existing rooms.
    """

    source_room: Room  # The blueprint room (preserves original ID)
    x: float
    y: float
    canvas: FactoryCanvas

    # Pre-generated placement ID for deterministic undo/redo
    created_placement_id: str = ""
    # Track whether we added the room (for undo)
    _room_was_added: bool = False

    def __post_init__(self) -> None:
        """Pre-generate placement ID for deterministic redo."""
        from satisfactory_planner.core.models import generate_id

        if not self.created_placement_id:
            object.__setattr__(self, "created_placement_id", generate_id())

    def execute(self, document: Document) -> None:
        from satisfactory_planner.core.models import RoomPlacement

        # Check if room already exists in document (linked case)
        room_exists = self.source_room.id in document.rooms

        if not room_exists:
            # Add the room to document (preserving its ID)
            document.rooms[self.source_room.id] = self.source_room
            object.__setattr__(self, "_room_was_added", True)

        # Get the room (either existing or just added)
        room = document.rooms[self.source_room.id]

        # Create placement
        placement = RoomPlacement(
            id=self.created_placement_id,
            room_id=room.id,
            x=self.x,
            y=self.y,
            parent_room_id=None,  # Blueprint placement always at root for now
        )
        document.room_placements[placement.id] = placement

        # Add to canvas
        self.canvas.add_room_item(placement, room)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        # Remove room item from canvas
        self.canvas.remove_room_item(self.created_placement_id)

        # Remove placement from document
        document.room_placements.pop(self.created_placement_id, None)

        # Only remove room if we added it
        if self._room_was_added:
            document.rooms.pop(self.source_room.id, None)

        self.canvas.notify_mutation()
