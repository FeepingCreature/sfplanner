"""Graphics item for building ports (inputs/outputs)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Port colors (matching Satisfactory)
INPUT_COLOR = QColor(220, 180, 50)  # Yellow for inputs
OUTPUT_COLOR = QColor(50, 200, 100)  # Green for outputs

PORT_RADIUS = 8  # Radius of the half-circle


def draw_half_circle_path(radius: float, angle: float = 0) -> QPainterPath:
    """Create a half-circle path facing the given angle.

    Args:
        radius: Radius of the half-circle
        angle: Direction the curved side faces (degrees, 0=right, 90=down, 180=left, 270=up)

    Returns:
        QPainterPath for the half-circle, centered at origin with flat edge at origin.
    """
    path = QPainterPath()
    r = radius

    # Base half-circle facing right (curved side to the right)
    # Then we rotate by angle
    path.moveTo(0, -r)
    path.arcTo(-r, -r, r * 2, r * 2, 90, -180)
    path.closeSubpath()

    # Apply rotation if needed
    if angle != 0:
        from PySide6.QtGui import QTransform

        transform = QTransform()
        transform.rotate(angle)
        path = transform.map(path)

    return path


class PortItem(QGraphicsItem):
    """A clickable port for connecting belts with directional arrow."""

    def __init__(
        self,
        is_output: bool,
        port_index: int,
        building_id: str,
        canvas: FactoryCanvas,
        angle: float = 0,  # 0=right, 90=down, 180=left, 270=up
        scene_room_id: str | None = None,  # None for document root, room ID for rooms
    ) -> None:
        super().__init__()

        self.is_output = is_output
        self.port_index = port_index
        self.building_id = building_id
        self.canvas = canvas
        self.angle = angle  # Direction the port faces
        self.scene_room_id = scene_room_id  # Which scene this port belongs to

        self._setup_flags()
        self._hovered = False
        self._drag_target = False  # Highlighted as valid drop target during belt drag
        self._spare_capacity: float | None = None  # For overflow display

    def _setup_flags(self) -> None:
        """Configure flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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
        """Paint the port as a half-circle facing the connection direction."""
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR

        painter.save()

        # Scale up if hovered or targeted during belt drag
        if self._hovered or self._drag_target:
            painter.scale(1.3, 1.3)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(QBrush(color.lighter(130)))
        else:
            painter.setPen(QPen(color.darker(120), 1.5))
            painter.setBrush(QBrush(color))

        # Draw half-circle facing the connection direction
        # The angle is passed to draw_half_circle_path which handles rotation
        path = draw_half_circle_path(PORT_RADIUS, self.angle)
        painter.drawPath(path)

        painter.restore()

    def hoverLeaveEvent(self, event: object) -> None:
        """Remove highlight."""
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle press to start belt drag from output port."""
        if event.button() == Qt.MouseButton.LeftButton and self.is_output:
            # scene_room_id was captured at construction time
            self.canvas.start_belt_drag(
                self.building_id, self.port_index, self.scenePos(), self.scene_room_id
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle release to complete belt connection on input port."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.is_output
            and self.canvas.is_dragging_belt()
        ):
            self.canvas.complete_belt_connection(self.building_id, self.port_index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def set_drag_target(self, targeted: bool) -> None:
        """Set whether this port is being targeted during belt drag."""
        self._drag_target = targeted
        self.update()

    def set_spare_capacity(self, spare: float | None) -> None:
        """Set the spare/overflow capacity for this port."""
        self._spare_capacity = spare
        if spare is not None and spare > 0:
            self.setToolTip(f"Spare capacity: {spare:.1f}/min")
        else:
            self.setToolTip("")

    def hoverEnterEvent(self, event: object) -> None:
        """Highlight on hover and show spare capacity."""
        self._hovered = True
        self.update()

        # Update spare capacity tooltip from flow solver
        if self.is_output and self._spare_capacity is None:
            self._update_spare_capacity()

    def _update_spare_capacity(self) -> None:
        """Fetch spare capacity from flow solver."""
        main_window = self.canvas.window()
        if not main_window.current_tab:
            return

        flow_solver = main_window.current_tab.flow_solver
        if not flow_solver or not flow_solver._solved_model:
            return

        # Find the node for this building

        graph = flow_solver._solved_model.graph
        for node in graph.nodes.values():
            # node.building_id is ItemKey, compare element_id
            if node.building_id and node.building_id.element_id == self.building_id:
                if self.port_index < len(node.outputs):
                    port = node.outputs[self.port_index]
                    # Spare = rate - actual_rate
                    spare = port.rate - port.actual_rate
                    if spare > 0.1:  # Only show if meaningful
                        self.set_spare_capacity(spare)
                break
