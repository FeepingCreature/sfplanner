"""Clipboard manager for the factory canvas.

Handles copy/paste operations for buildings, belts, and room placements.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF

from satisfactory_planner.core import Belt, Building
from satisfactory_planner.core.models import generate_id
from satisfactory_planner.ui.commands import ConnectBeltCommand, PlaceBuildingCommand

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas


class ClipboardManager:
    """Manages clipboard operations for the canvas."""

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._clipboard_buildings: list[Building] = []
        self._clipboard_belts: list[Belt] = []
        self._clipboard_room_ids: list[str] = []

    def copy_selection(self) -> None:
        """Copy selected items to clipboard."""
        from satisfactory_planner.ui.items.building_item import BuildingItem
        from satisfactory_planner.ui.items.room_item import RoomItem

        self._clipboard_buildings.clear()
        self._clipboard_belts.clear()
        self._clipboard_room_ids.clear()

        selected_building_ids: set[str] = set()
        for item in self.canvas._scene.selectedItems():
            if isinstance(item, BuildingItem):
                self._clipboard_buildings.append(copy.deepcopy(item.building))
                selected_building_ids.add(item.building.id)
            elif isinstance(item, RoomItem):
                self._clipboard_room_ids.append(item.room.id)

        for belt in self.canvas.document.belts.values():
            if (
                belt.source_building_id in selected_building_ids
                and belt.dest_building_id in selected_building_ids
            ):
                self._clipboard_belts.append(copy.deepcopy(belt))

    def paste(self) -> None:
        """Paste from clipboard."""
        if not self._clipboard_buildings and not self._clipboard_room_ids:
            return

        offset = 50.0
        new_item_ids: list[str] = []

        if self._clipboard_buildings:
            id_map: dict[str, str] = {}
            scene_room_id: str | None = None

            for old_building in self._clipboard_buildings:
                new_id = generate_id()
                id_map[old_building.id] = new_id
                # Deep-copy so ALL fields are preserved (item_id, tier, min_rate,
                # max_rate, port_index, ...), then reassign identity and position.
                new_building = copy.deepcopy(old_building)
                new_building.id = new_id
                new_building.x = old_building.x + offset
                new_building.y = old_building.y + offset
                # Check if pasting into a room - convert to room-local coordinates
                paste_pos = QPointF(new_building.x, new_building.y)
                placement = self.canvas.get_room_placement_at_point(paste_pos)
                if placement:
                    new_building.x = new_building.x - placement.x
                    new_building.y = new_building.y - placement.y
                    scene_room_id = placement.room_id
                else:
                    scene_room_id = None
                cmd = PlaceBuildingCommand(
                    scene_room_id=scene_room_id, building=new_building, canvas=self.canvas
                )
                self.canvas.command_stack.execute(cmd)
                new_item_ids.append(new_id)

            for old_belt in self._clipboard_belts:
                new_source = id_map.get(old_belt.source_building_id)
                new_dest = id_map.get(old_belt.dest_building_id)
                if new_source and new_dest:
                    new_belt = Belt(
                        id=generate_id(),
                        tier=old_belt.tier,
                        source_building_id=new_source,
                        source_port_index=old_belt.source_port_index,
                        dest_building_id=new_dest,
                        dest_port_index=old_belt.dest_port_index,
                    )
                    belt_cmd = ConnectBeltCommand(
                        scene_room_id=scene_room_id, belt=new_belt, canvas=self.canvas
                    )
                    self.canvas.command_stack.execute(belt_cmd)

        for room_id in self._clipboard_room_ids:
            room = self.canvas.document.rooms.get(room_id)
            if not room:
                continue

            existing = self.canvas.document.get_placements_for_room(room_id)
            if existing:
                base_x, base_y = existing[0].x + offset, existing[0].y + offset
            else:
                base_x, base_y = offset, offset

            # Use PlaceBlueprintCommand for proper undo/redo support
            from satisfactory_planner.ui.commands.room_commands import PlaceBlueprintCommand

            room_cmd = PlaceBlueprintCommand.create(
                source_room=room,
                x=base_x,
                y=base_y,
                canvas=self.canvas,
                document=self.canvas.document,
            )
            self.canvas.command_stack.execute(room_cmd)
            new_item_ids.append(room_cmd.created_placement_id)

        self.canvas.notify_mutation()

        # Select newly pasted items
        self._select_items(new_item_ids)

    def _select_items(self, item_ids: list[str]) -> None:
        """Select items by their IDs."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        self.canvas._scene.clearSelection()
        for new_id in item_ids:
            item = self.canvas._building_items.get(new_id)
            if item:
                item.setSelected(True)
            room_item = self.canvas._room_items.get(new_id)
            if room_item and isinstance(room_item, RoomItem):
                room_item.setSelected(True)
        self.canvas._emit_selection_changed()

    @property
    def has_content(self) -> bool:
        """Check if clipboard has any content."""
        return bool(self._clipboard_buildings or self._clipboard_room_ids)
