"""Graphics item for room ports - interactive belt connection points on room boundaries.

Extends BuildingItem with:
1. Edge snapping instead of grid snapping
2. External half-circle on room edge (for outside belt connections)
3. Belt drag initiation from external half-circle

The internal connector and building body are handled by BuildingItem.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core.models import Building, BuildingType, snap_port_to_room_edge
from satisfactory_planner.ui.items.building_item import BuildingItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem


class EdgeSide(Enum):
    """Which edge of the room the port is on."""

    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()


class RoomPortItem(BuildingItem):
    """Port on a room boundary - extends BuildingItem with edge snapping.

    Adds:
    - External half-circle on room edge (for belt connections from outside)
    - Edge snapping instead of grid snapping
    - Belt drag from external connector
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

        # Determine which edge this port is on based on position
        self._edge = self._determine_edge((building.x, building.y))

        # Set as child of room item for proper scene hierarchy
        self.setParentItem(room_item)

        # Position relative to parent RoomItem (re-set after parenting)
        self.setPos(building.x, building.y)

        # Z-value above room background but below regular buildings
        self.setZValue(0.5)

        # Drag target highlighting
        self._is_drag_target = False

    def _determine_edge(self, local_pos: tuple[float, float]) -> EdgeSide:
        """Determine which room edge this port is on."""
        x, y = local_pos
        room = self.room_item.room

        # Calculate distances to each edge
        dist_left = abs(x)
        dist_right = abs(x - room.width)
        dist_top = abs(y)
        dist_bottom = abs(y - room.height)

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

        if min_dist == dist_left:
            return EdgeSide.LEFT
        elif min_dist == dist_right:
            return EdgeSide.RIGHT
        elif min_dist == dist_top:
            return EdgeSide.TOP
        else:
            return EdgeSide.BOTTOM

    @property
    def port_index(self) -> int:
        """Get port index from the building model."""
        return self.building.port_index or 0

    @property
    def placement_id(self) -> str:
        """Get the room placement ID this port belongs to."""
        return self.room_item.placement.id

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Let BuildingItem paint the building - ports look like any other building."""
        super().paint(painter, option, widget)

    def set_drag_target(self, is_target: bool) -> None:
        """Set whether this port is being targeted for a belt connection."""
        self._is_drag_target = is_target
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press - start belt from external half-circle, or drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is near the external edge - start belt drag
            local_pos = event.pos()
            if self._is_on_external_edge(local_pos) and self.is_output:
                scene_pos = self.scenePos()
                self.canvas.start_belt_drag(self.building.id, self.port_index, scene_pos)
                event.accept()
                return
        # Let BuildingItem handle selection and drag
        super().mousePressEvent(event)

    def _is_on_external_edge(self, pos: QPointF) -> bool:
        """Check if position is on the external half-circle area."""
        if self._edge == EdgeSide.LEFT:
            return pos.x() < 0
        elif self._edge == EdgeSide.RIGHT:
            return pos.x() > 0
        elif self._edge == EdgeSide.TOP:
            return pos.y() < 0
        else:  # BOTTOM
            return pos.y() > 0

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes - snap to room edge instead of grid."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            if isinstance(new_pos, QPointF):
                # Snap to nearest room edge (not grid)
                new_pos = self._snap_to_edge(new_pos)
                return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Redetermine which edge we're on
            new_pos = self.pos()
            self._edge = self._determine_edge((new_pos.x(), new_pos.y()))
            self.update()
        # Let BuildingItem update model position and belts
        return super().itemChange(change, value)

    def _snap_to_edge(self, pos: QPointF) -> QPointF:
        """Snap a position to the nearest room edge using shared utility."""
        room = self.room_item.room
        x, y, _edge = snap_port_to_room_edge(
            self.building.building_type, room.width, room.height, pos.x(), pos.y()
        )
        return QPointF(x, y)
