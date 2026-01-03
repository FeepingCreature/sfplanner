"""Main application window."""

import os
import json
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QSplitter, QGroupBox, QMessageBox, QFileDialog,
    QDoubleSpinBox, QFormLayout, QComboBox, QProgressDialog,
    QApplication, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QTimer

from ..models.recipe import Recipe, RecipeRegistry
from ..models.production import ProductionGraph
from ..models.network import NetworkGraph
from ..algorithms.requirements import calculate_requirements
from ..algorithms.optimizer import optimize_layout
from .recipe_editor import RecipeEditorDialog
from .production_view import ProductionView


def get_data_dir() -> Path:
    """Get XDG-compliant data directory for the application."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    
    app_dir = base / "satisfactory-planner"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_recipes_path() -> Path:
    """Get path to the recipes JSON file."""
    return get_data_dir() / "recipes.json"


class TargetEditorDialog(QDialog):
    """Dialog for adding/editing a production target."""
    
    def __init__(self, available_items: list[str], item: str = "", rate: float = 60.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Target")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Item selector
        self.item_combo = QComboBox()
        self.item_combo.setEditable(True)  # Allow custom items
        self.item_combo.addItems(available_items)
        if item:
            self.item_combo.setCurrentText(item)
        form.addRow("Item:", self.item_combo)
        
        # Rate spinner
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.01, 100000)
        self.rate_spin.setDecimals(2)
        self.rate_spin.setSuffix(" /min")
        self.rate_spin.setValue(rate)
        form.addRow("Rate:", self.rate_spin)
        
        layout.addLayout(form)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_target(self) -> tuple[str, float]:
        """Return the (item_name, rate) tuple."""
        return self.item_combo.currentText().strip(), self.rate_spin.value()


class TargetWidget(QWidget):
    """Widget for editing production targets."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Target list
        self.target_list = QListWidget()
        self.target_list.itemDoubleClicked.connect(self._edit_target)
        layout.addWidget(self.target_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_target)
        btn_layout.addWidget(add_btn)
        
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_target)
        btn_layout.addWidget(edit_btn)
        
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_target)
        btn_layout.addWidget(remove_btn)
        
        layout.addLayout(btn_layout)
        
        # Storage for target data
        self.targets: dict[str, float] = {}
        self.available_items: list[str] = []
    
    def _add_target(self):
        """Add a new target."""
        dialog = TargetEditorDialog(self.available_items, parent=self)
        if dialog.exec():
            item, rate = dialog.get_target()
            if item:
                self.targets[item] = rate
                self._refresh_list()
    
    def _edit_target(self, list_item: QListWidgetItem):
        """Edit an existing target."""
        item_name = list_item.data(Qt.ItemDataRole.UserRole)
        if item_name and item_name in self.targets:
            rate = self.targets[item_name]
            dialog = TargetEditorDialog(self.available_items, item_name, rate, parent=self)
            if dialog.exec():
                new_item, new_rate = dialog.get_target()
                if new_item:
                    # Remove old, add new
                    del self.targets[item_name]
                    self.targets[new_item] = new_rate
                    self._refresh_list()
    
    def _edit_selected_target(self):
        """Edit the currently selected target."""
        item = self.target_list.currentItem()
        if item:
            self._edit_target(item)
    
    def _remove_target(self):
        """Remove the selected target."""
        item = self.target_list.currentItem()
        if item:
            item_name = item.data(Qt.ItemDataRole.UserRole)
            if item_name and item_name in self.targets:
                del self.targets[item_name]
                self._refresh_list()
    
    def _refresh_list(self):
        self.target_list.clear()
        for item, rate in self.targets.items():
            widget_item = QListWidgetItem(f"{item}: {rate}/min")
            widget_item.setData(Qt.ItemDataRole.UserRole, item)
            self.target_list.addItem(widget_item)
    
    def set_available_items(self, items: list[str]):
        """Set the available items for selection."""
        self.available_items = sorted(set(items))
    
    def get_targets(self) -> dict[str, float]:
        return self.targets.copy()
    
    def set_targets(self, targets: dict[str, float]):
        self.targets = targets.copy()
        self._refresh_list()


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Satisfactory Production Planner")
        self.setMinimumSize(1200, 800)
        
        # Data
        self.recipe_registry = RecipeRegistry()
        self.production_graph: Optional[ProductionGraph] = None
        self.network_graph: Optional[NetworkGraph] = None
        
        self._setup_ui()
        self._setup_menu()
        self._load_recipes_from_xdg()
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        
        # Left panel - controls
        left_panel = QWidget()
        left_panel.setMaximumWidth(300)
        left_layout = QVBoxLayout(left_panel)
        
        # Recipes section
        recipes_group = QGroupBox("Recipes")
        recipes_layout = QVBoxLayout(recipes_group)
        
        self.recipe_list = QListWidget()
        self.recipe_list.itemDoubleClicked.connect(self._edit_recipe)
        recipes_layout.addWidget(self.recipe_list)
        
        recipe_btns = QHBoxLayout()
        add_recipe_btn = QPushButton("Add")
        add_recipe_btn.clicked.connect(self._add_recipe)
        recipe_btns.addWidget(add_recipe_btn)
        
        edit_recipe_btn = QPushButton("Edit")
        edit_recipe_btn.clicked.connect(self._edit_selected_recipe)
        recipe_btns.addWidget(edit_recipe_btn)
        
        del_recipe_btn = QPushButton("Delete")
        del_recipe_btn.clicked.connect(self._delete_recipe)
        recipe_btns.addWidget(del_recipe_btn)
        
        recipes_layout.addLayout(recipe_btns)
        left_layout.addWidget(recipes_group)
        
        # Targets section
        targets_group = QGroupBox("Targets")
        targets_layout = QVBoxLayout(targets_group)
        
        self.target_widget = TargetWidget()
        targets_layout.addWidget(self.target_widget)
        
        left_layout.addWidget(targets_group)
        
        # Action buttons
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        calculate_btn = QPushButton("Calculate Requirements")
        calculate_btn.clicked.connect(self._calculate)
        actions_layout.addWidget(calculate_btn)
        
        optimize_btn = QPushButton("Optimize Layout")
        optimize_btn.clicked.connect(self._optimize)
        actions_layout.addWidget(optimize_btn)
        
        left_layout.addWidget(actions_group)
        
        # Stats display
        stats_group = QGroupBox("Statistics")
        stats_layout = QFormLayout(stats_group)
        
        self.crossings_label = QLabel("-")
        stats_layout.addRow("Crossings:", self.crossings_label)
        
        self.edge_length_label = QLabel("-")
        stats_layout.addRow("Total Belt:", self.edge_length_label)
        
        self.iterations_label = QLabel("-")
        stats_layout.addRow("Iterations:", self.iterations_label)
        
        left_layout.addWidget(stats_group)
        left_layout.addStretch()
        
        main_layout.addWidget(left_panel)
        
        # Right panel - graph view
        self.production_view = ProductionView()
        main_layout.addWidget(self.production_view, stretch=1)
    
    def _setup_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        save_recipes = file_menu.addAction("Save Recipes")
        save_recipes.triggered.connect(self._save_recipes)
        
        load_recipes = file_menu.addAction("Load Recipes")
        load_recipes.triggered.connect(self._load_recipes)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        fit_action = view_menu.addAction("Fit to Content")
        fit_action.triggered.connect(self.production_view.fit_to_content)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._show_about)
    
    def _load_recipes_from_xdg(self):
        """Load recipes from XDG data directory, or create defaults."""
        recipes_path = get_recipes_path()
        
        if recipes_path.exists():
            try:
                self.recipe_registry.load_from_file(str(recipes_path))
                self._refresh_recipe_list()
                return
            except Exception as e:
                QMessageBox.warning(
                    self, "Warning",
                    f"Failed to load saved recipes: {e}\nLoading defaults."
                )
        
        # Load default recipes if no saved recipes exist
        self._load_default_recipes()
    
    def _save_recipes_to_xdg(self):
        """Save recipes to XDG data directory."""
        recipes_path = get_recipes_path()
        try:
            self.recipe_registry.save_to_file(str(recipes_path))
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to save recipes: {e}")
    
    def _load_default_recipes(self):
        """Load some example recipes."""
        # Iron processing chain
        self.recipe_registry.register(Recipe(
            name="Iron Ingot",
            inputs={"Iron Ore": 30},
            outputs={"Iron Ingot": 30},
            description="Smelt iron ore into ingots",
        ))
        
        self.recipe_registry.register(Recipe(
            name="Iron Plate",
            inputs={"Iron Ingot": 30},
            outputs={"Iron Plate": 20},
            description="Press ingots into plates",
        ))
        
        self.recipe_registry.register(Recipe(
            name="Iron Rod",
            inputs={"Iron Ingot": 15},
            outputs={"Iron Rod": 15},
            description="Cast ingots into rods",
        ))
        
        self.recipe_registry.register(Recipe(
            name="Screw",
            inputs={"Iron Rod": 10},
            outputs={"Screw": 40},
            description="Cut rods into screws",
        ))
        
        self.recipe_registry.register(Recipe(
            name="Reinforced Iron Plate",
            inputs={"Iron Plate": 30, "Screw": 60},
            outputs={"Reinforced Iron Plate": 5},
            description="Assemble reinforced plates",
        ))
        
        self._refresh_recipe_list()
        
        # Set default target
        self.target_widget.set_targets({"Reinforced Iron Plate": 5})
    
    def _refresh_recipe_list(self):
        self.recipe_list.clear()
        for recipe in self.recipe_registry.all_recipes():
            item = QListWidgetItem(recipe.name)
            item.setData(Qt.ItemDataRole.UserRole, recipe.name)
            self.recipe_list.addItem(item)
        
        # Update available items for target selection
        self._update_available_items()
    
    def _update_available_items(self):
        """Update the list of available items for target selection."""
        items = set()
        for recipe in self.recipe_registry.all_recipes():
            items.update(recipe.inputs.keys())
            items.update(recipe.outputs.keys())
        self.target_widget.set_available_items(list(items))
    
    def _add_recipe(self):
        dialog = RecipeEditorDialog(parent=self)
        if dialog.exec():
            recipe = dialog.get_recipe()
            if recipe:
                self.recipe_registry.register(recipe)
                self._refresh_recipe_list()
    
    def _edit_recipe(self, item: QListWidgetItem):
        recipe_name = item.data(Qt.ItemDataRole.UserRole)
        recipe = self.recipe_registry.get(recipe_name)
        if recipe:
            dialog = RecipeEditorDialog(recipe, parent=self)
            if dialog.exec():
                new_recipe = dialog.get_recipe()
                if new_recipe:
                    # Remove old and add new
                    self.recipe_registry.unregister(recipe_name)
                    self.recipe_registry.register(new_recipe)
                    self._refresh_recipe_list()
    
    def _edit_selected_recipe(self):
        item = self.recipe_list.currentItem()
        if item:
            self._edit_recipe(item)
    
    def _delete_recipe(self):
        item = self.recipe_list.currentItem()
        if item:
            recipe_name = item.data(Qt.ItemDataRole.UserRole)
            reply = QMessageBox.question(
                self, "Delete Recipe",
                f"Are you sure you want to delete '{recipe_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.recipe_registry.unregister(recipe_name)
                self._refresh_recipe_list()
    
    def _calculate(self):
        """Calculate production requirements."""
        targets = self.target_widget.get_targets()
        
        if not targets:
            QMessageBox.warning(self, "Error", "Please add at least one production target.")
            return
        
        # Calculate requirements
        self.production_graph = calculate_requirements(
            self.recipe_registry,
            targets,
        )
        
        # Generate initial network (without optimization)
        from ..algorithms.splitter_gen import generate_network
        from ..algorithms.layout import compute_layout
        
        self.network_graph = generate_network(self.production_graph, randomize=False)
        compute_layout(self.network_graph)
        
        # Display
        self.production_view.set_network(self.network_graph)
        self.production_view.fit_to_content()
        
        # Update stats
        from ..algorithms.layout import count_crossings, total_edge_length
        crossings = count_crossings(self.network_graph)
        edge_len = total_edge_length(self.network_graph)
        
        self.crossings_label.setText(str(crossings))
        self.edge_length_label.setText(f"{edge_len:.0f}")
        self.iterations_label.setText("1 (no optimization)")
    
    def _optimize(self):
        """Optimize the layout."""
        if not self.production_graph:
            self._calculate()
            if not self.production_graph:
                return
        
        # Show progress dialog
        progress = QProgressDialog("Optimizing layout...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        
        def update_progress(iteration: int, score: float):
            progress.setValue(iteration)
            progress.setLabelText(f"Iteration {iteration}, Score: {score:.0f}")
            QApplication.processEvents()
        
        # Run optimization
        result = optimize_layout(
            self.production_graph,
            max_iterations=100,
            progress_callback=update_progress,
        )
        
        progress.close()
        
        self.network_graph = result.network
        
        # Display
        self.production_view.set_network(self.network_graph)
        self.production_view.fit_to_content()
        
        # Update stats
        self.crossings_label.setText(str(result.crossings))
        self.edge_length_label.setText(f"{result.edge_length:.0f}")
        self.iterations_label.setText(str(result.iterations))
    
    def _save_recipes(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Recipes", "", "JSON Files (*.json)"
        )
        if filepath:
            self.recipe_registry.save_to_file(filepath)
    
    def _load_recipes(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Recipes", "", "JSON Files (*.json)"
        )
        if filepath:
            try:
                self.recipe_registry.load_from_file(filepath)
                self._refresh_recipe_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load recipes: {e}")
    
    def _show_about(self):
        QMessageBox.about(
            self, "About",
            "Satisfactory Production Planner\n\n"
            "A tool for planning and optimizing factory layouts.\n\n"
            "Define recipes, set production targets, and generate\n"
            "optimized layouts with minimal belt crossings."
        )
    
    def closeEvent(self, event):
        """Save recipes when closing the application."""
        self._save_recipes_to_xdg()
        super().closeEvent(event)
