"""Graphics item for room ports - PORT buildings that sit on room edges.

Extends BuildingItem with:
1. Edge snapping instead of grid snapping
2. Auto-rotation based on edge (top/bottom = 90°, left/right = 0°)
3. Notifies RoomItem to redraw its edge ports when moved

The internal connector and building body are handled by BuildingItem.
The external port half-circles are drawn by RoomItem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)

from satisfactory_planner.core.models import Building, BuildingType, snap_port_to_room_edge
from satisfactory_planner.ui.items.building_item import BuildingItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem


class RoomPortItem(BuildingItem):
    """PORT building on a room boundary - extends BuildingItem with edge snapping.

    Adds:
    - Edge snapping instead of grid snapping
    - Auto-rotation based on edge position
    - Notifies RoomItem when moved so it can redraw edge ports
    """

    def __init__(
        self,
        room_item: RoomItem,
        building: Building,
        canvas: FactoryCanvas,
    ) -> None:
        # Initialize BuildingItem with the PORT building
        super().__init__(building, canvas, scene=room_item.room)

        self.room_item = room_item
        self.is_output = building.building_type == BuildingType.PORT_OUT

        # Set as child of room item for proper scene hierarchy
        self.setParentItem(room_item)

        # Position relative to parent RoomItem (re-set after parenting)
        self.setPos(building.x, building.y)

        # Z-value above room background but below regular buildings
        self.setZValue(0.5)

        # Drag target highlighting
        self._is_drag_target = False

    @property
    def port_index(self) -> int:
        """Get port index from the building model."""
        return self.building.port_index or 0

    @property
    def placement_id(self) -> str:
        """Get the room placement ID this port belongs to."""
        return self.room_item.placement.id

    def set_drag_target(self, is_target: bool) -> None:
        """Set whether this port is being targeted for a belt connection."""
        self._is_drag_target = is_target
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press - start belt from output port, or drag."""
        if event.button() == Qt.MouseButton.LeftButton and self.is_output:
            # Start belt drag from output port
            scene_pos = self.scenePos()
            self.canvas.start_belt_drag(self.building.id, self.port_index, scene_pos)
            event.accept()
            return
        # Let BuildingItem handle selection and drag
        super().mousePressEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes - snap to room edge instead of grid."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            if isinstance(new_pos, QPointF):
                # Snap to nearest room edge and get rotation
                new_pos, rotation = self._snap_to_edge_with_rotation(new_pos)
                # Update rotation if needed
                if self.building.rotation != rotation:
                    self.building.rotation = rotation
                    self._update_port_positions()
                    self.update()
                return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update()
            # Notify room to redraw its edge ports
            self.room_item.update_room_ports()
        # Let BuildingItem update model position and belts
        return super().itemChange(change, value)

    def rotate(self, delta: int) -> None:
        """Override to prevent manual rotation - ports auto-rotate based on edge."""
        pass

    def _snap_to_edge_with_rotation(self, pos: QPointF) -> tuple[QPointF, int]:
        """Snap to nearest room edge and return position + rotation.

        Rotation orients the PORT so its connector faces INTO the room:
        - Left edge: 0° (port faces right, into room)
        - Right edge: 180° (port faces left, into room)
        - Top edge: 90° (port faces down, into room)
        - Bottom edge: 270° (port faces up, into room)
        """
        room = self.room_item.room
        x, y, edge = snap_port_to_room_edge(
            self.building.building_type, room.width, room.height, pos.x(), pos.y()
        )
        # Rotate so port connector faces into the room
        edge_rotations = {
            "left": 0,
            "right": 180,
            "top": 90,
            "bottom": 270,
        }
        rotation = edge_rotations.get(edge, 0)
        return QPointF(x, y), rotation
