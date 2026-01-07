"""Command pattern for undo/redo support.

Commands are a UI concern - they exist for undo/redo which is a user interaction concept.
Commands can directly update both the data model and the UI.

Commands are immutable - all state needed for execute/undo is captured at construction.
Execute and undo are idempotent - calling them multiple times logs a warning but doesn't break.

Commands receive the Document at execute/undo time, not at construction. They store a
scene_room_id to identify which scene (Document or Room) they operate on, and look up
the scene from the document at execute time. This keeps commands serializable and avoids
stale references.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Building, Document, Room, Scene
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


class BuildingMove(NamedTuple):
    """A single building's position/rotation change."""

    building_id: str
    old_x: float
    old_y: float
    old_rotation: int
    new_x: float
    new_y: float
    new_rotation: int


class Command(ABC):
    """Base class for undoable commands.

    Commands receive the document at execute/undo time from the CommandStack.
    They should not store a document reference - instead store scene_room_id
    and look up the scene from the document.
    """

    @abstractmethod
    def execute(self, document: Document) -> None:
        """Execute the command."""
        ...

    @abstractmethod
    def undo(self, document: Document) -> None:
        """Undo the command."""
        ...

    def merge_with(self, other: Command) -> Command | None:
        """Optionally merge with another command. Return merged command or None."""
        return None


def get_scene(document: Document, scene_room_id: str | None) -> Scene:
    """Get a scene from a document by room ID.

    Args:
        document: The document to search
        scene_room_id: None for root document, or a room ID

    Returns:
        The Document itself if scene_room_id is None, otherwise the Room
    """
    if scene_room_id is None:
        return document
    return document.rooms[scene_room_id]


class CommandStack:
    """Stack of commands for undo/redo.

    The stack owns the document reference and passes it to commands at execute time.
    """

    def __init__(self, document: Document) -> None:
        self.document = document
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []

    def execute(self, cmd: Command) -> None:
        """Execute a command and add to undo stack."""
        cmd.execute(self.document)
        # Try to merge with previous
        if self.undo_stack:
            merged = self.undo_stack[-1].merge_with(cmd)
            if merged:
                self.undo_stack[-1] = merged
                self.redo_stack.clear()
                return
        self.undo_stack.append(cmd)
        self.redo_stack.clear()

    def undo(self) -> None:
        """Undo the last command."""
        if self.undo_stack:
            cmd = self.undo_stack.pop()
            cmd.undo(self.document)
            self.redo_stack.append(cmd)

    def redo(self) -> None:
        """Redo the last undone command."""
        if self.redo_stack:
            cmd = self.redo_stack.pop()
            cmd.execute(self.document)
            self.undo_stack.append(cmd)

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0


@dataclass(frozen=True)
class PlaceBuildingCommand(Command):
    """Command to place a building in a scene."""

    scene_room_id: str | None  # None = root document, else room ID
    building: Building
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        if self.building.id in scene.buildings:
            logger.warning(
                f"PlaceBuildingCommand.execute: building {self.building.id} already exists"
            )
            return
        scene.add_building(self.building)
        self.canvas.add_building_item(self.building)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        if self.building.id not in scene.buildings:
            logger.warning(f"PlaceBuildingCommand.undo: building {self.building.id} not found")
            return
        scene.remove_building(self.building.id)
        self.canvas.remove_building_item(self.building.id)
        self.canvas.notify_mutation()


