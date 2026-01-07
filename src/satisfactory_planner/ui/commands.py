"""Command pattern for undo/redo support.

Commands are a UI concern - they exist for undo/redo which is a user interaction concept.
Commands can directly update both the data model and the UI.

Commands are immutable - all state needed for execute/undo is captured at construction.
Execute and undo are idempotent - calling them multiple times logs a warning but doesn't break.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Building, Document
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
    """Base class for undoable commands."""

    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        ...

    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        ...

    def merge_with(self, other: Command) -> Command | None:
        """Optionally merge with another command. Return merged command or None."""
        return None


class CommandStack:
    """Stack of commands for undo/redo."""

    def __init__(self) -> None:
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []

    def execute(self, cmd: Command) -> None:
        """Execute a command and add to undo stack."""
        cmd.execute()
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
            cmd.undo()
            self.redo_stack.append(cmd)

    def redo(self) -> None:
        """Redo the last undone command."""
        if self.redo_stack:
            cmd = self.redo_stack.pop()
            cmd.execute()
            self.undo_stack.append(cmd)

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0


@dataclass(frozen=True)
class PlaceBuildingCommand(Command):
    """Command to place a building."""

    document: Document
    building: Building
    canvas: FactoryCanvas

    def execute(self) -> None:
        if self.building.id in self.document.buildings:
            logger.warning(
                f"PlaceBuildingCommand.execute: building {self.building.id} already exists"
            )
            return
        self.document.add_building(self.building)
        self.canvas.add_building_item(self.building)
        self.canvas.notify_mutation()

    def undo(self) -> None:
        if self.building.id not in self.document.buildings:
            logger.warning(f"PlaceBuildingCommand.undo: building {self.building.id} not found")
            return
        self.document.remove_building(self.building.id)
        self.canvas.remove_building_item(self.building.id)
        self.canvas.notify_mutation()


@dataclass(frozen=True)
class DeleteItemsCommand(Command):
    """Command to delete buildings and belts.

    Buildings and belts to delete are captured at construction time.
    """

    document: Document
    buildings: tuple[Building, ...]
    belts: tuple[Belt, ...]
    canvas: FactoryCanvas

    def execute(self) -> None:
        any_deleted = False
        for building in self.buildings:
            if building.id not in self.document.buildings:
                logger.warning(f"DeleteItemsCommand.execute: building {building.id} not found")
                continue
            self.document.remove_building(building.id)
            self.canvas.remove_building_item(building.id)
            any_deleted = True

        for belt in self.belts:
            if belt.id not in self.document.belts:
                logger.warning(f"DeleteItemsCommand.execute: belt {belt.id} not found")
                continue
            self.document.remove_belt(belt.id)
            self.canvas.remove_belt_item(belt.id)
            any_deleted = True

        if any_deleted:
            self.canvas.notify_mutation()

    def undo(self) -> None:
        any_restored = False
        for building in self.buildings:
            if building.id in self.document.buildings:
                logger.warning(f"DeleteItemsCommand.undo: building {building.id} already exists")
                continue
            self.document.add_building(building)
            self.canvas.add_building_item(building)
            any_restored = True

        for belt in self.belts:
            if belt.id in self.document.belts:
                logger.warning(f"DeleteItemsCommand.undo: belt {belt.id} already exists")
                continue
            self.document.add_belt(belt)
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

    document: Document
    canvas: FactoryCanvas
    moves: tuple[BuildingMove, ...]

    def execute(self) -> None:
        any_changed = False
        for move in self.moves:
            building = self.document.buildings.get(move.building_id)
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

    def undo(self) -> None:
        any_changed = False
        for move in self.moves:
            building = self.document.buildings.get(move.building_id)
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
            document=self.document,
            canvas=self.canvas,
            moves=merged_moves,
        )


@dataclass(frozen=True)
class ConnectBeltCommand(Command):
    """Command to connect a belt between buildings."""

    document: Document
    belt: Belt
    canvas: FactoryCanvas

    def execute(self) -> None:
        if self.belt.id in self.document.belts:
            logger.warning(f"ConnectBeltCommand.execute: belt {self.belt.id} already exists")
            return
        self.document.add_belt(self.belt)
        self.canvas.add_belt_item(self.belt)
        self.canvas.notify_mutation()

    def undo(self) -> None:
        if self.belt.id not in self.document.belts:
            logger.warning(f"ConnectBeltCommand.undo: belt {self.belt.id} not found")
            return
        self.document.remove_belt(self.belt.id)
        self.canvas.remove_belt_item(self.belt.id)
        self.canvas.notify_mutation()


# NOTE: If more property-change commands are added (e.g., belt item_id),
# consider refactoring to a generic ChangePropertyCommand pattern.


@dataclass(frozen=True)
class SetRecipeCommand(Command):
    """Command to set a building's recipe."""

    document: Document
    building_id: str
    old_recipe_id: str | None
    new_recipe_id: str | None
    canvas: FactoryCanvas

    def execute(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if not building:
            logger.warning(f"SetRecipeCommand.execute: building {self.building_id} not found")
            return
        if building.recipe_id == self.new_recipe_id:
            logger.warning(f"SetRecipeCommand.execute: recipe already set to {self.new_recipe_id}")
            return
        building.recipe_id = self.new_recipe_id
        self.canvas.refresh_building(self.building_id)
        self.canvas.notify_mutation()

    def undo(self) -> None:
        building = self.document.buildings.get(self.building_id)
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

    document: Document
    building_id: str
    old_clock_speed: float
    new_clock_speed: float
    canvas: FactoryCanvas

    def execute(self) -> None:
        building = self.document.buildings.get(self.building_id)
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

    def undo(self) -> None:
        building = self.document.buildings.get(self.building_id)
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
class SetBeltTierCommand(Command):
    """Command to set a belt's tier."""

    document: Document
    belt_id: str
    old_tier: int
    new_tier: int
    canvas: FactoryCanvas

    def execute(self) -> None:
        belt = self.document.belts.get(self.belt_id)
        if not belt:
            logger.warning(f"SetBeltTierCommand.execute: belt {self.belt_id} not found")
            return
        if belt.tier == self.new_tier:
            logger.warning(f"SetBeltTierCommand.execute: tier already set to {self.new_tier}")
            return
        belt.tier = self.new_tier
        self.canvas.refresh_belt(self.belt_id)
        self.canvas.notify_mutation()

    def undo(self) -> None:
        belt = self.document.belts.get(self.belt_id)
        if not belt:
            logger.warning(f"SetBeltTierCommand.undo: belt {self.belt_id} not found")
            return
        if belt.tier == self.old_tier:
            logger.warning(f"SetBeltTierCommand.undo: tier already set to {self.old_tier}")
            return
        belt.tier = self.old_tier
        self.canvas.refresh_belt(self.belt_id)
        self.canvas.notify_mutation()
