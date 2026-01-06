"""Command pattern for undo/redo support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Building, Document


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


@dataclass
class PlaceBuildingCommand(Command):
    """Command to place a building."""

    document: Document
    building: Building

    def execute(self) -> None:
        self.document.add_building(self.building)

    def undo(self) -> None:
        self.document.remove_building(self.building.id)


@dataclass
class DeleteItemsCommand(Command):
    """Command to delete buildings and belts."""

    document: Document
    building_ids: list[str]
    belt_ids: list[str]
    _deleted_buildings: list[Building] | None = None
    _deleted_belts: list[Belt] | None = None

    def execute(self) -> None:
        from satisfactory_planner.core.models import Belt, Building

        self._deleted_buildings = []
        self._deleted_belts = []

        for bid in self.building_ids:
            building = self.document.remove_building(bid)
            if building:
                self._deleted_buildings.append(building)

        for bid in self.belt_ids:
            belt = self.document.remove_belt(bid)
            if belt:
                self._deleted_belts.append(belt)

    def undo(self) -> None:
        if self._deleted_buildings:
            for building in self._deleted_buildings:
                self.document.add_building(building)
        if self._deleted_belts:
            for belt in self._deleted_belts:
                self.document.add_belt(belt)


@dataclass
class MoveBuildingsCommand(Command):
    """Command to move buildings."""

    document: Document
    building_ids: list[str]
    dx: float
    dy: float
    already_applied: bool = False  # If True, execute() won't apply the delta again

    def execute(self) -> None:
        if self.already_applied:
            # Model already updated by UI - just mark as not already applied for redo
            self.already_applied = False
            return
        for bid in self.building_ids:
            if bid in self.document.buildings:
                self.document.buildings[bid].x += self.dx
                self.document.buildings[bid].y += self.dy

    def undo(self) -> None:
        for bid in self.building_ids:
            if bid in self.document.buildings:
                self.document.buildings[bid].x -= self.dx
                self.document.buildings[bid].y -= self.dy

    def merge_with(self, other: Command) -> Command | None:
        """Merge consecutive move commands for same buildings."""
        if isinstance(other, MoveBuildingsCommand):
            if set(self.building_ids) == set(other.building_ids):
                return MoveBuildingsCommand(
                    document=self.document,
                    building_ids=self.building_ids,
                    dx=self.dx + other.dx,
                    dy=self.dy + other.dy,
                    already_applied=False,  # Merged command hasn't been applied
                )
        return None


@dataclass
class ConnectBeltCommand(Command):
    """Command to connect a belt between buildings."""

    document: Document
    belt: Belt

    def execute(self) -> None:
        self.document.add_belt(self.belt)

    def undo(self) -> None:
        self.document.remove_belt(self.belt.id)


@dataclass
class SetRecipeCommand(Command):
    """Command to set a building's recipe."""

    document: Document
    building_id: str
    new_recipe_id: str | None
    _old_recipe_id: str | None = None

    def execute(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            self._old_recipe_id = building.recipe_id
            building.recipe_id = self.new_recipe_id

    def undo(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            building.recipe_id = self._old_recipe_id


@dataclass
class SetClockSpeedCommand(Command):
    """Command to set a building's clock speed."""

    document: Document
    building_id: str
    new_clock_speed: float
    _old_clock_speed: float = 1.0

    def execute(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            self._old_clock_speed = building.clock_speed
            building.clock_speed = self.new_clock_speed

    def undo(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            building.clock_speed = self._old_clock_speed
