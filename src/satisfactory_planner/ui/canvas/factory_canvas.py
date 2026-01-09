"""Factory canvas using QGraphicsView."""

from __future__ import annotations

import copy
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
from satisfactory_planner.core.models import Scene, generate_id
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
from satisfactory_planner.ui.items.warning_icon_item import WarningIconItem

if TYPE_CHECKING:
    from satisfactory_planner.core.models import RoomPlacement

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
    """

    selection_changed = Signal(list)
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
        self._warning_icons: list[WarningIconItem] = []

        # Mutation callback
        self._mutation_callback: Callable[[], None] | None = None

        # Clipboard
        self._clipboard_buildings: list[Building] = []
        self._clipboard_belts: list[Belt] = []
        self._clipboard_room_ids: list[str] = []

        # Default belt tier for new connections
        self._default_belt_tier: int = 1

        # Initialize managers BEFORE _setup_scene (which uses _selection)
        from satisfactory_planner.ui.canvas.belt_connector import BeltConnector
        from satisfactory_planner.ui.canvas.drawing_tools import DrawingTools
        from satisfactory_planner.ui.canvas.placement_manager import PlacementManager
        from satisfactory_planner.ui.canvas.selection_manager import SelectionManager

        self._belt_connector = BeltConnector(self)
        self._placement = PlacementManager(self)
        self._drawing = DrawingTools(self)
        self._selection = SelectionManager(self)

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

    def update_belts_for_building(self, building_id: str, scene: Scene | None = None) -> None:
        """Redraw all belts connected to a building."""
        self._update_belts_for_building(building_id, scene)

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

    # === CommandHandler protocol ===

    def add_building_item(self, building: Building) -> BuildingItem:
        """Add a building item to the scene."""
        item = BuildingItem(building, self)
        self._scene.addItem(item)
        self._building_items[building.id] = item
        return item

    def remove_building_item(self, building_id: str) -> None:
        """Remove a building item from the scene."""
        item = self._building_items.pop(building_id, None)
        if item:
            self._scene.removeItem(item)

    def add_belt_item(self, belt: Belt) -> BeltItem | None:
        """Add a belt item to the scene.

        Supports belts connecting to:
        - Buildings (in document or rooms)
        - RoomPlacements (treated as buildings with ports)
        """
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

    def refresh_building(self, building_id: str) -> None:
        """Refresh a building's visual state."""
        item = self._building_items.get(building_id)
        if item:
            building = self.document.buildings.get(building_id)
            if building:
                item.setPos(building.x, building.y)
            item.update()

    def refresh_belts_for_building(self, building_id: str) -> None:
        """Refresh belts connected to a building."""
        for room_id, room in self.document.rooms.items():
            if building_id in room.buildings:
                self._refresh_all_room_items(room_id)
                return
        self._update_belts_for_building(building_id)

    def refresh_belt(self, belt_id: str, scene_room_id: str | None = None) -> None:
        """Refresh a belt's visual state."""
        belt_item = self._belt_items.get(belt_id)
        if not belt_item:
            return

        # Get belt from correct scene
        if scene_room_id and scene_room_id in self.document.rooms:
            scene: Scene = self.document.rooms[scene_room_id]
        else:
            scene = self.document

        belt = scene.belts.get(belt_id)
        if belt:
            source = scene.buildings.get(belt.source_building_id)
            dest = scene.buildings.get(belt.dest_building_id)
            if source and dest:
                belt_item.update_path(source, dest)
            else:
                # May be connected to placements - use generic update
                belt_item._update_path_from_endpoints()

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
        # Qt needs to finish processing the scene addition before child items
        # can be properly rendered. Using QTimer.singleShot(0, ...) ensures
        # the refresh happens after the current event is fully processed.
        def deferred_refresh() -> None:
            room_item.refresh()
            # Re-register items after refresh using composite keys (placement_id:item_id)
            # This ensures each room placement's items are tracked separately
            for building_id, building_item in room_item._building_items.items():
                composite_key = f"{placement_id}:{building_id}"
                self._building_items[composite_key] = building_item
            for belt_id, belt_item in room_item._belt_items.items():
                composite_key = f"{placement_id}:{belt_id}"
                self._belt_items[composite_key] = belt_item
            # Refresh linked rooms too
            for other_placement_id, other_room_item in list(self._room_items.items()):
                if (
                    isinstance(other_room_item, RoomItem)
                    and other_room_item.room.id == room.id
                    and other_placement_id != placement_id
                ):
                    other_room_item.refresh()
                    for building_id, building_item in other_room_item._building_items.items():
                        composite_key = f"{other_placement_id}:{building_id}"
                        self._building_items[composite_key] = building_item
                    for belt_id, belt_item in other_room_item._belt_items.items():
                        composite_key = f"{other_placement_id}:{belt_id}"
                        self._belt_items[composite_key] = belt_item

        QTimer.singleShot(0, deferred_refresh)

    def remove_room_item(self, placement_id: str) -> None:
        """Remove a room item from the scene."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        room_item = self._room_items.pop(placement_id, None)
        if room_item and isinstance(room_item, RoomItem):
            for building_id in list(room_item._building_items.keys()):
                composite_key = f"{placement_id}:{building_id}"
                self._building_items.pop(composite_key, None)
            for belt_id in list(room_item._belt_items.keys()):
                composite_key = f"{placement_id}:{belt_id}"
                self._belt_items.pop(composite_key, None)
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
        # Scroll up = counter-clockwise (-90), scroll down = clockwise (+90)
        delta = -90 if event.angleDelta().y() > 0 else 90

        # Placement mode rotation
        if self._placement.placement_mode:
            self._placement.rotate(delta)
            return

        # Drag rotation for existing building
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem) and item._is_dragging:
                item.rotate_building(delta)
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

        # Right click - cancel or pan (depending on context)
        if event.button() == Qt.MouseButton.RightButton:
            if self._placement.is_placing:
                self._placement.set_building_mode(None)
                return
            if self._drawing.is_box_selecting:
                self._drawing.cancel_box_select()
                return
            # Right-click on empty space = pan (alternative to middle mouse)
            item_at_pos = self.itemAt(event.pos())
            if item_at_pos is None or item_at_pos is self._selection.outline_item:
                self._is_panning = True
                self._pan_start = QPointF(float(event.pos().x()), float(event.pos().y()))
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return

        # Left click
        if event.button() == Qt.MouseButton.LeftButton:
            # Placement mode
            if self._placement.place_at(scene_pos):
                return

            # Room creation mode
            if self._tool_mode == ToolMode.CREATE_ROOM:
                self._drawing.start_room_create(scene_pos)
                return

            # Normal mode - start box select on empty space
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

        # Box select
        if self._drawing.is_box_selecting:
            self._drawing.update_box_select(scene_pos)
            return

        # Room creation
        if self._drawing.is_creating_room:
            self._drawing.update_room_create(scene_pos)
            return

        # Belt drag preview
        if self._belt_connector.is_connecting:
            self._belt_connector.update_preview(scene_pos)
            self._belt_connector.update_hover_target(scene_pos)

        # Placement ghost
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
            # Complete box select
            if self._drawing.is_box_selecting:
                self._drawing.complete_box_select()
                return

            # Complete room creation
            if self._drawing.is_creating_room:
                self._drawing.complete_room_create()
                return

            # Complete belt connection
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

        # Delete room placements
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
            # Determine which scene (document or room) these items belong to
            first_item = next(
                (
                    item
                    for item in self._scene.selectedItems()
                    if isinstance(item, (BuildingItem, BeltItem))
                ),
                None,
            )
            scene_room_id = self.get_scene_for_item(first_item) if first_item else None

            # Get the correct scene to look up items
            if scene_room_id and scene_room_id in self.document.rooms:
                target_scene: Scene = self.document.rooms[scene_room_id]
            else:
                target_scene = self.document

            # Add connected belts to deletion list
            for building_id in selected_buildings:
                for belt in target_scene.get_belts_for_building(building_id):
                    if belt.id not in selected_belts:
                        selected_belts.append(belt.id)

            # Look up items from the correct scene
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

    def start_belt_drag(self, building_id: str, port_index: int, start_pos: QPointF) -> None:
        """Start dragging a belt connection from an output port."""
        self._belt_connector.start_drag(building_id, port_index, start_pos)

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

    # === Copy/paste ===

    def copy_selection(self) -> None:
        """Copy selected items to clipboard."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        self._clipboard_buildings.clear()
        self._clipboard_belts.clear()
        self._clipboard_room_ids.clear()

        selected_building_ids: set[str] = set()
        for item in self._scene.selectedItems():
            if isinstance(item, BuildingItem):
                self._clipboard_buildings.append(copy.deepcopy(item.building))
                selected_building_ids.add(item.building.id)
            elif isinstance(item, RoomItem):
                self._clipboard_room_ids.append(item.room.id)

        for belt in self.document.belts.values():
            if (
                belt.source_building_id in selected_building_ids
                and belt.dest_building_id in selected_building_ids
            ):
                self._clipboard_belts.append(copy.deepcopy(belt))

    def paste(self) -> None:
        """Paste from clipboard."""
        from satisfactory_planner.core.models import RoomPlacement

        if not self._clipboard_buildings and not self._clipboard_room_ids:
            return

        offset = 50.0
        new_item_ids: list[str] = []

        if self._clipboard_buildings:
            id_map: dict[str, str] = {}
            scene_room_id: str | None = None

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
                scene_room_id = self.get_room_at_point(QPointF(new_building.x, new_building.y))
                cmd = PlaceBuildingCommand(
                    scene_room_id=scene_room_id, building=new_building, canvas=self
                )
                self.command_stack.execute(cmd)
                new_item_ids.append(new_id)

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
                    belt_cmd = ConnectBeltCommand(
                        scene_room_id=scene_room_id, belt=new_belt, canvas=self
                    )
                    self.command_stack.execute(belt_cmd)

        for room_id in self._clipboard_room_ids:
            room = self.document.rooms.get(room_id)
            if not room:
                continue

            existing = self.document.get_placements_for_room(room_id)
            if existing:
                base_x, base_y = existing[0].x + offset, existing[0].y + offset
            else:
                base_x, base_y = offset, offset

            new_placement = RoomPlacement(
                id=generate_id(),
                room_id=room_id,
                x=base_x,
                y=base_y,
                parent_room_id=None,
            )
            self.document.room_placements[new_placement.id] = new_placement
            self.add_room_item(new_placement, room)
            new_item_ids.append(new_placement.id)

        self.notify_mutation()

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

    # === Building movement ===

    def on_building_moved(
        self,
        item_or_id: BuildingItem | str,
        old_x: float,
        old_y: float,
        old_rotation: int | None = None,
    ) -> None:
        """Handle a building being moved.

        Args:
            item_or_id: Either the BuildingItem itself (preferred) or building_id (legacy)
        """
        if isinstance(item_or_id, str):
            # Legacy path - lookup by ID (may get wrong item for linked rooms)
            item = self._building_items.get(item_or_id)
            building_id = item_or_id
        else:
            # New path - use the actual item that was dragged
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
        self._update_belts_for_building(building_id)

    # === Internal helpers ===

    def _update_belts_for_building(self, building_id: str, scene: Scene | None = None) -> None:
        """Redraw all belts connected to a building.

        Handles belts where one or both endpoints may be:
        - A Building in the scene
        - A RoomPlacement (for belts crossing room boundaries)
        """
        target_scene: Scene = scene if scene is not None else self.document
        for belt in target_scene.get_belts_for_building(building_id):
            belt_item = self._belt_items.get(belt.id)
            if belt_item:
                # Use _update_path_from_endpoints which handles both
                # Buildings and RoomPlacements
                belt_item._update_path_from_endpoints()

    def _update_belts_for_placement(self, placement_id: str) -> None:
        """Redraw all belts connected to a room placement."""
        # Belts to room placements are stored in document.belts (or parent scene)
        # and use the placement_id as source/dest_building_id
        for belt in self.document.belts.values():
            if belt.source_building_id == placement_id or belt.dest_building_id == placement_id:
                belt_item = self._belt_items.get(belt.id)
                if belt_item:
                    # Use _update_path_from_endpoints which handles placements
                    belt_item._update_path_from_endpoints()

    def set_show_flow_rates(self, show: bool) -> None:
        """Toggle flow rate display on all belts."""
        for belt_item in self._belt_items.values():
            belt_item.set_show_flow_rate(show)

    def set_show_efficiency(self, show: bool) -> None:
        """Toggle efficiency overlay on all buildings."""
        for building_item in self._building_items.values():
            building_item.set_show_efficiency(show)
            if not show:
                # Clear efficiency value when disabling
                building_item.set_efficiency(None)

    def update_flow_visualization(self) -> None:
        """Update visual state of items based on flow solver results."""
        main_window = self.window()
        if not hasattr(main_window, "current_tab") or not main_window.current_tab:
            return

        flow_solver = main_window.current_tab.flow_solver
        if not flow_solver or not flow_solver._solved_model:
            return

        solved = flow_solver._solved_model

        # Update belt overcapacity state and utilization
        for edge in solved.graph.edges.values():
            if edge.belt_id and edge.belt_id in self._belt_items:
                belt_item = self._belt_items[edge.belt_id]
                belt_item.set_overcapacity(edge.is_overcapacity)
                # Calculate utilization
                if edge.capacity > 0:
                    belt_item.set_utilization(edge.flow_rate / edge.capacity)
                else:
                    belt_item.set_utilization(None)

        # Update building efficiency
        for eff in solved.efficiencies.values():
            if eff.building_id in self._building_items:
                item = self._building_items[eff.building_id]
                item.set_efficiency(eff.duty_cycle)

        # Update warning icons
        self._update_warning_icons(flow_solver._warnings)

    def _update_warning_icons(self, warnings: list[object]) -> None:
        """Update warning icons based on current warnings."""
        from satisfactory_planner.core.flow_solver import Warning

        # Remove existing warning icons
        for icon in self._warning_icons:
            self._scene.removeItem(icon)
        self._warning_icons.clear()

        # Add new warning icons at element positions
        for warning in warnings:
            if not isinstance(warning, Warning):
                continue

            position = self._get_element_position(warning.element_id)
            if position:
                # Offset slightly so icon doesn't cover the element
                offset_pos = QPointF(position.x() + 30, position.y() - 10)
                icon = WarningIconItem(warning, offset_pos)
                self._scene.addItem(icon)
                self._warning_icons.append(icon)

    def _get_element_position(self, element_id: str) -> QPointF | None:
        """Get the scene position for an element (building or belt)."""
        # Check buildings
        if element_id in self._building_items:
            building_item = self._building_items[element_id]
            rect = building_item.boundingRect()
            # Use mapToScene to handle buildings inside rooms correctly
            return building_item.mapToScene(rect.center())

        # Check belts - use midpoint
        if element_id in self._belt_items:
            belt_item = self._belt_items[element_id]
            path = belt_item.path()
            if path.length() > 0:
                # Use mapToScene to handle belts inside rooms correctly
                point = path.pointAtPercent(0.5)
                return belt_item.mapToScene(point)

        return None

    def clear_warning_icons(self) -> None:
        """Remove all warning icons from the scene."""
        for icon in self._warning_icons:
            self._scene.removeItem(icon)
        self._warning_icons.clear()

    def _refresh_all_room_items(self, room_id: str) -> None:
        """Refresh all RoomItems displaying the given room."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        for placement_id, room_item in self._room_items.items():
            if isinstance(room_item, RoomItem) and room_item.room.id == room_id:
                for building_id in list(room_item._building_items.keys()):
                    composite_key = f"{placement_id}:{building_id}"
                    self._building_items.pop(composite_key, None)
                for belt_id in list(room_item._belt_items.keys()):
                    composite_key = f"{placement_id}:{belt_id}"
                    self._belt_items.pop(composite_key, None)

                room_item.refresh()

                for building_id, building_item in room_item._building_items.items():
                    composite_key = f"{placement_id}:{building_id}"
                    self._building_items[composite_key] = building_item
                for belt_id, belt_item in room_item._belt_items.items():
                    composite_key = f"{placement_id}:{belt_id}"
                    self._belt_items[composite_key] = belt_item

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
