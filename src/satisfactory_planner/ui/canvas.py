"""Factory canvas using QGraphicsView."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
)

from satisfactory_planner.core import (
    DEFAULT_GRID_SIZE,
    Belt,
    Building,
    BuildingType,
    Document,
)
from satisfactory_planner.core.models import generate_id
import copy
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path
from satisfactory_planner.ui.commands import (
    BuildingMove,
    CommandStack,
    ConnectBeltCommand,
    DeleteItemsCommand,
    MoveBuildingsCommand,
    PlaceBuildingCommand,
)
from satisfactory_planner.ui.items.belt_item import BeltItem
from satisfactory_planner.ui.items.building_item import BuildingItem

if TYPE_CHECKING:
    pass


class GhostBuildingItem(BuildingItem):
    """Semi-transparent preview of building being placed."""

    def __init__(self, building: Building, canvas: FactoryCanvas) -> None:
        super().__init__(building, canvas)
        self.setOpacity(0.6)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)


class FactoryCanvas(QGraphicsView):
    """The main factory canvas for placing buildings and belts.

    Implements CommandHandler protocol to receive UI updates from commands.
    """

    # Signals
    selection_changed = Signal(list)  # List of selected item IDs
    # Note: document_changed signal removed - commands now call handler methods directly

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
        self._grid_size = DEFAULT_GRID_SIZE

        # Item tracking
        self._building_items: dict[str, BuildingItem] = {}
        self._belt_items: dict[str, BeltItem] = {}

        # Belt drag preview
        self._drag_preview: QGraphicsPathItem | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_start_dir: float = 0  # Direction belt leaves start port
        self._hover_target_port: object | None = None  # PortItem being hovered during drag

        # Mutation callback (set by MainWindow to handle warnings, dirty flag, etc.)
        self._mutation_callback: Callable[[], None] | None = None

        # Clipboard for copy/paste
        self._clipboard_buildings: list[Building] = []
        self._clipboard_belts: list[Belt] = []

        # Enable drag-drop
        self.setAcceptDrops(True)

    def _setup_scene(self) -> None:
        """Initialize the graphics scene."""
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)

    def _setup_view(self) -> None:
        """Configure view settings."""
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # Make canvas focusable for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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

    @property
    def grid_snap(self) -> bool:
        """Return whether grid snapping is enabled."""
        return self._grid_snap

    @property
    def grid_size(self) -> int:
        """Return the grid size."""
        return self._grid_size

    def update_belts_for_building(self, building_id: str) -> None:
        """Redraw all belts connected to a building."""
        self._update_belts_for_building(building_id)

    def set_placement_mode(self, building_type: BuildingType | None) -> None:
        """Enter placement mode for a building type."""
        # Clean up old ghost
        if self._ghost_item:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None

        self._placement_mode = building_type
        self._placement_rotation = 0

        if building_type:
            self.setCursor(Qt.CursorShape.CrossCursor)
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
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def refresh(self) -> None:
        """Refresh all items from the document."""
        # Clear existing items
        for building_item in list(self._building_items.values()):
            self._scene.removeItem(building_item)
        for belt_item in list(self._belt_items.values()):
            self._scene.removeItem(belt_item)
        self._building_items.clear()
        self._belt_items.clear()

        # Add buildings
        for building in self.document.buildings.values():
            self._add_building_item(building)

        # Add belts
        for belt in self.document.belts.values():
            self._add_belt_item(belt)

    # CommandHandler protocol implementation

    def add_building_item(self, building: Building) -> BuildingItem:
        """Add a building item to the scene (CommandHandler protocol)."""
        item = BuildingItem(building, self)
        self._scene.addItem(item)
        self._building_items[building.id] = item
        return item

    def remove_building_item(self, building_id: str) -> None:
        """Remove a building item from the scene (CommandHandler protocol)."""
        item = self._building_items.pop(building_id, None)
        if item:
            self._scene.removeItem(item)

    def add_belt_item(self, belt: Belt) -> BeltItem | None:
        """Add a belt item to the scene (CommandHandler protocol)."""
        source = self.document.buildings.get(belt.source_building_id)
        dest = self.document.buildings.get(belt.dest_building_id)
        if source and dest:
            item = BeltItem(belt, source, dest)
            self._scene.addItem(item)
            self._belt_items[belt.id] = item
            return item
        return None

    def remove_belt_item(self, belt_id: str) -> None:
        """Remove a belt item from the scene (CommandHandler protocol)."""
        item = self._belt_items.pop(belt_id, None)
        if item:
            self._scene.removeItem(item)

    def refresh_building(self, building_id: str) -> None:
        """Refresh a building's visual state (CommandHandler protocol)."""
        item = self._building_items.get(building_id)
        if item:
            # Update position from model
            building = self.document.buildings.get(building_id)
            if building:
                item.setPos(building.x, building.y)
            item.update()

    def refresh_belts_for_building(self, building_id: str) -> None:
        """Refresh belts connected to a building (CommandHandler protocol)."""
        self._update_belts_for_building(building_id)

    def refresh_belt(self, belt_id: str) -> None:
        """Refresh a belt's visual state (CommandHandler protocol)."""
        belt_item = self._belt_items.get(belt_id)
        belt = self.document.belts.get(belt_id)
        if belt_item and belt:
            source = self.document.buildings.get(belt.source_building_id)
            dest = self.document.buildings.get(belt.dest_building_id)
            if source and dest:
                belt_item.update_path(source, dest)

    def notify_mutation(self) -> None:
        """Notify that the document was mutated (CommandHandler protocol).

        This is called by commands after they modify the document.
        The MainWindow connects to this via a callback to update warnings, dirty flag, etc.
        """
        if self._mutation_callback:
            self._mutation_callback()

    # Legacy helper (used internally)
    def _add_building_item(self, building: Building) -> BuildingItem:
        """Internal helper - delegates to add_building_item."""
        return self.add_building_item(building)

    def _add_belt_item(self, belt: Belt) -> BeltItem | None:
        """Internal helper - delegates to add_belt_item."""
        return self.add_belt_item(belt)

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
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = QPointF(float(event.pos().x()), float(event.pos().y()))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # Right click to cancel placement
        if event.button() == Qt.MouseButton.RightButton and self._placement_mode:
            self.set_placement_mode(None)
            return

        # Left click - placement mode
        if event.button() == Qt.MouseButton.LeftButton and self._placement_mode:
            snapped = self._snap_to_grid(scene_pos)
            self._place_building(self._placement_mode, snapped.x(), snapped.y())
            # Stay in placement mode for rapid placement
            return

        super().mousePressEvent(event)
        self._emit_selection_changed()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move."""
        if self._is_panning:
            delta = event.pos() - self._pan_start.toPoint()
            self._pan_start = QPointF(float(event.pos().x()), float(event.pos().y()))
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return

        # Update belt drag preview and check for target port
        if self._drag_preview and self._drag_start_pos:
            scene_pos = self.mapToScene(event.pos())
            self._update_drag_preview(scene_pos)

            # Check if hovering over a valid input port
            from satisfactory_planner.ui.items.port_item import PortItem

            new_target = None
            for item in self._scene.items(scene_pos):
                if isinstance(item, PortItem) and not item.is_output:
                    new_target = item
                    break

            # Update hover state if target changed
            if new_target != self._hover_target_port:
                if self._hover_target_port:
                    self._hover_target_port.set_drag_target(False)  # type: ignore[attr-defined]
                if new_target:
                    new_target.set_drag_target(True)
                self._hover_target_port = new_target

        # Update ghost position in placement mode
        if self._placement_mode and self._ghost_item:
            scene_pos = self.mapToScene(event.pos())
            snapped = self._snap_to_grid(scene_pos)
            self._ghost_item.setPos(snapped)
            self._ghost_item.setVisible(True)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._is_panning = False
            if self._placement_mode:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # Cancel belt drag if released not on an input port
        if event.button() == Qt.MouseButton.LeftButton and self._is_connecting:
            # Check if we're over an input port - if not, cancel
            scene_pos = self.mapToScene(event.pos())
            from satisfactory_planner.ui.items.port_item import PortItem

            # Find all items at this point and look for an input port
            for item in self._scene.items(scene_pos):
                if isinstance(item, PortItem) and not item.is_output:
                    # Check if port is already connected
                    if self.document.is_port_connected(item.building_id, item.port_index, False):
                        # Port already has a connection - cancel
                        self.cancel_belt_connection()
                        super().mouseReleaseEvent(event)
                        return
                    self.complete_belt_connection(item.building_id, item.port_index)
                    super().mouseReleaseEvent(event)
                    return

            # No input port found - cancel
            self.cancel_belt_connection()

        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter for building placement."""
        if event.mimeData().hasFormat("application/x-building-type"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        """Handle drag move."""
        if event.mimeData().hasFormat("application/x-building-type"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop to place building."""
        if event.mimeData().hasFormat("application/x-building-type"):
            building_name = bytes(
                event.mimeData().data("application/x-building-type").data()
            ).decode()
            # Find the BuildingType by value
            building_type = None
            for bt in BuildingType:
                if bt.value == building_name:
                    building_type = bt
                    break

            if building_type:
                from satisfactory_planner.core import BUILDING_METADATA

                scene_pos = self.mapToScene(event.position().toPoint())
                # Center the building on the cursor (building pos is top-left)
                spec = BUILDING_METADATA.get(building_type)
                if spec:
                    scene_pos = QPointF(scene_pos.x() - spec.width / 2, scene_pos.y() - spec.height / 2)
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
        cmd = PlaceBuildingCommand(document=self.document, building=building, canvas=self)
        self.command_stack.execute(cmd)
        # Command already added the item via handler, but we need to set rotation
        item = self._building_items.get(building.id)
        if item:
            item.rotation_angle = self._placement_rotation

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

            # Collect the actual objects to delete (for immutable command)
            buildings_to_delete = tuple(
                self.document.buildings[bid]
                for bid in selected_buildings
                if bid in self.document.buildings
            )
            belts_to_delete = tuple(
                self.document.belts[bid] for bid in selected_belts if bid in self.document.belts
            )
            cmd = DeleteItemsCommand(
                document=self.document,
                buildings=buildings_to_delete,
                belts=belts_to_delete,
                canvas=self,
            )
            self.command_stack.execute(cmd)
            # Command handles UI updates via handler

    def _emit_selection_changed(self) -> None:
        """Emit signal with current selection."""
        selected_ids = []
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                selected_ids.append(item.building.id)
            elif isinstance(item, BeltItem):
                selected_ids.append(item.belt.id)
        self.selection_changed.emit(selected_ids)

    def start_belt_drag(self, building_id: str, port_index: int, start_pos: QPointF) -> None:
        """Start dragging a belt connection from an output port."""
        # Check if output port is already connected
        if self.document.is_port_connected(building_id, port_index, True):
            return  # Don't allow starting a new connection from an already-connected output

        self._is_connecting = True
        self._connect_start_building = building_id
        self._connect_start_port = port_index
        self._drag_start_pos = start_pos
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Get start direction from the source building
        building = self.document.buildings.get(building_id)
        if building:
            self._drag_start_dir = building.output_port_direction(port_index)
        else:
            self._drag_start_dir = 0

        # Create preview path (not pickable so it doesn't block mouse events)
        self._drag_preview = QGraphicsPathItem()
        self._drag_preview.setPen(QPen(QColor(100, 200, 100, 180), 3, Qt.PenStyle.DashLine))
        self._drag_preview.setZValue(1000)  # On top
        self._drag_preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._drag_preview.setAcceptedMouseButtons(
            Qt.MouseButton.NoButton
        )  # Ignore all mouse events
        self._scene.addItem(self._drag_preview)

    def is_dragging_belt(self) -> bool:
        """Return True if currently dragging a belt connection."""
        return self._is_connecting and self._drag_preview is not None

    def _update_drag_preview(self, end_pos: QPointF) -> None:
        """Update the drag preview path to the given end position."""
        import math

        if not self._drag_preview or not self._drag_start_pos:
            return

        start = Point(self._drag_start_pos.x(), self._drag_start_pos.y())
        end = Point(end_pos.x(), end_pos.y())

        # Default end direction: direction of travel toward end point
        dx = end_pos.x() - self._drag_start_pos.x()
        dy = end_pos.y() - self._drag_start_pos.y()
        end_dir = math.atan2(dy, dx)

        # Compute Dubins path and convert to QPainterPath
        belt_path = compute_belt_path(start, self._drag_start_dir, end, end_dir)
        path = belt_path_to_painter_path(start, end, belt_path)
        self._drag_preview.setPath(path)

    def start_belt_connection(self, building_id: str, port_index: int) -> None:
        """Start a belt connection from an output port (legacy, kept for compatibility)."""
        self._is_connecting = True
        self._connect_start_building = building_id
        self._connect_start_port = port_index
        self.setCursor(Qt.CursorShape.CrossCursor)

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
            cmd = ConnectBeltCommand(document=self.document, belt=belt, canvas=self)
            self.command_stack.execute(cmd)
            # Command handles UI updates via handler

        # Clean up drag state
        self._is_connecting = False
        self._connect_start_building = None
        self._drag_start_pos = None
        if self._drag_preview:
            self._scene.removeItem(self._drag_preview)
            self._drag_preview = None
        if self._hover_target_port:
            self._hover_target_port.set_drag_target(False)  # type: ignore[attr-defined]
            self._hover_target_port = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def cancel_belt_connection(self) -> None:
        """Cancel the current belt connection."""
        self._is_connecting = False
        self._connect_start_building = None
        self._drag_start_pos = None
        if self._drag_preview:
            self._scene.removeItem(self._drag_preview)
            self._drag_preview = None
        if self._hover_target_port:
            self._hover_target_port.set_drag_target(False)  # type: ignore[attr-defined]
            self._hover_target_port = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Handle key presses."""
        if event is None:
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selection()
            return
        elif event.key() == Qt.Key.Key_Escape:
            if self._placement_mode:
                self.set_placement_mode(None)
            elif self._is_connecting:
                self.cancel_belt_connection()
            return
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selection()
            return
        elif event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.paste()
            return
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.select_all()
            return
        super().keyPressEvent(event)

    def select_all(self) -> None:
        """Select all buildings and belts."""
        for building_item in self._building_items.values():
            building_item.setSelected(True)
        for belt_item in self._belt_items.values():
            belt_item.setSelected(True)
        self._emit_selection_changed()

    def copy_selection(self) -> None:
        """Copy selected buildings and their connecting belts to clipboard."""
        self._clipboard_buildings.clear()
        self._clipboard_belts.clear()

        selected_building_ids: set[str] = set()
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                # Deep copy the building
                self._clipboard_buildings.append(copy.deepcopy(item.building))
                selected_building_ids.add(item.building.id)

        # Copy belts that connect selected buildings to each other
        for belt in self.document.belts.values():
            if belt.source_building_id in selected_building_ids and belt.dest_building_id in selected_building_ids:
                self._clipboard_belts.append(copy.deepcopy(belt))

    def paste(self) -> None:
        """Paste buildings from clipboard at an offset from originals."""
        if not self._clipboard_buildings:
            return

        # Offset for pasted items
        offset = 50.0

        # Map old IDs to new IDs
        id_map: dict[str, str] = {}

        # Create new buildings with new IDs
        for old_building in self._clipboard_buildings:
            new_id = generate_id()
            id_map[old_building.id] = new_id
            new_building = Building(
                id=new_id,
                building_type=old_building.building_type,
                x=old_building.x + offset,
                y=old_building.y + offset,
                recipe_id=old_building.recipe_id,
                clock_speed=old_building.clock_speed,
                rotation=old_building.rotation,
            )
            cmd = PlaceBuildingCommand(document=self.document, building=new_building, canvas=self)
            self.command_stack.execute(cmd)

        # Create new belts with updated building references
        for old_belt in self._clipboard_belts:
            new_source = id_map.get(old_belt.source_building_id)
            new_dest = id_map.get(old_belt.dest_building_id)
            if new_source and new_dest:
                new_belt = Belt(
                    id=generate_id(),
                    tier=old_belt.tier,
                    source_building_id=new_source,
                    source_port_index=old_belt.source_port_index,
                    dest_building_id=new_dest,
                    dest_port_index=old_belt.dest_port_index,
                    item_id=old_belt.item_id,
                )
                belt_cmd = ConnectBeltCommand(document=self.document, belt=new_belt, canvas=self)
                self.command_stack.execute(belt_cmd)

        # Select the newly pasted buildings
        self._scene.clearSelection()
        for new_id in id_map.values():
            item = self._building_items.get(new_id)
            if item:
                item.setSelected(True)
        self._emit_selection_changed()

    def on_building_moved(
        self, building_id: str, old_x: float, old_y: float, old_rotation: int | None = None
    ) -> None:
        """Handle a building being moved and/or rotated.

        Args:
            building_id: The building that was moved
            old_x: Original x position before the move
            old_y: Original y position before the move
            old_rotation: Original rotation before the move (if changed)
        """
        building = self.document.buildings.get(building_id)
        if not building:
            return

        item = self._building_items.get(building_id)
        if not item:
            return

        # Get the new position from the visual item (may have grid snap applied)
        new_x = item.pos().x()
        new_y = item.pos().y()

        # Get rotation (use current if old not provided)
        new_rot = building.rotation
        old_rot = old_rotation if old_rotation is not None else new_rot

        # Sync model to visual position
        building.x = new_x
        building.y = new_y

        # Create immutable command with captured positions and rotation
        move = BuildingMove(
            building_id=building_id,
            old_x=old_x,
            old_y=old_y,
            old_rotation=old_rot,
            new_x=new_x,
            new_y=new_y,
            new_rotation=new_rot,
        )
        cmd = MoveBuildingsCommand(
            document=self.document,
            canvas=self,
            moves=(move,),
        )
        # Command will see model already at new position and log warning, which is fine
        # The important thing is the command captures old/new for undo/redo
        self.command_stack.execute(cmd)

        # Redraw all connected belts using absolute positions from model
        self._update_belts_for_building(building_id)

    def _update_belts_for_building(self, building_id: str) -> None:
        """Redraw all belts connected to a building using current model positions."""
        for belt in self.document.get_belts_for_building(building_id):
            belt_item = self._belt_items.get(belt.id)
            if belt_item:
                source = self.document.buildings.get(belt.source_building_id)
                dest = self.document.buildings.get(belt.dest_building_id)
                if source and dest:
                    belt_item.update_path(source, dest)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        """Draw the grid background."""
        super().drawBackground(painter, rect)

        if not self._grid_snap:
            return

        # Draw grid
        left = int(rect.left()) - (int(rect.left()) % self._grid_size)
        top = int(rect.top()) - (int(rect.top()) % self._grid_size)

        lines: list[tuple[int, float, int, float]] = []
        x = left
        while x < rect.right():
            lines.append((x, rect.top(), x, rect.bottom()))
            x += self._grid_size

        y = top
        while y < rect.bottom():
            lines.append((int(rect.left()), float(y), int(rect.right()), float(y)))
            y += self._grid_size

        pen = QPen(QColor(60, 60, 65), 0.5)
        painter.setPen(pen)
        for x1, y1, x2, y2 in lines:
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