@dataclass(frozen=True)
class DeleteItemsCommand(Command):
    """Command to delete buildings and belts.

    Buildings and belts to delete are captured at construction time.
    """

    scene_room_id: str | None  # None = root document, else room ID
    buildings: tuple[Building, ...]
    belts: tuple[Belt, ...]
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        any_deleted = False
        for building in self.buildings:
            if building.id not in scene.buildings:
                logger.warning(f"DeleteItemsCommand.execute: building {building.id} not found")
                continue
            scene.remove_building(building.id)
            self.canvas.remove_building_item(building.id)
            any_deleted = True

        for belt in self.belts:
            if belt.id not in scene.belts:
                logger.warning(f"DeleteItemsCommand.execute: belt {belt.id} not found")
                continue
            scene.remove_belt(belt.id)
            self.canvas.remove_belt_item(belt.id)
            any_deleted = True

        if any_deleted:
            self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        any_restored = False
        for building in self.buildings:
            if building.id in scene.buildings:
                logger.warning(f"DeleteItemsCommand.undo: building {building.id} already exists")
                continue
            scene.add_building(building)
            self.canvas.add_building_item(building)
            any_restored = True

        for belt in self.belts:
            if belt.id in scene.belts:
                logger.warning(f"DeleteItemsCommand.undo: belt {belt.id} already exists")
                continue
            scene.add_belt(belt)
            self.canvas.add_belt_item(belt)
            any_restored = True

        if any_restored:
            self.canvas.notify_mutation()


@dataclass(frozen=True)
class MoveBuildingsCommand(Command):
    """Command to move and/or rotate buildings.

    Stores original and new positions/rotations for idempotent execute/undo.
    Movement and rotation during drag are a single UI gesture.
    """

    scene_room_id: str | None  # None = root document, else room ID
    canvas: FactoryCanvas
    moves: tuple[BuildingMove, ...]

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        any_changed = False
        for move in self.moves:
            building = scene.buildings.get(move.building_id)
            if not building:
                logger.warning(
                    f"MoveBuildingsCommand.execute: building {move.building_id} not found"
                )
                continue
            changed = False
            if building.x != move.new_x or building.y != move.new_y:
                building.x = move.new_x
                building.y = move.new_y
                changed = True
            if building.rotation != move.new_rotation:
                building.rotation = move.new_rotation
                changed = True
            if changed:
                self.canvas.refresh_building(move.building_id)
                self.canvas.refresh_belts_for_building(move.building_id)
                any_changed = True
        if any_changed:
            self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        any_changed = False
        for move in self.moves:
            building = scene.buildings.get(move.building_id)
            if not building:
                logger.warning(f"MoveBuildingsCommand.undo: building {move.building_id} not found")
                continue
            changed = False
            if building.x != move.old_x or building.y != move.old_y:
                building.x = move.old_x
                building.y = move.old_y
                changed = True
            if building.rotation != move.old_rotation:
                building.rotation = move.old_rotation
                changed = True
            if changed:
                self.canvas.refresh_building(move.building_id)
                self.canvas.refresh_belts_for_building(move.building_id)
                any_changed = True
        if any_changed:
            self.canvas.notify_mutation()

    def merge_with(self, other: Command) -> Command | None:
        """Merge consecutive move commands for same buildings."""
        if not isinstance(other, MoveBuildingsCommand):
            return None

        # Can only merge commands in the same scene
        if self.scene_room_id != other.scene_room_id:
            return None

        self_ids = {m.building_id for m in self.moves}
        other_ids = {m.building_id for m in other.moves}
        if self_ids != other_ids:
            return None

        # Merge: keep our old state, use their new state
        other_new = {m.building_id: (m.new_x, m.new_y, m.new_rotation) for m in other.moves}
        merged_moves = tuple(
            BuildingMove(
                building_id=m.building_id,
                old_x=m.old_x,
                old_y=m.old_y,
                old_rotation=m.old_rotation,
                new_x=other_new[m.building_id][0],
                new_y=other_new[m.building_id][1],
                new_rotation=other_new[m.building_id][2],
            )
            for m in self.moves
        )
        return MoveBuildingsCommand(
            scene_room_id=self.scene_room_id,
            canvas=self.canvas,
            moves=merged_moves,
        )


