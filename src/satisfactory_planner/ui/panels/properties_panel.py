"""Properties panel for editing selected items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
)

from satisfactory_planner.core import Document, CommandStack, SetClockSpeedCommand

if TYPE_CHECKING:
    pass


class PropertiesPanel(QWidget):
    """Panel for editing properties of selected items."""

    def __init__(
        self,
        document: Document,
        command_stack: CommandStack,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.document = document
        self.command_stack = command_stack
        self._selected_ids: list[str] = []
        self._updating = False  # Prevent signal loops

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Selection info
        self.selection_label = QLabel("No selection")
        layout.addWidget(self.selection_label)

        # Building properties group
        self.building_group = QGroupBox("Building Properties")
        building_layout = QFormLayout(self.building_group)

        # Building type (read-only)
        self.type_label = QLabel("-")
        building_layout.addRow("Type:", self.type_label)

        # Recipe selector
        self.recipe_combo = QComboBox()
        self.recipe_combo.addItem("(No recipe)", None)
        # TODO: Populate with actual recipes
        building_layout.addRow("Recipe:", self.recipe_combo)

        # Clock speed
        self.clock_spin = QDoubleSpinBox()
        self.clock_spin.setRange(1, 250)
        self.clock_spin.setSuffix("%")
        self.clock_spin.setValue(100)
        self.clock_spin.valueChanged.connect(self._on_clock_speed_changed)
        building_layout.addRow("Clock Speed:", self.clock_spin)

        layout.addWidget(self.building_group)
        self.building_group.hide()

        # Belt properties group
        self.belt_group = QGroupBox("Belt Properties")
        belt_layout = QFormLayout(self.belt_group)

        # Belt tier
        self.tier_combo = QComboBox()
        self.tier_combo.addItem("Mk.1 (60/min)", 1)
        self.tier_combo.addItem("Mk.2 (120/min)", 2)
        self.tier_combo.addItem("Mk.3 (270/min)", 3)
        self.tier_combo.addItem("Mk.4 (480/min)", 4)
        self.tier_combo.addItem("Mk.5 (780/min)", 5)
        self.tier_combo.addItem("Mk.6 (1200/min)", 6)
        belt_layout.addRow("Tier:", self.tier_combo)

        # Flow rate (read-only)
        self.flow_label = QLabel("-")
        belt_layout.addRow("Flow Rate:", self.flow_label)

        # Item type (read-only)
        self.item_label = QLabel("-")
        belt_layout.addRow("Item:", self.item_label)

        layout.addWidget(self.belt_group)
        self.belt_group.hide()

        # Production stats
        self.stats_group = QGroupBox("Production Stats")
        stats_layout = QFormLayout(self.stats_group)

        self.power_label = QLabel("-")
        stats_layout.addRow("Power:", self.power_label)

        self.input_label = QLabel("-")
        stats_layout.addRow("Input:", self.input_label)

        self.output_label = QLabel("-")
        stats_layout.addRow("Output:", self.output_label)

        layout.addWidget(self.stats_group)
        self.stats_group.hide()

        layout.addStretch()

    def set_document(self, document: Document, command_stack: CommandStack) -> None:
        """Set a new document."""
        self.document = document
        self.command_stack = command_stack
        self._selected_ids = []
        self._update_display()

    def set_selection(self, selected_ids: list[str]) -> None:
        """Update the displayed properties for the selection."""
        self._selected_ids = selected_ids
        self._update_display()

    def _update_display(self) -> None:
        """Update the panel to show current selection."""
        self._updating = True

        if not self._selected_ids:
            self.selection_label.setText("No selection")
            self.building_group.hide()
            self.belt_group.hide()
            self.stats_group.hide()
            self._updating = False
            return

        if len(self._selected_ids) == 1:
            item_id = self._selected_ids[0]

            # Check if it's a building
            if item_id in self.document.buildings:
                building = self.document.buildings[item_id]
                self.selection_label.setText(f"Building: {building.building_type.value}")
                self.type_label.setText(building.building_type.value)
                self.clock_spin.setValue(building.clock_speed * 100)

                self.building_group.show()
                self.stats_group.show()
                self.belt_group.hide()

                # Update stats
                self.power_label.setText("- MW")  # TODO: Calculate from recipe
                self.input_label.setText("-")
                self.output_label.setText("-")

            # Check if it's a belt
            elif item_id in self.document.belts:
                belt = self.document.belts[item_id]
                self.selection_label.setText(f"Belt Mk.{belt.tier}")

                # Set tier combo
                self.tier_combo.setCurrentIndex(belt.tier - 1)
                self.flow_label.setText(f"{belt.capacity}/min")
                self.item_label.setText(belt.item_id or "-")

                self.belt_group.show()
                self.building_group.hide()
                self.stats_group.hide()
        else:
            self.selection_label.setText(f"{len(self._selected_ids)} items selected")
            self.building_group.hide()
            self.belt_group.hide()
            self.stats_group.hide()

        self._updating = False

    def _on_clock_speed_changed(self, value: float) -> None:
        """Handle clock speed change."""
        if self._updating:
            return

        if len(self._selected_ids) == 1:
            building_id = self._selected_ids[0]
            if building_id in self.document.buildings:
                cmd = SetClockSpeedCommand(
                    document=self.document,
                    building_id=building_id,
                    new_clock_speed=value / 100.0,
                )
                self.command_stack.execute(cmd)
