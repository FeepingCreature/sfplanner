"""Library panel for selecting buildings to place."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
)

from satisfactory_planner.core import BuildingType


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

        # Production buildings
        production_group = QGroupBox("Production")
        production_layout = QVBoxLayout(production_group)
        self.production_list = QListWidget()
        self.production_list.setMaximumHeight(200)

        production_types = [
            BuildingType.SMELTER,
            BuildingType.FOUNDRY,
            BuildingType.CONSTRUCTOR,
            BuildingType.ASSEMBLER,
            BuildingType.MANUFACTURER,
            BuildingType.REFINERY,
            BuildingType.PACKAGER,
            BuildingType.BLENDER,
        ]
        for building_type in production_types:
            item = QListWidgetItem(building_type.value)
            item.setData(Qt.UserRole, building_type)
            self.production_list.addItem(item)

        self.production_list.itemClicked.connect(self._on_item_clicked)
        production_layout.addWidget(self.production_list)
        layout.addWidget(production_group)

        # Extraction buildings
        extraction_group = QGroupBox("Extraction")
        extraction_layout = QVBoxLayout(extraction_group)
        self.extraction_list = QListWidget()
        self.extraction_list.setMaximumHeight(100)

        extraction_types = [
            BuildingType.MINER_MK1,
            BuildingType.MINER_MK2,
            BuildingType.MINER_MK3,
        ]
        for building_type in extraction_types:
            item = QListWidgetItem(building_type.value)
            item.setData(Qt.UserRole, building_type)
            self.extraction_list.addItem(item)

        self.extraction_list.itemClicked.connect(self._on_item_clicked)
        extraction_layout.addWidget(self.extraction_list)
        layout.addWidget(extraction_group)

        # Logistics buildings
        logistics_group = QGroupBox("Logistics")
        logistics_layout = QVBoxLayout(logistics_group)
        self.logistics_list = QListWidget()
        self.logistics_list.setMaximumHeight(80)

        logistics_types = [
            BuildingType.SPLITTER,
            BuildingType.MERGER,
        ]
        for building_type in logistics_types:
            item = QListWidgetItem(building_type.value)
            item.setData(Qt.UserRole, building_type)
            self.logistics_list.addItem(item)

        self.logistics_list.itemClicked.connect(self._on_item_clicked)
        logistics_layout.addWidget(self.logistics_list)
        layout.addWidget(logistics_group)

        # User blueprints section (placeholder)
        blueprints_group = QGroupBox("Blueprints")
        blueprints_layout = QVBoxLayout(blueprints_group)
        self.blueprints_list = QListWidget()
        self.blueprints_list.setMaximumHeight(100)

        placeholder = QListWidgetItem("(No saved blueprints)")
        placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsEnabled)
        self.blueprints_list.addItem(placeholder)

        blueprints_layout.addWidget(self.blueprints_list)
        layout.addWidget(blueprints_group)

        layout.addStretch()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle building selection."""
        building_type = item.data(Qt.UserRole)
        if building_type:
            self.building_selected.emit(building_type)

            # Clear selection in other lists
            sender = self.sender()
            for list_widget in [
                self.production_list,
                self.extraction_list,
                self.logistics_list,
            ]:
                if list_widget != sender:
                    list_widget.clearSelection()
