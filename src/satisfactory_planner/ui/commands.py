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
    from satisfactory_planner.core.models import Belt, Building, Document, Scene
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

    Moves buildings and belts into the new room, leaving crossing belts for now
    (port creation will be added in Phase 7).
    """

    parent_scene_room_id: str | None  # None = root document
    rect: tuple[float, float, float, float]  # x, y, width, height
    building_ids: tuple[str, ...]  # Buildings to move into room
    belt_ids: tuple[str, ...]  # Belts fully inside room
    crossing_belt_ids: tuple[str, ...]  # Belts crossing boundary (for future port creation)
    canvas: FactoryCanvas

    # Generated IDs (mutable for undo tracking)
    created_room_id: str = ""
    created_placement_id: str = ""

    def __post_init__(self) -> None:
        """Generate IDs if not already set."""
        from satisfactory_planner.core.models import generate_id

        if not self.created_room_id:
            object.__setattr__(self, "created_room_id", generate_id())
        if not self.created_placement_id:
            object.__setattr__(self, "created_placement_id", generate_id())

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

        # For now, just delete crossing belts (ports will handle this in Phase 7)
        for belt_id in self.crossing_belt_ids:
            belt = parent.remove_belt(belt_id)
            if belt:
                self.canvas.remove_belt_item(belt_id)

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

        # Restore crossing belts (they were deleted, need to recreate from document state)
        # For now, crossing belts are lost on undo - will fix with proper port handling

        # Remove room and placement from document
        document.rooms.pop(self.created_room_id, None)
        document.room_placements.pop(self.created_placement_id, None)

        self.canvas.notify_mutation()


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
