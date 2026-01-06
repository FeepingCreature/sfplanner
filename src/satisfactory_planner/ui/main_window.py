"""Main application window with docking panels."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QToolBar

import PySide6QtAds as ads

from satisfactory_planner.core import Document, CommandStack, FlowSolver
from satisfactory_planner.ui.canvas import FactoryCanvas
from satisfactory_planner.ui.panels.library_panel import LibraryPanel
from satisfactory_planner.ui.panels.properties_panel import PropertiesPanel
from satisfactory_planner.ui.panels.warnings_panel import WarningsPanel

if TYPE_CHECKING:
    pass


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        self.document = Document()
        self.command_stack = CommandStack()
        self.flow_solver = FlowSolver(self.document)

        self._setup_window()
        self._setup_dock_manager()
        self._setup_panels()
        self._setup_menu()
        self._setup_toolbar()

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

    def _setup_panels(self) -> None:
        """Create and arrange dock panels."""
        # Central canvas (non-closable)
        self.canvas = FactoryCanvas(self.document, self.command_stack)
        canvas_dock = ads.CDockWidget("Canvas")
        canvas_dock.setWidget(self.canvas)
        canvas_dock.setFeature(ads.CDockWidget.DockWidgetClosable, False)
        central_area = self.dock_manager.setCentralWidget(canvas_dock)
        central_area.setAllowedAreas(ads.DockWidgetArea.OuterDockAreas)

        # Library panel - left
        self.library_panel = LibraryPanel()
        library_dock = ads.CDockWidget("Library")
        library_dock.setWidget(self.library_panel)
        library_dock.setMinimumSizeHintMode(ads.CDockWidget.MinimumSizeHintFromContent)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.LeftDockWidgetArea, library_dock)

        # Connect library to canvas for drag-drop
        self.library_panel.building_selected.connect(self.canvas.set_placement_mode)

        # Properties panel - right
        self.properties_panel = PropertiesPanel(self.document, self.command_stack)
        props_dock = ads.CDockWidget("Properties")
        props_dock.setWidget(self.properties_panel)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.RightDockWidgetArea, props_dock)

        # Connect canvas selection to properties
        self.canvas.selection_changed.connect(self.properties_panel.set_selection)

        # Warnings panel - right, tabbed with properties
        self.warnings_panel = WarningsPanel(self.document, self.flow_solver)
        warnings_dock = ads.CDockWidget("Warnings")
        warnings_dock.setWidget(self.warnings_panel)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.RightDockWidgetArea, warnings_dock)

        # Connect for warning updates
        self.canvas.document_changed.connect(self._update_warnings)

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

        delete_action = QAction("Delete", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self.canvas.delete_selection)
        edit_menu.addAction(delete_action)

        # Layout menu
        layout_menu = self.menuBar().addMenu("Layout")

        save_layout_action = QAction("Save Layout...", self)
        save_layout_action.triggered.connect(self._save_layout)
        layout_menu.addAction(save_layout_action)

        load_layout_action = QAction("Load Layout...", self)
        load_layout_action.triggered.connect(self._load_layout)
        layout_menu.addAction(load_layout_action)

        # View menu (auto-generated toggle actions)
        view_menu = self.menuBar().addMenu("View")
        for dock_widget in self.dock_manager.dockWidgetsMap().values():
            view_menu.addAction(dock_widget.toggleViewAction())

    def _setup_toolbar(self) -> None:
        """Create toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Grid snap toggle
        self.grid_snap_action = QAction("Grid Snap", self)
        self.grid_snap_action.setCheckable(True)
        self.grid_snap_action.setChecked(True)
        self.grid_snap_action.toggled.connect(self.canvas.set_grid_snap)
        toolbar.addAction(self.grid_snap_action)

    def _new_document(self) -> None:
        """Create a new empty document."""
        self.document = Document()
        self.command_stack = CommandStack()
        self.flow_solver = FlowSolver(self.document)
        self.canvas.set_document(self.document, self.command_stack)
        self.properties_panel.set_document(self.document, self.command_stack)
        self.warnings_panel.set_document(self.document, self.flow_solver)
        self._update_warnings()

    def _open_document(self) -> None:
        """Open a document from file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Satisfactory Planner (*.satplan)"
        )
        if path:
            # TODO: Implement document loading
            QMessageBox.information(self, "TODO", "Document loading not yet implemented")

    def _save_document(self) -> None:
        """Save the document to file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "Satisfactory Planner (*.satplan)"
        )
        if path:
            # TODO: Implement document saving
            QMessageBox.information(self, "TODO", "Document saving not yet implemented")

    def _undo(self) -> None:
        """Undo the last command."""
        self.command_stack.undo()
        self.canvas.refresh()
        self._update_warnings()

    def _redo(self) -> None:
        """Redo the last undone command."""
        self.command_stack.redo()
        self.canvas.refresh()
        self._update_warnings()

    def _update_warnings(self) -> None:
        """Update the warnings panel."""
        self.warnings_panel.refresh()
        self._update_undo_redo_state()

    def _update_undo_redo_state(self) -> None:
        """Update undo/redo action enabled state."""
        self.undo_action.setEnabled(self.command_stack.can_undo())
        self.redo_action.setEnabled(self.command_stack.can_redo())

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
