"""Building-related commands: place, delete, move."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from satisfactory_planner.ui.commands.base import BuildingMove, Command, get_scene

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Building, Document
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


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
        # Update data model
        scene.add_building(self.building)
        # Sync visual
        self.canvas.sync_add_building(self.building.id, self.scene_room_id)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        if self.building.id not in scene.buildings:
            logger.warning(f"PlaceBuildingCommand.undo: building {self.building.id} not found")
            return
        # Update data model
        scene.remove_building(self.building.id)
        # Sync visual
        self.canvas.sync_remove_building(self.building.id, self.scene_room_id)
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
            self.canvas.sync_remove_building(building.id, self.scene_room_id)
            any_deleted = True

        for belt in self.belts:
            if belt.id not in scene.belts:
                logger.warning(f"DeleteItemsCommand.execute: belt {belt.id} not found")
                continue
            scene.remove_belt(belt.id)
            self.canvas.sync_remove_belt(belt.id, self.scene_room_id)
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
            self.canvas.sync_add_building(building.id, self.scene_room_id)
            any_restored = True

        for belt in self.belts:
            if belt.id in scene.belts:
                logger.warning(f"DeleteItemsCommand.undo: belt {belt.id} already exists")
                continue
            scene.add_belt(belt)
            self.canvas.sync_add_belt(belt.id, self.scene_room_id)
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
        for move in self.moves:
            building = scene.buildings.get(move.building_id)
            if not building:
                logger.warning(
                    f"MoveBuildingsCommand.execute: building {move.building_id} not found"
                )
                continue
            # Always update model (may already be synced by Qt drag)
            building.x = move.new_x
            building.y = move.new_y
            building.rotation = move.new_rotation
            # Always refresh - for rooms this updates all linked instances
            self.canvas.refresh_building(move.building_id)
            self.canvas.refresh_belts_for_building(move.building_id)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        for move in self.moves:
            building = scene.buildings.get(move.building_id)
            if not building:
                logger.warning(f"MoveBuildingsCommand.undo: building {move.building_id} not found")
                continue
            # Always restore old position
            building.x = move.old_x
            building.y = move.old_y
            building.rotation = move.old_rotation
            # Always refresh - for rooms this updates all linked instances
            self.canvas.refresh_building(move.building_id)
            self.canvas.refresh_belts_for_building(move.building_id)
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
