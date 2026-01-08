"""Selection management for the factory canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from satisfactory_planner.core import SELECTION_MARGIN
from satisfactory_planner.core.models import Scene
from satisfactory_planner.ui.items.building_item import BuildingItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas


class SelectionManager:
    """Manages selection state and the selection outline.

    Handles scene-local selection (items can only be selected within one scene at a time).
    """

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._selection_outline: QGraphicsRectItem | None = None

    def update_outline(self) -> None:
        """Update the dashed selection outline around selected buildings."""
        # Remove old outline (guard against deleted scene)
        if self._selection_outline:
            try:
                if self.canvas._scene is not None:
                    self.canvas._scene.removeItem(self._selection_outline)
            except RuntimeError:
                pass  # Scene already deleted
            self._selection_outline = None

        # Get selected building items
        selected_buildings = [
            item for item in self.canvas._scene.selectedItems() if isinstance(item, BuildingItem)
        ]

        if not selected_buildings:
            return

        # Compute bounding rect
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

        # Create dashed outline
        self._selection_outline = QGraphicsRectItem(bounds)
        pen = QPen(QColor(100, 150, 255), 2, Qt.PenStyle.DashLine)
        self._selection_outline.setPen(pen)
        self._selection_outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_outline.setZValue(-1)
        self._selection_outline.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._selection_outline.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.canvas._scene.addItem(self._selection_outline)

    @property
    def outline_item(self) -> QGraphicsRectItem | None:
        """Return the selection outline item (for hit testing)."""
        return self._selection_outline

    def get_scene_for_item(self, item: QGraphicsItem) -> Scene | None:
        """Get the scene (Document or Room) that an item belongs to."""
        from satisfactory_planner.ui.items.belt_item import BeltItem
        from satisfactory_planner.ui.items.room_item import RoomItem

        if isinstance(item, BuildingItem):
            return item.building_scene
        elif isinstance(item, BeltItem):
            parent = item.parentItem()
            if isinstance(parent, RoomItem):
                return parent.room
            return self.canvas.document
        elif isinstance(item, RoomItem):
            return item.parent_scene
        return None

    def clear_selection_in_other_scenes(self, current_scene: Scene) -> None:
        """Clear selection for all items not in the given scene."""
        for item in self.canvas._scene.selectedItems():
            item_scene = self.get_scene_for_item(item)
            if item_scene is not None and item_scene is not current_scene:
                item.setSelected(False)

    def on_item_clicked(self, item: QGraphicsItem) -> None:
        """Handle an item being clicked - enforce scene-local selection."""
        item_scene = self.get_scene_for_item(item)
        if item_scene is None:
            return
        self.clear_selection_in_other_scenes(item_scene)

    def select_all(self) -> None:
        """Select all buildings and belts."""
        for building_item in self.canvas._building_items.values():
            building_item.setSelected(True)
        for belt_item in self.canvas._belt_items.values():
            belt_item.setSelected(True)
        self.canvas._emit_selection_changed()
