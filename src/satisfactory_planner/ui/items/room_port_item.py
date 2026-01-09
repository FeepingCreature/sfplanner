"""Graphics item for room ports - interactive belt connection points on room boundaries.

Ports are rendered as a half-circle on the room edge (external connection point).
The PORT_IN/PORT_OUT building inside the room handles the internal connection.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core.models import BuildingType
from satisfactory_planner.ui.items.port_item import (
    INPUT_COLOR,
    OUTPUT_COLOR,
    PORT_RADIUS,
    draw_half_circle_path,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem


# Building body constants
BUILDING_SIZE = 30  # Size of the draggable building body
BUILDING_COLOR = QColor(70, 70, 80)  # Dark gray for building body
BUILDING_BORDER = QColor(100, 100, 110)  # Lighter border


class EdgeSide(Enum):
    """Which edge of the room the port is on."""

    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()


class RoomPortItem(QGraphicsObject):
    """Interactive port on a room boundary with half-building visualization.

    Renders as:
    - Half-circle on room edge (external belt connection)
    - Half-building shape inside room (internal belt connection)
    - Connector port on the room-facing side of the building

    The port can be dragged along the room edge (future feature).
    """

    def __init__(
        self,
        room_item: RoomItem,
        port_index: int,
        is_output: bool,
        local_pos: tuple[float, float],
        canvas: FactoryCanvas,
    ) -> None:
        super().__init__(parent=room_item)

        self.room_item = room_item
        self.port_index = port_index
        self.is_output = is_output
        self.canvas = canvas
        self._is_drag_target = False

        # Determine which edge this port is on based on position
        self._edge = self._determine_edge(local_pos)

        # Position relative to parent RoomItem
        self.setPos(local_pos[0], local_pos[1])

        # Enable hover events for belt connection highlighting
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Z-value above room background but below regular buildings
        self.setZValue(0.5)

        # Drag state
        self._is_dragging = False

    def _determine_edge(self, local_pos: tuple[float, float]) -> EdgeSide:
        """Determine which room edge this port is on."""
        x, y = local_pos
        room_width = self.room_item.room.width

        # Check proximity to each edge
        if x <= 1:
            return EdgeSide.LEFT
        elif x >= room_width - 1:
            return EdgeSide.RIGHT
        elif y <= 1:
            return EdgeSide.TOP
        else:
            return EdgeSide.BOTTOM

    @property
    def placement_id(self) -> str:
        """Get the room placement ID this port belongs to."""
        return self.room_item.placement.id

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle for the port (half-circle + building body)."""
        r = PORT_RADIUS
        b = BUILDING_SIZE
        # Include half-circle on edge + building body inside room
        if self._edge == EdgeSide.LEFT:
            # Building extends to the right, half-circle to the left (output) or right (input)
            if self.is_output:
                return QRectF(-r, -b / 2, r + b, b)
            else:
                return QRectF(0, -b / 2, b + r, b)
        elif self._edge == EdgeSide.RIGHT:
            # Building extends to the left
            if self.is_output:
                return QRectF(-b, -b / 2, b + r, b)
            else:
                return QRectF(-b - r, -b / 2, b + r, b)
        elif self._edge == EdgeSide.TOP:
            # Building extends downward
            if self.is_output:
                return QRectF(-b / 2, -r, b, r + b)
            else:
                return QRectF(-b / 2, 0, b, b + r)
        else:  # BOTTOM
            # Building extends upward
            if self.is_output:
                return QRectF(-b / 2, -b, b, b + r)
            else:
                return QRectF(-b / 2, -b - r, b, b + r)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the port with half-circle and half-building."""
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR

        # Draw based on edge orientation
        if self._edge == EdgeSide.LEFT:
            self._paint_left_edge(painter, color)
        elif self._edge == EdgeSide.RIGHT:
            self._paint_right_edge(painter, color)
        elif self._edge == EdgeSide.TOP:
            self._paint_top_edge(painter, color)
        else:
            self._paint_bottom_edge(painter, color)

    def _paint_left_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on left edge: half-circle + building body + internal connector."""
        # Half-circle on room edge
        self._draw_half_circle(painter, color, "left")
        # Building body inside room (to the right)
        self._draw_building_body(
            painter, QRectF(0, -BUILDING_SIZE / 2, BUILDING_SIZE, BUILDING_SIZE)
        )
        # Internal connector on far side of building
        internal_color = INPUT_COLOR if self.is_output else OUTPUT_COLOR
        self._draw_internal_connector(painter, QPointF(BUILDING_SIZE, 0), internal_color, "left")

    def _paint_right_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on right edge: half-circle + building body + internal connector."""
        # Half-circle on room edge
        self._draw_half_circle(painter, color, "right")
        # Building body inside room (to the left)
        self._draw_building_body(
            painter, QRectF(-BUILDING_SIZE, -BUILDING_SIZE / 2, BUILDING_SIZE, BUILDING_SIZE)
        )
        # Internal connector on far side of building
        internal_color = INPUT_COLOR if self.is_output else OUTPUT_COLOR
        self._draw_internal_connector(painter, QPointF(-BUILDING_SIZE, 0), internal_color, "right")

    def _paint_top_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on top edge: half-circle + building body + internal connector."""
        # Half-circle on room edge
        self._draw_half_circle(painter, color, "top")
        # Building body inside room (below)
        self._draw_building_body(
            painter, QRectF(-BUILDING_SIZE / 2, 0, BUILDING_SIZE, BUILDING_SIZE)
        )
        # Internal connector on far side of building
        internal_color = INPUT_COLOR if self.is_output else OUTPUT_COLOR
        self._draw_internal_connector(painter, QPointF(0, BUILDING_SIZE), internal_color, "top")

    def _paint_bottom_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on bottom edge: half-circle + building body + internal connector."""
        # Half-circle on room edge
        self._draw_half_circle(painter, color, "bottom")
        # Building body inside room (above)
        self._draw_building_body(
            painter, QRectF(-BUILDING_SIZE / 2, -BUILDING_SIZE, BUILDING_SIZE, BUILDING_SIZE)
        )
        # Internal connector on far side of building
        internal_color = INPUT_COLOR if self.is_output else OUTPUT_COLOR
        self._draw_internal_connector(painter, QPointF(0, -BUILDING_SIZE), internal_color, "bottom")

    def _draw_building_body(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the draggable building body inside the room."""
        painter.setPen(QPen(BUILDING_BORDER, 1.5))
        painter.setBrush(QBrush(BUILDING_COLOR))
        painter.drawRoundedRect(rect, 4, 4)

    def _draw_internal_connector(
        self, painter: QPainter, pos: QPointF, color: QColor, edge: str
    ) -> None:
        """Draw the internal connector half-circle where belts inside the room connect."""
        painter.setPen(QPen(color.darker(120), 1.5))
        painter.setBrush(QBrush(color))

        # Determine angle - connector faces INTO the room (opposite of external half-circle)
        angle_map = {
            "left": 0,  # Face right (into room)
            "right": 180,  # Face left (into room)
            "top": 90,  # Face down (into room)
            "bottom": 270,  # Face up (into room)
        }
        angle = angle_map.get(edge, 0)
        path = draw_half_circle_path(PORT_RADIUS, angle)

        painter.save()
        painter.translate(pos)
        painter.drawPath(path)
        painter.restore()

    def _draw_half_circle(self, painter: QPainter, color: QColor, side: str) -> None:
        """Draw the half-circle on the room edge.

        - Input ports: half-circle faces INTO the room (curved side inside)
        - Output ports: half-circle faces OUT of the room (curved side outside)

        The flat edge of the half-circle sits on the room boundary.
        """
        if self._is_drag_target:
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            painter.setBrush(QBrush(color.lighter(130)))
        else:
            painter.setPen(QPen(color.darker(120), 2))
            painter.setBrush(QBrush(color))

        # Determine angle based on edge and port type
        # Output = face outward, Input = face inward
        angle_map = {
            ("left", True): 180,  # Output on left edge -> face left (outside)
            ("left", False): 0,  # Input on left edge -> face right (inside)
            ("right", True): 0,  # Output on right edge -> face right (outside)
            ("right", False): 180,  # Input on right edge -> face left (inside)
            ("top", True): 270,  # Output on top edge -> face up (outside)
            ("top", False): 90,  # Input on top edge -> face down (inside)
            ("bottom", True): 90,  # Output on bottom edge -> face down (outside)
            ("bottom", False): 270,  # Input on bottom edge -> face up (inside)
        }
        angle = angle_map.get((side, self.is_output), 0)
        path = draw_half_circle_path(PORT_RADIUS, angle)
        painter.drawPath(path)

    def set_drag_target(self, is_target: bool) -> None:
        """Set whether this port is being targeted for a belt connection."""
        if self._is_drag_target != is_target:
            self._is_drag_target = is_target
            self.update()

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Handle hover enter."""
        self.setCursor(Qt.CursorShape.CrossCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Handle hover leave."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press - start belt connection or drag port."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_output:
                # Start belt drag from this output port
                scene_pos = self.scenePos()
                self.canvas.start_belt_drag(self.placement_id, self.port_index, scene_pos)
                event.accept()
                return
            else:
                # Start dragging the port
                self._is_dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse release - end port drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
        super().mouseReleaseEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes - snap to room edge while dragging."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            if isinstance(new_pos, QPointF):
                # Snap to nearest room edge
                new_pos = self._snap_to_edge(new_pos)
                return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update the port building's position in the model
            new_pos = self.pos()
            self._update_port_position(new_pos)
            # Redetermine which edge we're on
            self._edge = self._determine_edge((new_pos.x(), new_pos.y()))
            self.update()
        return super().itemChange(change, value)

    def _snap_to_edge(self, pos: QPointF) -> QPointF:
        """Snap a position to the nearest room edge."""
        room = self.room_item.room
        x, y = pos.x(), pos.y()

        # Calculate distances to each edge
        dist_left = abs(x)
        dist_right = abs(x - room.width)
        dist_top = abs(y)
        dist_bottom = abs(y - room.height)

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

        # Clamp y/x to room bounds and snap to nearest edge
        if min_dist == dist_left:
            return QPointF(0, max(0, min(y, room.height)))
        elif min_dist == dist_right:
            return QPointF(room.width, max(0, min(y, room.height)))
        elif min_dist == dist_top:
            return QPointF(max(0, min(x, room.width)), 0)
        else:  # dist_bottom
            return QPointF(max(0, min(x, room.width)), room.height)

    def _update_port_position(self, new_pos: QPointF) -> None:
        """Update the PORT building's position in the room model."""
        room = self.room_item.room
        port_type = BuildingType.PORT_OUT if self.is_output else BuildingType.PORT_IN

        # Find the port building and update its position
        for building in room.buildings.values():
            if building.building_type == port_type and building.port_index == self.port_index:
                # Port position IS the edge position (no offset needed)
                building.x = new_pos.x()
                building.y = new_pos.y()
                break

        # Update belts connected to this port
        self.canvas._update_belts_for_placement(self.placement_id)

    def get_scene_pos(self) -> QPointF:
        """Get the scene position of this port."""
        return self.scenePos()
