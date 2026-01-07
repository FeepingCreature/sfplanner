"""Properties panel for editing selected items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from satisfactory_planner.core import BuildingType, Document, Room, RoomPlacement
from satisfactory_planner.core.models import get_building_io_counts, get_building_power
from satisfactory_planner.core.persistence import load_all_recipes, save_user_recipes
from satisfactory_planner.ui.commands import (
    CommandStack,
    DelinkRoomCommand,
    SetBeltTierCommand,
    SetClockSpeedCommand,
    SetRecipeCommand,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


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
        self.canvas: FactoryCanvas | None = None  # Set by MainWindow
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

        # Recipe selector with edit button on right
        recipe_layout = QHBoxLayout()
        recipe_layout.setSpacing(4)

        self.recipe_combo = QComboBox()
        self.recipe_combo.addItem("(No recipe)", None)
        self.recipe_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.recipe_combo.currentIndexChanged.connect(self._on_recipe_changed)
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
        self.tier_combo.currentIndexChanged.connect(self._on_tier_changed)
        belt_layout.addRow("Tier:", self.tier_combo)

        # Flow rate (read-only)
        self.flow_label = QLabel("-")
        belt_layout.addRow("Flow Rate:", self.flow_label)

        # Item type (read-only)
        self.item_label = QLabel("-")
        belt_layout.addRow("Item:", self.item_label)

        layout.addWidget(self.belt_group)
        self.belt_group.hide()

        # Room properties group
        self.room_group = QGroupBox("Room Properties")
        room_layout = QFormLayout(self.room_group)

        # Room name
        self.room_name_label = QLabel("-")
        room_layout.addRow("Name:", self.room_name_label)

        # Size
        self.room_size_label = QLabel("-")
        room_layout.addRow("Size:", self.room_size_label)

        # Contents
        self.room_contents_label = QLabel("-")
        room_layout.addRow("Contents:", self.room_contents_label)

        # Link status
        self.room_link_label = QLabel("-")
        room_layout.addRow("Instances:", self.room_link_label)

        # Action buttons
        room_buttons = QHBoxLayout()

        self.save_blueprint_btn = QPushButton("Save to Library")
        self.save_blueprint_btn.setToolTip("Save this room as a blueprint")
        self.save_blueprint_btn.clicked.connect(self._on_save_blueprint)
        room_buttons.addWidget(self.save_blueprint_btn)

        self.delink_btn = QPushButton("Unlink")
        self.delink_btn.setToolTip("Make this instance independent")
        self.delink_btn.clicked.connect(self._on_delink)
        room_buttons.addWidget(self.delink_btn)

        room_layout.addRow(room_buttons)

        layout.addWidget(self.room_group)
        self.room_group.hide()

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

    def _update_recipe_combo(self, building_type: BuildingType | None = None) -> None:
        """Update recipe combo with available recipes filtered by building type."""
        # Load all recipes (base game + user) into the document
        all_recipes = load_all_recipes()
        for recipe_id, recipe in all_recipes.items():
            if recipe_id not in self.document.recipes:
                self.document.recipes[recipe_id] = recipe

        self.recipe_combo.clear()
        self.recipe_combo.addItem("(No recipe)", None)
        for recipe_id, recipe in self.document.recipes.items():
            # Filter by building type if specified
            if building_type is None or recipe.building_type == building_type:
                self.recipe_combo.addItem(recipe.name, recipe_id)

    def set_document(
        self, document: Document, command_stack: CommandStack, canvas: FactoryCanvas
    ) -> None:
        """Set a new document."""
        self.document = document
        self.command_stack = command_stack
        self.canvas = canvas
        self._selected_ids = []
        self._update_recipe_combo()
        self._update_display()

    def set_selection(self, selected_ids: list[str]) -> None:
        """Update the displayed properties for the selection."""
        self._selected_ids = selected_ids
        self._update_display()

    def _get_selected_room_item(self) -> tuple[RoomPlacement, Room] | None:
        """Get the selected RoomItem if exactly one room is selected.

        Returns (placement, room) or None.
        """
        if not self.canvas or len(self._selected_ids) != 1:
            return None

        from satisfactory_planner.ui.items import RoomItem

        # Check if selected item is a room placement
        item_id = self._selected_ids[0]
        if item_id in self.canvas._room_items:
            room_item = self.canvas._room_items[item_id]
            if isinstance(room_item, RoomItem):
                return (room_item.placement, room_item.room)

        return None

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

                # Update recipe combo filtered by building type
                self._update_recipe_combo(building.building_type)

                # Select current recipe in combo
                if building.recipe_id:
                    for i in range(self.recipe_combo.count()):
                        if self.recipe_combo.itemData(i) == building.recipe_id:
                            self.recipe_combo.setCurrentIndex(i)
                            break
                else:
                    self.recipe_combo.setCurrentIndex(0)

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
            # Check if it's a room placement
            else:
                room_info = self._get_selected_room_item()
                if room_info:
                    placement, room = room_info
                    self.selection_label.setText(f"Room: {room.name}")

                    self.room_name_label.setText(room.name)
                    self.room_size_label.setText(f"{int(room.width)} × {int(room.height)}")
                    self.room_contents_label.setText(
                        f"{len(room.buildings)} buildings, {len(room.belts)} belts"
                    )

                    # Count placements of this room
                    placements = self.document.get_placements_for_room(room.id)
                    num_placements = len(placements)
                    if num_placements > 1:
                        self.room_link_label.setText(f"{num_placements} (linked)")
                        self.delink_btn.setEnabled(True)
                    else:
                        self.room_link_label.setText("1 (unique)")
                        self.delink_btn.setEnabled(False)

                    self.room_group.show()
                    self.building_group.hide()
                    self.belt_group.hide()
                    self.stats_group.hide()
                else:
                    # Unknown item type
                    self.selection_label.setText("Unknown item")
                    self.building_group.hide()
                    self.belt_group.hide()
                    self.room_group.hide()
                    self.stats_group.hide()
        else:
            self.selection_label.setText(f"{len(self._selected_ids)} items selected")
            self.building_group.hide()
            self.belt_group.hide()
            self.room_group.hide()
            self.stats_group.hide()

        self._updating = False

    def _on_clock_speed_changed(self, value: float) -> None:
        """Handle clock speed change."""
        if self._updating or not self.canvas:
            return

        if len(self._selected_ids) == 1:
            building_id = self._selected_ids[0]
            building = self.document.buildings.get(building_id)
            if building:
                # Get scene from the building item itself
                building_item = self.canvas._building_items.get(building_id)
                scene_room_id = (
                    self.canvas.get_scene_for_item(building_item) if building_item else None
                )
                cmd = SetClockSpeedCommand(
                    scene_room_id=scene_room_id,
                    building_id=building_id,
                    old_clock_speed=building.clock_speed,
                    new_clock_speed=value / 100.0,
                    canvas=self.canvas,
                )
                self.command_stack.execute(cmd)

    def _on_recipe_changed(self, index: int) -> None:
        """Handle recipe selection change."""
        if self._updating or not self.canvas:
            return

        if len(self._selected_ids) == 1:
            building_id = self._selected_ids[0]
            building = self.document.buildings.get(building_id)
            if building:
                recipe_id = self.recipe_combo.currentData()
                # Get scene from the building item itself
                building_item = self.canvas._building_items.get(building_id)
                scene_room_id = (
                    self.canvas.get_scene_for_item(building_item) if building_item else None
                )
                cmd = SetRecipeCommand(
                    scene_room_id=scene_room_id,
                    building_id=building_id,
                    old_recipe_id=building.recipe_id,
                    new_recipe_id=recipe_id,
                    canvas=self.canvas,
                )
                self.command_stack.execute(cmd)

    def _on_tier_changed(self, index: int) -> None:
        """Handle belt tier change."""
        if self._updating or not self.canvas:
            return

        if len(self._selected_ids) == 1:
            belt_id = self._selected_ids[0]
            belt = self.document.belts.get(belt_id)
            if belt:
                new_tier = self.tier_combo.currentData()
                if new_tier and new_tier != belt.tier:
                    # Get scene from the belt item itself
                    belt_item = self.canvas._belt_items.get(belt_id)
                    scene_room_id = self.canvas.get_scene_for_item(belt_item) if belt_item else None
                    cmd = SetBeltTierCommand(
                        scene_room_id=scene_room_id,
                        belt_id=belt_id,
                        old_tier=belt.tier,
                        new_tier=new_tier,
                        canvas=self.canvas,
                    )
                    self.command_stack.execute(cmd)

    def _on_save_blueprint(self) -> None:
        """Save the selected room as a blueprint."""
        if not self.canvas:
            return

        room_info = self._get_selected_room_item()
        if not room_info:
            return

        _placement, room = room_info

        from satisfactory_planner.core import save_blueprint

        save_blueprint(room)

        # Try to refresh the library panel if accessible
        # (MainWindow connects this)
        QMessageBox.information(
            self,
            "Blueprint Saved",
            f"Blueprint '{room.name}' saved to library.",
        )

    def _on_delink(self) -> None:
        """Unlink the selected room placement."""
        if not self.canvas:
            return

        room_info = self._get_selected_room_item()
        if not room_info:
            return

        placement, room = room_info

        # Check if room has multiple placements
        placements = self.document.get_placements_for_room(room.id)
        if len(placements) <= 1:
            QMessageBox.information(
                self,
                "Cannot Unlink",
                "This room has only one instance. Nothing to unlink.",
            )
            return

        cmd = DelinkRoomCommand(
            placement_id=placement.id,
            canvas=self.canvas,
            old_room_id=room.id,
        )
        self.command_stack.execute(cmd)

        # Refresh display
        self._update_display()
