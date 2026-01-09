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
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core.models import Building, BuildingType
from satisfactory_planner.ui.items.building_item import BuildingItem
from satisfactory_planner.ui.items.port_item import (
    INPUT_COLOR,
    OUTPUT_COLOR,
    PORT_RADIUS,
    draw_half_circle_path,
)

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
        """Paint external half-circle, then let BuildingItem paint the rest."""
        # Draw external half-circle on room edge first
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR
        self._draw_external_half_circle(painter, color)

        # Let BuildingItem paint the building body and internal ports
        super().paint(painter, option, widget)

    def set_drag_target(self, is_target: bool) -> None:
        """Set whether this port is being targeted for a belt connection."""
        self._is_drag_target = is_target
        self.update()

    def _draw_external_half_circle(self, painter: QPainter, color: QColor) -> None:
        """Draw the external half-circle on the room edge."""
        if hasattr(self, "_is_drag_target") and self._is_drag_target:
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            painter.setBrush(QBrush(color.lighter(130)))
        else:
            painter.setPen(QPen(color.darker(120), 2))
            painter.setBrush(QBrush(color))

        w, h = self._get_display_size()

        # External half-circle faces AWAY from room, positioned on the edge-facing side
        # For PORT_IN on left edge: external circle is on LEFT side of building (x=0)
        # For PORT_OUT on right edge: external circle is on RIGHT side of building (x=w)
        painter.save()
        if self._edge == EdgeSide.LEFT:
            painter.translate(0, h / 2)
            angle = 180  # Face left (outside)
        elif self._edge == EdgeSide.RIGHT:
            painter.translate(w, h / 2)
            angle = 0  # Face right (outside)
        elif self._edge == EdgeSide.TOP:
            painter.translate(w / 2, 0)
            angle = 270  # Face up (outside)
        else:  # BOTTOM
            painter.translate(w / 2, h)
            angle = 90  # Face down (outside)

        path = draw_half_circle_path(PORT_RADIUS, angle)
        painter.drawPath(path)
        painter.restore()

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
        """Snap a position to the nearest room edge.

        The building is positioned so it sits ON the edge (straddling it),
        with its edge-facing side aligned to the room boundary.
        """
        room = self.room_item.room
        w, h = self._get_display_size()
        x, y = pos.x(), pos.y()

        # Calculate distances to each edge (from building center)
        center_x, center_y = x + w / 2, y + h / 2
        dist_left = abs(center_x)
        dist_right = abs(center_x - room.width)
        dist_top = abs(center_y)
        dist_bottom = abs(center_y - room.height)

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

        # Snap to edge, positioning so building straddles the edge
        # For left/right edges: building's left/right side aligns with edge
        # For top/bottom edges: building's top/bottom side aligns with edge
        if min_dist == dist_left:
            # Left edge: x=0 means left side of building is on edge
            clamped_y = max(0, min(y, room.height - h))
            return QPointF(0, clamped_y)
        elif min_dist == dist_right:
            # Right edge: right side of building on edge, so x = room.width - w
            clamped_y = max(0, min(y, room.height - h))
            return QPointF(room.width - w, clamped_y)
        elif min_dist == dist_top:
            # Top edge: y=0 means top side of building is on edge
            clamped_x = max(0, min(x, room.width - w))
            return QPointF(clamped_x, 0)
        else:  # dist_bottom
            # Bottom edge: bottom side of building on edge, so y = room.height - h
            clamped_x = max(0, min(x, room.width - w))
            return QPointF(clamped_x, room.height - h)
