"""Main application window with docking panels and multi-document support."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QToolBar,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QDialog,
    QFormLayout,
    QSpinBox,
    QFontComboBox,
    QDialogButtonBox,
)

import PySide6QtAds as ads

from satisfactory_planner.core import Document, CommandStack, FlowSolver, load_document, save_document, DEFAULT_GRID_SIZE
from satisfactory_planner.ui.canvas import FactoryCanvas
from satisfactory_planner.ui.panels.library_panel import LibraryPanel
from satisfactory_planner.ui.panels.properties_panel import PropertiesPanel
from satisfactory_planner.ui.panels.warnings_panel import WarningsPanel

if TYPE_CHECKING:
    pass


class DocumentTab:
    """Holds state for a single document."""

    def __init__(self, name: str = "Untitled") -> None:
        self.name = name
        self.document = Document()
        self.command_stack = CommandStack()
        self.flow_solver = FlowSolver(self.document)
        self.canvas: FactoryCanvas | None = None
        self.file_path: str | None = None
        self.dirty: bool = False  # Track unsaved changes


class SettingsDialog(QDialog):
    """Settings dialog for application preferences."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(300)

        layout = QFormLayout(self)

        # Font selection
        self.font_combo = QFontComboBox()
        layout.addRow("Font:", self.font_combo)

        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 24)
        self.font_size_spin.setValue(10)
        layout.addRow("Font Size:", self.font_size_spin)

        # Grid size
        self.grid_size_spin = QSpinBox()
        self.grid_size_spin.setRange(5, 100)
        self.grid_size_spin.setValue(DEFAULT_GRID_SIZE)
        layout.addRow("Grid Size:", self.grid_size_spin)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def load_settings(self, settings: QSettings) -> None:
        """Load settings into dialog."""
        font_family = settings.value("font_family", "")
        if font_family:
            self.font_combo.setCurrentFont(font_family)
        self.font_size_spin.setValue(int(settings.value("font_size", 10)))
        self.grid_size_spin.setValue(int(settings.value("grid_size", DEFAULT_GRID_SIZE)))

    def save_settings(self, settings: QSettings) -> None:
        """Save dialog values to settings."""
        settings.setValue("font_family", self.font_combo.currentFont().family())
        settings.setValue("font_size", self.font_size_spin.value())
        settings.setValue("grid_size", self.grid_size_spin.value())


