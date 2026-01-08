"""Properties panel for editing selected items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from satisfactory_planner.core import (
    BuildingEfficiency,
    BuildingType,
    Document,
    Room,
    RoomPlacement,
)
from satisfactory_planner.core.persistence import load_all_recipes
from satisfactory_planner.ui.commands import (
    CommandStack,
    DelinkRoomCommand,
    SetBeltTierCommand,
    SetClockSpeedCommand,
    SetRecipeCommand,
)
from satisfactory_planner.ui.dialogs import RecipeEditorDialog

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


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

        # Room name (editable)
        self.room_name_edit = QLineEdit()
        self.room_name_edit.editingFinished.connect(self._on_room_name_changed)
        room_layout.addRow("Name:", self.room_name_edit)

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

        # Efficiency section
        self.efficiency_label = QLabel("-")
        stats_layout.addRow("Efficiency:", self.efficiency_label)

        self.status_label = QLabel("-")
        stats_layout.addRow("Status:", self.status_label)

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
        self.flow_solver = getattr(canvas, "_flow_solver", None)
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

                # Update efficiency from flow solver
                self._update_efficiency_display(building.id)

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

                    self.room_name_edit.setText(room.name)
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

    def _on_room_name_changed(self) -> None:
        """Handle room name edit."""
        if self._updating or not self.canvas:
            return

        room_info = self._get_selected_room_item()
        if not room_info:
            return

        _placement, room = room_info
        new_name = self.room_name_edit.text().strip()

        if new_name and new_name != room.name:
            # Directly update room name (affects all linked placements)
            room.name = new_name
            self.selection_label.setText(f"Room: {new_name}")

            # Refresh canvas to update room item display
            self.canvas.notify_mutation()

            # Refresh all room items showing this room
            from satisfactory_planner.ui.items import RoomItem

            for _placement_id, room_item in self.canvas._room_items.items():
                if isinstance(room_item, RoomItem) and room_item.room.id == room.id:
                    room_item.update()

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

    def _update_efficiency_display(self, building_id: str) -> None:
        """Update the efficiency display for a building."""
        # Try to get flow solver from main window
        flow_solver = None
        if self.canvas:
            # Access flow solver through main window's current tab
            main_window = self.canvas.window()
            if hasattr(main_window, "current_tab") and main_window.current_tab:
                flow_solver = main_window.current_tab.flow_solver

        if flow_solver is None:
            self.efficiency_label.setText("-")
            self.status_label.setText("-")
            return

        efficiency: BuildingEfficiency | None = flow_solver.get_efficiency(building_id)
        if efficiency is None:
            self.efficiency_label.setText("-")
            self.status_label.setText("-")
            return

        # Display efficiency as percentage
        pct = efficiency.duty_cycle * 100
        if pct >= 99.9:
            self.efficiency_label.setText(f"✅ {pct:.1f}%")
        elif pct >= 50:
            self.efficiency_label.setText(f"⚠️ {pct:.1f}%")
        else:
            self.efficiency_label.setText(f"❌ {pct:.1f}%")

        # Display limiting factor
        self.status_label.setText(efficiency.limiting_details or "Running normally")

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
