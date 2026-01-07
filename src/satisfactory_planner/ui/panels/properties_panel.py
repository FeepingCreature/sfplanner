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
    QPushButton,
    QToolButton,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QSpinBox,
    QSizePolicy,
)

from satisfactory_planner.core import Document, CommandStack, SetClockSpeedCommand, BuildingType

if TYPE_CHECKING:
    pass


class RecipeEditorDialog(QDialog):
    """Dialog for viewing and editing recipes."""

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Recipe Editor")
        self.setMinimumSize(500, 400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the dialog UI."""
        layout = QVBoxLayout(self)

        # Recipe list
        list_layout = QHBoxLayout()

        self.recipe_list = QListWidget()
        self.recipe_list.currentItemChanged.connect(self._on_recipe_selected)
        list_layout.addWidget(self.recipe_list, 1)

        # Recipe details form
        details_widget = QWidget()
        details_layout = QFormLayout(details_widget)

        self.name_edit = QLineEdit()
        details_layout.addRow("Name:", self.name_edit)

        self.building_combo = QComboBox()
        for bt in BuildingType:
            if bt not in (BuildingType.SPLITTER, BuildingType.MERGER,
                          BuildingType.MINER_MK1, BuildingType.MINER_MK2, BuildingType.MINER_MK3):
                self.building_combo.addItem(bt.value, bt)
        details_layout.addRow("Building:", self.building_combo)

        # Inputs section
        details_layout.addRow(QLabel("<b>Inputs (per minute):</b>"))
        self.input1_name = QLineEdit()
        self.input1_rate = QDoubleSpinBox()
        self.input1_rate.setRange(0, 10000)
        input1_layout = QHBoxLayout()
        input1_layout.addWidget(self.input1_name)
        input1_layout.addWidget(self.input1_rate)
        details_layout.addRow("Input 1:", input1_layout)

        self.input2_name = QLineEdit()
        self.input2_rate = QDoubleSpinBox()
        self.input2_rate.setRange(0, 10000)
        input2_layout = QHBoxLayout()
        input2_layout.addWidget(self.input2_name)
        input2_layout.addWidget(self.input2_rate)
        details_layout.addRow("Input 2:", input2_layout)

        # Outputs section
        details_layout.addRow(QLabel("<b>Outputs (per minute):</b>"))
        self.output1_name = QLineEdit()
        self.output1_rate = QDoubleSpinBox()
        self.output1_rate.setRange(0, 10000)
        output1_layout = QHBoxLayout()
        output1_layout.addWidget(self.output1_name)
        output1_layout.addWidget(self.output1_rate)
        details_layout.addRow("Output 1:", output1_layout)

        self.output2_name = QLineEdit()
        self.output2_rate = QDoubleSpinBox()
        self.output2_rate.setRange(0, 10000)
        output2_layout = QHBoxLayout()
        output2_layout.addWidget(self.output2_name)
        output2_layout.addWidget(self.output2_rate)
        details_layout.addRow("Output 2:", output2_layout)

        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(0, 1000)
        self.power_spin.setSuffix(" MW")
        details_layout.addRow("Power:", self.power_spin)

        list_layout.addWidget(details_widget, 2)
        layout.addLayout(list_layout)

        # Buttons
        button_layout = QHBoxLayout()

        add_btn = QPushButton("Add New")
        add_btn.clicked.connect(self._add_recipe)
        button_layout.addWidget(add_btn)

        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self._save_recipe)
        button_layout.addWidget(save_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Load existing recipes
        self._load_recipes()

    def _load_recipes(self) -> None:
        """Load recipes into list."""
        self.recipe_list.clear()
        for recipe_id, recipe in self.document.recipes.items():
            item = QListWidgetItem(recipe.name)
            item.setData(Qt.UserRole, recipe_id)
            self.recipe_list.addItem(item)

    def _on_recipe_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        """Handle recipe selection."""
        if not current:
            return

        recipe_id = current.data(Qt.UserRole)
        recipe = self.document.recipes.get(recipe_id)
        if not recipe:
            return

        self.name_edit.setText(recipe.name)

        # Set building type
        for i in range(self.building_combo.count()):
            if self.building_combo.itemData(i) == recipe.building_type:
                self.building_combo.setCurrentIndex(i)
                break

        # Set inputs
        if len(recipe.inputs) >= 1:
            self.input1_name.setText(recipe.inputs[0].item_id)
            self.input1_rate.setValue(recipe.inputs[0].rate)
        else:
            self.input1_name.clear()
            self.input1_rate.setValue(0)

        if len(recipe.inputs) >= 2:
            self.input2_name.setText(recipe.inputs[1].item_id)
            self.input2_rate.setValue(recipe.inputs[1].rate)
        else:
            self.input2_name.clear()
            self.input2_rate.setValue(0)

        # Set outputs
        if len(recipe.outputs) >= 1:
            self.output1_name.setText(recipe.outputs[0].item_id)
            self.output1_rate.setValue(recipe.outputs[0].rate)
        else:
            self.output1_name.clear()
            self.output1_rate.setValue(0)

        if len(recipe.outputs) >= 2:
            self.output2_name.setText(recipe.outputs[1].item_id)
            self.output2_rate.setValue(recipe.outputs[1].rate)
        else:
            self.output2_name.clear()
            self.output2_rate.setValue(0)

        self.power_spin.setValue(recipe.power_mw)

    def _add_recipe(self) -> None:
        """Add a new recipe."""
        from satisfactory_planner.core.models import generate_id, Recipe, ItemRate

        recipe_id = generate_id()
        recipe = Recipe(
            id=recipe_id,
            name="New Recipe",
            building_type=self.building_combo.currentData(),
            inputs=[],
            outputs=[],
            power_mw=0,
            crafting_time=1.0,
        )
        self.document.recipes[recipe_id] = recipe
        self._load_recipes()

    def _save_recipe(self) -> None:
        """Save current recipe changes."""
        current = self.recipe_list.currentItem()
        if not current:
            return

        from satisfactory_planner.core.models import Recipe, ItemRate

        recipe_id = current.data(Qt.UserRole)

        inputs = []
        if self.input1_name.text() and self.input1_rate.value() > 0:
            inputs.append(ItemRate(self.input1_name.text(), self.input1_rate.value()))
        if self.input2_name.text() and self.input2_rate.value() > 0:
            inputs.append(ItemRate(self.input2_name.text(), self.input2_rate.value()))

        outputs = []
        if self.output1_name.text() and self.output1_rate.value() > 0:
            outputs.append(ItemRate(self.output1_name.text(), self.output1_rate.value()))
        if self.output2_name.text() and self.output2_rate.value() > 0:
            outputs.append(ItemRate(self.output2_name.text(), self.output2_rate.value()))

        recipe = Recipe(
            id=recipe_id,
            name=self.name_edit.text(),
            building_type=self.building_combo.currentData(),
            inputs=inputs,
            outputs=outputs,
            power_mw=self.power_spin.value(),
            crafting_time=1.0,
        )
        self.document.recipes[recipe_id] = recipe

        # Update list item text
        current.setText(recipe.name)


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
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Set minimum width for the panel
        self.setMinimumWidth(220)

        # Selection info
        self.selection_label = QLabel("No selection")
        layout.addWidget(self.selection_label)

        # Building properties group
        self.building_group = QGroupBox("Building Properties")
        building_layout = QFormLayout(self.building_group)

        # Building type (read-only)
        self.type_label = QLabel("-")
        building_layout.addRow("Type:", self.type_label)

        # Recipe selector with edit button
        recipe_layout = QHBoxLayout()
        recipe_layout.setSpacing(4)
        self.recipe_combo = QComboBox()
        self.recipe_combo.addItem("(No recipe)", None)
        self.recipe_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        recipe_layout.addWidget(self.recipe_combo, 1)

        self.recipe_edit_btn = QToolButton()
        self.recipe_edit_btn.setText("✎")
        self.recipe_edit_btn.setToolTip("Edit recipes...")
        self.recipe_edit_btn.setAutoRaise(True)  # Flat look, highlights on hover
        self.recipe_edit_btn.clicked.connect(self._open_recipe_editor)
        recipe_layout.addWidget(self.recipe_edit_btn)
        building_layout.addRow("Recipe:", recipe_layout)

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

    def _open_recipe_editor(self) -> None:
        """Open the recipe editor dialog."""
        dialog = RecipeEditorDialog(self.document, self)
        dialog.exec()
        # Refresh recipe combo
        self._update_recipe_combo()

    def _update_recipe_combo(self) -> None:
        """Update recipe combo with available recipes."""
        self.recipe_combo.clear()
        self.recipe_combo.addItem("(No recipe)", None)
        for recipe_id, recipe in self.document.recipes.items():
            self.recipe_combo.addItem(recipe.name, recipe_id)

    def set_document(self, document: Document, command_stack: CommandStack) -> None:
        """Set a new document."""
        self.document = document
        self.command_stack = command_stack
        self._selected_ids = []
        self._update_recipe_combo()
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
