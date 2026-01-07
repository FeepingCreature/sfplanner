"""Factory canvas using QGraphicsView."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
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
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from satisfactory_planner.core import (
    DEFAULT_GRID_SIZE,
    SELECTION_MARGIN,
    Belt,
    Building,
    BuildingType,
    Document,
    Room,
)
from satisfactory_planner.core.models import Scene, generate_id
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.commands import (
    BuildingMove,
    CommandStack,
    ConnectBeltCommand,
    CreateRoomCommand,
    DeleteItemsCommand,
    MoveBuildingsCommand,
    PlaceBlueprintCommand,
    PlaceBuildingCommand,
)
from satisfactory_planner.ui.items.belt_item import BeltItem
from satisfactory_planner.ui.items.building_item import BuildingItem
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ToolMode(Enum):
    """Active tool mode for the canvas."""

    SELECT = auto()  # Click to select, drag to move
    BOX_SELECT = auto()  # Drag to box select
    PAN = auto()  # Drag to pan
    CREATE_ROOM = auto()  # Drag to create a room (one-shot)


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
        self._room_items: dict[str, object] = {}  # RoomItem, using object to avoid circular import

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
        self._clipboard_room_ids: list[str] = []  # Room IDs for shallow-copy paste

        # Drag-drop state for building placement from library
        self._drag_building_type: BuildingType | None = None
        self._drag_rotation: int = 0
        self._drag_ghost: GhostBuildingItem | None = None

        # Tool mode
        self._tool_mode: ToolMode = ToolMode.SELECT

        # Blueprint placement mode
        self._blueprint_placement_room: Room | None = None
        self._blueprint_ghost: QGraphicsRectItem | None = None

        # Box select state
        self._box_select_start: QPointF | None = None
        self._box_select_rect: QGraphicsRectItem | None = None

        # Room creation state (similar to box select)
        self._room_create_start: QPointF | None = None
        self._room_create_rect: QGraphicsRectItem | None = None

        # Selection outline (dashed rect around selected items)
        self._selection_outline: QGraphicsRectItem | None = None

        # Enable drag-drop
        self.setAcceptDrops(True)

    def _setup_scene(self) -> None:
        """Initialize the graphics scene."""
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)

        # Connect to selection changes to update outline and notify listeners
        self._scene.selectionChanged.connect(self._update_selection_outline)
        self._scene.selectionChanged.connect(self._emit_selection_changed)

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

    def update_belts_for_building(self, building_id: str, scene: Scene | None = None) -> None:
        """Redraw all belts connected to a building.

        Args:
            building_id: The building whose belts need updating
            scene: The scene containing the building (defaults to document for backwards compat)
        """
        self._update_belts_for_building(building_id, scene)

    def set_placement_mode(self, building_type: BuildingType | None) -> None:
        """Enter placement mode for a building type."""
        # Clean up old ghost
        if self._ghost_item:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None

        # Also clear blueprint placement mode
        self._clear_blueprint_placement()

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

    def set_blueprint_placement_mode(self, room: Room) -> None:
        """Enter placement mode for a blueprint (room from library).

        Creates a deep copy of the room with new IDs when placed.
        """
        # Clear building placement mode
        if self._ghost_item:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None
        self._placement_mode = None

        # Clear any previous blueprint placement
        self._clear_blueprint_placement()

        self._blueprint_placement_room = room
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Create ghost rectangle for preview
        self._blueprint_ghost = QGraphicsRectItem(0, 0, room.width, room.height)
        self._blueprint_ghost.setPen(QPen(QColor(100, 200, 100), 2, Qt.PenStyle.DashLine))
        self._blueprint_ghost.setBrush(QBrush(QColor(100, 200, 100, 50)))
        self._blueprint_ghost.setOpacity(0.7)
        self._blueprint_ghost.setVisible(False)
        self._blueprint_ghost.setZValue(1000)
        self._scene.addItem(self._blueprint_ghost)

    def _clear_blueprint_placement(self) -> None:
        """Clear blueprint placement mode."""
        self._blueprint_placement_room = None
        if self._blueprint_ghost:
            self._scene.removeItem(self._blueprint_ghost)
            self._blueprint_ghost = None

    def _place_blueprint(self, room: Room, x: float, y: float) -> None:
        """Place a blueprint (room from library) at the given position.

        Creates a deep copy of the room with new IDs for all contents,
        then creates a placement for it.
        """

        cmd = PlaceBlueprintCommand(
            source_room=room,
            x=x,
            y=y,
            canvas=self,
        )
        self.command_stack.execute(cmd)

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
        """Refresh belts connected to a building (CommandHandler protocol).

        If the building is in a Room, refreshes belts in ALL RoomItems that
        display that Room (linked instances all need updating).
        """
        # First, check if this building is in a room
        for room_id, room in self.document.rooms.items():
            if building_id in room.buildings:
                # Building is in a room - refresh all RoomItems that display this room
                self._refresh_all_room_items(room_id)
                return

        # Building is in root document
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

    def add_room_item(
        self,
        placement: object,
        room: object,  # RoomPlacement, Room - avoid circular import
    ) -> None:
        """Add a room item to the scene (CommandHandler protocol)."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        # Determine parent scene using getattr to avoid type errors
        parent_scene_id = getattr(placement, "parent_scene_id", None)
        if parent_scene_id:
            parent_scene: Scene = self.document.rooms[parent_scene_id]
        else:
            parent_scene = self.document

        room_item = RoomItem(placement, room, parent_scene, self)  # type: ignore[arg-type]
        self._scene.addItem(room_item)

        # Track the room item and all its children
        placement_id = getattr(placement, "id", "")
        self._room_items[placement_id] = room_item
        for building_id, building_item in room_item._building_items.items():
            self._building_items[building_id] = building_item
        for belt_id, belt_item in room_item._belt_items.items():
            self._belt_items[belt_id] = belt_item

    def remove_room_item(self, placement_id: str) -> None:
        """Remove a room item from the scene (CommandHandler protocol)."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        room_item = self._room_items.pop(placement_id, None)
        if room_item and isinstance(room_item, RoomItem):
            # Untrack all children
            for building_id in list(room_item._building_items.keys()):
                self._building_items.pop(building_id, None)
            for belt_id in list(room_item._belt_items.keys()):
                self._belt_items.pop(belt_id, None)
            self._scene.removeItem(room_item)

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
        """Handle zoom with mouse wheel, rotation in placement/drag mode."""

        # Case 1: Placement mode (click in library, then move to canvas)
        if self._placement_mode and self._ghost_item:
            if event.angleDelta().y() > 0:
                self._placement_rotation = (self._placement_rotation + 90) % 360
            else:
                self._placement_rotation = (self._placement_rotation - 90) % 360
            self._ghost_item.rotation_angle = self._placement_rotation
            self._ghost_item.update()
            return

        # Case 2: Dragging an existing building on canvas
        # Check if any selected building is being dragged
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem) and item._is_dragging:
                if event.angleDelta().y() > 0:
                    item.rotate_building(90)
                else:
                    item.rotate_building(-90)
                # Update connected belts
                self._update_belts_for_building(item.building.id)
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

        # Right click to cancel placement or box select
        if event.button() == Qt.MouseButton.RightButton:
            if self._placement_mode:
                self.set_placement_mode(None)
                return
            if self._blueprint_placement_room:
                self._clear_blueprint_placement()
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
            if self._box_select_start:
                self._cancel_box_select()
                return

        # Left click - placement mode
        if event.button() == Qt.MouseButton.LeftButton and self._placement_mode:
            snapped = self._snap_to_grid(scene_pos)
            self._place_building(self._placement_mode, snapped.x(), snapped.y())
            # Stay in placement mode for rapid placement
            return

        # Left click - blueprint placement mode
        if event.button() == Qt.MouseButton.LeftButton and self._blueprint_placement_room:
            snapped = self._snap_to_grid(scene_pos)
            self._place_blueprint(self._blueprint_placement_room, snapped.x(), snapped.y())
            # Exit placement mode after placing (unlike buildings)
            self._clear_blueprint_placement()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # Left click - box select mode (explicit tool or empty canvas in SELECT mode)
        if event.button() == Qt.MouseButton.LeftButton and self._tool_mode == ToolMode.BOX_SELECT:
            self._start_box_select(scene_pos)
            return

        # Left click - room creation mode (one-shot tool)
        if event.button() == Qt.MouseButton.LeftButton and self._tool_mode == ToolMode.CREATE_ROOM:
            self._start_room_create(scene_pos)
            return

        # Left click on empty canvas in SELECT mode - start box select
        if event.button() == Qt.MouseButton.LeftButton and self._tool_mode == ToolMode.SELECT:
            item_at_pos = self.itemAt(event.pos())
            # Check if clicking on empty space (no item or just the selection outline)
            if item_at_pos is None or item_at_pos is self._selection_outline:
                self._start_box_select(scene_pos)
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

        # Update box select rect
        if self._box_select_start and self._box_select_rect:
            scene_pos = self.mapToScene(event.pos())
            self._update_box_select(scene_pos)
            return

        # Update room creation rect
        if self._room_create_start and self._room_create_rect:
            scene_pos = self.mapToScene(event.pos())
            self._update_room_create(scene_pos)
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

        # Update blueprint ghost position
        if self._blueprint_placement_room and self._blueprint_ghost:
            scene_pos = self.mapToScene(event.pos())
            snapped = self._snap_to_grid(scene_pos)
            self._blueprint_ghost.setPos(snapped)
            self._blueprint_ghost.setVisible(True)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._is_panning = False
            if self._placement_mode or self._tool_mode == ToolMode.BOX_SELECT:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif self._tool_mode == ToolMode.PAN:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # Complete box select
        if event.button() == Qt.MouseButton.LeftButton and self._box_select_start:
            self._complete_box_select()
            return

        # Complete room creation
        if event.button() == Qt.MouseButton.LeftButton and self._room_create_start:
            self._complete_room_create()
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
        """Handle drag enter for building or blueprint placement."""
        if event.mimeData().hasFormat("application/x-building-type"):
            # Track drag state for wheel rotation
            building_name = bytes(
                event.mimeData().data("application/x-building-type").data()
            ).decode()
            for bt in BuildingType:
                if bt.value == building_name:
                    self._drag_building_type = bt
                    break
            self._drag_rotation = 0

            # Create ghost building for visual preview
            if self._drag_building_type:
                ghost_building = Building(
                    id="drag_ghost",
                    building_type=self._drag_building_type,
                    x=0,
                    y=0,
                )
                self._drag_ghost = GhostBuildingItem(ghost_building, self)
                scene_pos = self.mapToScene(event.position().toPoint())
                self._drag_ghost.setPos(self._snap_to_grid(scene_pos))
                self._scene.addItem(self._drag_ghost)

            # Install event filter to capture wheel events during drag
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-blueprint-room-id"):
            # Blueprint drag - get room from library panel's drag state
            from satisfactory_planner.ui.panels.library_panel import LibraryPanel

            # Find the library panel (it's the drag source)
            source = event.source()
            if source:
                parent = source.parent()
                while parent and not isinstance(parent, LibraryPanel):
                    parent = parent.parent()
                if isinstance(parent, LibraryPanel) and parent._dragging_blueprint:
                    self._blueprint_placement_room = parent._dragging_blueprint

                    # Create ghost rectangle for preview
                    room = self._blueprint_placement_room
                    self._blueprint_ghost = QGraphicsRectItem(0, 0, room.width, room.height)
                    self._blueprint_ghost.setPen(
                        QPen(QColor(100, 200, 100), 2, Qt.PenStyle.DashLine)
                    )
                    self._blueprint_ghost.setBrush(QBrush(QColor(100, 200, 100, 50)))
                    self._blueprint_ghost.setOpacity(0.7)
                    self._blueprint_ghost.setZValue(1000)
                    scene_pos = self.mapToScene(event.position().toPoint())
                    self._blueprint_ghost.setPos(self._snap_to_grid(scene_pos))
                    self._scene.addItem(self._blueprint_ghost)

            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        """Handle drag move - update ghost position."""
        if event.mimeData().hasFormat("application/x-building-type"):
            if self._drag_ghost:
                scene_pos = self.mapToScene(event.position().toPoint())
                # Center ghost on cursor
                w, h = self._drag_ghost.building._get_display_size()
                centered = QPointF(scene_pos.x() - w / 2, scene_pos.y() - h / 2)
                self._drag_ghost.setPos(self._snap_to_grid(centered))
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-blueprint-room-id"):
            if self._blueprint_ghost:
                scene_pos = self.mapToScene(event.position().toPoint())
                self._blueprint_ghost.setPos(self._snap_to_grid(scene_pos))
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        """Handle drag leave - clear drag state."""
        self._drag_building_type = None
        self._drag_rotation = 0
        # Remove building ghost
        if self._drag_ghost:
            self._scene.removeItem(self._drag_ghost)
            self._drag_ghost = None
        # Remove blueprint ghost
        self._clear_blueprint_placement()
        # Remove event filter
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        super().dragLeaveEvent(event)  # type: ignore[arg-type]

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        """Capture wheel events during drag-drop for building rotation."""
        if self._drag_building_type is not None and event.type() == QEvent.Type.Wheel:
            wheel_event: QWheelEvent = event  # type: ignore[assignment]
            if wheel_event.angleDelta().y() > 0:
                self._drag_rotation = (self._drag_rotation + 90) % 360
            else:
                self._drag_rotation = (self._drag_rotation - 90) % 360
            # Update ghost building rotation
            if self._drag_ghost:
                self._drag_ghost.rotation_angle = self._drag_rotation
            return True  # Consume the event
        return super().eventFilter(obj, event)  # type: ignore[arg-type]

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop to place building or blueprint."""
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
                    scene_pos = QPointF(
                        scene_pos.x() - spec.width / 2, scene_pos.y() - spec.height / 2
                    )
                snapped = self._snap_to_grid(scene_pos)
                # Use rotation accumulated during drag
                rotation = self._drag_rotation
                self._place_building_with_rotation(
                    building_type, snapped.x(), snapped.y(), rotation
                )
                event.acceptProposedAction()

            # Clean up drag state
            self._drag_building_type = None
            self._drag_rotation = 0
            if self._drag_ghost:
                self._scene.removeItem(self._drag_ghost)
                self._drag_ghost = None
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
        elif event.mimeData().hasFormat("application/x-blueprint-room-id"):
            # Place the blueprint
            if self._blueprint_placement_room:
                scene_pos = self.mapToScene(event.position().toPoint())
                snapped = self._snap_to_grid(scene_pos)
                self._place_blueprint(self._blueprint_placement_room, snapped.x(), snapped.y())
                event.acceptProposedAction()

            # Clean up
            self._clear_blueprint_placement()
        else:
            super().dropEvent(event)

    def _place_building(self, building_type: BuildingType, x: float, y: float) -> None:
        """Place a new building at the given position (uses placement mode rotation)."""
        self._place_building_with_rotation(building_type, x, y, self._placement_rotation)

    def _place_building_with_rotation(
        self, building_type: BuildingType, x: float, y: float, rotation: int
    ) -> None:
        """Place a new building at the given position with specified rotation."""
        building = Building(
            id=generate_id(),
            building_type=building_type,
            x=x,
            y=y,
            rotation=rotation,
        )
        # Determine scene from placement position (hit-test to find deepest room)
        scene_room_id = self.get_room_at_point(QPointF(x, y))
        cmd = PlaceBuildingCommand(scene_room_id=scene_room_id, building=building, canvas=self)
        self.command_stack.execute(cmd)
        # Command already added the item via handler, but we need to set visual rotation
        item = self._building_items.get(building.id)
        if item:
            item.rotation_angle = rotation

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
            # Get scene from first selected item (all selected items are in same scene)
            first_item = next(
                (item for item in self._scene.selectedItems() if isinstance(item, BuildingItem)),
                None,
            )
            scene_room_id = self.get_scene_for_item(first_item) if first_item else None
            cmd = DeleteItemsCommand(
                scene_room_id=scene_room_id,
                buildings=buildings_to_delete,
                belts=belts_to_delete,
                canvas=self,
            )
            self.command_stack.execute(cmd)
            # Command handles UI updates via handler

    def _emit_selection_changed(self) -> None:
        """Emit signal with current selection."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        selected_ids = []
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                selected_ids.append(item.building.id)
            elif isinstance(item, BeltItem):
                selected_ids.append(item.belt.id)
            elif isinstance(item, RoomItem):
                selected_ids.append(item.placement.id)
        self.selection_changed.emit(selected_ids)

    def _get_scene_for_item(self, item: QGraphicsItem) -> Scene | None:
        """Get the scene (Document or Room) that an item belongs to.

        Returns None for items that don't belong to a scene (e.g., selection outline).
        """
        from satisfactory_planner.ui.items.room_item import RoomItem

        if isinstance(item, BuildingItem):
            return item.building_scene
        elif isinstance(item, BeltItem):
            # Belt's scene is determined by its parent
            parent = item.parentItem()
            if isinstance(parent, RoomItem):
                return parent.room
            return self.document
        elif isinstance(item, RoomItem):
            # RoomItem itself belongs to its parent scene
            return item.parent_scene
        return None

    def _clear_selection_in_other_scenes(self, current_scene: Scene) -> None:
        """Clear selection for all items not in the given scene."""
        for item in self._scene.selectedItems():
            item_scene = self._get_scene_for_item(item)
            if item_scene is not None and item_scene is not current_scene:
                item.setSelected(False)

    def on_item_clicked(self, item: QGraphicsItem) -> None:
        """Handle an item being clicked - enforce scene-local selection.

        Called by items (BuildingItem, RoomItem) when they're clicked.
        Clears selection in other scenes before the item is selected.

        NOTE: This does NOT track an "active scene". It just ensures selection
        cannot span multiple scenes by clearing selection in other scenes.
        """
        item_scene = self._get_scene_for_item(item)
        if item_scene is None:
            return

        # Clear selection in all other scenes (selection cannot span scenes)
        self._clear_selection_in_other_scenes(item_scene)

    def get_room_at_point(self, pos: QPointF) -> str | None:
        """Get the deepest room_id at a scene position, or None for root document.

        Used by placement commands to determine which scene to place into.
        Hit-tests the position to find rooms, returns the innermost (deepest) one.
        """
        from satisfactory_planner.ui.items.room_item import RoomItem

        # Find all items at this point, sorted by Z-order (topmost first)
        items_at_pos = self._scene.items(pos)

        # Find the deepest RoomItem
        for item in items_at_pos:
            if isinstance(item, RoomItem):
                # Found a room - return its ID
                return item.room.id

        # No room at this point - root document
        return None

    def get_scene_for_item(self, item: QGraphicsItem) -> str | None:
        """Get the room_id for the scene an item belongs to, or None for root document.

        Used by commands that operate on existing items (move, delete, property changes).
        The item knows its scene - we just convert it to a room_id.
        """
        scene = self._get_scene_for_item(item)
        if scene is None or scene is self.document:
            return None
        # It's a Room - find its ID
        for room_id, room in self.document.rooms.items():
            if room is scene:
                return room_id
        return None

    def _update_selection_outline(self) -> None:
        """Update the dashed selection outline around selected buildings."""
        # Remove old outline
        if self._selection_outline:
            self._scene.removeItem(self._selection_outline)
            self._selection_outline = None

        # Get selected building items
        selected_buildings = [
            item for item in self._scene.selectedItems() if isinstance(item, BuildingItem)
        ]

        if not selected_buildings:
            return

        # Compute bounding rect of all selected buildings
        bounds: QRectF | None = None
        for item in selected_buildings:
            item_rect = item.sceneBoundingRect()
            bounds = item_rect if bounds is None else bounds.united(item_rect)

        if bounds is None:
            return

        # Add margin
        bounds = bounds.adjusted(
            -SELECTION_MARGIN, -SELECTION_MARGIN, SELECTION_MARGIN, SELECTION_MARGIN
        )

        # Create dashed outline rect
        self._selection_outline = QGraphicsRectItem(bounds)
        pen = QPen(QColor(100, 150, 255), 2, Qt.PenStyle.DashLine)
        self._selection_outline.setPen(pen)
        self._selection_outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_outline.setZValue(-1)  # Behind buildings
        # Don't make it selectable or movable
        self._selection_outline.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._selection_outline.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._scene.addItem(self._selection_outline)

    def set_tool_mode(self, mode: ToolMode) -> None:
        """Set the active tool mode."""
        self._tool_mode = mode
        if mode == ToolMode.PAN:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode == ToolMode.BOX_SELECT:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    @property
    def tool_mode(self) -> ToolMode:
        """Get the current tool mode."""
        return self._tool_mode

    def _start_box_select(self, scene_pos: QPointF) -> None:
        """Start a box selection at the given scene position."""
        self._box_select_start = scene_pos

        # Create the selection rectangle
        self._box_select_rect = QGraphicsRectItem(QRectF(scene_pos, scene_pos))
        pen = QPen(QColor(100, 150, 255), 1, Qt.PenStyle.DashLine)
        self._box_select_rect.setPen(pen)
        self._box_select_rect.setBrush(QBrush(QColor(100, 150, 255, 30)))
        self._box_select_rect.setZValue(1000)  # On top
        self._box_select_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._scene.addItem(self._box_select_rect)

    def _update_box_select(self, scene_pos: QPointF) -> None:
        """Update the box selection rectangle to the given position."""
        if not self._box_select_start or not self._box_select_rect:
            return

        # Create rect from start to current position
        rect = QRectF(self._box_select_start, scene_pos).normalized()
        self._box_select_rect.setRect(rect)

    def _complete_box_select(self) -> None:
        """Complete the box selection, selecting all items in the rect."""
        if not self._box_select_rect:
            self._cancel_box_select()
            return

        select_rect = self._box_select_rect.rect()

        # Clear current selection
        self._scene.clearSelection()

        # Select all building items within the rect
        for building_item in self._building_items.values():
            if select_rect.intersects(building_item.sceneBoundingRect()):
                building_item.setSelected(True)

        # Optionally select belts within the rect too
        for belt_item in self._belt_items.values():
            if select_rect.intersects(belt_item.sceneBoundingRect()):
                belt_item.setSelected(True)

        self._cancel_box_select()
        self._emit_selection_changed()

    def _cancel_box_select(self) -> None:
        """Cancel the current box selection."""
        self._box_select_start = None
        if self._box_select_rect:
            self._scene.removeItem(self._box_select_rect)
            self._box_select_rect = None

    # Room creation methods

    def _start_room_create(self, scene_pos: QPointF) -> None:
        """Start room creation at the given scene position."""
        self._room_create_start = scene_pos

        # Create the room rectangle preview (different color from box select)
        self._room_create_rect = QGraphicsRectItem(QRectF(scene_pos, scene_pos))
        pen = QPen(QColor(100, 200, 100), 2, Qt.PenStyle.DashLine)
        self._room_create_rect.setPen(pen)
        self._room_create_rect.setBrush(QBrush(QColor(100, 200, 100, 30)))
        self._room_create_rect.setZValue(1000)  # On top
        self._room_create_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._scene.addItem(self._room_create_rect)

    def _update_room_create(self, scene_pos: QPointF) -> None:
        """Update the room creation rectangle to the given position."""
        if not self._room_create_start or not self._room_create_rect:
            return

        rect = QRectF(self._room_create_start, scene_pos).normalized()
        self._room_create_rect.setRect(rect)

    def _complete_room_create(self) -> None:
        """Complete room creation, validating and creating the room."""

        if not self._room_create_rect:
            self._cancel_room_create()
            return

        rect = self._room_create_rect.rect()

        # Validate: minimum size
        if rect.width() < 50 or rect.height() < 50:
            logger.info("Room too small - minimum 50x50")
            self._cancel_room_create()
            self._tool_mode = ToolMode.SELECT  # One-shot tool
            return

        # Determine which scene we're creating in (based on top-left corner)
        parent_scene_room_id = self.get_room_at_point(rect.topLeft())

        # Get the parent scene
        if parent_scene_room_id:
            parent_scene: Scene = self.document.rooms[parent_scene_room_id]
        else:
            parent_scene = self.document

        # Validate: no buildings intersected (partially inside)
        for building in parent_scene.buildings.values():
            building_rect = self._get_building_rect(building)
            if rect.intersects(building_rect) and not rect.contains(building_rect):
                logger.warning("Room boundary cannot intersect buildings")
                self._cancel_room_create()
                self._tool_mode = ToolMode.SELECT
                return

        # Collect buildings completely inside
        contained_building_ids: list[str] = []
        for building in parent_scene.buildings.values():
            if rect.contains(self._get_building_rect(building)):
                contained_building_ids.append(building.id)

        # Collect belts where BOTH endpoints are inside, and crossing belts
        contained_belt_ids: list[str] = []
        crossing_belts: list[Belt] = []
        for belt in parent_scene.belts.values():
            source_inside = belt.source_building_id in contained_building_ids
            dest_inside = belt.dest_building_id in contained_building_ids
            if source_inside and dest_inside:
                contained_belt_ids.append(belt.id)
            elif source_inside or dest_inside:
                crossing_belts.append(belt)

        # Create the room command (crossing belts captured as objects, not just IDs)
        cmd = CreateRoomCommand(
            parent_scene_room_id=parent_scene_room_id,
            rect=(rect.x(), rect.y(), rect.width(), rect.height()),
            building_ids=tuple(contained_building_ids),
            belt_ids=tuple(contained_belt_ids),
            original_crossing_belts=tuple(crossing_belts),
            canvas=self,
        )
        self.command_stack.execute(cmd)

        self._cancel_room_create()
        self._tool_mode = ToolMode.SELECT  # One-shot tool
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _cancel_room_create(self) -> None:
        """Cancel the current room creation."""
        self._room_create_start = None
        if self._room_create_rect:
            self._scene.removeItem(self._room_create_rect)
            self._room_create_rect = None

    def _get_building_rect(self, building: Building) -> QRectF:
        """Get the bounding rectangle of a building."""
        w, h = building._get_display_size()
        return QRectF(building.x, building.y, w, h)

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
            # Get scene from source building (belt endpoints must be in same scene)
            source_item = self._building_items.get(self._connect_start_building)
            scene_room_id = self.get_scene_for_item(source_item) if source_item else None
            cmd = ConnectBeltCommand(scene_room_id=scene_room_id, belt=belt, canvas=self)
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
        elif (
            event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.copy_selection()
            return
        elif (
            event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.paste()
            return
        elif (
            event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
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
        """Copy selected buildings, belts, and rooms to clipboard.

        For rooms, we store the room_id for shallow-copy (linked instance) paste.
        """
        from satisfactory_planner.ui.items.room_item import RoomItem

        self._clipboard_buildings.clear()
        self._clipboard_belts.clear()
        self._clipboard_room_ids.clear()

        selected_building_ids: set[str] = set()
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                # Deep copy the building
                self._clipboard_buildings.append(copy.deepcopy(item.building))
                selected_building_ids.add(item.building.id)
            elif isinstance(item, RoomItem):
                # Store room_id for shallow copy (linked instance)
                self._clipboard_room_ids.append(item.room.id)

        # Copy belts that connect selected buildings to each other
        for belt in self.document.belts.values():
            if (
                belt.source_building_id in selected_building_ids
                and belt.dest_building_id in selected_building_ids
            ):
                self._clipboard_belts.append(copy.deepcopy(belt))

    def paste(self) -> None:
        """Paste buildings and rooms from clipboard at an offset from originals.

        Rooms are pasted as linked instances (shallow copy) - they reference
        the same Room definition, so editing one edits all instances.
        """
        from satisfactory_planner.core.models import RoomPlacement

        if not self._clipboard_buildings and not self._clipboard_room_ids:
            return

        # Offset for pasted items
        offset = 50.0

        # Track new items for selection
        new_item_ids: list[str] = []

        # Paste buildings
        if self._clipboard_buildings:
            # Map old IDs to new IDs
            id_map: dict[str, str] = {}
            scene_room_id: str | None = None

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
                # Determine scene from paste position
                scene_room_id = self.get_room_at_point(QPointF(new_building.x, new_building.y))
                cmd = PlaceBuildingCommand(
                    scene_room_id=scene_room_id, building=new_building, canvas=self
                )
                self.command_stack.execute(cmd)
                new_item_ids.append(new_id)

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
                    # Paste belts into same scene as buildings
                    belt_cmd = ConnectBeltCommand(
                        scene_room_id=scene_room_id, belt=new_belt, canvas=self
                    )
                    self.command_stack.execute(belt_cmd)

        # Paste rooms as linked instances (shallow copy)
        for room_id in self._clipboard_room_ids:
            room = self.document.rooms.get(room_id)
            if not room:
                continue

            # Find existing placement to get position for offset
            existing_placements = self.document.get_placements_for_room(room_id)
            if existing_placements:
                base_x = existing_placements[0].x + offset
                base_y = existing_placements[0].y + offset
            else:
                base_x, base_y = offset, offset

            # Create new placement pointing to same room (linked instance!)
            new_placement = RoomPlacement(
                id=generate_id(),
                room_id=room_id,
                x=base_x,
                y=base_y,
                parent_room_id=None,  # Paste into root for now
            )
            self.document.room_placements[new_placement.id] = new_placement
            self.add_room_item(new_placement, room)
            new_item_ids.append(new_placement.id)

        self.notify_mutation()

        # Select the newly pasted items
        self._scene.clearSelection()
        for new_id in new_item_ids:
            item = self._building_items.get(new_id)
            if item:
                item.setSelected(True)
            room_item = self._room_items.get(new_id)
            if room_item:
                from satisfactory_planner.ui.items.room_item import RoomItem

                if isinstance(room_item, RoomItem):
                    room_item.setSelected(True)
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
        item = self._building_items.get(building_id)
        if not item:
            return

        # Get building from item's scene (could be root document or a Room)
        building = item.building_scene.buildings.get(building_id)
        if not building:
            return

        # Get the new position from the visual item (may have grid snap applied)
        new_x = item.pos().x()
        new_y = item.pos().y()

        # Get rotation (use current if old not provided)
        new_rot = building.rotation
        old_rot = old_rotation if old_rotation is not None else new_rot

        # NOTE: Do NOT sync model here - let the command do it.
        # This ensures the command's execute() sees a real change and triggers refresh.

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
        # Get scene from the item being moved
        scene_room_id = self.get_scene_for_item(item)
        cmd = MoveBuildingsCommand(
            scene_room_id=scene_room_id,
            canvas=self,
            moves=(move,),
        )
        # Command will see model already at new position and log warning, which is fine
        # The important thing is the command captures old/new for undo/redo
        self.command_stack.execute(cmd)

        # Redraw all connected belts using absolute positions from model
        self._update_belts_for_building(building_id)

    def _update_belts_for_building(self, building_id: str, scene: Scene | None = None) -> None:
        """Redraw all belts connected to a building using current model positions.

        Args:
            building_id: The building whose belts need updating
            scene: The scene containing the building (defaults to document)
        """
        target_scene: Scene = scene if scene is not None else self.document
        for belt in target_scene.get_belts_for_building(building_id):
            belt_item = self._belt_items.get(belt.id)
            if belt_item:
                source = target_scene.buildings.get(belt.source_building_id)
                dest = target_scene.buildings.get(belt.dest_building_id)
                if source and dest:
                    belt_item.update_path(source, dest)

    def _refresh_all_room_items(self, room_id: str) -> None:
        """Refresh ALL RoomItems that display the given room.

        Calls refresh() on each RoomItem and re-tracks the new child items.
        """
        from satisfactory_planner.ui.items.room_item import RoomItem

        for room_item in self._room_items.values():
            if isinstance(room_item, RoomItem) and room_item.room.id == room_id:
                # Untrack old children
                for building_id in list(room_item._building_items.keys()):
                    self._building_items.pop(building_id, None)
                for belt_id in list(room_item._belt_items.keys()):
                    self._belt_items.pop(belt_id, None)

                # Refresh (recreates child items)
                room_item.refresh()

                # Re-track new children
                for building_id, building_item in room_item._building_items.items():
                    self._building_items[building_id] = building_item
                for belt_id, belt_item in room_item._belt_items.items():
                    self._belt_items[belt_id] = belt_item

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