@dataclass(frozen=True)
class ConnectBeltCommand(Command):
    """Command to connect a belt between buildings."""

    scene_room_id: str | None  # None = root document, else room ID
    belt: Belt
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        if self.belt.id in scene.belts:
            logger.warning(f"ConnectBeltCommand.execute: belt {self.belt.id} already exists")
            return
        scene.add_belt(self.belt)
        self.canvas.add_belt_item(self.belt)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        if self.belt.id not in scene.belts:
            logger.warning(f"ConnectBeltCommand.undo: belt {self.belt.id} not found")
            return
        scene.remove_belt(self.belt.id)
        self.canvas.remove_belt_item(self.belt.id)
        self.canvas.notify_mutation()


# NOTE: If more property-change commands are added (e.g., belt item_id),
# consider refactoring to a generic ChangePropertyCommand pattern.


@dataclass(frozen=True)
class SetRecipeCommand(Command):
    """Command to set a building's recipe."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_recipe_id: str | None
    new_recipe_id: str | None
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetRecipeCommand.execute: building {self.building_id} not found")
            return
        if building.recipe_id == self.new_recipe_id:
            logger.warning(f"SetRecipeCommand.execute: recipe already set to {self.new_recipe_id}")
            return
        building.recipe_id = self.new_recipe_id
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetRecipeCommand.undo: building {self.building_id} not found")
            return
        if building.recipe_id == self.old_recipe_id:
            logger.warning(f"SetRecipeCommand.undo: recipe already set to {self.old_recipe_id}")
            return
        building.recipe_id = self.old_recipe_id
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()


@dataclass(frozen=True)
class SetClockSpeedCommand(Command):
    """Command to set a building's clock speed."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_clock_speed: float
    new_clock_speed: float
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetClockSpeedCommand.execute: building {self.building_id} not found")
            return
        if building.clock_speed == self.new_clock_speed:
            logger.warning(
                f"SetClockSpeedCommand.execute: clock speed already set to {self.new_clock_speed}"
            )
            return
        building.clock_speed = self.new_clock_speed
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetClockSpeedCommand.undo: building {self.building_id} not found")
            return
        if building.clock_speed == self.old_clock_speed:
            logger.warning(
                f"SetClockSpeedCommand.undo: clock speed already set to {self.old_clock_speed}"
            )
            return
        building.clock_speed = self.old_clock_speed
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()


