"""Command pattern for undo/redo support.

Commands are a UI concern - they exist for undo/redo which is a user interaction concept.
Commands can directly update both the data model and the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Building, Document


class CommandHandler(Protocol):
    """Interface for handling command side effects.
    
    Implemented by FactoryCanvas to receive UI update calls from commands.
    """
    
    def add_building_item(self, building: "Building") -> None:
        """Add a building item to the scene."""
        ...
    
    def remove_building_item(self, building_id: str) -> None:
        """Remove a building item from the scene."""
        ...
    
    def add_belt_item(self, belt: "Belt") -> None:
        """Add a belt item to the scene."""
        ...
    
    def remove_belt_item(self, belt_id: str) -> None:
        """Remove a belt item from the scene."""
        ...
    
    def refresh_building(self, building_id: str) -> None:
        """Refresh a building's visual state."""
        ...
    
    def refresh_belts_for_building(self, building_id: str) -> None:
        """Refresh belts connected to a building."""
        ...
    
    def notify_mutation(self) -> None:
        """Notify that the document was mutated (for warnings, dirty flag, etc)."""
        ...


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
    handler: CommandHandler | None = None

    def execute(self) -> None:
        self.document.add_building(self.building)
        if self.handler:
            self.handler.add_building_item(self.building)
            self.handler.notify_mutation()

    def undo(self) -> None:
        self.document.remove_building(self.building.id)
        if self.handler:
            self.handler.remove_building_item(self.building.id)
            self.handler.notify_mutation()


@dataclass
class DeleteItemsCommand(Command):
    """Command to delete buildings and belts."""

    document: Document
    building_ids: list[str]
    belt_ids: list[str]
    handler: CommandHandler | None = None
    _deleted_buildings: list[Building] | None = field(default=None, repr=False)
    _deleted_belts: list[Belt] | None = field(default=None, repr=False)

    def execute(self) -> None:
        from satisfactory_planner.core.models import Belt, Building

        self._deleted_buildings = []
        self._deleted_belts = []

        for bid in self.building_ids:
            building = self.document.remove_building(bid)
            if building:
                self._deleted_buildings.append(building)
                if self.handler:
                    self.handler.remove_building_item(bid)

        for bid in self.belt_ids:
            belt = self.document.remove_belt(bid)
            if belt:
                self._deleted_belts.append(belt)
                if self.handler:
                    self.handler.remove_belt_item(bid)

        if self.handler:
            self.handler.notify_mutation()

    def undo(self) -> None:
        if self._deleted_buildings:
            for building in self._deleted_buildings:
                self.document.add_building(building)
                if self.handler:
                    self.handler.add_building_item(building)
        if self._deleted_belts:
            for belt in self._deleted_belts:
                self.document.add_belt(belt)
                if self.handler:
                    self.handler.add_belt_item(belt)
        if self.handler:
            self.handler.notify_mutation()


@dataclass
class MoveBuildingsCommand(Command):
    """Command to move buildings."""

    document: Document
    building_ids: list[str]
    dx: float
    dy: float
    handler: CommandHandler | None = None
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
                if self.handler:
                    self.handler.refresh_building(bid)
                    self.handler.refresh_belts_for_building(bid)
        if self.handler:
            self.handler.notify_mutation()

    def undo(self) -> None:
        for bid in self.building_ids:
            if bid in self.document.buildings:
                self.document.buildings[bid].x -= self.dx
                self.document.buildings[bid].y -= self.dy
                if self.handler:
                    self.handler.refresh_building(bid)
                    self.handler.refresh_belts_for_building(bid)
        if self.handler:
            self.handler.notify_mutation()

    def merge_with(self, other: Command) -> Command | None:
        """Merge consecutive move commands for same buildings."""
        if isinstance(other, MoveBuildingsCommand):
            if set(self.building_ids) == set(other.building_ids):
                return MoveBuildingsCommand(
                    document=self.document,
                    building_ids=self.building_ids,
                    dx=self.dx + other.dx,
                    dy=self.dy + other.dy,
                    handler=self.handler,
                    already_applied=False,  # Merged command hasn't been applied
                )
        return None


@dataclass
class ConnectBeltCommand(Command):
    """Command to connect a belt between buildings."""

    document: Document
    belt: Belt
    handler: CommandHandler | None = None

    def execute(self) -> None:
        self.document.add_belt(self.belt)
        if self.handler:
            self.handler.add_belt_item(self.belt)
            self.handler.notify_mutation()

    def undo(self) -> None:
        self.document.remove_belt(self.belt.id)
        if self.handler:
            self.handler.remove_belt_item(self.belt.id)
            self.handler.notify_mutation()


@dataclass
class SetRecipeCommand(Command):
    """Command to set a building's recipe."""

    document: Document
    building_id: str
    new_recipe_id: str | None
    handler: CommandHandler | None = None
    _old_recipe_id: str | None = field(default=None, repr=False)

    def execute(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            self._old_recipe_id = building.recipe_id
            building.recipe_id = self.new_recipe_id
            if self.handler:
                self.handler.refresh_building(self.building_id)
                self.handler.notify_mutation()

    def undo(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            building.recipe_id = self._old_recipe_id
            if self.handler:
                self.handler.refresh_building(self.building_id)
                self.handler.notify_mutation()


@dataclass
class SetClockSpeedCommand(Command):
    """Command to set a building's clock speed."""

    document: Document
    building_id: str
    new_clock_speed: float
    handler: CommandHandler | None = None
    _old_clock_speed: float = field(default=1.0, repr=False)

    def execute(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            self._old_clock_speed = building.clock_speed
            building.clock_speed = self.new_clock_speed
            if self.handler:
                self.handler.refresh_building(self.building_id)
                self.handler.notify_mutation()

    def undo(self) -> None:
        building = self.document.buildings.get(self.building_id)
        if building:
            building.clock_speed = self._old_clock_speed
            if self.handler:
                self.handler.refresh_building(self.building_id)
                self.handler.notify_mutation()
