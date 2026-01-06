"""Library panel for selecting buildings to place."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
)

from satisfactory_planner.core import BuildingType, BUILDING_METADATA


# Building info: (description, extra_info)
BUILDING_INFO: dict[BuildingType, tuple[str, str]] = {
    BuildingType.SMELTER: ("Smelts ore into ingots", "1 input → 1 output"),
    BuildingType.FOUNDRY: ("Alloy smelting", "2 inputs → 1 output"),
    BuildingType.CONSTRUCTOR: ("Basic crafting", "1 input → 1 output"),
    BuildingType.ASSEMBLER: ("Two-part assembly", "2 inputs → 1 output"),
    BuildingType.MANUFACTURER: ("Complex crafting", "4 inputs → 1 output"),
    BuildingType.REFINERY: ("Fluid processing", "2 inputs → 2 outputs"),
    BuildingType.PACKAGER: ("Fluid packaging", "2 inputs → 2 outputs"),
    BuildingType.BLENDER: ("Fluid blending", "4 inputs → 2 outputs"),
    BuildingType.MINER_MK1: ("60/min base rate", "Extracts ore"),
    BuildingType.MINER_MK2: ("120/min base rate", "Extracts ore"),
    BuildingType.MINER_MK3: ("240/min base rate", "Extracts ore"),
    BuildingType.SPLITTER: ("1 → 3 split", "Divides belt"),
    BuildingType.MERGER: ("3 → 1 merge", "Combines belts"),
}


class BuildingTreeItem(QTreeWidgetItem):
    """Tree item for a building type with rich display."""

    def __init__(self, building_type: BuildingType) -> None:
        super().__init__()
        self.building_type = building_type

        info = BUILDING_INFO.get(building_type, ("", ""))
        meta = BUILDING_METADATA.get(building_type, (80, 60, 1, 1))

        # Main text is the building name
        self.setText(0, building_type.value)
        # Store extra info for tooltip
        self.setToolTip(0, f"{info[0]}\n{info[1]}\nSize: {meta[0]}x{meta[1]}")
        self.setData(0, Qt.UserRole, building_type)


class LibraryPanel(QWidget):
    """Panel for selecting buildings to place on the canvas."""

    # Emitted when a building type is selected for placement
    building_selected = Signal(object)  # BuildingType or None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Single tree view for all buildings
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragOnly)

        # Production category
        production_item = QTreeWidgetItem(["Production"])
        production_item.setFlags(production_item.flags() & ~Qt.ItemIsDragEnabled)
        font = production_item.font(0)
        font.setBold(True)
        production_item.setFont(0, font)

        for bt in [
            BuildingType.SMELTER,
            BuildingType.FOUNDRY,
            BuildingType.CONSTRUCTOR,
            BuildingType.ASSEMBLER,
            BuildingType.MANUFACTURER,
            BuildingType.REFINERY,
            BuildingType.PACKAGER,
            BuildingType.BLENDER,
        ]:
            production_item.addChild(BuildingTreeItem(bt))

        self.tree.addTopLevelItem(production_item)
        production_item.setExpanded(True)

        # Extraction category
        extraction_item = QTreeWidgetItem(["Extraction"])
        extraction_item.setFlags(extraction_item.flags() & ~Qt.ItemIsDragEnabled)
        extraction_item.setFont(0, font)

        for bt in [
            BuildingType.MINER_MK1,
            BuildingType.MINER_MK2,
            BuildingType.MINER_MK3,
        ]:
            extraction_item.addChild(BuildingTreeItem(bt))

        self.tree.addTopLevelItem(extraction_item)
        extraction_item.setExpanded(True)

        # Logistics category
        logistics_item = QTreeWidgetItem(["Logistics"])
        logistics_item.setFlags(logistics_item.flags() & ~Qt.ItemIsDragEnabled)
        logistics_item.setFont(0, font)

        for bt in [
            BuildingType.SPLITTER,
            BuildingType.MERGER,
        ]:
            logistics_item.addChild(BuildingTreeItem(bt))

        self.tree.addTopLevelItem(logistics_item)
        logistics_item.setExpanded(True)

        # Blueprints category (placeholder)
        blueprints_item = QTreeWidgetItem(["Blueprints"])
        blueprints_item.setFlags(blueprints_item.flags() & ~Qt.ItemIsDragEnabled)
        blueprints_item.setFont(0, font)

        placeholder = QTreeWidgetItem(["(No saved blueprints)"])
        placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsDragEnabled)
        blueprints_item.addChild(placeholder)

        self.tree.addTopLevelItem(blueprints_item)
        blueprints_item.setExpanded(True)

        # Connect signals
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.startDrag = self._start_drag  # type: ignore[method-assign]

        layout.addWidget(self.tree)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle building selection - attach to cursor."""
        building_type = item.data(0, Qt.UserRole)
        if building_type:
            self.building_selected.emit(building_type)

    def _start_drag(self, supported_actions: Qt.DropActions) -> None:
        """Start drag operation with building type."""
        item = self.tree.currentItem()
        if not item:
            return

        building_type = item.data(0, Qt.UserRole)
        if not building_type:
            return

        # Create drag with building type data
        drag = QDrag(self.tree)
        mime_data = QMimeData()
        mime_data.setText(building_type.value)
        mime_data.setData("application/x-building-type", building_type.value.encode())
        drag.setMimeData(mime_data)

        # Create a simple pixmap for drag preview
        pixmap = QPixmap(60, 40)
        pixmap.fill(QColor(100, 100, 100, 180))
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, building_type.value[:8])
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(30, 20))

        drag.exec(Qt.CopyAction)
