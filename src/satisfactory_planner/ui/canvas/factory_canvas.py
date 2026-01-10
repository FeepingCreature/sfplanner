"""Factory canvas using QGraphicsView."""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
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
    QGraphicsScene,
    QGraphicsView,
)

from satisfactory_planner.core import (
    DEFAULT_GRID_SIZE,
    Belt,
    Building,
    BuildingType,
    Document,
    Room,
)
from satisfactory_planner.core.models import Scene
from satisfactory_planner.ui.commands import (
    BuildingMove,
    CommandStack,
    DeleteItemsCommand,
    MoveBuildingsCommand,
)
from satisfactory_planner.ui.items.belt_item import BeltItem
from satisfactory_planner.ui.items.building_item import BuildingItem

if TYPE_CHECKING:
    from satisfactory_planner.core.models import RoomPlacement
    from satisfactory_planner.ui.main_window import MainWindow


logger = logging.getLogger(__name__)


class ToolMode(Enum):
    """Active tool mode for the canvas.

    Most interactions are stateless (select, pan via middle-mouse, box select on empty space).
    Only CREATE_ROOM requires an explicit mode toggle.
    """

    CREATE_ROOM = auto()


class GhostBuildingItem(BuildingItem):
    """Semi-transparent preview of building being placed."""

    def __init__(self, building: Building, canvas: FactoryCanvas) -> None:
        super().__init__(building, canvas)
        self.setOpacity(0.6)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)


