"""Graphics item for building ports (inputs/outputs)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
    QGraphicsSceneMouseEvent,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Port colors (matching Satisfactory)
INPUT_COLOR = QColor(255, 200, 50)   # Yellow for inputs
OUTPUT_COLOR = QColor(50, 200, 100)  # Green for outputs

PORT_RADIUS = 10
ARROW_SIZE = 7


class PortItem(QGraphicsItem):
    """A clickable port for connecting belts with directional arrow."""

    def __init__(
        self,
        is_output: bool,
        port_index: int,
        building_id: str,
        canvas: FactoryCanvas,
        angle: float = 0,  # 0=right, 90=down, 180=left, 270=up
    ) -> None:
        super().__init__()

        self.is_output = is_output
        self.port_index = port_index
        self.building_id = building_id
        self.canvas = canvas
        self.angle = angle  # Direction the port faces

        self._setup_flags()
        self._hovered = False

    def _setup_flags(self) -> None:
        """Configure flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        r = PORT_RADIUS + 2
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the port as an arrow pointing in/out."""
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR

        painter.save()

        # Rotate to face the right direction
        painter.rotate(self.angle)

        # Scale up if hovered
        if self._hovered:
            painter.scale(1.2, 1.2)

        # Draw filled arrow pointing outward (for output) or inward (for input)
        # Arrow points right by default
        arrow = QPolygonF()

        if self.is_output:
            # Arrow pointing outward (right): tip at right
            arrow.append(QPointF(ARROW_SIZE, 0))       # tip
            arrow.append(QPointF(-ARROW_SIZE, -ARROW_SIZE))  # top left
            arrow.append(QPointF(-ARROW_SIZE / 2, 0))  # indent
            arrow.append(QPointF(-ARROW_SIZE, ARROW_SIZE))   # bottom left
        else:
            # Arrow pointing inward (left): tip at left
            arrow.append(QPointF(-ARROW_SIZE, 0))      # tip
            arrow.append(QPointF(ARROW_SIZE, -ARROW_SIZE))   # top right
            arrow.append(QPointF(ARROW_SIZE / 2, 0))   # indent
            arrow.append(QPointF(ARROW_SIZE, ARROW_SIZE))    # bottom right

        painter.setBrush(QBrush(color))
        pen_width = 2 if self._hovered else 1.5
        painter.setPen(QPen(QColor(255, 255, 255), pen_width))
        painter.drawPolygon(arrow)

        painter.restore()

    def hoverEnterEvent(self, event: object) -> None:
        """Highlight on hover."""
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event: object) -> None:
        """Remove highlight."""
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle press to start belt drag from output port."""
        if event.button() == Qt.LeftButton and self.is_output:
            # Start dragging a connection from output
            self.canvas.start_belt_drag(self.building_id, self.port_index, self.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle release to complete belt connection on input port."""
        print(f"[DEBUG] PortItem.mouseReleaseEvent: is_output={self.is_output}, button={event.button()}, dragging={self.canvas.is_dragging_belt()}")
        if event.button() == Qt.LeftButton and not self.is_output:
            # Complete connection to this input
            if self.canvas.is_dragging_belt():
                print(f"[DEBUG]   -> completing belt to {self.building_id}:{self.port_index}")
                self.canvas.complete_belt_connection(self.building_id, self.port_index)
                event.accept()
                return
        super().mouseReleaseEvent(event)
