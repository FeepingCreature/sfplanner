"""Graphics item for belts connecting buildings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core import Belt, Building
from satisfactory_planner.core.models import RoomPlacement
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Belt colors by tier (darker = lower tier)
BELT_COLORS = {
    1: QColor(100, 100, 100),
    2: QColor(120, 120, 120),
    3: QColor(140, 140, 140),
    4: QColor(160, 160, 160),
    5: QColor(180, 180, 180),
    6: QColor(200, 180, 100),  # Gold for max tier
}

# Belt widths by tier
BELT_WIDTHS = {
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
    6: 7,
}


class BeltItem(QGraphicsPathItem):
    """A belt connecting two buildings or room placements."""

    def __init__(
        self,
        belt: Belt,
        source: Building | None = None,
        dest: Building | None = None,
        source_placement: RoomPlacement | None = None,
        dest_placement: RoomPlacement | None = None,
        canvas: FactoryCanvas | None = None,
    ) -> None:
        super().__init__()

        self.belt = belt
        self.canvas = canvas
        self._source = source
        self._dest = dest
        self._source_placement = source_placement
        self._dest_placement = dest_placement
        self._show_flow_rate = False  # Controlled by toolbar toggle
        self._is_overcapacity = False  # Set by flow solver
        self._utilization: float | None = None  # 0.0-1.0, for efficiency outline

        self._setup_flags()
        self._setup_appearance()
        self._update_path_from_endpoints()
        self.setAcceptHoverEvents(True)

    def _setup_flags(self) -> None:
        """Configure item flags."""
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(-1)  # Draw behind buildings

    def shape(self) -> QPainterPath:
        """Return a wider shape for easier clicking."""
        from PySide6.QtGui import QPainterPathStroker

        stroker = QPainterPathStroker()
        # Make clickable area wider than visual
        stroker.setWidth(self.pen().widthF() + 8)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stroker.createStroke(self.path())

    def _setup_appearance(self) -> None:
        """Configure appearance based on tier."""
        color = BELT_COLORS.get(self.belt.tier, BELT_COLORS[1])
        width = BELT_WIDTHS.get(self.belt.tier, BELT_WIDTHS[1])
        self.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

    def _update_path_from_endpoints(self) -> None:
        """Update the belt path from stored endpoints."""
        if not self.canvas:
            return

        document = self.canvas.document

        # Get start position and direction
        if self._source:
            start_pos = self._source.output_port_pos(self.belt.source_port_index)
            start_dir = self._source.output_port_direction(self.belt.source_port_index)
        elif self._source_placement:
            start_pos = self._source_placement.output_port_pos(
                self.belt.source_port_index, document
            )
            start_dir = self._source_placement.output_port_direction(self.belt.source_port_index)
        else:
            return

        # Get end position and direction
        if self._dest:
            end_pos = self._dest.input_port_pos(self.belt.dest_port_index)
            end_dir = self._dest.input_port_direction(self.belt.dest_port_index)
        elif self._dest_placement:
            end_pos = self._dest_placement.input_port_pos(self.belt.dest_port_index, document)
            end_dir = self._dest_placement.input_port_direction(self.belt.dest_port_index)
        else:
            return

        start = Point(start_pos[0], start_pos[1])
        end = Point(end_pos[0], end_pos[1])

        # Compute Dubins path and convert to QPainterPath
        belt_path = compute_belt_path(start, start_dir, end, end_dir)
        path = belt_path_to_painter_path(start, end, belt_path)
        self.setPath(path)

    def update_path(self, source: Building, dest: Building) -> None:
        """Update the belt path between source and dest buildings.

        Legacy method for backward compatibility with room-internal belts.
        """
        self._source = source
        self._dest = dest
        self._source_placement = None
        self._dest_placement = None
        self._update_path_from_endpoints()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the belt with flow direction indicators."""
        # Draw utilization underlay first (wider, behind) - green to yellow to red
        if self._utilization is not None and not self._is_overcapacity:
            util = self._utilization
            if util >= 0.9:
                util_color = QColor(80, 255, 80, 180)  # Bright green - well utilized
            elif util >= 0.5:
                t = (util - 0.5) / 0.4
                util_color = QColor(int(255 - t * 175), int(220 + t * 35), 50, 180)
            else:
                util_color = QColor(255, 220, 50, 140)  # Yellow - underutilized
            util_pen = QPen(util_color, self.pen().widthF() + 5)
            util_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(util_pen)
            painter.drawPath(self.path())

        # Draw overcapacity underlay (wider, behind, red)
        if self._is_overcapacity:
            overcap_pen = QPen(QColor(255, 80, 80), self.pen().widthF() + 6)
            overcap_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(overcap_pen)
            painter.drawPath(self.path())

        # Draw the main belt line
        super().paint(painter, option, widget)

        # Draw selection highlight
        if self.isSelected():
            highlight_pen = QPen(QColor(255, 255, 0), self.pen().widthF() + 2)
            painter.setPen(highlight_pen)
            painter.drawPath(self.path())

        # Draw flow direction arrows
        self._draw_flow_arrows(painter)

        # Draw flow rate if enabled
        if self._show_flow_rate:
            self._draw_flow_rate(painter)

    def _draw_flow_arrows(self, painter: QPainter) -> None:
        """Draw small arrows along the belt to show flow direction."""
        path = self.path()
        length = path.length()

        if length < 50:
            return  # Too short for arrows

        # Draw arrows at regular intervals
        arrow_spacing = 50
        num_arrows = int(length / arrow_spacing)

        painter.setPen(QPen(QColor(100, 100, 100, 150), 1))
        painter.setBrush(QBrush(QColor(100, 100, 100, 150)))

        for i in range(1, num_arrows):
            t = (i * arrow_spacing) / length
            point = path.pointAtPercent(t)
            angle = path.angleAtPercent(t)

            painter.save()
            painter.translate(point)
            painter.rotate(-angle)

            # Draw a small triangle arrow
            arrow_size = 4
            painter.drawPolygon(
                [
                    QPointF(arrow_size, 0),
                    QPointF(-arrow_size, -arrow_size),
                    QPointF(-arrow_size, arrow_size),
                ]
            )
            painter.restore()

    def _draw_flow_rate(self, painter: QPainter) -> None:
        """Draw the flow rate at the belt midpoint."""
        if not self.canvas:
            return

        # Get flow rate from flow solver
        flow_rate = self._get_flow_rate()
        if flow_rate is None:
            return

        path = self.path()
        if path.length() < 30:
            return

        # Draw at midpoint
        midpoint = path.pointAtPercent(0.5)

        # Background for readability
        text = f"{flow_rate:.1f}/min"
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        from PySide6.QtGui import QFontMetrics

        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(text)
        bg_rect = QRectF(
            midpoint.x() - text_rect.width() / 2 - 3,
            midpoint.y() - text_rect.height() / 2 - 2,
            text_rect.width() + 6,
            text_rect.height() + 4,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 30, 30, 200)))
        painter.drawRoundedRect(bg_rect, 3, 3)

        # Draw text
        if self._is_overcapacity:
            painter.setPen(QPen(QColor(255, 100, 100)))
        else:
            painter.setPen(QPen(QColor(200, 200, 200)))
        painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _get_flow_rate(self) -> float | None:
        """Get flow rate from the flow solver."""
        if not self.canvas:
            return None

        main_window = self.canvas.window()
        if not hasattr(main_window, "current_tab") or not main_window.current_tab:
            return None

        flow_solver = main_window.current_tab.flow_solver
        if flow_solver:
            result: float | None = flow_solver.get_flow_rate(self.belt.id)
            return result
        return None

    def set_show_flow_rate(self, show: bool) -> None:
        """Toggle flow rate display."""
        self._show_flow_rate = show
        self.update()

    def set_overcapacity(self, overcapacity: bool) -> None:
        """Set overcapacity state for visual feedback."""
        self._is_overcapacity = overcapacity
        self.update()

    def set_utilization(self, utilization: float | None) -> None:
        """Set belt utilization for efficiency outline."""
        self._utilization = utilization
        self.update()

    def hoverEnterEvent(self, event: object) -> None:
        """Show flow rate tooltip on hover."""
        flow_rate = self._get_flow_rate()
        capacity = self.belt.capacity
        if flow_rate is not None:
            usage_pct = (flow_rate / capacity) * 100 if capacity > 0 else 0
            tooltip = (
                f"Flow: {flow_rate:.1f}/min\nCapacity: {capacity}/min\nUsage: {usage_pct:.1f}%"
            )
            if self._is_overcapacity:
                tooltip += "\n⚠️ OVERCAPACITY"
            self.setToolTip(tooltip)

    def hoverLeaveEvent(self, event: object) -> None:
        """Clear tooltip on hover exit."""
        self.setToolTip("")
