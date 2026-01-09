"""Graphics item for a room (blueprint) placement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core import Room, RoomPlacement
from satisfactory_planner.core.models import Building, BuildingType, Scene
from satisfactory_planner.ui.items.belt_item import BeltItem
from satisfactory_planner.ui.items.building_item import BuildingItem
from satisfactory_planner.ui.items.port_item import PortItem
from satisfactory_planner.ui.items.room_port_item import RoomPortItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Colors for linked rooms (cycle through these based on room id hash)
ROOM_COLORS = [
    QColor(100, 150, 200),  # Blue
    QColor(150, 100, 200),  # Purple
    QColor(200, 150, 100),  # Orange
    QColor(100, 200, 150),  # Teal
    QColor(200, 100, 150),  # Pink
    QColor(150, 200, 100),  # Lime
]


def _get_room_color(room_id: str) -> QColor:
    """Get a consistent color for a room based on its ID."""
    # Use hash to get a consistent color for the same room
    color_index = hash(room_id) % len(ROOM_COLORS)
    return ROOM_COLORS[color_index]


class RoomItem(QGraphicsRectItem):
    """A room placement on the canvas - contains child items for its contents.

    RoomItem renders a RoomPlacement. Since multiple placements can reference
    the same Room, edits to the Room's contents affect all RoomItems that
    reference it.
    """

    def __init__(
        self,
        placement: RoomPlacement,
        room: Room,
        parent_scene: Scene,
        canvas: FactoryCanvas,
    ) -> None:
        super().__init__()

        self.placement = placement
        self.room = room
        self.parent_scene = parent_scene
        self.canvas = canvas

        # Setup visual rect (local coords: 0,0 to width,height)
        self.setRect(0, 0, room.width, room.height)
        self.setPos(placement.x, placement.y)

        # Flags for selection/movement in parent scene
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Z-value: rooms are behind top-level buildings but their children are on top
        self.setZValue(-0.5)

        # Child item tracking (all parented to this item for coordinate transform)
        self._building_items: dict[str, BuildingItem] = {}
        self._belt_items: dict[str, BeltItem] = {}
        self._room_items: dict[str, RoomItem] = {}
        self._port_items: list[RoomPortItem] = []
        self._room_port_items: dict[str, PortItem] = {}  # External ports on room edge

        # Populate child items
        self._populate_children()

    def _populate_children(self) -> None:
        """Create child graphics items for room contents."""
        # Buildings inside the room - note: scene=self.room, not self.parent_scene
        # Skip PORT_IN/PORT_OUT buildings - they're rendered by RoomPortItem instead
        for building in self.room.buildings.values():
            if building.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
                continue
            building_item = BuildingItem(building, self.canvas, scene=self.room)
            building_item.setParentItem(self)  # Qt parent = coordinate transform
            # Re-apply position after parenting (BuildingItem sets pos in __init__
            # before parenting, which can cause incorrect positioning)
            building_item.setPos(building.x, building.y)
            # Set placement ID for flow solver lookup with composite key
            building_item.set_placement_id(self.placement.id)
            self._building_items[building.id] = building_item

        # Belts inside the room
        for belt in self.room.belts.values():
            source = self.room.buildings.get(belt.source_building_id)
            dest = self.room.buildings.get(belt.dest_building_id)
            if source and dest:
                belt_item = BeltItem(belt, self.canvas, source, dest, scene=self.room)
                belt_item.setParentItem(self)
                # Set placement ID for flow solver lookup with composite key
                belt_item.set_placement_id(self.placement.id)
                self._belt_items[belt.id] = belt_item

        # Nested room placements
        # Find placements whose parent_room_id matches this room
        for p in self.canvas.document.room_placements.values():
            if p.parent_room_id == self.room.id:
                nested_room = self.canvas.document.rooms.get(p.room_id)
                if nested_room:
                    room_item = RoomItem(p, nested_room, parent_scene=self.room, canvas=self.canvas)
                    room_item.setParentItem(self)
                    self._room_items[p.id] = room_item

        # Create interactive port items on the room boundary
        self._create_port_items()

        # Create room-level ports (external connectors on room edge)
        self._create_room_ports()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the room boundary, name, and port symbols."""
        rect = self.rect()

        # Check if room has multiple placements (linked)
        placements = self.canvas.document.get_placements_for_room(self.room.id)
        is_linked = len(placements) > 1

        # Room boundary style
        if is_linked:
            # Linked rooms get a distinct color
            color = _get_room_color(self.room.id)
            pen = QPen(color, 2, Qt.PenStyle.SolidLine)
        else:
            # Single placement - dashed gray
            pen = QPen(QColor(100, 100, 100), 2, Qt.PenStyle.DashLine)

        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(50, 50, 55, 100)))
        painter.drawRect(rect)

        # Port symbols are now rendered by RoomPortItem children

        # Selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 0), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))

        # Room name at top
        painter.setPen(QPen(QColor(200, 200, 200)))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        # Draw name centered at top, with some padding
        name_rect = QRectF(rect.x(), rect.y() + 4, rect.width(), 20)
        painter.drawText(
            name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.room.name
        )

    def _create_port_items(self) -> None:
        """Create interactive RoomPortItem for each PORT building in the room."""
        for building in self.room.buildings.values():
            if building.building_type not in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
                continue

            port_item = RoomPortItem(
                room_item=self,
                building=building,
                canvas=self.canvas,
            )
            # Set placement ID for flow solver lookup with composite key
            port_item.set_placement_id(self.placement.id)
            self._port_items.append(port_item)
            # Register in _building_items so belt connector can find them
            self._building_items[building.id] = port_item

    def _create_room_ports(self) -> None:
        """Create PortItem children for each PORT building's external connector.

        These are the room's input/output ports where external belts connect.
        Position and angle are derived from the PORT building's position and rotation.

        Note: These ports connect to the PARENT scene (where the room is placed),
        not inside the room. So scene_room_id is the parent's room id (or None for document).
        """
        # Get parent scene's room id from the Scene protocol
        parent_scene_room_id = self.parent_scene.scene_room_id

        for building in self.room.buildings.values():
            if building.building_type not in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
                continue

            is_output = building.building_type == BuildingType.PORT_OUT
            x, y, angle = self._get_room_port_position(building)

            port_item = PortItem(
                is_output=is_output,
                port_index=building.port_index or 0,
                building_id=self.placement.id,
                canvas=self.canvas,
                angle=angle,
                scene_room_id=parent_scene_room_id,
            )
            port_item.setParentItem(self)
            port_item.setPos(x, y)
            port_item.setZValue(1)
            self._room_port_items[building.id] = port_item

    def _get_room_port_position(self, building: Building) -> tuple[float, float, float]:
        """Get room port position and angle based on PORT building position/rotation.

        Returns (x, y, angle) for the room's external port (the PortItem on room edge).

        Port angles follow the puzzle piece model:
        - Output ports (tabs): half-circle curves OUTWARD from room
        - Input ports (blanks): half-circle curves INWARD into room

        The angle is where the curved part faces.
        """
        base_w, base_h = building._get_display_size()
        is_output = building.building_type == BuildingType.PORT_OUT

        # Use building rotation to determine which edge it's on
        # 0° = left, 180° = right, 90° = top, 270° = bottom
        rotation = building.rotation

        # For top/bottom edges, the visual center x is at the center of the
        # VISUAL width (base_h after rotation), not the unrotated width.
        # The building.x is the unrotated top-left, and the visual rect is
        # centered around (base_w/2, base_h/2), so visual center x =
        # building.x + base_w/2 for the unrotated center, which after rotation
        # becomes the visual center of the 40x20 rect.

        if rotation == 0:
            # Left edge - port on left side of building, at vertical center
            x = building.x
            y = building.y + base_h / 2
            # PORT_IN: blank faces right (into room), PORT_OUT: tab faces left (out)
            angle = 0 if not is_output else 180
        elif rotation == 180:
            # Right edge - port on right side of building
            x = building.x + base_w
            y = building.y + base_h / 2
            # PORT_IN: blank faces left (into room), PORT_OUT: tab faces right (out)
            angle = 180 if not is_output else 0
        elif rotation == 90:
            # Top edge - port at visual center of rotated building
            # Rotation is around (base_w/2, base_h/2), so visual center x = building.x + base_w/2
            x = building.x + base_w / 2
            y = 0  # Top edge of room
            # PORT_IN: blank faces down (into room), PORT_OUT: tab faces up (out)
            angle = 90 if not is_output else 270
        else:  # rotation == 270
            # Bottom edge - port at visual center of rotated building
            x = building.x + base_w / 2
            y = self.room.height  # Bottom edge of room
            # PORT_IN: blank faces up (into room), PORT_OUT: tab faces down (out)
            angle = 270 if not is_output else 90

        return (x, y, angle)

    def _clear_room_ports(self) -> None:
        """Remove all room-level port items."""
        for port_item in self._room_port_items.values():
            if port_item.scene():
                port_item.scene().removeItem(port_item)
        self._room_port_items.clear()

    def _clear_port_items(self) -> None:
        """Remove all port items."""
        for port_item in self._port_items:
            if port_item.scene():
                port_item.scene().removeItem(port_item)
        self._port_items.clear()

    def update_room_ports(self) -> None:
        """Called when a PORT building moves - update room edge port positions and belts."""
        # Reposition room-level ports to match their PORT buildings
        for building in self.room.buildings.values():
            if building.id not in self._room_port_items:
                continue

            port_item = self._room_port_items[building.id]
            x, y, angle = self._get_room_port_position(building)
            port_item.setPos(x, y)
            port_item.angle = angle
            port_item.update()

        # Update external belts connected to this room's ports
        self.canvas._update_belts_for_placement(self.placement.id)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press - enforce scene-local selection."""
        # Enforce scene-local selection before Qt handles selection
        self.canvas.on_item_clicked(self)
        super().mousePressEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes."""

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # Snap to grid
            new_pos = value
            if isinstance(new_pos, QPointF) and self.canvas.grid_snap:
                grid = self.canvas.grid_size
                x = round(new_pos.x() / grid) * grid
                y = round(new_pos.y() / grid) * grid
                new_pos = QPointF(x, y)
            return new_pos

        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            # Update placement position in model
            new_pos = self.pos()
            self.placement.x = new_pos.x()
            self.placement.y = new_pos.y()
            # Update belts connected to this room's ports
            self.canvas._update_belts_for_placement(self.placement.id)

        return super().itemChange(change, value)

    def add_building_item(self, building_id: str) -> BuildingItem | None:
        """Add a building item for a building that was added to the room."""
        building = self.room.buildings.get(building_id)
        if not building:
            return None

        item = BuildingItem(building, self.canvas, scene=self.room)
        item.setParentItem(self)
        # Re-apply position after parenting
        item.setPos(building.x, building.y)
        # Set placement ID for flow solver lookup with composite key
        item.set_placement_id(self.placement.id)
        self._building_items[building_id] = item
        return item

    def remove_building_item(self, building_id: str) -> None:
        """Remove a building item."""
        item = self._building_items.pop(building_id, None)
        if item and item.scene():
            item.scene().removeItem(item)

    def add_belt_item(self, belt_id: str) -> BeltItem | None:
        """Add a belt item for a belt that was added to the room."""
        belt = self.room.belts.get(belt_id)
        if not belt:
            return None

        source = self.room.buildings.get(belt.source_building_id)
        dest = self.room.buildings.get(belt.dest_building_id)
        if source and dest:
            item = BeltItem(belt, self.canvas, source, dest, scene=self.room)
            item.setParentItem(self)
            # Set placement ID for flow solver lookup with composite key
            item.set_placement_id(self.placement.id)
            self._belt_items[belt_id] = item
            return item
        return None

    def remove_belt_item(self, belt_id: str) -> None:
        """Remove a belt item."""
        item = self._belt_items.pop(belt_id, None)
        if item and item.scene():
            item.scene().removeItem(item)

    def refresh(self) -> None:
        """Refresh all child items from the room data."""
        # Clear existing children
        for building_item in self._building_items.values():
            if building_item.scene():
                building_item.scene().removeItem(building_item)
        for belt_item in self._belt_items.values():
            if belt_item.scene():
                belt_item.scene().removeItem(belt_item)
        for room_item in self._room_items.values():
            if room_item.scene():
                room_item.scene().removeItem(room_item)
        self._clear_port_items()

        self._building_items.clear()
        self._belt_items.clear()
        self._room_items.clear()
        self._clear_room_ports()
        self._room_port_items.clear()

        # Repopulate
        self._populate_children()
        self.update()
