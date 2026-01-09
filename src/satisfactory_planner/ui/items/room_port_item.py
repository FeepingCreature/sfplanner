"""Graphics item for room ports - interactive belt connection points on room boundaries.

Ports are rendered as:
- A half-circle on the room edge (external connection point)
- A half-building shape inside the room (internal connection point)
- The whole unit is draggable along the room edge
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem


# Port visual constants
HALF_CIRCLE_RADIUS = 10  # Radius of the half-circle on room edge
BUILDING_WIDTH = 30  # Width of the half-building inside
BUILDING_HEIGHT = 24  # Height of the half-building
INPUT_COLOR = QColor(220, 180, 50)  # Yellow for inputs
OUTPUT_COLOR = QColor(50, 200, 100)  # Green for outputs
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
        """Return bounding rectangle for the port."""
        # Account for half-circle outside + building inside
        if self._edge == EdgeSide.LEFT:
            return QRectF(
                -HALF_CIRCLE_RADIUS,
                -BUILDING_HEIGHT / 2,
                HALF_CIRCLE_RADIUS + BUILDING_WIDTH,
                BUILDING_HEIGHT,
            )
        elif self._edge == EdgeSide.RIGHT:
            return QRectF(
                -BUILDING_WIDTH,
                -BUILDING_HEIGHT / 2,
                BUILDING_WIDTH + HALF_CIRCLE_RADIUS,
                BUILDING_HEIGHT,
            )
        elif self._edge == EdgeSide.TOP:
            return QRectF(
                -BUILDING_HEIGHT / 2,
                -HALF_CIRCLE_RADIUS,
                BUILDING_HEIGHT,
                HALF_CIRCLE_RADIUS + BUILDING_WIDTH,
            )
        else:  # BOTTOM
            return QRectF(
                -BUILDING_HEIGHT / 2,
                -BUILDING_WIDTH,
                BUILDING_HEIGHT,
                BUILDING_WIDTH + HALF_CIRCLE_RADIUS,
            )

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
        """Paint port on left edge: half-circle left, building right."""
        # Half-circle on the outside (left of room edge)
        self._draw_half_circle(painter, color, "left")

        # Half-building inside room (to the right)
        building_rect = QRectF(0, -BUILDING_HEIGHT / 2, BUILDING_WIDTH, BUILDING_HEIGHT)
        self._draw_half_building(painter, building_rect)

    def _paint_right_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on right edge: building left, half-circle right."""
        # Half-circle on the outside (right of room edge)
        self._draw_half_circle(painter, color, "right")

        # Half-building inside room (to the left)
        building_rect = QRectF(
            -BUILDING_WIDTH, -BUILDING_HEIGHT / 2, BUILDING_WIDTH, BUILDING_HEIGHT
        )
        self._draw_half_building(painter, building_rect)

    def _paint_top_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on top edge: half-circle top, building bottom."""
        # Half-circle on the outside (above room edge)
        self._draw_half_circle(painter, color, "top")

        # Half-building inside room (below)
        building_rect = QRectF(-BUILDING_HEIGHT / 2, 0, BUILDING_HEIGHT, BUILDING_WIDTH)
        self._draw_half_building(painter, building_rect)

    def _paint_bottom_edge(self, painter: QPainter, color: QColor) -> None:
        """Paint port on bottom edge: building top, half-circle bottom."""
        # Half-circle on the outside (below room edge)
        self._draw_half_circle(painter, color, "bottom")

        # Half-building inside room (above)
        building_rect = QRectF(
            -BUILDING_HEIGHT / 2, -BUILDING_WIDTH, BUILDING_HEIGHT, BUILDING_WIDTH
        )
        self._draw_half_building(painter, building_rect)

    def _draw_half_circle(self, painter: QPainter, color: QColor, side: str) -> None:
        """Draw the half-circle on the room edge."""
        if self._is_drag_target:
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            painter.setBrush(QBrush(color.lighter(130)))
        else:
            painter.setPen(QPen(color.darker(120), 2))
            painter.setBrush(QBrush(color))

        path = QPainterPath()

        if side == "left":
            # Half-circle facing left (outside room)
            path.moveTo(0, -HALF_CIRCLE_RADIUS)
            path.arcTo(
                -HALF_CIRCLE_RADIUS,
                -HALF_CIRCLE_RADIUS,
                HALF_CIRCLE_RADIUS * 2,
                HALF_CIRCLE_RADIUS * 2,
                90,
                180,
            )
            path.closeSubpath()
        elif side == "right":
            # Half-circle facing right (outside room)
            path.moveTo(0, -HALF_CIRCLE_RADIUS)
            path.arcTo(
                -HALF_CIRCLE_RADIUS,
                -HALF_CIRCLE_RADIUS,
                HALF_CIRCLE_RADIUS * 2,
                HALF_CIRCLE_RADIUS * 2,
                90,
                -180,
            )
            path.closeSubpath()
        elif side == "top":
            # Half-circle facing up (outside room)
            path.moveTo(-HALF_CIRCLE_RADIUS, 0)
            path.arcTo(
                -HALF_CIRCLE_RADIUS,
                -HALF_CIRCLE_RADIUS,
                HALF_CIRCLE_RADIUS * 2,
                HALF_CIRCLE_RADIUS * 2,
                180,
                180,
            )
            path.closeSubpath()
        else:  # bottom
            # Half-circle facing down (outside room)
            path.moveTo(-HALF_CIRCLE_RADIUS, 0)
            path.arcTo(
                -HALF_CIRCLE_RADIUS,
                -HALF_CIRCLE_RADIUS,
                HALF_CIRCLE_RADIUS * 2,
                HALF_CIRCLE_RADIUS * 2,
                180,
                -180,
            )
            path.closeSubpath()

        painter.drawPath(path)

    def _draw_half_building(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the half-building shape inside the room."""
        painter.setPen(QPen(BUILDING_BORDER, 1.5))
        painter.setBrush(QBrush(BUILDING_COLOR))

        # Draw rounded rectangle for building body
        painter.drawRoundedRect(rect, 4, 4)

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
