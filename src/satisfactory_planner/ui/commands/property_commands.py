"""Building property commands: recipe, clock speed."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from satisfactory_planner.ui.commands.base import Command, get_scene

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Document, ItemId, RecipeId
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetRecipeCommand(Command):
    """Command to set a building's recipe."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_recipe_id: RecipeId | None
    new_recipe_id: RecipeId | None
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
class SetItemCommand(Command):
    """Command to set a building's item_id (for Source/Sink/Miner)."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_item_id: ItemId | None
    new_item_id: ItemId | None
    canvas: FactoryCanvas

    def execute(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetItemCommand.execute: building {self.building_id} not found")
            return
        if building.item_id == self.new_item_id:
            logger.warning(f"SetItemCommand.execute: item_id already set to {self.new_item_id}")
            return
        building.item_id = self.new_item_id
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetItemCommand.undo: building {self.building_id} not found")
            return
        if building.item_id == self.old_item_id:
            logger.warning(f"SetItemCommand.undo: item_id already set to {self.old_item_id}")
            return
        building.item_id = self.old_item_id
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


@dataclass(frozen=True)
class SetMinerTierCommand(Command):
    """Command to set a miner's tier (Mk.1/2/3)."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_tier: int
    new_tier: int
    canvas: FactoryCanvas

    def _set_tier(self, document: Document, tier: int) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetMinerTierCommand: building {self.building_id} not found")
            return
        building.tier = tier
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()

    def execute(self, document: Document) -> None:
        self._set_tier(document, self.new_tier)

    def undo(self, document: Document) -> None:
        self._set_tier(document, self.old_tier)


@dataclass(frozen=True)
class SetMinerPurityCommand(Command):
    """Command to set a miner's resource node purity."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_purity: str
    new_purity: str
    canvas: FactoryCanvas

    def _set_purity(self, document: Document, purity: str) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetMinerPurityCommand: building {self.building_id} not found")
            return
        building.purity = purity
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()

    def execute(self, document: Document) -> None:
        self._set_purity(document, self.new_purity)

    def undo(self, document: Document) -> None:
        self._set_purity(document, self.old_purity)


@dataclass(frozen=True)
class SetRateLimitsCommand(Command):
    """Command to set a Source/Sink's min/max rate thresholds."""

    scene_room_id: str | None  # None = root document, else room ID
    building_id: str
    old_min_rate: float | None
    old_max_rate: float | None
    new_min_rate: float | None
    new_max_rate: float | None
    canvas: FactoryCanvas

    def _set_rates(
        self, document: Document, min_rate: float | None, max_rate: float | None
    ) -> None:
        scene = get_scene(document, self.scene_room_id)
        building = scene.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetRateLimitsCommand: building {self.building_id} not found")
            return
        building.min_rate = min_rate
        building.max_rate = max_rate
        self.canvas.notify_mutation()

    def execute(self, document: Document) -> None:
        self._set_rates(document, self.new_min_rate, self.new_max_rate)

    def undo(self, document: Document) -> None:
        self._set_rates(document, self.old_min_rate, self.old_max_rate)


@dataclass(frozen=True)
class RenameRoomCommand(Command):
    """Command to rename a room (affects all linked placements)."""

    room_id: str
    old_name: str
    new_name: str
    canvas: FactoryCanvas

    def _set_name(self, document: Document, name: str) -> None:
        room = next((r for r in document.get_all_rooms() if r.id == self.room_id), None)
        if not room:
            logger.warning(f"RenameRoomCommand: room {self.room_id} not found")
            return
        room.name = name
        # Repaint every RoomItem showing this room (all linked placements)
        for room_item in self.canvas._sync.iter_room_items_for_room(self.room_id):
            room_item.update()
        self.canvas.notify_mutation()

    def execute(self, document: Document) -> None:
        self._set_name(document, self.new_name)

    def undo(self, document: Document) -> None:
        self._set_name(document, self.old_name)
