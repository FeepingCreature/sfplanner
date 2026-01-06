"""Factory canvas using QGraphicsView."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QWheelEvent, QMouseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
)

from satisfactory_planner.core import (
    Document,
    CommandStack,
    BuildingType,
    Building,
    Belt,
    PlaceBuildingCommand,
    DeleteItemsCommand,
    MoveBuildingsCommand,
    ConnectBeltCommand,
)
from satisfactory_planner.core.models import generate_id
from satisfactory_planner.ui.items.building_item import BuildingItem
from satisfactory_planner.ui.items.belt_item import BeltItem

if TYPE_CHECKING:
    pass


class GhostBuildingItem(BuildingItem):
    """Semi-transparent preview of building being placed."""

    def __init__(self, building: Building, canvas: "FactoryCanvas") -> None:
        super().__init__(building, canvas)
        self.setOpacity(0.6)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)


class FactoryCanvas(QGraphicsView):
    """The main factory canvas for placing buildings and belts."""

    # Signals
    selection_changed = Signal(list)  # List of selected item IDs
    document_changed = Signal()  # Emitted when document is modified

    def __init__(
        self, document: Document, command_stack: CommandStack, parent: QGraphicsView | None = None
    ) -> None:
        super().__init__(parent)

        self.document = document
        self.command_stack = command_stack

        self._setup_scene()
        self._setup_view()

        # Interaction state
        self._placement_mode: BuildingType | None = None
        self._placement_rotation: int = 0  # 0, 90, 180, 270
        self._ghost_item: GhostBuildingItem | None = None
        self._is_panning = False
        self._pan_start = QPointF()
        self._is_connecting = False
        self._connect_start_building: str | None = None
        self._connect_start_port: int = 0
        self._grid_snap = True
        self._grid_size = 20

        # Item tracking
        self._building_items: dict[str, BuildingItem] = {}
        self._belt_items: dict[str, BeltItem] = {}

        # Enable drag-drop
        self.setAcceptDrops(True)

    def _setup_scene(self) -> None:
        """Initialize the graphics scene."""
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)

    def _setup_view(self) -> None:
        """Configure view settings."""
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        
        # Make canvas focusable for keyboard events
        self.setFocusPolicy(Qt.StrongFocus)

        # Background
        self.setBackgroundBrush(QBrush(QColor(40, 40, 45)))

    def set_document(self, document: Document, command_stack: CommandStack) -> None:
        """Set a new document."""
        self.document = document
        self.command_stack = command_stack
        self.refresh()

    def set_grid_snap(self, enabled: bool) -> None:
        """Enable or disable grid snapping."""
        self._grid_snap = enabled
        self.viewport().update()

    def set_placement_mode(self, building_type: BuildingType | None) -> None:
        """Enter placement mode for a building type."""
        # Clean up old ghost
        if self._ghost_item:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None

        self._placement_mode = building_type
        self._placement_rotation = 0

        if building_type:
            self.setCursor(Qt.CrossCursor)
            # Create ghost building for preview
            ghost_building = Building(
                id="ghost",
                building_type=building_type,
                x=0,
                y=0,
            )
            self._ghost_item = GhostBuildingItem(ghost_building, self)
            self._ghost_item.setVisible(False)
            self._scene.addItem(self._ghost_item)
        else:
            self.setCursor(Qt.ArrowCursor)

    def refresh(self) -> None:
        """Refresh all items from the document."""
        # Clear existing items
        for item in list(self._building_items.values()):
            self._scene.removeItem(item)
        for item in list(self._belt_items.values()):
            self._scene.removeItem(item)
        self._building_items.clear()
        self._belt_items.clear()

        # Add buildings
        for building in self.document.buildings.values():
            self._add_building_item(building)

        # Add belts
        for belt in self.document.belts.values():
            self._add_belt_item(belt)

    def _add_building_item(self, building: Building) -> BuildingItem:
        """Add a building item to the scene."""
        item = BuildingItem(building, self)
        self._scene.addItem(item)
        self._building_items[building.id] = item
        return item

    def _add_belt_item(self, belt: Belt) -> BeltItem | None:
        """Add a belt item to the scene."""
        source = self.document.buildings.get(belt.source_building_id)
        dest = self.document.buildings.get(belt.dest_building_id)
        if source and dest:
            item = BeltItem(belt, source, dest)
            self._scene.addItem(item)
            self._belt_items[belt.id] = item
            return item
        return None

    def _snap_to_grid(self, pos: QPointF) -> QPointF:
        """Snap a position to the grid if enabled."""
        if self._grid_snap:
            x = round(pos.x() / self._grid_size) * self._grid_size
            y = round(pos.y() / self._grid_size) * self._grid_size
            return QPointF(x, y)
        return pos

    # Event handlers

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle zoom with mouse wheel, rotation in placement mode."""
        if self._placement_mode and self._ghost_item:
            # Rotate building in placement mode
            if event.angleDelta().y() > 0:
                self._placement_rotation = (self._placement_rotation + 90) % 360
            else:
                self._placement_rotation = (self._placement_rotation - 90) % 360
            self._ghost_item.rotation_angle = self._placement_rotation
            self._ghost_item.update()
            return

        # Normal zoom
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press."""
        scene_pos = self.mapToScene(event.pos())

        # Middle mouse for panning
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        # Right click to cancel placement
        if event.button() == Qt.RightButton and self._placement_mode:
            self.set_placement_mode(None)
            return

        # Left click
        if event.button() == Qt.LeftButton:
            # Placement mode
            if self._placement_mode:
                snapped = self._snap_to_grid(scene_pos)
                self._place_building(self._placement_mode, snapped.x(), snapped.y())
                # Stay in placement mode for rapid placement
                return

        super().mousePressEvent(event)
        self._emit_selection_changed()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move."""
        if self._is_panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            return

        # Update ghost position in placement mode
        if self._placement_mode and self._ghost_item:
            scene_pos = self.mapToScene(event.pos())
            snapped = self._snap_to_grid(scene_pos)
            self._ghost_item.setPos(snapped)
            self._ghost_item.setVisible(True)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        if event.button() == Qt.MiddleButton and self._is_panning:
            self._is_panning = False
            if self._placement_mode:
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return

        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter for building placement."""
        if event.mimeData().hasFormat("application/x-building-type"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag move."""
        if event.mimeData().hasFormat("application/x-building-type"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop to place building."""
        if event.mimeData().hasFormat("application/x-building-type"):
            building_name = event.mimeData().data("application/x-building-type").data().decode()
            # Find the BuildingType by value
            building_type = None
            for bt in BuildingType:
                if bt.value == building_name:
                    building_type = bt
                    break

            if building_type:
                scene_pos = self.mapToScene(event.position().toPoint())
                snapped = self._snap_to_grid(scene_pos)
                self._place_building(building_type, snapped.x(), snapped.y())
                event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _place_building(self, building_type: BuildingType, x: float, y: float) -> None:
        """Place a new building at the given position."""
        building = Building(
            id=generate_id(),
            building_type=building_type,
            x=x,
            y=y,
        )
        cmd = PlaceBuildingCommand(document=self.document, building=building)
        self.command_stack.execute(cmd)
        item = self._add_building_item(building)
        item.rotation_angle = self._placement_rotation
        self.document_changed.emit()

    def delete_selection(self) -> None:
        """Delete selected items."""
        selected_buildings: list[str] = []
        selected_belts: list[str] = []

        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                selected_buildings.append(item.building.id)
            elif isinstance(item, BeltItem):
                selected_belts.append(item.belt.id)

        if selected_buildings or selected_belts:
            # Also delete belts connected to deleted buildings
            for building_id in selected_buildings:
                for belt in self.document.get_belts_for_building(building_id):
                    if belt.id not in selected_belts:
                        selected_belts.append(belt.id)

            cmd = DeleteItemsCommand(
                document=self.document,
                building_ids=selected_buildings,
                belt_ids=selected_belts,
            )
            self.command_stack.execute(cmd)
            self.refresh()
            self.document_changed.emit()

    def _emit_selection_changed(self) -> None:
        """Emit signal with current selection."""
        selected_ids = []
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                selected_ids.append(item.building.id)
            elif isinstance(item, BeltItem):
                selected_ids.append(item.belt.id)
        self.selection_changed.emit(selected_ids)

    def start_belt_connection(self, building_id: str, port_index: int) -> None:
        """Start a belt connection from an output port."""
        self._is_connecting = True
        self._connect_start_building = building_id
        self._connect_start_port = port_index
        self.setCursor(Qt.CrossCursor)

    def complete_belt_connection(self, building_id: str, port_index: int) -> None:
        """Complete a belt connection to an input port."""
        if self._is_connecting and self._connect_start_building:
            belt = Belt(
                id=generate_id(),
                tier=1,  # Default to Mk.1
                source_building_id=self._connect_start_building,
                source_port_index=self._connect_start_port,
                dest_building_id=building_id,
                dest_port_index=port_index,
            )
            cmd = ConnectBeltCommand(document=self.document, belt=belt)
            self.command_stack.execute(cmd)
            self._add_belt_item(belt)
            self.document_changed.emit()

        self._is_connecting = False
        self._connect_start_building = None
        self.setCursor(Qt.ArrowCursor)

    def cancel_belt_connection(self) -> None:
        """Cancel the current belt connection."""
        self._is_connecting = False
        self._connect_start_building = None
        self.setCursor(Qt.ArrowCursor)

    def keyPressEvent(self, event: object) -> None:
        """Handle key presses."""
        from PySide6.QtGui import QKeyEvent
        if isinstance(event, QKeyEvent):
            if event.key() == Qt.Key_Delete:
                self.delete_selection()
                return
            elif event.key() == Qt.Key_Escape:
                if self._placement_mode:
                    self.set_placement_mode(None)
                elif self._is_connecting:
                    self.cancel_belt_connection()
                return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def on_building_moved(self, building_id: str, dx: float, dy: float) -> None:
        """Handle a building being moved."""
        # First update the model position to match visual
        building = self.document.buildings.get(building_id)
        if building:
            item = self._building_items.get(building_id)
            if item:
                # Sync model to visual position (in case of grid snap adjustments)
                building.x = item.pos().x()
                building.y = item.pos().y()
        
        # Create command for undo (but don't double-apply - model already updated)
        # We need to track the delta for undo purposes
        cmd = MoveBuildingsCommand(
            document=self.document,
            building_ids=[building_id],
            dx=dx,
            dy=dy,
            already_applied=True,  # Flag that model is already at new position
        )
        self.command_stack.execute(cmd)

        # Redraw all connected belts using absolute positions from model
        self._update_belts_for_building(building_id)

        self.document_changed.emit()

    def _update_belts_for_building(self, building_id: str) -> None:
        """Redraw all belts connected to a building using current model positions."""
        for belt in self.document.get_belts_for_building(building_id):
            belt_item = self._belt_items.get(belt.id)
            if belt_item:
                source = self.document.buildings.get(belt.source_building_id)
                dest = self.document.buildings.get(belt.dest_building_id)
                if source and dest:
                    belt_item.update_path(source, dest)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the grid background."""
        super().drawBackground(painter, rect)

        if not self._grid_snap:
            return

        # Draw grid
        left = int(rect.left()) - (int(rect.left()) % self._grid_size)
        top = int(rect.top()) - (int(rect.top()) % self._grid_size)

        lines = []
        x = left
        while x < rect.right():
            lines.append((x, rect.top(), x, rect.bottom()))
            x += self._grid_size

        y = top
        while y < rect.bottom():
            lines.append((rect.left(), y, rect.right(), y))
            y += self._grid_size

        pen = QPen(QColor(60, 60, 65), 0.5)
        painter.setPen(pen)
        for x1, y1, x2, y2 in lines:
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
