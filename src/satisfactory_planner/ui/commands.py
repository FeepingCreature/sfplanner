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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Building, Document
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


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
    """Command to move buildings.

    Stores original and new positions for idempotent execute/undo.
    """

    document: Document
    canvas: FactoryCanvas
    # Maps building_id -> (old_x, old_y, new_x, new_y)
    positions: tuple[tuple[str, float, float, float, float], ...]

    def execute(self) -> None:
        any_moved = False
        for building_id, _old_x, _old_y, new_x, new_y in self.positions:
            building = self.document.buildings.get(building_id)
            if not building:
                logger.warning(f"MoveBuildingsCommand.execute: building {building_id} not found")
                continue
            if building.x == new_x and building.y == new_y:
                logger.warning(
                    f"MoveBuildingsCommand.execute: building {building_id} already at target"
                )
                continue
            building.x = new_x
            building.y = new_y
            self.canvas.refresh_building(building_id)
            self.canvas.refresh_belts_for_building(building_id)
            any_moved = True
        if any_moved:
            self.canvas.notify_mutation()

    def undo(self) -> None:
        any_moved = False
        for building_id, old_x, old_y, _new_x, _new_y in self.positions:
            building = self.document.buildings.get(building_id)
            if not building:
                logger.warning(f"MoveBuildingsCommand.undo: building {building_id} not found")
                continue
            if building.x == old_x and building.y == old_y:
                logger.warning(
                    f"MoveBuildingsCommand.undo: building {building_id} already at original"
                )
                continue
            building.x = old_x
            building.y = old_y
            self.canvas.refresh_building(building_id)
            self.canvas.refresh_belts_for_building(building_id)
            any_moved = True
        if any_moved:
            self.canvas.notify_mutation()

    def merge_with(self, other: Command) -> Command | None:
        """Merge consecutive move commands for same buildings."""
        if not isinstance(other, MoveBuildingsCommand):
            return None

        self_ids = {p[0] for p in self.positions}
        other_ids = {p[0] for p in other.positions}
        if self_ids != other_ids:
            return None

        # Merge: keep our old positions, use their new positions
        other_new = {p[0]: (p[3], p[4]) for p in other.positions}
        merged_positions = tuple(
            (bid, old_x, old_y, other_new[bid][0], other_new[bid][1])
            for bid, old_x, old_y, new_x, new_y in self.positions
        )
        return MoveBuildingsCommand(
            document=self.document,
            canvas=self.canvas,
            positions=merged_positions,
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
