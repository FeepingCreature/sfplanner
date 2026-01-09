"""Belt-related commands: connect, set tier."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from satisfactory_planner.ui.commands.base import Command, get_scene

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Document
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


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

        # Add belt item to the correct container (room or canvas)
        if self.scene_room_id:
            # Belt is inside a room - add to the RoomItem
            from satisfactory_planner.ui.items.room_item import RoomItem

            for room_item in self.canvas._room_items.values():
                if isinstance(room_item, RoomItem) and room_item.room.id == self.scene_room_id:
                    belt_item = room_item.add_belt_item(self.belt.id)
                    if belt_item:
                        self.canvas._belt_items[self.belt.id] = belt_item
                    break
        else:
            self.canvas.add_belt_item(self.belt)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        scene = get_scene(document, self.scene_room_id)
        if self.belt.id not in scene.belts:
            logger.warning(f"ConnectBeltCommand.undo: belt {self.belt.id} not found")
            return
        scene.remove_belt(self.belt.id)

        # Remove belt item from the correct container (room or canvas)
        if self.scene_room_id:
            from satisfactory_planner.ui.items.room_item import RoomItem

            for room_item in self.canvas._room_items.values():
                if isinstance(room_item, RoomItem) and room_item.room.id == self.scene_room_id:
                    room_item.remove_belt_item(self.belt.id)
                    break
        self.canvas.remove_belt_item(self.belt.id)
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
        self.canvas.refresh_belt(self.belt_id, self.scene_room_id)
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
        self.canvas.refresh_belt(self.belt_id, self.scene_room_id)
        self.canvas.notify_mutation()
