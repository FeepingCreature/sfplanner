"""Graphics item for a factory building."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core import (
    BUILDING_COLORS,
    Building,
    BuildingType,
)
from satisfactory_planner.core.flow_key import FlowKey
from satisfactory_planner.core.models import Scene
from satisfactory_planner.ui.items.port_item import PortItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


def _get_building_color(building_type: BuildingType) -> QColor:
    """Get QColor for a building type from the core color definitions."""
    rgb = BUILDING_COLORS.get(building_type, (150, 150, 150))
    return QColor(rgb[0], rgb[1], rgb[2])


class BuildingItem(QGraphicsRectItem):
    """A draggable building item on the canvas."""

    def __init__(
        self, building: Building, canvas: FactoryCanvas, scene: Scene | None = None
    ) -> None:
        super().__init__()

        self.building = building
        self.canvas = canvas
        # Scene this building belongs to (Document or Room)
        # If not provided, defaults to canvas.document for backwards compatibility
        self._scene: Scene = scene if scene is not None else canvas.document

        # Setup
        self._setup_rect()
        self._setup_flags()
        self._setup_ports()

        # Drag tracking
        self._drag_start_pos: QPointF | None = None
        self._drag_start_rotation: int = 0
        self._is_dragging: bool = False
        self._multi_drag_offsets: dict[str, QPointF] = {}

        # Efficiency overlay state
        self._show_efficiency = False
        self._efficiency_value: float | None = None  # 0.0 - 1.0
        self._is_starved = False
        self._is_blocked = False
        self._placement_id: str | None = None  # Set when building is inside a room placement

    def _get_display_size(self) -> tuple[int, int]:
        """Get display size - delegates to model."""
        return self.building._get_display_size()

    def boundingRect(self) -> QRectF:
        """Return bounding rect accounting for rotation."""
        import math

        w, h = self._get_display_size()
        if self.building.rotation == 0:
            return QRectF(-2, -2, w + 4, h + 4)  # Small margin for selection highlight

        # For rotated buildings, compute the axis-aligned bounding box
        rad = math.radians(self.building.rotation)
        cos_r, sin_r = abs(math.cos(rad)), abs(math.sin(rad))
        # Rotated width/height
        new_w = w * cos_r + h * sin_r
        new_h = w * sin_r + h * cos_r
        # Center offset
        cx, cy = w / 2, h / 2
        new_cx, new_cy = new_w / 2, new_h / 2
        offset_x = cx - new_cx
        offset_y = cy - new_cy
        return QRectF(offset_x - 2, offset_y - 2, new_w + 4, new_h + 4)

    def shape(self) -> QPainterPath:
        """Return shape for hit testing, accounting for rotation."""

        w, h = self._get_display_size()
        path = QPainterPath()
        path.addRect(QRectF(0, 0, w, h))

        if self.building.rotation != 0:
            # Transform the path by rotating around center
            transform = QTransform()
            transform.translate(w / 2, h / 2)
            transform.rotate(self.building.rotation)
            transform.translate(-w / 2, -h / 2)
            path = transform.map(path)

        return path

    def _setup_rect(self) -> None:
        """Configure the rectangle."""
        w, h = self._get_display_size()
        self.setRect(0, 0, w, h)
        self.setPos(self.building.x, self.building.y)

        color = _get_building_color(self.building.building_type)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(255, 255, 255), 2))

    def _setup_flags(self) -> None:
        """Configure item flags."""
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def _setup_ports(self) -> None:
        """Create port items based on building type and rotation."""
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []
        self._create_ports()

    def _create_ports(self) -> None:
        """Create the actual port items from building's port layout."""
        w, h = self._get_display_size()
        rotation = self.building.rotation

        # Get port layout from the building model
        input_layout, output_layout = self.building.get_port_layout()

        # Get scene_room_id from the Scene protocol
        scene_room_id = self._scene.scene_room_id

        # Create input ports
        for i, (px, py, base_angle) in enumerate(input_layout):
            angle = base_angle + rotation
            port = PortItem(
                False, i, self.building.id, self.canvas, angle=angle, scene_room_id=scene_room_id
            )
            port.setParentItem(self)
            port.setPos(*self._rotate_port_pos(px, py, w, h, rotation))
            self._input_ports.append(port)

        # Create output ports
        for i, (px, py, base_angle) in enumerate(output_layout):
            angle = base_angle + rotation
            port = PortItem(
                True, i, self.building.id, self.canvas, angle=angle, scene_room_id=scene_room_id
            )
            port.setParentItem(self)
            port.setPos(*self._rotate_port_pos(px, py, w, h, rotation))
            self._output_ports.append(port)

    def _rotate_port_pos(
        self, x: float, y: float, w: float, h: float, rotation: int
    ) -> tuple[float, float]:
        """Rotate a port position around the building center."""
        import math

        # Center of building
        cx, cy = w / 2, h / 2
        # Translate to origin
        dx, dy = x - cx, y - cy
        # Rotate
        rad = math.radians(rotation)
        rx = dx * math.cos(rad) - dy * math.sin(rad)
        ry = dx * math.sin(rad) + dy * math.cos(rad)
        # Translate back
        return cx + rx, cy + ry

    def _update_port_positions(self) -> None:
        """Update port positions and angles after rotation change."""
        # Remove existing ports
        for port in self._input_ports + self._output_ports:
            if port.scene():
                port.scene().removeItem(port)
        self._input_ports.clear()
        self._output_ports.clear()
        # Recreate with new rotation
        self._create_ports()

    @property
    def rotation_angle(self) -> int:
        """Get rotation angle from model."""
        return self.building.rotation

    @rotation_angle.setter
    def rotation_angle(self, value: int) -> None:
        """Set rotation angle on model and update port positions."""
        self.building.rotation = value
        self._update_port_positions()

    def rotate_building(self, delta: int = 90) -> None:
        """Rotate the building by delta degrees."""
        self.building.rotation = (self.building.rotation + delta) % 360
        self._update_port_positions()
        self.update()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the building."""
        w, h = self._get_display_size()
        rect = QRectF(0, 0, w, h)

        # Save state for rotation
        painter.save()

        # Apply rotation around center
        if self.rotation_angle != 0:
            painter.translate(w / 2, h / 2)
            painter.rotate(self.rotation_angle)
            painter.translate(-w / 2, -h / 2)

        # Draw the rectangle
        color = _get_building_color(self.building.building_type)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawRect(rect)

        painter.restore()

        # Draw the building name and recipe (always upright, centered)
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont()
        is_small = self.building.building_type in (
            BuildingType.SPLITTER,
            BuildingType.MERGER,
            BuildingType.PORT_IN,
            BuildingType.PORT_OUT,
        )
        font.setPointSize(7 if is_small else 8)
        painter.setFont(font)

        # Building type name
        name = self.building.building_type.value
        # Abbreviate for small buildings
        if self.building.building_type == BuildingType.SPLITTER:
            name = "SPL"
        elif self.building.building_type == BuildingType.MERGER:
            name = "MRG"
        elif self.building.building_type == BuildingType.PORT_IN:
            name = "IN"
        elif self.building.building_type == BuildingType.PORT_OUT:
            name = "OUT"

        # Get recipe name if available (skip for logistics)
        recipe_text = ""
        if not is_small:
            if self.building.building_type in (
                BuildingType.SOURCE,
                BuildingType.SINK,
                BuildingType.MINER,
            ):
                # For Source/Sink/Miner, recipe_id holds the item_id directly
                if self.building.recipe_id:
                    # Show the item name (recipe_id is actually item_id)
                    recipe_text = self.building.recipe_id.replace("_", " ").title()
                else:
                    recipe_text = "No Item"
            elif self.building.recipe_id:
                # Look up recipe in document
                doc = self.canvas.document
                recipe = doc.recipes.get(self.building.recipe_id)
                recipe_text = recipe.name if recipe else "No Recipe"
            else:
                recipe_text = "No Recipe"

        if recipe_text:
            # Draw building type at top, recipe in middle, efficiency at bottom
            row_height = h / 3
            top_rect = QRectF(0, 2, w, row_height - 2)
            middle_rect = QRectF(0, row_height, w, row_height)
            bottom_rect = QRectF(0, row_height * 2, w, row_height - 2)

            # Building name
            painter.drawText(
                top_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, name
            )

            # Recipe in smaller, slightly dimmer text
            painter.setPen(QPen(QColor(200, 200, 200)))
            small_font = QFont()
            small_font.setPointSize(7)
            painter.setFont(small_font)
            painter.drawText(
                middle_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                recipe_text,
            )

            # Load factor (efficiency) at bottom
            if self._efficiency_value is not None:
                pct = self._efficiency_value * 100
                if pct >= 99.9:
                    eff_text = "✓ 100%"
                    eff_color = QColor(100, 255, 100)
                elif pct >= 50:
                    eff_text = f"{pct:.0f}%"
                    eff_color = QColor(255, 200, 50)
                else:
                    eff_text = f"{pct:.0f}%"
                    eff_color = QColor(255, 100, 100)
                painter.setPen(QPen(eff_color))
                painter.drawText(
                    bottom_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, eff_text
                )
        else:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name)

        # Draw efficiency underlay if enabled (behind selection)
        if self._show_efficiency and self._efficiency_value is not None:
            painter.save()
            if self.rotation_angle != 0:
                painter.translate(w / 2, h / 2)
                painter.rotate(self.rotation_angle)
                painter.translate(-w / 2, -h / 2)

            # Color based on efficiency: green (100%) -> yellow (50%) -> red (0%)
            eff = self._efficiency_value
            if eff >= 0.99:
                eff_color = QColor(80, 255, 80, 180)  # Bright green
            elif eff >= 0.5:
                # Lerp from yellow to green
                t = (eff - 0.5) * 2
                eff_color = QColor(int(255 - t * 175), int(220 + t * 35), 50, 180)
            else:
                # Lerp from red to yellow
                t = eff * 2
                eff_color = QColor(255, int(t * 180), 50, 180)

            painter.setPen(QPen(eff_color, 5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-4, -4, 4, 4))
            painter.restore()

        # Draw selection highlight (rotated with the building)
        if self.isSelected():
            painter.save()
            if self.rotation_angle != 0:
                painter.translate(w / 2, h / 2)
                painter.rotate(self.rotation_angle)
                painter.translate(-w / 2, -h / 2)
            painter.setPen(QPen(QColor(255, 255, 0), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))
            painter.restore()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Track drag start."""
        self._drag_start_pos = self.pos()
        self._drag_start_rotation = self.building.rotation
        self._is_dragging = True

        # Enforce scene-local selection before Qt handles selection
        self.canvas.on_item_clicked(self)

        # Let Qt handle selection changes FIRST (e.g., clicking unselected item
        # clears old selection), then compute offsets based on new selection
        super().mousePressEvent(event)

        # For multi-select drag: compute offset from this item's position
        # All other selected items will move by the same delta (not snap individually)
        self._multi_drag_offsets.clear()
        for item in self.scene().selectedItems():
            if isinstance(item, BuildingItem) and item is not self:
                # Store offset from this building's current position
                self._multi_drag_offsets[item.building.id] = item.pos() - self.pos()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle drag end - create move command."""
        super().mouseReleaseEvent(event)

        if self._drag_start_pos is not None:
            new_pos = self.pos()
            moved = new_pos != self._drag_start_pos
            rotated = self.building.rotation != self._drag_start_rotation

            # Create single command if moved or rotated
            if moved or rotated:
                self.canvas.on_building_moved(
                    self,  # Pass the actual item, not just ID
                    self._drag_start_pos.x(),
                    self._drag_start_pos.y(),
                    self._drag_start_rotation,
                )

            self._drag_start_pos = None

        self._is_dragging = False
        # Clear multi-drag offsets to prevent stale data on next drag
        self._multi_drag_offsets = {}

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

            # Multi-select: move other selected buildings by same delta
            # Only the "lead" building snaps; others maintain relative positions
            if isinstance(new_pos, QPointF) and hasattr(self, "_multi_drag_offsets"):
                for building_id, offset in self._multi_drag_offsets.items():
                    other_item = self.canvas._building_items.get(building_id)
                    if other_item and other_item is not self:
                        # Temporarily disable the other item's individual snapping
                        other_item.setFlag(
                            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, False
                        )
                        other_item.setPos(new_pos + offset)
                        other_item.building.x = other_item.pos().x()
                        other_item.building.y = other_item.pos().y()
                        other_item.setFlag(
                            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True
                        )
                        self.canvas.update_belts_for_building(building_id, self._scene)

            return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            # Update model position
            new_pos = self.pos()
            self.building.x = new_pos.x()
            self.building.y = new_pos.y()

            # Let canvas handle all visual updates (linked rooms, belts, ports)
            self.canvas.sync_building_moved(
                self.building.id, self._scene.scene_room_id, source_item=self
            )
        return super().itemChange(change, value)

    def wheelEvent(self, event: object) -> None:
        """Handle mouse wheel for rotation while dragging."""
        from PySide6.QtWidgets import QGraphicsSceneWheelEvent

        if not isinstance(event, QGraphicsSceneWheelEvent):
            return

        if self._is_dragging:
            # Rotate building while dragging
            if event.delta() > 0:
                self.rotate_building(90)
            else:
                self.rotate_building(-90)
            event.accept()
        else:
            # Pass to parent for zoom
            event.ignore()

    @property
    def building_scene(self) -> Scene:
        """Get the scene this building belongs to."""
        return self._scene

    @building_scene.setter
    def building_scene(self, scene: Scene) -> None:
        """Set the scene this building belongs to."""
        self._scene = scene

    def set_show_efficiency(self, show: bool) -> None:
        """Toggle efficiency overlay display."""
        self._show_efficiency = show
        if show:
            self._update_efficiency_from_solver()
        self.update()

    def set_efficiency(
        self, value: float | None, starved: bool = False, blocked: bool = False
    ) -> None:
        """Set the efficiency value for overlay display."""
        self._efficiency_value = value
        self._is_starved = starved
        self._is_blocked = blocked
        self.update()

    @property
    def flow_key(self) -> FlowKey:
        """Get the flow solver key for this building."""
        return FlowKey(element_id=self.building.id, placement_id=self._placement_id)

    def set_placement_id(self, placement_id: str | None) -> None:
        """Set the placement ID for buildings inside room placements."""
        self._placement_id = placement_id

    def _update_efficiency_from_solver(self) -> None:
        """Fetch efficiency from flow solver."""
        from satisfactory_planner.ui.main_window import MainWindow

        main_window = self.canvas.window()
        if not isinstance(main_window, MainWindow) or not main_window.current_tab:
            return

        flow_solver = main_window.current_tab.flow_solver
        if flow_solver:
            eff = flow_solver.get_efficiency(self.flow_key)
            if eff:
                self.set_efficiency(eff.duty_cycle)
            else:
                self.set_efficiency(None)
