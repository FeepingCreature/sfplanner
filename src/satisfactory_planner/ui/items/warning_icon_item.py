"""Warning icon graphics item for displaying warnings at element locations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_solver import Warning


# Icon characters for different warning types
WARNING_ICONS: dict[str, str] = {
    "disconnected_belt": "🔌",
    "input_missing": "❓",
    "resource_underflow": "📉",
    "production_underflow": "⚠️",
    "leftover_items": "📦",
    "belt_overcapacity": "🚫",
    "item_mismatch": "❌",
    "recipe_not_set": "📋",
}

# Priority order for warning types (higher = more important, shown first)
WARNING_PRIORITY: dict[str, int] = {
    "item_mismatch": 100,
    "recipe_not_set": 90,
    "input_missing": 80,
    "disconnected_belt": 70,
    "resource_underflow": 60,
    "production_underflow": 50,
    "belt_overcapacity": 40,
    "leftover_items": 10,
}

# Colors for different severity levels
SEVERITY_COLORS = {
    "high": QColor(255, 80, 80),  # Red
    "medium": QColor(255, 180, 50),  # Orange
    "low": QColor(255, 255, 100),  # Yellow
    "info": QColor(100, 180, 255),  # Blue
}


class WarningIconItem(QGraphicsObject):
    """A floating warning icon that appears at the location of an issue.

    These are independent items (not children of BuildingItem/BeltItem) so that
    the same room can have different warnings for different placements.
    """

    ICON_SIZE = 20

    def __init__(
        self,
        warning: Warning,
        position: QPointF,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)

        self.warning = warning
        self._icon = WARNING_ICONS.get(warning.type.value, "⚠️")
        self._severity_color = self._get_severity_color(warning.severity)

        self.setPos(position)
        self.setZValue(1000)  # Always on top
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Build tooltip with causal chain
        self._build_tooltip()

    def _get_severity_color(self, severity: float) -> QColor:
        """Get color based on severity value."""
        if severity >= 0.8:
            return SEVERITY_COLORS["high"]
        elif severity >= 0.5:
            return SEVERITY_COLORS["medium"]
        elif severity >= 0.2:
            return SEVERITY_COLORS["low"]
        else:
            return SEVERITY_COLORS["info"]

    def _build_tooltip(self) -> None:
        """Build tooltip text including causal chain."""
        lines = [self.warning.message]

        # Add causal chain
        if self.warning.caused_by:
            lines.append("")
            lines.append("Caused by:")
            for cause in self.warning.caused_by:
                lines.append(f"  • {cause.message}")
                # Recurse one level deep
                for sub_cause in cause.caused_by:
                    lines.append(f"    ↳ {sub_cause.message}")

        self.setToolTip("\n".join(lines))

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        size = self.ICON_SIZE
        return QRectF(-size / 2, -size / 2, size, size)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the warning icon."""
        size = self.ICON_SIZE
        rect = QRectF(-size / 2, -size / 2, size, size)

        # Draw background circle
        painter.setPen(QPen(self._severity_color.darker(150), 2))
        painter.setBrush(QBrush(self._severity_color))
        painter.drawEllipse(rect)

        # Draw icon text
        painter.setPen(QPen(QColor(0, 0, 0)))
        from PySide6.QtGui import QFont

        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._icon)

    def hoverEnterEvent(self, event: object) -> None:
        """Highlight on hover."""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def hoverLeaveEvent(self, event: object) -> None:
        """Remove highlight."""
        self.unsetCursor()
        self.update()
