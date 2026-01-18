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
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.models import RoomPlacement, Scene
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Belt colors by tier (darker = lower tier) - used as fallback when item unknown
BELT_COLORS = {
    1: QColor(100, 100, 100),
    2: QColor(120, 120, 120),
    3: QColor(140, 140, 140),
    4: QColor(160, 160, 160),
    5: QColor(180, 180, 180),
    6: QColor(200, 180, 100),  # Gold for max tier
}

# Item colors for belt visualization - maps item names to colors
# Colors chosen to be visually distinct and roughly match in-game item colors
ITEM_COLORS: dict[str, QColor] = {
    # Ores
    "Iron Ore": QColor(139, 90, 43),  # Brown
    "Copper Ore": QColor(184, 115, 51),  # Copper orange
    "Limestone": QColor(180, 170, 150),  # Tan/beige
    "Coal": QColor(50, 50, 50),  # Dark gray
    "Caterium Ore": QColor(255, 200, 50),  # Gold
    "Raw Quartz": QColor(255, 182, 193),  # Pink
    "Sulfur": QColor(255, 255, 100),  # Yellow
    "Bauxite": QColor(150, 75, 75),  # Reddish brown
    "Uranium": QColor(50, 255, 50),  # Bright green (radioactive)
    "SAM": QColor(150, 50, 200),  # Purple
    # Ingots
    "Iron Ingot": QColor(120, 120, 140),  # Steel gray
    "Copper Ingot": QColor(200, 120, 50),  # Copper
    "Steel Ingot": QColor(80, 80, 100),  # Dark steel
    "Caterium Ingot": QColor(220, 180, 50),  # Gold
    "Aluminum Ingot": QColor(200, 200, 210),  # Light silver
    # Basic parts
    "Iron Plate": QColor(100, 100, 120),  # Gray-blue
    "Iron Rod": QColor(110, 110, 130),  # Slightly different gray
    "Copper Sheet": QColor(210, 130, 60),  # Copper
    "Screw": QColor(140, 140, 160),  # Light steel
    "Wire": QColor(190, 100, 40),  # Copper wire
    "Cable": QColor(60, 60, 70),  # Dark (insulated)
    "Concrete": QColor(150, 150, 140),  # Gray
    "Steel Beam": QColor(70, 70, 90),  # Dark steel
    "Steel Pipe": QColor(75, 75, 95),  # Dark steel
    # Electronics
    "Rotor": QColor(100, 100, 110),  # Metal gray
    "Stator": QColor(90, 90, 100),  # Metal gray
    "Motor": QColor(80, 80, 90),  # Darker metal
    "Circuit Board": QColor(0, 100, 0),  # Green PCB
    "Computer": QColor(50, 50, 60),  # Dark
    "Supercomputer": QColor(40, 40, 50),  # Darker
    "AI Limiter": QColor(200, 50, 50),  # Red
    # Misc
    "Plastic": QColor(240, 240, 250),  # White-ish
    "Rubber": QColor(30, 30, 35),  # Black
    "Fuel": QColor(200, 150, 50),  # Amber
    "Packaged Fuel": QColor(180, 130, 40),  # Darker amber
}

