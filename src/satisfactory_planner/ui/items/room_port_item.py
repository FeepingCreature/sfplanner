"""Graphics item for room ports - interactive belt connection points on room boundaries.

Ports are rendered as a half-circle on the room edge (external connection point),
plus a building body inside the room with an internal connector.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneHoverEvent,
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


class RoomPortItem(BuildingItem):
    """Interactive port on a room boundary with half-building visualization.

    Extends BuildingItem to reuse selection, dragging, and scene handling.
    Overrides rendering to show half-circle on room edge plus building body.

    Renders as:
    - Half-circle on room edge (external belt connection)
    - Building body inside room
    - Internal connector half-circle (for belts inside the room)
    """

    def __init__(
        self,
        room_item: RoomItem,
        building: Building,
        canvas: FactoryCanvas,
    ) -> None:
        # Get local position from building
        local_pos = (building.x, building.y)

        # Initialize BuildingItem with the PORT building
        super().__init__(building, canvas, scene=room_item.room)

        self.room_item = room_item
        self.is_output = building.building_type == BuildingType.PORT_OUT
        self._is_drag_target = False

        # Determine which edge this port is on based on position
        self._edge = self._determine_edge(local_pos)

        # Set as child of room item for proper scene hierarchy
        self.setParentItem(room_item)

        # Position relative to parent RoomItem
        self.setPos(local_pos[0], local_pos[1])

        # Enable hover events for belt connection highlighting
        self.setAcceptHoverEvents(True)

        # Z-value above room background but below regular buildings
        self.setZValue(0.5)

        # Reposition the PortItem children based on room edge
        self._update_port_positions_for_edge()

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
    def port_index(self) -> int:
        """Get port index from the building model."""
        return self.building.port_index or 0

    def _update_port_positions_for_edge(self) -> None:
        """Reposition PortItem children based on which room edge we're on."""
        # Get angle for internal connector based on edge
        # The internal connector faces INTO the room
        internal_angle_map = {
            EdgeSide.LEFT: 0,  # Face right (into room)
            EdgeSide.RIGHT: 180,  # Face left (into room)
            EdgeSide.TOP: 90,  # Face down (into room)
            EdgeSide.BOTTOM: 270,  # Face up (into room)
        }
        internal_angle = internal_angle_map.get(self._edge, 0)

        # Position for internal connector (on far side of building body from edge)
        internal_pos_map = {
            EdgeSide.LEFT: (BUILDING_SIZE, 0),
            EdgeSide.RIGHT: (-BUILDING_SIZE, 0),
            EdgeSide.TOP: (0, BUILDING_SIZE),
            EdgeSide.BOTTOM: (0, -BUILDING_SIZE),
        }
        internal_pos = internal_pos_map.get(self._edge, (0, 0))

        # PORT_IN has output ports (internal connector is output)
        # PORT_OUT has input ports (internal connector is input)
        ports = self._output_ports if not self.is_output else self._input_ports
        for port in ports:
            port.setPos(internal_pos[0], internal_pos[1])
            port.angle = internal_angle
            port.update()

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
        """Paint the port: external half-circle + building body.

        The internal connector is handled by the PortItem child from BuildingItem.
        """
        # External half-circle color (on room edge)
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR

        # Draw external half-circle on room edge
        self._draw_half_circle(painter, color, self._edge.name.lower())

        # Draw building body
        body_rect = self._get_body_rect()
        self._draw_building_body(painter, body_rect)

    def _get_body_rect(self) -> QRectF:
        """Get the rectangle for the building body based on edge."""
        b = BUILDING_SIZE
        if self._edge == EdgeSide.LEFT:
            return QRectF(0, -b / 2, b, b)
        elif self._edge == EdgeSide.RIGHT:
            return QRectF(-b, -b / 2, b, b)
        elif self._edge == EdgeSide.TOP:
            return QRectF(-b / 2, 0, b, b)
        else:  # BOTTOM
            return QRectF(-b / 2, -b, b, b)

    def _draw_building_body(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the draggable building body inside the room."""
        painter.setPen(QPen(BUILDING_BORDER, 1.5))
        painter.setBrush(QBrush(BUILDING_COLOR))
        painter.drawRoundedRect(rect, 4, 4)

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
        """Handle mouse press - start belt connection from half-circle, or drag port."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on the half-circle (external connector) area
            local_pos = event.pos()
            if self._is_on_half_circle(local_pos) and self.is_output:
                # Start belt drag from output port's external connector
                scene_pos = self.scenePos()
                self.canvas.start_belt_drag(self.building.id, self.port_index, scene_pos)
                event.accept()
                return
        # Let BuildingItem handle selection and drag tracking
        super().mousePressEvent(event)

    def _is_on_half_circle(self, pos: QPointF) -> bool:
        """Check if a local position is on the half-circle area (not building body)."""
        r = PORT_RADIUS
        x, y = pos.x(), pos.y()

        if self._edge == EdgeSide.LEFT:
            # Half-circle is at x <= 0 for output, or we check the external side
            return x < r if self.is_output else x < 0
        elif self._edge == EdgeSide.RIGHT:
            # Half-circle is at x >= 0 for output
            return x > -r if self.is_output else x > 0
        elif self._edge == EdgeSide.TOP:
            return y < r if self.is_output else y < 0
        else:  # BOTTOM
            return y > -r if self.is_output else y > 0

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes - snap to room edge instead of grid."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            if isinstance(new_pos, QPointF):
                # Snap to nearest room edge (not grid)
                new_pos = self._snap_to_edge(new_pos)
                return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Redetermine which edge we're on and update port positions
            new_pos = self.pos()
            old_edge = self._edge
            self._edge = self._determine_edge((new_pos.x(), new_pos.y()))
            if self._edge != old_edge:
                self._update_port_positions_for_edge()
            self.update()
        # Let BuildingItem update model position and belts
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

    def get_scene_pos(self) -> QPointF:
        """Get the scene position of this port."""
        return self.scenePos()