@dataclass
class CreateRoomCommand(Command):
    """Command to create a room from selected buildings.

    Moves buildings and belts into the new room, creating ports for crossing belts.

    NOTE: Not frozen because we need mutable state for tracking created objects.
    All tracking state is initialized in __post_init__ and persists across undo/redo.
    """

    parent_scene_room_id: str | None  # None = root document
    rect: tuple[float, float, float, float]  # x, y, width, height
    building_ids: tuple[str, ...]  # Buildings to move into room
    belt_ids: tuple[str, ...]  # Belts fully inside room
    crossing_belt_ids: tuple[str, ...]  # Belts crossing boundary
    canvas: FactoryCanvas

    # Generated IDs - stable across undo/redo
    created_room_id: str = ""
    created_placement_id: str = ""

    # Tracking for crossing belt handling - initialized once in __post_init__
    # NOTE: These use field(default_factory=...) pattern via __post_init__ init
    # Type is list[str] but dataclass default must be None to detect first init
    _created_port_ids: list[str] = None  # type: ignore[assignment]
    _created_belt_ids: list[str] = None  # type: ignore[assignment]
    _original_belts: dict[str, Belt] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Generate IDs and initialize tracking lists (only once)."""
        from satisfactory_planner.core.models import generate_id

        if not self.created_room_id:
            object.__setattr__(self, "created_room_id", generate_id())
        if not self.created_placement_id:
            object.__setattr__(self, "created_placement_id", generate_id())

        # Initialize tracking lists only once
        if self._created_port_ids is None:
            object.__setattr__(self, "_created_port_ids", [])
        if self._created_belt_ids is None:
            object.__setattr__(self, "_created_belt_ids", [])
        if self._original_belts is None:
            object.__setattr__(self, "_original_belts", {})

    def execute(self, document: Document) -> None:
        from satisfactory_planner.core import Room, RoomPlacement

        parent = get_scene(document, self.parent_scene_room_id)
        x, y, w, h = self.rect

        # Check if this is a redo (room already created once before)
        is_redo = len(self._original_belts) > 0

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

        # Handle crossing belts
        if is_redo:
            # Redo: restore the ports and belts we created before
            self._redo_crossing_belts(document, parent, room, x, y)
        else:
            # First execute: create new ports for crossing belts
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
        self._undo_crossing_belts(document, parent, room, x, y)

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

        For each crossing belt:
        1. Remove the original belt
        2. Create a port at the room boundary (PORT_IN or PORT_OUT)
        3. Create belt from external building to port (in parent scene)
        4. Create belt from port to internal building (in room)

        Tracking lists are initialized in __post_init__ and persist across undo/redo.
        """
        room_rect = (room_x, room_y, self.rect[2], self.rect[3])

        for belt_id in self.crossing_belt_ids:
            belt = parent.belts.get(belt_id)
            if not belt:
                continue

            # Determine direction: is source inside or outside?
            source_inside = belt.source_building_id in self.building_ids
            dest_inside = belt.dest_building_id in self.building_ids

            if source_inside and not dest_inside:
                # Output: source is inside room, dest is outside
                # Create PORT_OUT inside room, belt from room building to port,
                # belt from port (via room boundary) to external building
                self._create_output_port(document, parent, room, belt, room_rect)
            elif dest_inside and not source_inside:
                # Input: source is outside room, dest is inside
                # Create PORT_IN inside room, belt from external to port,
                # belt from port to room building
                self._create_input_port(document, parent, room, belt, room_rect)

            # Save original belt for undo and remove it
            self._original_belts[belt_id] = belt
            parent.remove_belt(belt_id)
            self.canvas.remove_belt_item(belt_id)

    def _create_input_port(
        self,
        document: Document,
        parent: Scene,
        room: Room,
        belt: Belt,
        room_rect: tuple[float, float, float, float],
    ) -> None:
        """Create an input port for a belt entering the room."""
        from satisfactory_planner.core.models import Belt, Building, BuildingType, generate_id

        room_x, room_y, room_w, room_h = room_rect

        # Get dest building position (inside room, already moved)
        dest_building = room.buildings.get(belt.dest_building_id)
        if not dest_building:
            return

        # Port goes on left edge of room (simplified - could be smarter about edge selection)
        port_id = generate_id()
        port = Building(
            id=port_id,
            building_type=BuildingType.PORT_IN,
            x=0,  # Left edge of room (room-relative)
            y=dest_building.y,  # Same Y as destination
            rotation=0,
        )
        room.add_building(port)
        self._created_port_ids.append(port_id)

        # Belt from external source to room boundary (in parent scene coords)
        # The "port" from outside is just the room placement itself
        # For now, we connect to a virtual position - this is a simplification
        # In a full implementation, ports would be rendered on the room boundary

        # Belt inside room: from port to destination
        inside_belt_id = generate_id()
        inside_belt = Belt(
            id=inside_belt_id,
            tier=belt.tier,
            source_building_id=port_id,
            source_port_index=0,  # PORT_IN has output at index 0 (inside room)
            dest_building_id=belt.dest_building_id,
            dest_port_index=belt.dest_port_index,
            item_id=belt.item_id,
        )
        room.add_belt(inside_belt)
        self._created_belt_ids.append(inside_belt_id)

    def _create_output_port(
        self,
        document: Document,
        parent: Scene,
        room: Room,
        belt: Belt,
        room_rect: tuple[float, float, float, float],
    ) -> None:
        """Create an output port for a belt leaving the room."""
        from satisfactory_planner.core.models import Belt, Building, BuildingType, generate_id

        room_x, room_y, room_w, room_h = room_rect

        # Get source building position (inside room, already moved)
        source_building = room.buildings.get(belt.source_building_id)
        if not source_building:
            return

        # Port goes on right edge of room (simplified)
        port_id = generate_id()
        port = Building(
            id=port_id,
            building_type=BuildingType.PORT_OUT,
            x=room_w - 30,  # Right edge of room (room-relative), port is 30 wide
            y=source_building.y,  # Same Y as source
            rotation=0,
        )
        room.add_building(port)
        self._created_port_ids.append(port_id)

        # Belt inside room: from source to port
        inside_belt_id = generate_id()
        inside_belt = Belt(
            id=inside_belt_id,
            tier=belt.tier,
            source_building_id=belt.source_building_id,
            source_port_index=belt.source_port_index,
            dest_building_id=port_id,
            dest_port_index=0,  # PORT_OUT has input at index 0 (inside room)
            item_id=belt.item_id,
        )
        room.add_belt(inside_belt)
        self._created_belt_ids.append(inside_belt_id)

    def _undo_crossing_belts(
        self,
        document: Document,
        parent: Scene,
        room: Room,
        room_x: float,
        room_y: float,
    ) -> None:
        """Undo crossing belt handling - restore original belts, remove ports.

        NOTE: Does NOT clear the tracking lists - they persist for redo.
        Saves created ports/belts for redo.
        """
        # Save created belts before removing (for redo)
        if not hasattr(self, "_saved_internal_belts"):
            object.__setattr__(self, "_saved_internal_belts", {})
        if not hasattr(self, "_saved_ports"):
            object.__setattr__(self, "_saved_ports", {})

        for belt_id in self._created_belt_ids:
            belt = room.belts.get(belt_id)
            if belt:
                self._saved_internal_belts[belt_id] = belt  # type: ignore[attr-defined]
                room.remove_belt(belt_id)

        for port_id in self._created_port_ids:
            port = room.buildings.get(port_id)
            if port:
                self._saved_ports[port_id] = port  # type: ignore[attr-defined]
                room.remove_building(port_id)

        # Restore original belts to parent scene
        for _belt_id, belt in self._original_belts.items():
            parent.add_belt(belt)
            self.canvas.add_belt_item(belt)

    def _redo_crossing_belts(
        self,
        document: Document,
        parent: Scene,
        room: Room,
        room_x: float,
        room_y: float,
    ) -> None:
        """Redo crossing belt handling - restore created ports/belts, remove originals."""
        # Remove original belts from parent (they were restored during undo)
        for belt_id, _belt in self._original_belts.items():
            parent.remove_belt(belt_id)
            self.canvas.remove_belt_item(belt_id)

        # Restore saved ports to room
        for _port_id, port in getattr(self, "_saved_ports", {}).items():
            room.add_building(port)

        # Restore saved internal belts to room
        for _belt_id, belt in getattr(self, "_saved_internal_belts", {}).items():
            room.add_belt(belt)


@dataclass(frozen=True)
class SetBeltTierCommand(Command):
    """Command to set a belt's tier."""

    scene_room_id: str | None  # None = root document, else room ID
    belt_id: str
    old_tier: int
    new_tier: int
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        belt = scene.belts.get(self.belt_id)
        if not belt:
            logger.warning(f"SetBeltTierCommand.execute: belt {self.belt_id} not found")
            return
        if belt.tier == self.new_tier:
            logger.warning(f"SetBeltTierCommand.execute: tier already set to {self.new_tier}")
            return
        belt.tier = self.new_tier
        self.canvas.refresh_belt(self.belt_id)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        belt = scene.belts.get(self.belt_id)
        if not belt:
            logger.warning(f"SetBeltTierCommand.undo: belt {self.belt_id} not found")
            return
        if belt.tier == self.old_tier:
            logger.warning(f"SetBeltTierCommand.undo: tier already set to {self.old_tier}")
            return
        belt.tier = self.old_tier
        self.canvas.refresh_belt(self.belt_id)
        self.canvas.notify_mutation()