class MainWindow(QMainWindow):
    """Main application window with multi-document tabs."""

    def __init__(self) -> None:
        super().__init__()

        self.settings = QSettings("SatisfactoryPlanner", "SatisfactoryPlanner")
        self.tabs: list[DocumentTab] = []
        self.current_tab: DocumentTab | None = None

        self._setup_window()
        self._setup_dock_manager()
        self._setup_tab_widget()
        self._setup_panels()
        self._setup_menu()
        self._setup_toolbar()

        # Create initial document
        self._new_document()

    def _setup_window(self) -> None:
        """Configure the main window."""
        self.setWindowTitle("Satisfactory Planner")
        self.resize(1400, 900)

    def _setup_dock_manager(self) -> None:
        """Initialize the PyQtAds dock manager."""
        ads.CDockManager.setConfigFlag(ads.CDockManager.FocusHighlighting, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.DockAreaHasTabsMenuButton, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.OpaqueSplitterResize, True)

        self.dock_manager = ads.CDockManager(self)
        self.setCentralWidget(self.dock_manager)

    def _setup_tab_widget(self) -> None:
        """Create the central tab widget for multiple documents."""
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Create dock widget for tabs
        self.canvas_dock = ads.CDockWidget("Documents")
        self.canvas_dock.setWidget(self.tab_widget)
        self.canvas_dock.setFeature(ads.CDockWidget.DockWidgetClosable, False)
        central_area = self.dock_manager.setCentralWidget(self.canvas_dock)
        central_area.setAllowedAreas(ads.DockWidgetArea.OuterDockAreas)

    def _setup_panels(self) -> None:
        """Create and arrange dock panels."""
        # Library panel - left
        self.library_panel = LibraryPanel()
        library_dock = ads.CDockWidget("Library")
        library_dock.setWidget(self.library_panel)
        library_dock.setMinimumSizeHintMode(ads.CDockWidget.MinimumSizeHintFromContent)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.LeftDockWidgetArea, library_dock)

        # Connect library to current canvas for placement
        self.library_panel.building_selected.connect(self._on_building_selected)

        # Properties panel - right
        self.properties_panel = PropertiesPanel(Document(), CommandStack())
        props_dock = ads.CDockWidget("Properties")
        props_dock.setWidget(self.properties_panel)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.RightDockWidgetArea, props_dock)

        # Warnings panel - below properties panel
        self.warnings_panel = WarningsPanel(Document(), FlowSolver(Document()))
        self.warnings_panel.warning_clicked.connect(self._on_warning_clicked)
        warnings_dock = ads.CDockWidget("Warnings")
        warnings_dock.setWidget(self.warnings_panel)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.BottomDockWidgetArea, warnings_dock, props_dock.dockAreaWidget())

        # Store dock widgets for view menu
        self._dock_widgets = [library_dock, props_dock, warnings_dock]

    def _setup_menu(self) -> None:
        """Create menu bar."""
        # File menu
        file_menu = self.menuBar().addMenu("File")

        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_document)
        file_menu.addAction(new_action)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_document)
        file_menu.addAction(open_action)

        save_action = QAction("Save...", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_document)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = self.menuBar().addMenu("Edit")

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        self.delete_action = QAction("Delete", self)
        self.delete_action.setShortcut(Qt.Key_Delete)
        self.delete_action.triggered.connect(self._delete_selection)
        edit_menu.addAction(self.delete_action)

        # View menu (merged with Layout)
        view_menu = self.menuBar().addMenu("View")

        # Panel visibility toggles
        view_menu.addSeparator()
        for dock_widget in self._dock_widgets:
            view_menu.addAction(dock_widget.toggleViewAction())

        view_menu.addSeparator()

        save_layout_action = QAction("Save Layout...", self)
        save_layout_action.triggered.connect(self._save_layout)
        view_menu.addAction(save_layout_action)

        load_layout_action = QAction("Load Layout...", self)
        load_layout_action.triggered.connect(self._load_layout)
        view_menu.addAction(load_layout_action)

    def _setup_toolbar(self) -> None:
        """Create toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Grid snap toggle
        self.grid_snap_action = QAction("Grid Snap", self)
        self.grid_snap_action.setCheckable(True)
        self.grid_snap_action.setChecked(True)
        self.grid_snap_action.toggled.connect(self._toggle_grid_snap)
        toolbar.addAction(self.grid_snap_action)

    def _new_document(self) -> None:
        """Create a new document tab."""
        tab = DocumentTab(f"Untitled {len(self.tabs) + 1}")
        canvas = FactoryCanvas(tab.document, tab.command_stack)
        tab.canvas = canvas

        # Connect signals
        canvas.selection_changed.connect(self.properties_panel.set_selection)
        canvas.document_changed.connect(self._update_warnings)
        canvas.document_changed.connect(lambda: self._mark_dirty(tab))

        # Add tab
        index = self.tab_widget.addTab(canvas, tab.name)
        self.tabs.append(tab)
        self.tab_widget.setCurrentIndex(index)
        
        # Ensure current_tab is set (signal might not fire on first tab)
        self.current_tab = tab
        self._on_tab_changed(index)

    def _close_tab(self, index: int) -> None:
        """Close a document tab."""
        if len(self.tabs) <= 1:
            # Don't close the last tab
            return

        tab = self.tabs[index]
        
        # Check for unsaved changes
        if tab.dirty:
            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"'{tab.name}' has unsaved changes. Close anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                return

        self.tab_widget.removeTab(index)
        self.tabs.pop(index)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab selection change."""
        if 0 <= index < len(self.tabs):
            self.current_tab = self.tabs[index]
            # Update panels to use current document
            self.properties_panel.set_document(
                self.current_tab.document,
                self.current_tab.command_stack
            )
            self.warnings_panel.set_document(
                self.current_tab.document,
                self.current_tab.flow_solver
            )
            self._update_warnings()
            self._update_undo_redo_state()

    def _on_building_selected(self, building_type: object) -> None:
        """Handle building selection from library."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.set_placement_mode(building_type)  # type: ignore[arg-type]

    def _toggle_grid_snap(self, enabled: bool) -> None:
        """Toggle grid snap on current canvas."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.set_grid_snap(enabled)

    def _delete_selection(self) -> None:
        """Delete selected items in current canvas."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.delete_selection()

    def _open_document(self) -> None:
        """Open a document from file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Satisfactory Planner (*.sfp)"
        )
        if path:
            self._open_file(path)

    def _open_file(self, path: str) -> bool:
        """Open a file by path. Returns True on success."""
        try:
            document, view_state = load_document(path)
            
            # Create new tab with loaded document
            tab = DocumentTab(Path(path).stem)
            tab.document = document
            tab.command_stack = CommandStack()
            tab.flow_solver = FlowSolver(document)
            tab.file_path = path
            
            canvas = FactoryCanvas(tab.document, tab.command_stack)
            tab.canvas = canvas
            
            # Refresh canvas to show loaded buildings/belts
            canvas.refresh()
            
            # Restore view state (zoom, pan)
            if view_state:
                if "scale" in view_state:
                    scale = view_state["scale"]
                    canvas.resetTransform()
                    canvas.scale(scale, scale)
                if "center_x" in view_state and "center_y" in view_state:
                    canvas.centerOn(view_state["center_x"], view_state["center_y"])
            
            # Connect signals
            canvas.selection_changed.connect(self.properties_panel.set_selection)
            canvas.document_changed.connect(self._update_warnings)
            
            # Add tab
            index = self.tab_widget.addTab(canvas, tab.name)
            self.tabs.append(tab)
            self.tab_widget.setCurrentIndex(index)
            
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")
            return False

    def _save_document(self) -> None:
        """Save the document to file."""
        if not self.current_tab:
            return
        
        # If already has a path, save directly; otherwise prompt
        if self.current_tab.file_path:
            path = self.current_tab.file_path
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", "", "Satisfactory Planner (*.sfp)"
            )
        
        if path:
            try:
                # Ensure .sfp extension
                if not path.endswith(".sfp"):
                    path += ".sfp"
                
                # Capture view state from canvas
                view_state = None
                if self.current_tab.canvas:
                    canvas = self.current_tab.canvas
                    transform = canvas.transform()
                    center = canvas.mapToScene(canvas.viewport().rect().center())
                    view_state = {
                        "scale": transform.m11(),  # Horizontal scale factor
                        "center_x": center.x(),
                        "center_y": center.y(),
                    }
                
                save_document(self.current_tab.document, path, view_state)
                self.current_tab.file_path = path
                self.current_tab.name = Path(path).stem
                self.current_tab.dirty = False
                
                # Update tab title (remove dirty indicator)
                current_index = self.tab_widget.currentIndex()
                self.tab_widget.setTabText(current_index, self.current_tab.name)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")

    def _open_settings(self) -> None:
        """Open settings dialog."""
        dialog = SettingsDialog(self)
        dialog.load_settings(self.settings)

        if dialog.exec() == QDialog.Accepted:
            dialog.save_settings(self.settings)
            self._apply_settings()

    def _apply_settings(self) -> None:
        """Apply current settings."""
        # Apply grid size to all canvases
        grid_size = int(self.settings.value("grid_size", DEFAULT_GRID_SIZE))
        for tab in self.tabs:
            if tab.canvas:
                tab.canvas._grid_size = grid_size
                tab.canvas.viewport().update()

    def _undo(self) -> None:
        """Undo the last command."""
        if self.current_tab:
            self.current_tab.command_stack.undo()
            if self.current_tab.canvas:
                self.current_tab.canvas.refresh()
            self._update_warnings()

    def _redo(self) -> None:
        """Redo the last undone command."""
        if self.current_tab:
            self.current_tab.command_stack.redo()
            if self.current_tab.canvas:
                self.current_tab.canvas.refresh()
            self._update_warnings()

    def _update_warnings(self) -> None:
        """Update the warnings panel."""
        self.warnings_panel.refresh()
        self._update_undo_redo_state()

    def _on_warning_clicked(self, element_id: str) -> None:
        """Navigate to and select the element referenced by a warning."""
        if not self.current_tab or not self.current_tab.canvas:
            return
        
        canvas = self.current_tab.canvas
        doc = self.current_tab.document
        
        # Find the element (could be building or belt)
        if element_id in doc.buildings:
            building = doc.buildings[element_id]
            # Select and center on the building
            canvas.scene().clearSelection()
            for item in canvas.scene().items():
                from satisfactory_planner.ui.items import BuildingItem
                if isinstance(item, BuildingItem) and item.building.id == element_id:
                    item.setSelected(True)
                    canvas.centerOn(item)
                    break
        elif element_id in doc.belts:
            belt = doc.belts[element_id]
            # Select and center on the belt
            canvas.scene().clearSelection()
            for item in canvas.scene().items():
                from satisfactory_planner.ui.items import BeltItem
                if isinstance(item, BeltItem) and item.belt.id == element_id:
                    item.setSelected(True)
                    canvas.centerOn(item)
                    break

    def _update_undo_redo_state(self) -> None:
        """Update undo/redo action enabled state."""
        if self.current_tab:
            self.undo_action.setEnabled(self.current_tab.command_stack.can_undo())
            self.redo_action.setEnabled(self.current_tab.command_stack.can_redo())
        else:
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)

    def _save_layout(self) -> None:
        """Save the current panel layout."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Layout", "", "Layout Files (*.layout)"
        )
        if path:
            state = self.dock_manager.saveState()
            Path(path).write_bytes(state.data())

    def _load_layout(self) -> None:
        """Load a panel layout."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Layout", "", "Layout Files (*.layout)"
        )
        if path:
            state = Path(path).read_bytes()
            self.dock_manager.restoreState(state)

    def _mark_dirty(self, tab: DocumentTab) -> None:
        """Mark a tab as having unsaved changes."""
        if not tab.dirty:
            tab.dirty = True
            # Update tab title to show dirty indicator
            index = self.tabs.index(tab) if tab in self.tabs else -1
            if index >= 0:
                self.tab_widget.setTabText(index, f"{tab.name}*")

    def _has_unsaved_changes(self) -> bool:
        """Check if any tab has unsaved changes."""
        return any(tab.dirty for tab in self.tabs)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close."""
        if self._has_unsaved_changes():
            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Quit anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()