class FactoryCanvas(QGraphicsView):
    """The main factory canvas for placing buildings and belts.

    Uses composition to delegate to specialized managers:
    - BeltConnector: Belt connection dragging
    - PlacementManager: Building/blueprint placement
    - DrawingTools: Box selection and room creation
    - SelectionManager: Selection state and outline
    - VisualSyncManager: Model-to-view synchronization
    - ClipboardManager: Copy/paste operations
    """

    # Emits (list of selected IDs, scene_room_id or None for root document)
    selection_changed = Signal(list, object)
    tool_mode_changed = Signal(object)  # Emits ToolMode when it changes

    def __init__(
        self, document: Document, command_stack: CommandStack, parent: QGraphicsView | None = None
    ) -> None:
        super().__init__(parent)

        self.document = document
        self.command_stack = command_stack

        # Core state
        self._is_panning = False
        self._pan_start = QPointF()
        self._grid_snap = True
        self._grid_size = DEFAULT_GRID_SIZE
        self._tool_mode: ToolMode | None = None

        # Item tracking
        self._building_items: dict[str, BuildingItem] = {}
        self._belt_items: dict[str, BeltItem] = {}
        self._room_items: dict[str, object] = {}

        # Mutation callback
        self._mutation_callback: Callable[[], None] | None = None

        # Default belt tier for new connections
        self._default_belt_tier: int = 1

        # Rendering settings
        self._show_flow_rate: bool = False
        self._show_efficiency: bool = False

        # Initialize managers BEFORE _setup_scene (which uses _selection)
        from satisfactory_planner.ui.canvas.belt_connector import BeltConnector
        from satisfactory_planner.ui.canvas.clipboard_manager import ClipboardManager
        from satisfactory_planner.ui.canvas.drawing_tools import DrawingTools
        from satisfactory_planner.ui.canvas.placement_manager import PlacementManager
        from satisfactory_planner.ui.canvas.selection_manager import SelectionManager
        from satisfactory_planner.ui.canvas.visual_sync_manager import VisualSyncManager

        self._belt_connector = BeltConnector(self)
        self._placement = PlacementManager(self)
        self._drawing = DrawingTools(self)
        self._selection = SelectionManager(self)
        self._sync = VisualSyncManager(self)
        self._clipboard = ClipboardManager(self)

        self._setup_scene()
        self._setup_view()

        self.setAcceptDrops(True)

    def _setup_scene(self) -> None:
        """Initialize the graphics scene."""
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)

        self._scene.selectionChanged.connect(self._selection.update_outline)
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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 45)))

    # === Public API ===

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
        return self._grid_snap

    @property
    def grid_size(self) -> int:
        return self._grid_size

    @property
    def default_belt_tier(self) -> int:
        return self._default_belt_tier

    def set_default_belt_tier(self, tier: int) -> None:
        """Set the default belt tier for new connections."""
        self._default_belt_tier = tier

    @property
    def tool_mode(self) -> ToolMode | None:
        return self._tool_mode

    def set_tool_mode(self, mode: ToolMode | None) -> None:
        """Set the active tool mode."""
        self._tool_mode = mode
        if mode == ToolMode.CREATE_ROOM:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.tool_mode_changed.emit(mode)

    def set_placement_mode(self, building_type: BuildingType | None) -> None:
        """Enter placement mode for a building type."""
        self._placement.set_building_mode(building_type)

    def set_blueprint_placement_mode(self, room: Room) -> None:
        """Enter placement mode for a blueprint."""
        self._placement.set_blueprint_mode(room)

    def update_belts_for_building(self, building_id: str, scene: Scene) -> None:
        """Redraw all belts connected to a building.

        Handles belts where one or both endpoints may be:
        - A Building in the scene
        - A RoomPlacement (for belts crossing room boundaries)
        """
        for belt in scene.get_belts_for_building(building_id):
            belt_item = self._belt_items.get(belt.id)
            if belt_item:
                belt_item._update_path_from_endpoints()

    # === Refresh ===

    def refresh(self) -> None:
        """Refresh all items from the document."""
        for building_item in list(self._building_items.values()):
            self._scene.removeItem(building_item)
        for belt_item in list(self._belt_items.values()):
            self._scene.removeItem(belt_item)
        self._building_items.clear()
        self._belt_items.clear()

        for building in self.document.buildings.values():
            self.add_building_item(building)
        for belt in self.document.belts.values():
            self.add_belt_item(belt)

        # Clear and reload room items
        for room_item in list(self._room_items.values()):
            from satisfactory_planner.ui.items.room_item import RoomItem

            if isinstance(room_item, RoomItem):
                self._scene.removeItem(room_item)
        self._room_items.clear()

        for placement in self.document.room_placements.values():
            room = self.document.rooms.get(placement.room_id)
            if room:
                self.add_room_item(placement, room)

    # === Item management (VisualContainer protocol) ===

    def add_building_item(self, building_or_id: Building | str) -> BuildingItem | None:
        """Add a building item to the scene.

        Args:
            building_or_id: Either a Building object or building ID (str).
                           When called via VisualContainer protocol, this is a str.
        """
        if isinstance(building_or_id, str):
            building = self.document.buildings.get(building_or_id)
            if not building:
                return None
        else:
            building = building_or_id

        item = BuildingItem(building, self)
        self._scene.addItem(item)
        self._building_items[building.id] = item
        return item

    def remove_building_item(self, building_id: str) -> None:
        """Remove a building item from the scene."""
        item = self._building_items.pop(building_id, None)
        if item:
            self._scene.removeItem(item)

    def add_belt_item(self, belt_or_id: Belt | str) -> BeltItem | None:
        """Add a belt item to the scene.

        Supports belts connecting to:
        - Buildings (in document or rooms)
        - RoomPlacements (treated as buildings with ports)

        Args:
            belt_or_id: Either a Belt object or belt ID (str).
                       When called via VisualContainer protocol, this is a str.
        """
        if isinstance(belt_or_id, str):
            belt = self.document.belts.get(belt_or_id)
            if not belt:
                return None
        else:
            belt = belt_or_id

        # Look up source - could be a Building or RoomPlacement
        source = self.document.buildings.get(belt.source_building_id)
        source_placement = None
        if source is None:
            source_placement = self.document.room_placements.get(belt.source_building_id)

        # Look up dest - could be a Building or RoomPlacement
        dest = self.document.buildings.get(belt.dest_building_id)
        dest_placement = None
        if dest is None:
            dest_placement = self.document.room_placements.get(belt.dest_building_id)

        # Need at least one valid endpoint
        if (source is None and source_placement is None) or (
            dest is None and dest_placement is None
        ):
            return None

        item = BeltItem(
            belt,
            self,
            self.document,
            source=source,
            dest=dest,
            source_placement=source_placement,
            dest_placement=dest_placement,
        )
        self._scene.addItem(item)
        self._belt_items[belt.id] = item
        return item

    def remove_belt_item(self, belt_id: str) -> None:
        """Remove a belt item from the scene."""
        item = self._belt_items.pop(belt_id, None)
        if item:
            self._scene.removeItem(item)

    # === Visual sync methods (delegated to VisualSyncManager) ===

    def sync_add_belt(self, belt_id: str, scene_room_id: str | None) -> None:
        """Add visual for a belt - routes to correct container(s)."""
        self._sync.sync_add_belt(belt_id, scene_room_id)

    def sync_remove_belt(self, belt_id: str, scene_room_id: str | None) -> None:
        """Remove visual for a belt - routes to correct container(s)."""
        self._sync.sync_remove_belt(belt_id, scene_room_id)

    def sync_add_building(self, building_id: str, scene_room_id: str | None) -> None:
        """Add visual for a building - routes to correct container(s)."""
        self._sync.sync_add_building(building_id, scene_room_id)

    def sync_remove_building(self, building_id: str, scene_room_id: str | None) -> None:
        """Remove visual for a building - routes to correct container(s)."""
        self._sync.sync_remove_building(building_id, scene_room_id)

    def sync_building_moved(
        self, building_id: str, scene_room_id: str | None, source_item: object = None
    ) -> None:
        """Sync all visual items after a building's position changed in the model."""
        self._sync.sync_building_moved(building_id, scene_room_id, source_item)

    def refresh_building(self, building_id: str) -> None:
        """Refresh a building's visual state."""
        self._sync.refresh_building(building_id)

    def refresh_belt(self, belt_id: str, scene_room_id: str | None = None) -> None:
        """Refresh a belt's visual state."""
        self._sync.refresh_belt(belt_id, scene_room_id)

    def refresh_belts_for_building(self, building_id: str, scene: Scene) -> None:
        """Refresh belts connected to a building."""
        self._sync.refresh_belts_for_building(building_id, scene)

    def update_flow_visualization(self) -> None:
        """Update visual state of items based on flow solver results."""
        self._sync.update_flow_visualization()

    # === Scene lookup helper ===

    def _get_scene(self, scene_room_id: str | None) -> Scene:
        """Get the Scene for a room_id (or document if None)."""
        return self._sync.get_scene(scene_room_id)

    # === Room item management ===

    def add_room_item(self, placement: RoomPlacement, room: Room) -> None:
        """Add a room item to the scene."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        parent_scene_id = getattr(placement, "parent_scene_id", None)
        if parent_scene_id:
            parent_scene: Scene = self.document.rooms[parent_scene_id]
        else:
            parent_scene = self.document

        room_item = RoomItem(placement, room, parent_scene, self)
        self._scene.addItem(room_item)

        placement_id = getattr(placement, "id", "")
        self._room_items[placement_id] = room_item

        # IMPORTANT: Defer refresh to next event loop iteration.
        def deferred_refresh() -> None:
            room_item.refresh()
            for other_placement_id, other_room_item in list(self._room_items.items()):
                if (
                    isinstance(other_room_item, RoomItem)
                    and other_room_item.room.id == room.id
                    and other_placement_id != placement_id
                ):
                    other_room_item.refresh()

        QTimer.singleShot(0, deferred_refresh)

    def remove_room_item(self, placement_id: str) -> None:
        """Remove a room item from the scene."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        room_item = self._room_items.pop(placement_id, None)
        if room_item and isinstance(room_item, RoomItem):
            self._scene.removeItem(room_item)

    def notify_mutation(self) -> None:
        """Notify that the document was mutated."""
        if self._mutation_callback:
            self._mutation_callback()

    # === Grid snapping ===

    def _snap_to_grid(self, pos: QPointF) -> QPointF:
        """Snap a position to the grid if enabled."""
        if self._grid_snap:
            x = round(pos.x() / self._grid_size) * self._grid_size
            y = round(pos.y() / self._grid_size) * self._grid_size
            return QPointF(x, y)
        return pos

    # === Event handlers ===

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle zoom with mouse wheel, rotation in placement mode."""
        delta = -90 if event.angleDelta().y() > 0 else 90

        if self._placement.placement_mode:
            self._placement.rotate(delta)
            return

        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem) and item._is_dragging:
                item.rotate_building(delta)
                self.update_belts_for_building(item.building.id, item.building_scene)
                return

        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press."""
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = QPointF(float(event.pos().x()), float(event.pos().y()))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.RightButton:
            if self._placement.is_placing:
                self._placement.set_building_mode(None)
                return
            if self._drawing.is_box_selecting:
                self._drawing.cancel_box_select()
                return
            item_at_pos = self.itemAt(event.pos())
            if item_at_pos is None or item_at_pos is self._selection.outline_item:
                self._is_panning = True
                self._pan_start = QPointF(float(event.pos().x()), float(event.pos().y()))
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._placement.place_at(scene_pos):
                return

            if self._tool_mode == ToolMode.CREATE_ROOM:
                self._drawing.start_room_create(scene_pos)
                return

            item_at_pos = self.itemAt(event.pos())
            if item_at_pos is None or item_at_pos is self._selection.outline_item:
                self._drawing.start_box_select(scene_pos)
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

        scene_pos = self.mapToScene(event.pos())

        if self._drawing.is_box_selecting:
            self._drawing.update_box_select(scene_pos)
            return

        if self._drawing.is_creating_room:
            self._drawing.update_room_create(scene_pos)
            return

        if self._belt_connector.is_connecting:
            self._belt_connector.update_preview(scene_pos)
            self._belt_connector.update_hover_target(scene_pos)

        if self._placement.is_placing:
            self._placement.update_ghost_position(scene_pos)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        if (
            event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton)
            and self._is_panning
        ):
            self._is_panning = False
            if self._placement.is_placing or self._tool_mode == ToolMode.CREATE_ROOM:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._drawing.is_box_selecting:
                self._drawing.complete_box_select()
                return

            if self._drawing.is_creating_room:
                self._drawing.complete_room_create()
                return

            if self._belt_connector.is_connecting:
                scene_pos = self.mapToScene(event.pos())
                self._belt_connector.try_complete(scene_pos)

        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter."""
        if event.mimeData().hasFormat("application/x-building-type"):
            building_name = bytes(
                event.mimeData().data("application/x-building-type").data()
            ).decode()
            for bt in BuildingType:
                if bt.value == building_name:
                    scene_pos = self.mapToScene(event.position().toPoint())
                    self._placement.start_drag(bt, scene_pos)
                    break

            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-blueprint-room-id"):
            from satisfactory_planner.ui.panels.library_panel import LibraryPanel

            source = event.source()
            if source:
                parent = source.parent()
                while parent and not isinstance(parent, LibraryPanel):
                    parent = parent.parent()
                if isinstance(parent, LibraryPanel) and parent._dragging_blueprint:
                    scene_pos = self.mapToScene(event.position().toPoint())
                    self._placement.start_blueprint_drag(parent._dragging_blueprint, scene_pos)
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        """Handle drag move."""
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.mimeData().hasFormat("application/x-building-type"):
            self._placement.update_drag(scene_pos)
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-blueprint-room-id"):
            self._placement.update_blueprint_drag(scene_pos)
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        """Handle drag leave."""
        self._placement.cancel_drag()
        self._placement.clear_blueprint_mode()
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        super().dragLeaveEvent(event)  # type: ignore[arg-type]

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        """Capture wheel events during drag-drop for rotation."""
        if self._placement._drag_building_type is not None and event.type() == QEvent.Type.Wheel:
            wheel_event: QWheelEvent = event  # type: ignore[assignment]
            delta = 90 if wheel_event.angleDelta().y() > 0 else -90
            self._placement.rotate_drag(delta)
            return True
        return super().eventFilter(obj, event)  # type: ignore[arg-type]

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop."""
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.mimeData().hasFormat("application/x-building-type"):
            self._placement.complete_drag(scene_pos)
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-blueprint-room-id"):
            self._placement.complete_blueprint_drag(scene_pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Handle key presses."""
        if event is None:
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selection()
            return
        elif event.key() == Qt.Key.Key_Escape:
            if self._placement.is_placing:
                self._placement.set_building_mode(None)
            elif self._belt_connector.is_connecting:
                self._belt_connector.cancel()
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
            self._selection.select_all()
            return
        super().keyPressEvent(event)

    # === Selection and deletion ===

    def delete_selection(self) -> None:
        """Delete selected items."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        selected_buildings: list[str] = []
        selected_belts: list[str] = []
        selected_room_placements: list[str] = []

        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                selected_buildings.append(item.building.id)
            elif isinstance(item, BeltItem):
                selected_belts.append(item.belt.id)
            elif isinstance(item, RoomItem):
                selected_room_placements.append(item.placement.id)

        for placement_id in selected_room_placements:
            placement = self.document.room_placements.get(placement_id)
            if placement:
                room = self.document.rooms.get(placement.room_id)
                if room:
                    from satisfactory_planner.ui.commands.room_commands import (
                        DeleteRoomPlacementCommand,
                    )

                    room_cmd = DeleteRoomPlacementCommand(
                        placement_id=placement_id,
                        canvas=self,
                    )
                    self.command_stack.execute(room_cmd)

        if selected_buildings or selected_belts:
            first_item = next(
                (
                    item
                    for item in self._scene.selectedItems()
                    if isinstance(item, (BuildingItem, BeltItem))
                ),
                None,
            )
            scene_room_id = self.get_scene_for_item(first_item) if first_item else None
            target_scene = self._get_scene(scene_room_id)

            for building_id in selected_buildings:
                for belt in target_scene.get_belts_for_building(building_id):
                    if belt.id not in selected_belts:
                        selected_belts.append(belt.id)

            buildings_to_delete = tuple(
                target_scene.buildings[bid]
                for bid in selected_buildings
                if bid in target_scene.buildings
            )
            belts_to_delete = tuple(
                target_scene.belts[bid] for bid in selected_belts if bid in target_scene.belts
            )

            cmd = DeleteItemsCommand(
                scene_room_id=scene_room_id,
                buildings=buildings_to_delete,
                belts=belts_to_delete,
                canvas=self,
            )
            self.command_stack.execute(cmd)

    def _emit_selection_changed(self) -> None:
        """Emit signal with current selection and scene context."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        selected_ids = []
        scene_room_id: str | None = None

        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                selected_ids.append(item.building.id)
                if scene_room_id is None:
                    scene_room_id = item.building_scene.scene_room_id
            elif isinstance(item, BeltItem):
                selected_ids.append(item.belt.id)
                if scene_room_id is None:
                    scene_room_id = item.belt_scene.scene_room_id
            elif isinstance(item, RoomItem):
                selected_ids.append(item.placement.id)

        self.selection_changed.emit(selected_ids, scene_room_id)

    def select_all(self) -> None:
        """Select all buildings and belts."""
        self._selection.select_all()

    def on_item_clicked(self, item: QGraphicsItem) -> None:
        """Handle an item being clicked - enforce scene-local selection."""
        self._selection.on_item_clicked(item)

    def _update_selection_outline(self) -> None:
        """Update the selection outline (forwarded to SelectionManager)."""
        self._selection.update_outline()

    # === Scene queries ===

    def get_room_at_point(self, pos: QPointF) -> str | None:
        """Get the deepest room_id at a scene position."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        for item in self._scene.items(pos):
            if isinstance(item, RoomItem):
                return item.room.id
        return None

    def get_scene_for_item(self, item: QGraphicsItem) -> str | None:
        """Get the room_id for the scene an item belongs to."""
        scene = self._selection.get_scene_for_item(item)
        if scene is None or scene is self.document:
            return None
        for room_id, room in self.document.rooms.items():
            if room is scene:
                return room_id
        return None

    # === Belt connection (delegated) ===

    def start_belt_drag(
        self,
        building_id: str,
        port_index: int,
        start_pos: QPointF,
        scene_room_id: str | None = None,
    ) -> None:
        """Start dragging a belt connection from an output port."""
        self._belt_connector.start_drag(building_id, port_index, start_pos, scene_room_id)

    def is_dragging_belt(self) -> bool:
        """Return True if currently dragging a belt connection."""
        return self._belt_connector.is_connecting

    def start_belt_connection(self, building_id: str, port_index: int) -> None:
        """Start a belt connection (legacy compatibility)."""
        self._belt_connector.start_drag(building_id, port_index, QPointF(0, 0))

    def complete_belt_connection(self, building_id: str, port_index: int) -> None:
        """Complete a belt connection to an input port."""
        self._belt_connector.complete(building_id, port_index)

    def cancel_belt_connection(self) -> None:
        """Cancel the current belt connection."""
        self._belt_connector.cancel()

    # === Copy/paste (delegated to ClipboardManager) ===

    def copy_selection(self) -> None:
        """Copy selected items to clipboard."""
        self._clipboard.copy_selection()

    def paste(self) -> None:
        """Paste from clipboard."""
        self._clipboard.paste()

    # === Building movement ===

    def on_building_moved(
        self,
        item_or_id: BuildingItem | str,
        old_x: float,
        old_y: float,
        old_rotation: int | None = None,
    ) -> None:
        """Handle a building being moved."""
        if isinstance(item_or_id, str):
            item = self._building_items.get(item_or_id)
            building_id = item_or_id
        else:
            item = item_or_id
            building_id = item.building.id

        if not item:
            return

        building = item.building_scene.buildings.get(building_id)
        if not building:
            return

        new_x = item.pos().x()
        new_y = item.pos().y()
        new_rot = building.rotation
        old_rot = old_rotation if old_rotation is not None else new_rot

        move = BuildingMove(
            building_id=building_id,
            old_x=old_x,
            old_y=old_y,
            old_rotation=old_rot,
            new_x=new_x,
            new_y=new_y,
            new_rotation=new_rot,
        )
        scene_room_id = self.get_scene_for_item(item)
        cmd = MoveBuildingsCommand(scene_room_id=scene_room_id, canvas=self, moves=(move,))
        self.command_stack.execute(cmd)
        self.update_belts_for_building(building_id, item.building_scene)

    # === Internal helpers ===

    def _update_belts_for_placement(self, placement_id: str) -> None:
        """Redraw all belts connected to a room placement."""
        for belt in self.document.belts.values():
            if belt.source_building_id == placement_id or belt.dest_building_id == placement_id:
                belt_item = self._belt_items.get(belt.id)
                if belt_item:
                    belt_item._update_path_from_endpoints()

    def window(self) -> MainWindow:
        """Return the MainWindow that contains this canvas."""
        from satisfactory_planner.ui.main_window import MainWindow

        w = super().window()
        assert isinstance(w, MainWindow)
        return w

    def set_show_flow_rate(self, show: bool) -> None:
        self._show_flow_rate = show

    @property
    def show_flow_rate(self) -> bool:
        return self._show_flow_rate

    def set_show_efficiency(self, show: bool) -> None:
        self._show_efficiency = show

    @property
    def show_efficiency(self) -> bool:
        return self._show_efficiency

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        """Draw the grid background."""
        super().drawBackground(painter, rect)

        if not self._grid_snap:
            return

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
