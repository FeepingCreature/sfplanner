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

from satisfactory_planner.ui.items.port_item import (
    INPUT_COLOR,
    OUTPUT_COLOR,
    draw_half_circle_path,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem


# Port visual constants
HALF_CIRCLE_RADIUS = 10  # Radius of the half-circle on room edge


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

        # Z-value above room background but below regular buildings
        self.setZValue(0.5)

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
        """Return bounding rectangle for the half-circle."""
        r = HALF_CIRCLE_RADIUS
        # Half-circle centered on room edge:
        # - Input ports: half-circle inside room
        # - Output ports: half-circle outside room
        if self._edge == EdgeSide.LEFT:
            if self.is_output:
                return QRectF(-r, -r, r, r * 2)  # Outside (left)
            else:
                return QRectF(0, -r, r, r * 2)  # Inside (right)
        elif self._edge == EdgeSide.RIGHT:
            if self.is_output:
                return QRectF(0, -r, r, r * 2)  # Outside (right)
            else:
                return QRectF(-r, -r, r, r * 2)  # Inside (left)
        elif self._edge == EdgeSide.TOP:
            if self.is_output:
                return QRectF(-r, -r, r * 2, r)  # Outside (up)
            else:
                return QRectF(-r, 0, r * 2, r)  # Inside (down)
        else:  # BOTTOM
            if self.is_output:
                return QRectF(-r, 0, r * 2, r)  # Outside (down)
            else:
                return QRectF(-r, -r, r * 2, r)  # Inside (up)

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
        """Paint port on left edge: half-circle on room boundary."""
        self._draw_half_circle(painter, color, "left")

    def _paint_right_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on right edge: half-circle on room boundary."""
        self._draw_half_circle(painter, color, "right")

    def _paint_top_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on top edge: half-circle on room boundary."""
        self._draw_half_circle(painter, color, "top")

    def _paint_bottom_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on bottom edge: half-circle on room boundary."""
        self._draw_half_circle(painter, color, "bottom")

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
        path = draw_half_circle_path(HALF_CIRCLE_RADIUS, angle)
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
        """Handle mouse press - start belt connection from output ports."""
        if event.button() == Qt.MouseButton.LeftButton and self.is_output:
            # Start belt drag from this output port
            scene_pos = self.scenePos()
            self.canvas.start_belt_drag(self.placement_id, self.port_index, scene_pos)
            event.accept()
            return
        super().mousePressEvent(event)

    def get_scene_pos(self) -> QPointF:
        """Get the scene position of this port."""
        return self.scenePos()
