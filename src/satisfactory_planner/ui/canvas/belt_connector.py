"""Belt connection manager for the factory canvas."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from satisfactory_planner.core import Belt
from satisfactory_planner.core.models import generate_id
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.commands import ConnectBeltCommand
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas
    from satisfactory_planner.ui.items.port_item import PortItem
    from satisfactory_planner.ui.items.room_port_item import RoomPortItem


class BeltConnector:
    """Manages belt connection dragging and creation.

    Handles the drag preview, port hover highlighting, and connection completion.
    """

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._is_connecting = False
        self._connect_start_building: str | None = None
        self._connect_start_port: int = 0
        self._drag_preview: QGraphicsPathItem | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_start_dir: float = 0
        self._hover_target_port: PortItem | RoomPortItem | None = None

    @property
    def is_connecting(self) -> bool:
        """Return whether a belt connection is in progress."""
        return self._is_connecting

    def start_drag(self, building_id: str, port_index: int, start_pos: QPointF) -> None:
        """Start dragging a belt connection from an output port.

        The building_id can be either a Building ID or a RoomPlacement ID.
        If the port already has a belt, delete it first (implicit replacement).
        """
        # Check if output port is already connected - if so, delete existing belt
        existing_belt = self.canvas.document.get_belt_at_port(building_id, port_index, True)
        if existing_belt:
            from satisfactory_planner.ui.commands import DeleteItemsCommand

            cmd = DeleteItemsCommand(
                scene_room_id=None,
                buildings=(),
                belts=(existing_belt,),
                canvas=self.canvas,
            )
            self.canvas.command_stack.execute(cmd)

        self._is_connecting = True
        self._connect_start_building = building_id
        self._connect_start_port = port_index
        self._drag_start_pos = start_pos
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

        # Get start direction from the source (building or room placement)
        building = self.canvas.document.buildings.get(building_id)
        if building:
            self._drag_start_dir = building.output_port_direction(port_index)
        else:
            # Check if it's a room placement
            placement = self.canvas.document.room_placements.get(building_id)
            if placement:
                self._drag_start_dir = placement.output_port_direction(
                    port_index, self.canvas.document
                )
            else:
                self._drag_start_dir = 0

        # Create preview path
        self._drag_preview = QGraphicsPathItem()
        self._drag_preview.setPen(QPen(QColor(100, 200, 100, 180), 3, Qt.PenStyle.DashLine))
        self._drag_preview.setZValue(1000)
        self._drag_preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._drag_preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.canvas._scene.addItem(self._drag_preview)

    def update_preview(self, end_pos: QPointF) -> None:
        """Update the drag preview path to the given end position."""
        if not self._drag_preview or not self._drag_start_pos:
            return

        start = Point(self._drag_start_pos.x(), self._drag_start_pos.y())
        end = Point(end_pos.x(), end_pos.y())

        # Default end direction: toward end point
        dx = end_pos.x() - self._drag_start_pos.x()
        dy = end_pos.y() - self._drag_start_pos.y()
        end_dir = math.atan2(dy, dx)

        belt_path = compute_belt_path(start, self._drag_start_dir, end, end_dir)
        path = belt_path_to_painter_path(start, end, belt_path)
        self._drag_preview.setPath(path)

    def update_hover_target(self, scene_pos: QPointF) -> None:
        """Check if hovering over a valid input port and update highlight."""
        from satisfactory_planner.ui.items.port_item import PortItem
        from satisfactory_planner.ui.items.room_port_item import RoomPortItem

        new_target: PortItem | RoomPortItem | None = None
        for item in self.canvas._scene.items(scene_pos):
            # Check for building port
            if isinstance(item, PortItem) and not item.is_output:
                new_target = item
                break
            # Check for room port
            if isinstance(item, RoomPortItem) and not item.is_output:
                new_target = item
                break

        if new_target != self._hover_target_port:
            if self._hover_target_port:
                self._hover_target_port.set_drag_target(False)
            if new_target:
                new_target.set_drag_target(True)
            self._hover_target_port = new_target

    def try_complete(self, scene_pos: QPointF) -> bool:
        """Try to complete the connection at the given position.

        Returns True if connection was completed or cancelled, False if still dragging.
        """
        if not self._is_connecting:
            return False

        from satisfactory_planner.ui.items.port_item import PortItem
        from satisfactory_planner.ui.items.room_port_item import RoomPortItem

        # Find input port at position
        for item in self.canvas._scene.items(scene_pos):
            # Check for building port
            if isinstance(item, PortItem) and not item.is_output:
                # Check if port already connected
                if self.canvas.document.is_port_connected(item.building_id, item.port_index, False):
                    self.cancel()
                    return True
                self.complete(item.building_id, item.port_index)
                return True
            # Check for room port
            if isinstance(item, RoomPortItem) and not item.is_output:
                # Check if port already connected (using placement_id as building_id)
                if self.canvas.document.is_port_connected(
                    item.placement_id, item.port_index, False
                ):
                    self.cancel()
                    return True
                self.complete(item.placement_id, item.port_index)
                return True

        # No valid port - cancel
        self.cancel()
        return True

    def complete(self, dest_building_id: str, dest_port_index: int) -> None:
        """Complete a belt connection to an input port."""
        if self._is_connecting and self._connect_start_building:
            # Get belt tier from toolbar (1-indexed from combo box)
            tier = 1
            main_window = self.canvas.window()
            if hasattr(main_window, 'belt_tier_combo'):
                tier = main_window.belt_tier_combo.currentIndex() + 1
            
            belt = Belt(
                id=generate_id(),
                tier=tier,
                source_building_id=self._connect_start_building,
                source_port_index=self._connect_start_port,
                dest_building_id=dest_building_id,
                dest_port_index=dest_port_index,
            )
            source_item = self.canvas._building_items.get(self._connect_start_building)
            scene_room_id = self.canvas.get_scene_for_item(source_item) if source_item else None
            cmd = ConnectBeltCommand(scene_room_id=scene_room_id, belt=belt, canvas=self.canvas)
            self.canvas.command_stack.execute(cmd)

        self._cleanup()

    def cancel(self) -> None:
        """Cancel the current belt connection."""
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up drag state."""
        self._is_connecting = False
        self._connect_start_building = None
        self._drag_start_pos = None
        if self._drag_preview:
            self.canvas._scene.removeItem(self._drag_preview)
            self._drag_preview = None
        if self._hover_target_port:
            self._hover_target_port.set_drag_target(False)
            self._hover_target_port = None
        self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
