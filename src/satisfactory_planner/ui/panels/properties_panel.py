"""Properties panel for editing selected items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
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
    Belt,
    Building,
    BuildingEfficiency,
    BuildingType,
    Document,
    Room,
    RoomPlacement,
)
from satisfactory_planner.core.item_key import ItemKey
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

    # Emitted when a blueprint is saved to the library
    blueprint_saved = Signal()

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
        self._scene_room_id: str | None = None  # Room ID for current selection
        self._placement_id: str | None = None  # Placement ID for items in rooms
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

        # Source/Sink/Miner properties group (Item selector instead of Recipe)
        self.source_group = QGroupBox("Item Selection")
        source_layout = QFormLayout(self.source_group)

        # Item selector
        self.item_combo = QComboBox()
        self.item_combo.addItem("(No item)", None)
        self.item_combo.currentIndexChanged.connect(self._on_item_changed)
        source_layout.addRow("Item:", self.item_combo)

        # Tier dropdown for Miner
        self.miner_tier_combo = QComboBox()
        self.miner_tier_combo.addItem("Mk.1 (60/min)", 1)
        self.miner_tier_combo.addItem("Mk.2 (120/min)", 2)
        self.miner_tier_combo.addItem("Mk.3 (240/min)", 3)
        self.miner_tier_combo.currentIndexChanged.connect(self._on_miner_tier_changed)
        self.miner_tier_label = QLabel("Tier:")
        source_layout.addRow(self.miner_tier_label, self.miner_tier_combo)

        # Rate for Source (how much it produces) - editable
        self.source_rate_spin = QDoubleSpinBox()
        self.source_rate_spin.setRange(0, 10000)
        self.source_rate_spin.setSuffix("/min")
        self.source_rate_spin.setValue(60)
        self.source_rate_spin.valueChanged.connect(self._on_source_rate_changed)
        self.source_rate_label = QLabel("Rate:")
        source_layout.addRow(self.source_rate_label, self.source_rate_spin)

        # Actual flow for Sink (read-only, from simulation)
        self.sink_flow_label = QLabel("-")
        self.sink_flow_row_label = QLabel("Flow:")
        source_layout.addRow(self.sink_flow_row_label, self.sink_flow_label)

        # Min/Max for Source/Sink (warning thresholds)
        self.min_rate_spin = QDoubleSpinBox()
        self.min_rate_spin.setRange(0, 10000)
        self.min_rate_spin.setSuffix("/min")
        self.min_rate_spin.setValue(0)
        self.min_rate_spin.valueChanged.connect(self._on_min_max_changed)
        self.min_rate_label = QLabel("Min:")
        source_layout.addRow(self.min_rate_label, self.min_rate_spin)

        self.max_rate_spin = QDoubleSpinBox()
        self.max_rate_spin.setRange(0, 10000)
        self.max_rate_spin.setSuffix("/min")
        self.max_rate_spin.setValue(0)
        self.max_rate_spin.valueChanged.connect(self._on_min_max_changed)
        self.max_rate_label = QLabel("Max:")
        source_layout.addRow(self.max_rate_label, self.max_rate_spin)

        layout.addWidget(self.source_group)
        self.source_group.hide()

        # Belt properties group
        self.belt_group = QGroupBox("Belt Properties")
        belt_layout = QFormLayout(self.belt_group)

        # Belt tier (includes capacity)
        self.tier_combo = QComboBox()
        self.tier_combo.addItem("Mk.1 (60/min)", 1)
        self.tier_combo.addItem("Mk.2 (120/min)", 2)
        self.tier_combo.addItem("Mk.3 (270/min)", 3)
        self.tier_combo.addItem("Mk.4 (480/min)", 4)
        self.tier_combo.addItem("Mk.5 (780/min)", 5)
        self.tier_combo.addItem("Mk.6 (1200/min)", 6)
        self.tier_combo.currentIndexChanged.connect(self._on_tier_changed)
        belt_layout.addRow("Tier:", self.tier_combo)

        # Item type (read-only, determined by connected buildings)
        self.item_label = QLabel("-")
        belt_layout.addRow("Item:", self.item_label)

        # Current flow (read-only, from flow solver)
        self.current_flow_label = QLabel("-")
        belt_layout.addRow("Current Flow:", self.current_flow_label)

        layout.addWidget(self.belt_group)
        self.belt_group.hide()

        # Logistics properties group (Splitter/Merger)
        self.logistics_group = QGroupBox("Logistics Properties")
        logistics_layout = QFormLayout(self.logistics_group)

        # Item type (inferred from connections)
        self.logistics_item_label = QLabel("-")
        logistics_layout.addRow("Item:", self.logistics_item_label)

        # Input flows
        self.logistics_inputs_label = QLabel("-")
        logistics_layout.addRow("Inputs:", self.logistics_inputs_label)

        # Output flows
        self.logistics_outputs_label = QLabel("-")
        logistics_layout.addRow("Outputs:", self.logistics_outputs_label)

        # Total throughput
        self.logistics_total_label = QLabel("-")
        logistics_layout.addRow("Total:", self.logistics_total_label)

        layout.addWidget(self.logistics_group)
        self.logistics_group.hide()

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
        self._selected_ids = []
        self._update_recipe_combo()
        self._update_display()

    def set_selection(self, selected_ids: list[str], placement_id: str | None = None) -> None:
        """Update the displayed properties for the selection.

        Args:
            selected_ids: List of selected item IDs
            placement_id: The RoomPlacement ID if items are inside a room, or None for root
        """
        self._selected_ids = selected_ids
        self._placement_id = placement_id

        # Derive scene_room_id from placement_id for scene lookups
        if placement_id and placement_id in self.document.room_placements:
            self._scene_room_id = self.document.room_placements[placement_id].room_id
        else:
            self._scene_room_id = None

        self._update_display()

    def _get_scene(self) -> Document | Room:
        """Get the current scene (Document or Room) based on selection context."""
        if self._scene_room_id and self._scene_room_id in self.document.rooms:
            return self.document.rooms[self._scene_room_id]
        return self.document

    def _get_building(self, building_id: str) -> Building | None:
        """Get a building from the current scene."""

        scene = self._get_scene()
        return scene.buildings.get(building_id)

    def _get_belt(self, belt_id: str) -> Belt | None:
        """Get a belt from the current scene."""

        scene = self._get_scene()
        return scene.belts.get(belt_id)

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
            self.source_group.hide()
            self.room_group.hide()
            self.logistics_group.hide()
            self._updating = False
            return

        if len(self._selected_ids) == 1:
            item_id = self._selected_ids[0]

            # Check if it's a building in the current scene
            building = self._get_building(item_id)
            if building:
                self.selection_label.setText(f"Building: {building.building_type.value}")
                self.type_label.setText(building.building_type.value)
                self.clock_spin.setValue(building.clock_speed * 100)

                # PORT_IN/PORT_OUT have no useful properties to edit
                if building.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
                    self.building_group.hide()
                    self.belt_group.hide()
                    self.stats_group.hide()
                    self.source_group.hide()
                    self.room_group.hide()
                    self.logistics_group.hide()
                    self._updating = False
                    return

                # Source/Sink/Miner use item selector, not recipe
                if self._is_source_type(building.building_type):
                    self._populate_item_combo(building.building_type)

                    # Show/hide fields based on type
                    is_miner = building.building_type == BuildingType.MINER
                    is_sink = building.building_type == BuildingType.SINK
                    is_source = building.building_type == BuildingType.SOURCE

                    # Miner tier dropdown
                    self.miner_tier_label.setVisible(is_miner)
                    self.miner_tier_combo.setVisible(is_miner)
                    if is_miner:
                        self.miner_tier_combo.setCurrentIndex(building.tier - 1)

                    # Source rate (editable) - only for SOURCE
                    self.source_rate_label.setVisible(is_source)
                    self.source_rate_spin.setVisible(is_source)

                    # Sink flow (read-only) - only for SINK
                    self.sink_flow_row_label.setVisible(is_sink)
                    self.sink_flow_label.setVisible(is_sink)
                    if is_sink:
                        # Get flow from simulation
                        flow = self._get_sink_flow(building.id)
                        self.sink_flow_label.setText(f"{flow:.1f}/min" if flow else "-")

                    # Min/Max visible for Source/Sink only (not Miner)
                    show_min_max = is_source or is_sink
                    self.min_rate_label.setVisible(show_min_max)
                    self.min_rate_spin.setVisible(show_min_max)
                    self.max_rate_label.setVisible(show_min_max)
                    self.max_rate_spin.setVisible(show_min_max)

                    # Load min/max values from building
                    if show_min_max:
                        self.min_rate_spin.setValue(building.min_rate or 0)
                        self.max_rate_spin.setValue(building.max_rate or 0)

                    # Get item from recipe_id (which stores item_id for these types)
                    if building.recipe_id:
                        # For Source/Sink/Miner, recipe_id is the item_id
                        for i in range(self.item_combo.count()):
                            # Compare as strings since item_id is str and recipe_id is RecipeId
                            if self.item_combo.itemData(i) == str(building.recipe_id):
                                self.item_combo.setCurrentIndex(i)
                                break

                    self.source_group.show()
                    self.building_group.hide()  # Hide recipe selector
                    self.stats_group.hide()
                    self.logistics_group.hide()
                else:
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

                    # Splitter/Merger don't have recipes or production stats
                    is_logistics = building.building_type in (
                        BuildingType.SPLITTER,
                        BuildingType.MERGER,
                    )

                    self.building_group.setVisible(not is_logistics)
                    self.stats_group.setVisible(not is_logistics)
                    self.logistics_group.setVisible(is_logistics)
                    self.source_group.hide()

                    if is_logistics:
                        # Update logistics display (splitter/merger)
                        self._update_logistics_display(building)
                    else:
                        # Update stats from recipe
                        self._update_production_stats(building)

                        # Update efficiency from flow solver
                        self._update_efficiency_display(building.id)

                self.belt_group.hide()
                self.room_group.hide()

            # Check if it's a belt in the current scene
            elif belt := self._get_belt(item_id):
                self.selection_label.setText(f"Belt Mk.{belt.tier}")

                # Set tier combo
                self.tier_combo.setCurrentIndex(belt.tier - 1)

                # Get item type from flow solver's edge (authoritative source)
                item_display = self._get_belt_item_id(belt.id)
                self.item_label.setText(item_display or "(unknown)")

                # Get current flow from flow solver
                flow_rate = self._get_belt_flow_rate(belt.id)
                if flow_rate is not None:
                    self.current_flow_label.setText(f"{flow_rate:.1f}/min")
                else:
                    self.current_flow_label.setText("(run simulation)")

                self.belt_group.show()
                self.building_group.hide()
                self.stats_group.hide()
                self.source_group.hide()
                self.room_group.hide()
                self.logistics_group.hide()
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
                    self.logistics_group.hide()
                else:
                    # Unknown item type
                    self.selection_label.setText("Unknown item")
                    self.building_group.hide()
                    self.belt_group.hide()
                    self.room_group.hide()
                    self.stats_group.hide()
                    self.logistics_group.hide()
        else:
            self.selection_label.setText(f"{len(self._selected_ids)} items selected")
            self.building_group.hide()
            self.belt_group.hide()
            self.room_group.hide()
            self.stats_group.hide()
            self.logistics_group.hide()

        self._updating = False

    def _on_clock_speed_changed(self, value: float) -> None:
        """Handle clock speed change."""
        if self._updating or not self.canvas:
            return

        if len(self._selected_ids) == 1:
            building_id = self._selected_ids[0]
            # Look up building in the correct scene
            building = self._get_building(building_id)
            if building:
                cmd = SetClockSpeedCommand(
                    scene_room_id=self._scene_room_id,
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
            # Look up building in the correct scene
            building = self._get_building(building_id)
            if building:
                recipe_id = self.recipe_combo.currentData()
                cmd = SetRecipeCommand(
                    scene_room_id=self._scene_room_id,
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
            # Look up belt in the correct scene
            belt = self._get_belt(belt_id)
            if belt:
                new_tier = self.tier_combo.currentData()
                if new_tier and new_tier != belt.tier:
                    cmd = SetBeltTierCommand(
                        scene_room_id=self._scene_room_id,
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

        # Notify listeners (MainWindow connects this to refresh library panel)
        self.blueprint_saved.emit()

    def _is_source_type(self, building_type: BuildingType) -> bool:
        """Check if building type uses item selector instead of recipe."""
        return building_type in (
            BuildingType.SOURCE,
            BuildingType.SINK,
            BuildingType.MINER,
        )

    def _populate_item_combo(self, building_type: BuildingType) -> None:
        """Populate item combo based on building type."""
        self.item_combo.clear()
        self.item_combo.addItem("(No item)", None)

        # Get items from recipes
        items: set[str] = set()
        for recipe in self.document.recipes.values():
            for inp in recipe.inputs:
                items.add(inp.item_id)
            for out in recipe.outputs:
                items.add(out.item_id)

        # For miners, filter to ores only
        if building_type == BuildingType.MINER:
            ore_items = [
                i
                for i in sorted(items)
                if "Ore" in i
                or i
                in (
                    "Coal",
                    "Sulfur",
                    "Bauxite",
                    "Uranium",
                    "Raw Quartz",
                    "Caterium Ore",
                    "Limestone",
                    "Copper Ore",
                    "Iron Ore",
                )
            ]
            for item_id in ore_items:
                self.item_combo.addItem(item_id, item_id)
        else:
            # Source/Sink can use any item
            for item_id in sorted(items):
                self.item_combo.addItem(item_id, item_id)

    def _make_item_key(self, element_id: str) -> ItemKey:
        """Create a ItemKey for an element in the current selection context."""
        return ItemKey(element_id=element_id, placement_id=self._placement_id)

    def _get_belt_item_id(self, belt_id: str) -> str | None:
        """Get item type for a belt from flow solver's graph."""
        if not self.canvas or not self.canvas.flow_solver:
            return None

        flow_solver = self.canvas.flow_solver
        if flow_solver._solved_model:
            key = self._make_item_key(belt_id)
            edge = flow_solver._solved_model.graph.edges.get(key)
            if edge:
                return edge.item_id
        return None

    def _get_belt_flow_rate(self, belt_id: str) -> float | None:
        """Get flow rate for a belt from flow solver."""
        if not self.canvas or not self.canvas.flow_solver:
            return None

        key = self._make_item_key(belt_id)
        return self.canvas.flow_solver.get_flow_rate(key)

    def _get_sink_flow(self, building_id: str) -> float | None:
        """Get the actual flow into a sink from flow solver."""
        if not self.canvas:
            return None

        # Find belts connected to this sink's input in the current scene
        scene = self._get_scene()
        building = scene.buildings.get(building_id)
        if not building:
            return None

        # Get belt connected to input port 0
        belt = scene.get_belt_at_port(building_id, 0, is_output=False)
        if belt:
            return self._get_belt_flow_rate(belt.id)
        return None

    def _update_logistics_display(self, building: Building) -> None:
        """Update the logistics panel for splitter/merger."""
        import logging

        logger = logging.getLogger(__name__)

        scene = self._get_scene()

        # Find connected belts and get flow rates
        input_flows: list[tuple[int, str | None, float | None]] = []
        output_flows: list[tuple[int, str | None, float | None]] = []
        item_id: str | None = None

        # Check all belts in the scene
        for belt in scene.belts.values():
            flow_rate = self._get_belt_flow_rate(belt.id)
            # Get item type from flow solver, not belt model
            belt_item_id = self._get_belt_item_id(belt.id)

            if belt.dest_building_id == building.id:
                # This is an input belt
                input_flows.append((belt.dest_port_index, belt_item_id, flow_rate))
                if belt_item_id:
                    item_id = belt_item_id
            elif belt.source_building_id == building.id:
                # This is an output belt
                output_flows.append((belt.source_port_index, belt_item_id, flow_rate))
                if belt_item_id:
                    item_id = belt_item_id

        # Debug logging
        key = self._make_item_key(building.id)
        logger.debug(f"Logistics display: building={building.id}, key={key}, item_id={item_id}")

        # Sort by port index
        input_flows.sort(key=lambda x: x[0])
        output_flows.sort(key=lambda x: x[0])

        # Display item type
        self.logistics_item_label.setText(item_id or "(unknown)")

        # Display input flows
        if input_flows:
            input_strs = []
            for port_idx, _item, flow in input_flows:
                if flow is not None:
                    input_strs.append(f"Port {port_idx}: {flow:.1f}/min")
                else:
                    input_strs.append(f"Port {port_idx}: -")
            self.logistics_inputs_label.setText("\n".join(input_strs))
        else:
            self.logistics_inputs_label.setText("(none connected)")

        # Display output flows
        if output_flows:
            output_strs = []
            for port_idx, _item, flow in output_flows:
                if flow is not None:
                    output_strs.append(f"Port {port_idx}: {flow:.1f}/min")
                else:
                    output_strs.append(f"Port {port_idx}: -")
            self.logistics_outputs_label.setText("\n".join(output_strs))
        else:
            self.logistics_outputs_label.setText("(none connected)")

        # Display total throughput
        total_in = sum(f for _, _, f in input_flows if f is not None)
        total_out = sum(f for _, _, f in output_flows if f is not None)
        if total_in > 0 or total_out > 0:
            self.logistics_total_label.setText(f"In: {total_in:.1f}  Out: {total_out:.1f}/min")
        else:
            self.logistics_total_label.setText("-")

    def _update_production_stats(self, building: object) -> None:
        """Update input/output/power stats from recipe."""
        from satisfactory_planner.core.models import Building

        if not isinstance(building, Building):
            return

        if not building.recipe_id or building.recipe_id not in self.document.recipes:
            self.power_label.setText("- MW")
            self.input_label.setText("-")
            self.output_label.setText("-")
            return

        recipe = self.document.recipes[building.recipe_id].scaled(building.clock_speed)

        # Power
        self.power_label.setText(f"{recipe.power_mw:.1f} MW")

        # Inputs
        if recipe.inputs:
            input_strs = [f"{inp.item_id}: {inp.rate:.1f}/min" for inp in recipe.inputs]
            self.input_label.setText("\n".join(input_strs))
        else:
            self.input_label.setText("-")

        # Outputs
        if recipe.outputs:
            output_strs = [f"{out.item_id}: {out.rate:.1f}/min" for out in recipe.outputs]
            self.output_label.setText("\n".join(output_strs))
        else:
            self.output_label.setText("-")

    def _update_efficiency_display(self, building_id: str) -> None:
        """Update the efficiency display for a building."""
        if not self.canvas or not self.canvas.flow_solver:
            self.efficiency_label.setText("-")
            self.status_label.setText("-")
            return

        flow_solver = self.canvas.flow_solver

        # Use ItemKey for lookup
        key = self._make_item_key(building_id)
        efficiency: BuildingEfficiency | None = flow_solver.get_efficiency(key)
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

    def _on_miner_tier_changed(self, index: int) -> None:
        """Handle miner tier change."""
        if self._updating or not self.canvas:
            return

        if len(self._selected_ids) != 1:
            return

        building_id = self._selected_ids[0]
        building = self._get_building(building_id)
        if not building or building.building_type != BuildingType.MINER:
            return

        new_tier = self.miner_tier_combo.currentData()
        if new_tier is not None and new_tier != building.tier:
            building.tier = new_tier
            # Notify mutation to trigger visual refresh
            self.canvas.notify_mutation()

    def _on_item_changed(self, index: int) -> None:
        """Handle item selection change for Source/Sink/Miner."""
        if self._updating or not self.canvas:
            return

        self._save_source_recipe()

    def _on_source_rate_changed(self, value: float) -> None:
        """Handle rate change for Source/Sink/Miner."""
        if self._updating or not self.canvas:
            return

        self._save_source_recipe()

    def _on_min_max_changed(self, value: float) -> None:
        """Handle min/max rate change for Source/Sink."""
        if self._updating or not self.canvas:
            return

        if len(self._selected_ids) != 1:
            return

        building_id = self._selected_ids[0]
        building = self._get_building(building_id)
        if not building:
            return

        # Update building min/max directly
        new_min = self.min_rate_spin.value()
        new_max = self.max_rate_spin.value()

        # Only update if changed
        if building.min_rate != new_min or building.max_rate != new_max:
            building.min_rate = new_min if new_min > 0 else None
            building.max_rate = new_max if new_max > 0 else None
            self.canvas.notify_mutation()

    def _save_source_recipe(self) -> None:
        """Save Source/Sink/Miner item selection - just store item_id in recipe_id."""
        if len(self._selected_ids) != 1:
            return

        building_id = self._selected_ids[0]
        building = self._get_building(building_id)
        if not building or not self._is_source_type(building.building_type):
            return

        item_id = self.item_combo.currentData()

        # For Source/Sink/Miner, we store item_id directly in recipe_id
        # The flow_builder handles these specially
        old_recipe_id = building.recipe_id
        if item_id != old_recipe_id and self.canvas is not None:
            cmd = SetRecipeCommand(
                scene_room_id=self._scene_room_id,
                building_id=building_id,
                old_recipe_id=old_recipe_id,
                new_recipe_id=item_id,
                canvas=self.canvas,
            )
            self.command_stack.execute(cmd)

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

        cmd = DelinkRoomCommand.create(
            placement_id=placement.id,
            canvas=self.canvas,
            document=self.canvas.document,
        )
        if cmd:
            self.command_stack.execute(cmd)

        # Refresh display
        self._update_display()
