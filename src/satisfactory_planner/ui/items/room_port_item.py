"""Graphics item for room ports - interactive belt connection points on room boundaries."""

from __future__ import annotations

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

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem


# Port visual constants
PORT_RADIUS = 8
INPUT_COLOR = QColor(220, 180, 50)  # Yellow for inputs
OUTPUT_COLOR = QColor(50, 200, 100)  # Green for outputs


class RoomPortItem(QGraphicsObject):
    """Interactive port symbol on a room boundary.

    This item allows belt connections to/from rooms. When a belt is dragged
    to this port, the connection is made to the RoomPlacement with the
    appropriate port index.
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

        # Position relative to parent RoomItem
        self.setPos(local_pos[0], local_pos[1])

        # Enable hover events for belt connection highlighting
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        # Z-value above room background but below buildings
        self.setZValue(0.5)

    @property
    def placement_id(self) -> str:
        """Get the room placement ID this port belongs to."""
        return self.room_item.placement.id

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle for the port."""
        return QRectF(
            -PORT_RADIUS - 2, -PORT_RADIUS - 2, (PORT_RADIUS + 2) * 2, (PORT_RADIUS + 2) * 2
        )

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the port symbol."""
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR

        # Highlight when being targeted for belt connection
        if self._is_drag_target:
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            painter.setBrush(QBrush(color.lighter(130)))
        else:
            painter.setPen(QPen(color.darker(120), 2))
            painter.setBrush(QBrush(color))

        painter.drawEllipse(QPointF(0, 0), PORT_RADIUS, PORT_RADIUS)

        # Draw direction arrow
        self._draw_arrow(painter, color)

    def _draw_arrow(self, painter: QPainter, color: QColor) -> None:
        """Draw a directional arrow inside the port."""
        painter.setPen(QPen(color.darker(150), 2))

        arrow_size = 4
        if self.is_output:
            # Arrow pointing right (out of room)
            painter.drawLine(
                QPointF(-arrow_size, -arrow_size),
                QPointF(arrow_size, 0),
            )
            painter.drawLine(
                QPointF(-arrow_size, arrow_size),
                QPointF(arrow_size, 0),
            )
        else:
            # Arrow pointing right (into room)
            painter.drawLine(
                QPointF(arrow_size, -arrow_size),
                QPointF(-arrow_size, 0),
            )
            painter.drawLine(
                QPointF(arrow_size, arrow_size),
                QPointF(-arrow_size, 0),
            )

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
