"""Recipe editor dialog for viewing and editing recipes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from satisfactory_planner.core import BuildingType, Document
from satisfactory_planner.core.models import get_building_io_counts, get_building_power
from satisfactory_planner.core.persistence import save_user_recipes


class RecipeEditorDialog(QDialog):
    """Dialog for viewing and editing recipes.

    Features auto-save: changes are applied immediately when fields change.
    """

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self._updating = False  # Prevent auto-save during programmatic updates
        self.setWindowTitle("Recipe Editor")
        self.setMinimumSize(600, 450)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the dialog UI."""
        layout = QVBoxLayout(self)

        # Main content: list on left, details on right
        content_layout = QHBoxLayout()

        # Left side: recipe list + action buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.recipe_list = QListWidget()
        self.recipe_list.currentItemChanged.connect(self._on_recipe_selected)
        left_layout.addWidget(self.recipe_list)

        # Action buttons below list
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        self.add_btn = QToolButton()
        self.add_btn.setText("+")
        self.add_btn.setToolTip("Add new recipe")
        self.add_btn.clicked.connect(self._add_recipe)
        action_layout.addWidget(self.add_btn)

        self.duplicate_btn = QToolButton()
        self.duplicate_btn.setText("📋")
        self.duplicate_btn.setToolTip("Duplicate selected recipe")
        self.duplicate_btn.clicked.connect(self._duplicate_recipe)
        action_layout.addWidget(self.duplicate_btn)

        self.delete_btn = QToolButton()
        self.delete_btn.setText("🗑")
        self.delete_btn.setToolTip("Delete selected recipe")
        self.delete_btn.clicked.connect(self._delete_recipe)
        action_layout.addWidget(self.delete_btn)

        action_layout.addStretch()
        left_layout.addLayout(action_layout)

        content_layout.addWidget(left_widget, 1)

        # Right side: recipe details form
        details_widget = QWidget()
        self.details_layout = QFormLayout(details_widget)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_field_changed)
        self.details_layout.addRow("Name:", self.name_edit)

        self.building_combo = QComboBox()
        for bt in BuildingType:
            if bt not in (
                BuildingType.SPLITTER,
                BuildingType.MERGER,
                BuildingType.MINER_MK1,
                BuildingType.MINER_MK2,
                BuildingType.MINER_MK3,
            ):
                self.building_combo.addItem(bt.value, bt)
        self.building_combo.currentIndexChanged.connect(self._on_building_changed)
        self.details_layout.addRow("Building:", self.building_combo)

        # Power display (read-only, determined by building)
        self.power_label = QLabel("-")
        self.details_layout.addRow("Power:", self.power_label)

        # Dynamic input/output sections (created based on building)
        self.inputs_label = QLabel("<b>Inputs (per minute):</b>")
        self.details_layout.addRow(self.inputs_label)

        # Input fields (up to 4 for Manufacturer/Blender)
        self.input_rows: list[tuple[QLineEdit, QDoubleSpinBox, QWidget]] = []
        for i in range(4):
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("Item name")
            name_edit.textChanged.connect(self._on_field_changed)
            rate_spin = QDoubleSpinBox()
            rate_spin.setRange(0, 10000)
            rate_spin.setDecimals(2)
            rate_spin.valueChanged.connect(self._on_field_changed)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(name_edit)
            row_layout.addWidget(rate_spin)
            self.details_layout.addRow(f"Input {i + 1}:", row_widget)
            self.input_rows.append((name_edit, rate_spin, row_widget))

        self.outputs_label = QLabel("<b>Outputs (per minute):</b>")
        self.details_layout.addRow(self.outputs_label)

        # Output fields (up to 2 for Refinery/Packager/Blender)
        self.output_rows: list[tuple[QLineEdit, QDoubleSpinBox, QWidget]] = []
        for i in range(2):
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("Item name")
            name_edit.textChanged.connect(self._on_field_changed)
            rate_spin = QDoubleSpinBox()
            rate_spin.setRange(0, 10000)
            rate_spin.setDecimals(2)
            rate_spin.valueChanged.connect(self._on_field_changed)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(name_edit)
            row_layout.addWidget(rate_spin)
            self.details_layout.addRow(f"Output {i + 1}:", row_widget)
            self.output_rows.append((name_edit, rate_spin, row_widget))

        content_layout.addWidget(details_widget, 2)
        layout.addLayout(content_layout)

        # Initialize visibility based on default building
        self._update_io_visibility()

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Load existing recipes
        self._load_recipes()

        # Update button states
        self._update_button_states()

    def _update_button_states(self) -> None:
        """Enable/disable buttons based on selection."""
        has_selection = self.recipe_list.currentItem() is not None
        self.duplicate_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _on_building_changed(self, index: int) -> None:
        """Handle building type change - update IO fields visibility and auto-save."""
        self._update_io_visibility()
        self._auto_save()

    def _on_field_changed(self) -> None:
        """Handle any field change - auto-save the recipe."""
        self._auto_save()

    def _auto_save(self) -> None:
        """Auto-save current recipe if we're not in the middle of loading."""
        if self._updating:
            return

        current = self.recipe_list.currentItem()
        if not current:
            return

        from satisfactory_planner.core.models import ItemRate, Recipe

        recipe_id = current.data(Qt.ItemDataRole.UserRole)
        building_type = self.building_combo.currentData()
        if not building_type:
            return

        num_inputs, num_outputs = get_building_io_counts(building_type)

        # Gather inputs based on building's input count
        inputs = []
        for i in range(num_inputs):
            name = self.input_rows[i][0].text()
            rate = self.input_rows[i][1].value()
            if name and rate > 0:
                inputs.append(ItemRate(name, rate))

        # Gather outputs based on building's output count
        outputs = []
        for i in range(num_outputs):
            name = self.output_rows[i][0].text()
            rate = self.output_rows[i][1].value()
            if name and rate > 0:
                outputs.append(ItemRate(name, rate))

        # Power is determined by building type
        power = get_building_power(building_type)

        recipe = Recipe(
            id=recipe_id,
            name=self.name_edit.text(),
            building_type=building_type,
            inputs=inputs,
            outputs=outputs,
            power_mw=power,
            crafting_time=1.0,
        )
        self.document.recipes[recipe_id] = recipe

        # Update list item text to reflect name change
        current.setText(recipe.name)

    def _update_io_visibility(self) -> None:
        """Show/hide input/output rows based on selected building type."""
        building_type = self.building_combo.currentData()
        if not building_type:
            return

        num_inputs, num_outputs = get_building_io_counts(building_type)
        power = get_building_power(building_type)

        # Update power display
        self.power_label.setText(f"{power} MW")

        # Show/hide input rows
        for i, (_name_edit, _rate_spin, row_widget) in enumerate(self.input_rows):
            visible = i < num_inputs
            row_widget.setVisible(visible)
            # Find and hide the label too
            label_index = self.details_layout.indexOf(row_widget)
            if label_index >= 0:
                label_item = self.details_layout.itemAt(label_index - 1)
                if label_item:
                    widget = label_item.widget()
                    if widget:
                        widget.setVisible(visible)

        # Show/hide output rows
        for i, (_name_edit, _rate_spin, row_widget) in enumerate(self.output_rows):
            visible = i < num_outputs
            row_widget.setVisible(visible)
            label_index = self.details_layout.indexOf(row_widget)
            if label_index >= 0:
                label_item = self.details_layout.itemAt(label_index - 1)
                if label_item:
                    widget = label_item.widget()
                    if widget:
                        widget.setVisible(visible)

    def _load_recipes(self) -> None:
        """Load recipes into list."""
        self.recipe_list.clear()
        for recipe_id, recipe in self.document.recipes.items():
            item = QListWidgetItem(recipe.name)
            item.setData(Qt.ItemDataRole.UserRole, recipe_id)
            self.recipe_list.addItem(item)

    def _on_recipe_selected(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        """Handle recipe selection."""
        self._update_button_states()

        if not current:
            return

        recipe_id = current.data(Qt.ItemDataRole.UserRole)
        recipe = self.document.recipes.get(recipe_id)
        if not recipe:
            return

        # Block auto-save while populating fields
        self._updating = True

        self.name_edit.setText(recipe.name)

        # Set building type (this will trigger _update_io_visibility)
        for i in range(self.building_combo.count()):
            if self.building_combo.itemData(i) == recipe.building_type:
                self.building_combo.setCurrentIndex(i)
                break

        # Clear all input/output fields first
        for name_edit, rate_spin, _ in self.input_rows:
            name_edit.clear()
            rate_spin.setValue(0)
        for name_edit, rate_spin, _ in self.output_rows:
            name_edit.clear()
            rate_spin.setValue(0)

        # Set inputs
        for i, item_rate in enumerate(recipe.inputs):
            if i < len(self.input_rows):
                self.input_rows[i][0].setText(item_rate.item_id)
                self.input_rows[i][1].setValue(item_rate.rate)

        # Set outputs
        for i, item_rate in enumerate(recipe.outputs):
            if i < len(self.output_rows):
                self.output_rows[i][0].setText(item_rate.item_id)
                self.output_rows[i][1].setValue(item_rate.rate)

        self._updating = False

    def _add_recipe(self) -> None:
        """Add a new recipe."""
        from satisfactory_planner.core.models import Recipe, generate_id

        recipe_id = generate_id()
        recipe = Recipe(
            id=recipe_id,
            name="New Recipe",
            building_type=self.building_combo.currentData() or BuildingType.SMELTER,
            inputs=[],
            outputs=[],
            power_mw=0,
            crafting_time=1.0,
        )
        self.document.recipes[recipe_id] = recipe

        # Add to list and select it
        item = QListWidgetItem(recipe.name)
        item.setData(Qt.ItemDataRole.UserRole, recipe_id)
        self.recipe_list.addItem(item)
        self.recipe_list.setCurrentItem(item)

    def _duplicate_recipe(self) -> None:
        """Duplicate the currently selected recipe."""
        current = self.recipe_list.currentItem()
        if not current:
            return

        from satisfactory_planner.core.models import ItemRate, Recipe, generate_id

        source_id = current.data(Qt.ItemDataRole.UserRole)
        source = self.document.recipes.get(source_id)
        if not source:
            return

        # Create a copy with new ID and modified name
        new_id = generate_id()
        new_recipe = Recipe(
            id=new_id,
            name=f"{source.name} (copy)",
            building_type=source.building_type,
            inputs=[ItemRate(ir.item_id, ir.rate) for ir in source.inputs],
            outputs=[ItemRate(ir.item_id, ir.rate) for ir in source.outputs],
            power_mw=source.power_mw,
            crafting_time=source.crafting_time,
        )
        self.document.recipes[new_id] = new_recipe

        # Add to list and select it
        item = QListWidgetItem(new_recipe.name)
        item.setData(Qt.ItemDataRole.UserRole, new_id)
        self.recipe_list.addItem(item)
        self.recipe_list.setCurrentItem(item)

    def _delete_recipe(self) -> None:
        """Delete the currently selected recipe after confirmation."""
        current = self.recipe_list.currentItem()
        if not current:
            return

        recipe_id = current.data(Qt.ItemDataRole.UserRole)
        recipe = self.document.recipes.get(recipe_id)
        if not recipe:
            return

        # Confirm deletion
        result = QMessageBox.question(
            self,
            "Delete Recipe",
            f"Are you sure you want to delete '{recipe.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        # Remove from document and list
        del self.document.recipes[recipe_id]
        row = self.recipe_list.row(current)
        self.recipe_list.takeItem(row)

    def accept(self) -> None:
        """Save recipes to XDG before closing."""
        save_user_recipes(self.document.recipes)
        super().accept()

    def reject(self) -> None:
        """Save recipes to XDG before closing (even on cancel/X)."""
        save_user_recipes(self.document.recipes)
        super().reject()
