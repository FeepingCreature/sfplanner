"""Base command infrastructure for undo/redo support.

Commands are a UI concern - they exist for undo/redo which is a user interaction concept.
Commands can directly update both the data model and the UI.

=== CRITICAL INVARIANT ===
Undo/redo must perfectly restore the exact same state every time. This means:

1. Commands are IMMUTABLE - all state (including generated IDs) is captured at construction
2. Execute and undo are DETERMINISTIC - same command always produces same result
3. No external state - commands don't read from the document during construction
4. Pre-generate all IDs - use caller-supplied UUIDs so redo recreates identical objects

This allows treating undo/redo as sliding along a timeline - users can undo/redo
as many times as they want and always return to the exact same state. A building
undone and redone has the same ID, same position, same everything.

=== Implementation Notes ===
- Commands receive Document at execute/undo time, not construction (avoids stale refs)
- Store scene_room_id to identify which Scene (Document or Room) to operate on
- Execute/undo log warnings if state is unexpected but remain idempotent
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, NamedTuple

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Document, Scene


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
        self._stack_changed_callback: Callable[[], None] | None = None

    def execute(self, cmd: Command) -> None:
        """Execute a command and add to undo stack."""
        cmd.execute(self.document)
        # Try to merge with previous
        if self.undo_stack:
            merged = self.undo_stack[-1].merge_with(cmd)
            if merged:
                self.undo_stack[-1] = merged
                self.redo_stack.clear()
                self._notify_stack_changed()
                return
        self.undo_stack.append(cmd)
        self.redo_stack.clear()
        self._notify_stack_changed()

    def undo(self) -> None:
        """Undo the last command."""
        if self.undo_stack:
            cmd = self.undo_stack.pop()
            cmd.undo(self.document)
            self.redo_stack.append(cmd)
            self._notify_stack_changed()

    def redo(self) -> None:
        """Redo the last undone command."""
        if self.redo_stack:
            cmd = self.redo_stack.pop()
            cmd.execute(self.document)
            self.undo_stack.append(cmd)
            self._notify_stack_changed()

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def _notify_stack_changed(self) -> None:
        """Notify that the stack changed (for updating UI state)."""
        if self._stack_changed_callback:
            self._stack_changed_callback()