# Default color for unknown items
DEFAULT_ITEM_COLOR = QColor(150, 150, 150)  # Neutral gray

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
        canvas: FactoryCanvas,
        parent_scene: Scene,
        source: Building | None = None,
        dest: Building | None = None,
        source_placement: RoomPlacement | None = None,
        dest_placement: RoomPlacement | None = None,
    ) -> None:
        super().__init__()

        self.belt = belt
        self.canvas = canvas
        self.parent_scene = parent_scene  # Scene this belt belongs to (Document or Room)
        self._source = source
        self._dest = dest
        self._source_placement = source_placement
        self._dest_placement = dest_placement
        self._flow_rate: float | None = None  # Set by flow solver
        self._optimal_flow_rate: float | None = None  # set by flow solver, flow without belt limits
        self._item_name: str | None = None  # Set by flow solver - what item flows through
        # FIXME isn't this redundant with source_placement?
        self._placement_id: str | None = None  # Set when belt is inside a room placement

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
        """Configure appearance based on item being transported (or tier as fallback)."""
        if self._item_name:
            color = ITEM_COLORS.get(self._item_name, DEFAULT_ITEM_COLOR)
        else:
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
            start_dir = self._source_placement.output_port_direction(
                self.belt.source_port_index, document
            )
        else:
            return

        # Get end position and direction
        if self._dest:
            end_pos = self._dest.input_port_pos(self.belt.dest_port_index)
            end_dir = self._dest.input_port_direction(self.belt.dest_port_index)
        elif self._dest_placement:
            end_pos = self._dest_placement.input_port_pos(self.belt.dest_port_index, document)
            end_dir = self._dest_placement.input_port_direction(self.belt.dest_port_index, document)
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
        # Only show when efficiency visualization is enabled
        if (
            self.canvas.show_efficiency
            and self._flow_rate is not None
            and not self.is_over_capacity
        ):
            util = self._flow_rate / self.belt.capacity
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
        # Only show when efficiency visualization is enabled
        if self.canvas.show_efficiency and self.is_over_capacity:
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
        if self.canvas.show_flow_rate:
            self._draw_flow_rate(painter)

    def _draw_flow_arrows(self, painter: QPainter) -> None:
        """Draw directional triangles along the belt to show flow direction and capacity.

        Each marker group has one solid filled triangle followed by chevron outlines.
        Number of trailing chevrons indicates tier:
        - Tier 1: |>      (solid only)
        - Tier 2: |>>     (solid + 1 chevron)
        - Tier 3: |>>>    (solid + 2 chevrons)
        - Tier 4: |>>>>   (solid + 3 chevrons)
        - Tier 5: |>>>>>  (solid + 4 chevrons)
        - Tier 6: |>>>>>> (solid + 5 chevrons)
        """
        path = self.path()
        length = path.length()

        if length < 40:
            return  # Too short for arrows

        # Number of trailing chevrons based on tier (tier 1 = 0 chevrons, tier 6 = 5)
        trailing_chevrons = self.belt.tier - 1

        # Spacing between marker groups along the belt
        group_spacing = 80

        # Spacing between elements within a group
        chevron_spacing = 6

        # Arrow/chevron size
        arrow_size = 5

        # Calculate the total width of one marker group
        group_width = trailing_chevrons * chevron_spacing

        # Use belt tier color but brighter/more visible
        base_color = BELT_COLORS.get(self.belt.tier, BELT_COLORS[1])
        arrow_color = QColor(
            min(255, base_color.red() + 60),
            min(255, base_color.green() + 60),
            min(255, base_color.blue() + 60),
            220,
        )

        # Calculate marker group positions
        # For short belts, place one group centered
        # For longer belts, distribute groups evenly with spacing
        num_groups = max(1, int(length / group_spacing))

        if num_groups == 1:
            # Single group: center it on the belt
            # Position the solid triangle so the whole group is centered
            # The group spans from solid_pos to solid_pos + group_width
            # Center of group = solid_pos + group_width/2, so solid_pos = center - group_width/2
            group_positions = [length / 2 - group_width / 2]
        else:
            # Multiple groups: distribute evenly, avoiding endpoints
            # Start at group_spacing, then every group_spacing after
            group_positions = [i * group_spacing for i in range(1, num_groups + 1)]

        for group_start_dist in group_positions:
            if group_start_dist <= 0 or group_start_dist >= length:
                continue

            # Draw solid filled triangle at the front
            t = group_start_dist / length
            if 0 < t < 1:
                point = path.pointAtPercent(t)
                angle = path.angleAtPercent(t)

                painter.save()
                painter.translate(point)
                painter.rotate(-angle)

                painter.setPen(QPen(arrow_color.darker(120), 1))
                painter.setBrush(QBrush(arrow_color))
                painter.drawPolygon(
                    [
                        QPointF(arrow_size, 0),
                        QPointF(-arrow_size, -arrow_size),
                        QPointF(-arrow_size, arrow_size),
                    ]
                )
                painter.restore()

            # Draw leading chevrons ahead of the solid triangle (no fill)
            for j in range(trailing_chevrons):
                chevron_dist = group_start_dist + (j + 1) * chevron_spacing

                if chevron_dist <= 0 or chevron_dist >= length:
                    continue

                t = chevron_dist / length
                point = path.pointAtPercent(t)
                angle = path.angleAtPercent(t)

                painter.save()
                painter.translate(point)
                painter.rotate(-angle)

                # Draw chevron as two lines forming a ">" shape
                painter.setPen(QPen(arrow_color, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                chevron_path = QPainterPath()
                chevron_path.moveTo(-arrow_size * 0.7, -arrow_size * 0.8)
                chevron_path.lineTo(arrow_size * 0.5, 0)
                chevron_path.lineTo(-arrow_size * 0.7, arrow_size * 0.8)
                painter.drawPath(chevron_path)
                painter.restore()

    def _draw_flow_rate(self, painter: QPainter) -> None:
        """Draw the flow rate at the belt midpoint."""
        if not self.canvas:
            return

        if self._flow_rate is None:
            return

        path = self.path()
        if path.length() < 30:
            return

        # Draw at midpoint
        midpoint = path.pointAtPercent(0.5)

        # Background for readability
        text = f"{self._flow_rate:.1f}/min"
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
        if self.is_over_capacity:
            painter.setPen(QPen(QColor(255, 100, 100)))
        else:
            painter.setPen(QPen(QColor(200, 200, 200)))
        painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, text)

    @property
    def item_key(self) -> ItemKey:
        """Get the flow solver key for this belt."""
        return ItemKey(element_id=self.belt.id, placement_id=self._placement_id)

    def set_placement_id(self, placement_id: str | None) -> None:
        """Set the placement ID for belts inside room placements."""
        self._placement_id = placement_id

    def set_flow_rate(
        self,
        flow_rate: float | None,
        optimal_flow_rate: float | None,
        item_name: str | None = None,
    ) -> None:
        """Set belt flow rate and item for visualization."""
        self._flow_rate = flow_rate
        self._optimal_flow_rate = optimal_flow_rate
        # Update item name and refresh appearance if changed
        if item_name != self._item_name:
            self._item_name = item_name
            self._setup_appearance()
        self.update()

    @property
    def is_over_capacity(self) -> bool | None:
        if not self._optimal_flow_rate:
            return None
        return self._optimal_flow_rate > self.belt.capacity

    @property
    def belt_scene(self) -> Scene:
        """Get the scene this belt belongs to."""
        return self.parent_scene

    def hoverEnterEvent(self, event: object) -> None:
        """Show flow rate tooltip on hover."""
        flow_rate = self._flow_rate
        capacity = self.belt.capacity
        if flow_rate is not None:
            usage_pct = (flow_rate / capacity) * 100 if capacity > 0 else 0
            tooltip = (
                f"Flow: {flow_rate:.1f}/min\nCapacity: {capacity}/min\nUsage: {usage_pct:.1f}%"
            )
            if self.is_over_capacity:
                tooltip += "\n⚠️ OVERCAPACITY"
            self.setToolTip(tooltip)

    def hoverLeaveEvent(self, event: object) -> None:
        """Clear tooltip on hover exit."""
        self.setToolTip("")
