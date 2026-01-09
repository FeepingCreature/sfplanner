"""Main application window with docking panels and multi-document support."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import PySide6QtAds as ads
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStyle,
    QTabWidget,
    QToolBar,
    QToolButton,
)

from satisfactory_planner.core import (
    DEFAULT_GRID_SIZE,
    Document,
    FlowSolver,
    load_document,
    save_document,
)
from satisfactory_planner.ui.canvas import FactoryCanvas
from satisfactory_planner.ui.commands import CommandStack
from satisfactory_planner.ui.dialogs import SettingsDialog
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
        self.command_stack = CommandStack(self.document)
        self.flow_solver = FlowSolver(self.document)
        self.canvas: FactoryCanvas | None = None
        self.file_path: str | None = None
        self.dirty: bool = False  # Track unsaved changes


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
        self.library_panel.blueprint_selected.connect(self._on_blueprint_selected)

        # Properties panel - right (larger, should expand)
        dummy_doc = Document()
        self.properties_panel = PropertiesPanel(dummy_doc, CommandStack(dummy_doc))
        props_dock = ads.CDockWidget("Properties")
        props_dock.setWidget(self.properties_panel)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.RightDockWidgetArea, props_dock)

        # Warnings panel - below properties panel (smaller)
        self.warnings_panel = WarningsPanel(Document(), FlowSolver(Document()))
        self.warnings_panel.warning_clicked.connect(self._on_warning_clicked)
        warnings_dock = ads.CDockWidget("Warnings")
        warnings_dock.setWidget(self.warnings_panel)
        # Use content size hint so the dock respects our sizeHint()
        warnings_dock.setMinimumSizeHintMode(ads.CDockWidget.MinimumSizeHintFromContent)
        self.dock_manager.addDockWidget(
            ads.DockWidgetArea.BottomDockWidgetArea, warnings_dock, props_dock.dockAreaWidget()
        )

        # Store dock widgets for view menu
        self._dock_widgets = [library_dock, props_dock, warnings_dock]

    def _setup_menu(self) -> None:
        """Create menu bar."""
        # File menu
        file_menu = self.menuBar().addMenu("File")

        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._new_document)
        file_menu.addAction(new_action)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_document)
        file_menu.addAction(open_action)

        save_action = QAction("Save...", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_document)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = self.menuBar().addMenu("Edit")

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        self.delete_action = QAction("Delete", self)
        self.delete_action.setShortcut(Qt.Key.Key_Delete)
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
        """Create toolbar with logical groupings: File → Edit → Tools → Create → View → Analysis."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # === 1. File Actions ===
        style = self.style()

        new_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), "", self)
        new_action.setToolTip("New document (Ctrl+N)")
        new_action.triggered.connect(self._new_document)
        toolbar.addAction(new_action)

        open_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "", self
        )
        open_action.setToolTip("Open document (Ctrl+O)")
        open_action.triggered.connect(self._open_document)
        toolbar.addAction(open_action)

        save_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "", self
        )
        save_action.setToolTip("Save document (Ctrl+S)")
        save_action.triggered.connect(self._save_document)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # === 2. Edit Actions ===
        toolbar_undo = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "", self)
        toolbar_undo.setToolTip("Undo (Ctrl+Z)")
        toolbar_undo.triggered.connect(self._undo)
        toolbar.addAction(toolbar_undo)

        toolbar_redo = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "", self)
        toolbar_redo.setToolTip("Redo (Ctrl+Shift+Z)")
        toolbar_redo.triggered.connect(self._redo)
        toolbar.addAction(toolbar_redo)

        toolbar.addSeparator()

        # === 3. Selection/Interaction Tools ===
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        self.select_tool = QToolButton()
        self.select_tool.setText("Select")
        self.select_tool.setToolTip("Select tool (V)")
        self.select_tool.setCheckable(True)
        self.select_tool.setChecked(True)
        self.tool_group.addButton(self.select_tool)
        toolbar.addWidget(self.select_tool)

        self.pan_tool = QToolButton()
        self.pan_tool.setText("Pan")
        self.pan_tool.setToolTip("Pan tool (H) - also: middle-drag or space+drag")
        self.pan_tool.setCheckable(True)
        self.tool_group.addButton(self.pan_tool)
        toolbar.addWidget(self.pan_tool)

        self.box_select_tool = QToolButton()
        self.box_select_tool.setText("Box Select")
        self.box_select_tool.setToolTip("Box select tool (B)")
        self.box_select_tool.setCheckable(True)
        self.tool_group.addButton(self.box_select_tool)
        toolbar.addWidget(self.box_select_tool)

        # Connect tool buttons to mode changes
        self.select_tool.clicked.connect(lambda: self._set_tool_mode("select"))
        self.pan_tool.clicked.connect(lambda: self._set_tool_mode("pan"))
        self.box_select_tool.clicked.connect(lambda: self._set_tool_mode("box_select"))

        toolbar.addSeparator()

        # === 4. Creation Tools ===
        self.create_room_action = QAction("Room", self)
        self.create_room_action.setToolTip("Create a room (drag to select buildings)")
        self.create_room_action.setCheckable(True)
        self.create_room_action.toggled.connect(self._toggle_room_creation)
        toolbar.addAction(self.create_room_action)

        self.create_blueprint_action = QAction("Blueprint", self)
        self.create_blueprint_action.setToolTip("Save selected room as blueprint")
        self.create_blueprint_action.setEnabled(False)
        self.create_blueprint_action.triggered.connect(self._save_blueprint)
        toolbar.addAction(self.create_blueprint_action)

        self.unlink_blueprint_action = QAction("Unlink", self)
        self.unlink_blueprint_action.setToolTip(
            "Unlink selected room instance (make independent copy)"
        )
        self.unlink_blueprint_action.setEnabled(False)
        self.unlink_blueprint_action.triggered.connect(self._unlink_room)
        toolbar.addAction(self.unlink_blueprint_action)

        self.dissolve_room_action = QAction("Dissolve", self)
        self.dissolve_room_action.setToolTip("Dissolve room, restoring buildings to canvas")
        self.dissolve_room_action.setEnabled(False)
        self.dissolve_room_action.triggered.connect(self._dissolve_room)
        toolbar.addAction(self.dissolve_room_action)

        toolbar.addSeparator()

        # === 5. Belt Tier ===
        toolbar.addWidget(QLabel(" Belt: "))
        self.belt_tier_combo = QComboBox()
        self.belt_tier_combo.addItems(["Mk.1", "Mk.2", "Mk.3", "Mk.4", "Mk.5", "Mk.6"])
        self.belt_tier_combo.setToolTip("Default belt tier for new connections")
        self.belt_tier_combo.setCurrentIndex(0)
        # TODO: Wire up to canvas default belt tier
        toolbar.addWidget(self.belt_tier_combo)

        toolbar.addSeparator()

        # === 6. View Controls ===
        # Note: Qt doesn't have great zoom icons, using +/- text with magnifier-style tooltip
        zoom_in_action = QAction("🔍+", self)
        zoom_in_action.setToolTip("Zoom in (+)")
        zoom_in_action.triggered.connect(self._zoom_in)
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QAction("🔍−", self)
        zoom_out_action.setToolTip("Zoom out (-)")
        zoom_out_action.triggered.connect(self._zoom_out)
        toolbar.addAction(zoom_out_action)

        zoom_fit_action = QAction("⊡", self)
        zoom_fit_action.setToolTip("Fit all in view (0)")
        zoom_fit_action.triggered.connect(self._zoom_fit)
        toolbar.addAction(zoom_fit_action)

        toolbar.addSeparator()

        # === 7. Grid Controls ===
        self.grid_snap_action = QAction("Snap", self)
        self.grid_snap_action.setCheckable(True)
        self.grid_snap_action.setChecked(True)
        self.grid_snap_action.setToolTip("Toggle grid snapping (G)")
        self.grid_snap_action.toggled.connect(self._toggle_grid_snap)
        toolbar.addAction(self.grid_snap_action)

        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["10", "20", "25", "50", "100"])
        self.grid_size_combo.setCurrentText(str(DEFAULT_GRID_SIZE))
        self.grid_size_combo.setToolTip("Grid size")
        self.grid_size_combo.currentTextChanged.connect(self._on_grid_size_changed)
        toolbar.addWidget(self.grid_size_combo)

        toolbar.addSeparator()

        # === 8. Analysis/Visualization ===
        self.show_bottlenecks_action = QAction("Efficiency", self)
        self.show_bottlenecks_action.setCheckable(True)
        self.show_bottlenecks_action.setToolTip("Show efficiency overlay on buildings")
        self.show_bottlenecks_action.toggled.connect(self._toggle_efficiency_overlay)
        toolbar.addAction(self.show_bottlenecks_action)

        self.show_flow_rates_action = QAction("Rates", self)
        self.show_flow_rates_action.setCheckable(True)
        self.show_flow_rates_action.setToolTip("Show flow rates on belts")
        self.show_flow_rates_action.toggled.connect(self._toggle_flow_rates)
        toolbar.addAction(self.show_flow_rates_action)

    def _new_document(self) -> None:
        """Create a new document tab."""
        tab = DocumentTab(f"Untitled {len(self.tabs) + 1}")
        canvas = FactoryCanvas(tab.document, tab.command_stack)
        tab.canvas = canvas

        # Connect signals
        canvas.selection_changed.connect(self.properties_panel.set_selection)
        canvas.selection_changed.connect(self._update_selection_actions)
        canvas.tool_mode_changed.connect(self._on_tool_mode_changed)

        # Set mutation callback (replaces document_changed signal)
        canvas._mutation_callback = lambda t=tab: self._on_document_mutated(t)  # type: ignore[misc]

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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        self.tab_widget.removeTab(index)
        self.tabs.pop(index)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab selection change."""
        if 0 <= index < len(self.tabs):
            self.current_tab = self.tabs[index]
            # Update panels to use current document
            if self.current_tab.canvas:
                self.properties_panel.set_document(
                    self.current_tab.document,
                    self.current_tab.command_stack,
                    self.current_tab.canvas,
                )
            self.warnings_panel.set_document(
                self.current_tab.document, self.current_tab.flow_solver
            )
            self._update_warnings()
            self._update_undo_redo_state()

    def _on_building_selected(self, building_type: object) -> None:
        """Handle building selection from library."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.set_placement_mode(building_type)  # type: ignore[arg-type]

    def _set_tool_mode(self, mode: str) -> None:
        """Set the tool mode on the current canvas."""
        if not self.current_tab or not self.current_tab.canvas:
            return

        from satisfactory_planner.ui.canvas import ToolMode

        mode_map = {
            "select": ToolMode.SELECT,
            "pan": ToolMode.PAN,
            "box_select": ToolMode.BOX_SELECT,
        }
        if mode in mode_map:
            self.current_tab.canvas.set_tool_mode(mode_map[mode])

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
            tab.command_stack = CommandStack(document)
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
            canvas.selection_changed.connect(self._update_selection_actions)
            canvas.tool_mode_changed.connect(self._on_tool_mode_changed)

            # Set mutation callback (replaces document_changed signal)
            canvas._mutation_callback = lambda t=tab: self._on_document_mutated(t)  # type: ignore[misc]

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

        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.save_settings(self.settings)
            self._apply_settings()

    def _apply_settings(self) -> None:
        """Apply current settings."""
        # Apply grid size to all canvases
        grid_size_val = self.settings.value("grid_size", DEFAULT_GRID_SIZE)
        grid_size = int(str(grid_size_val)) if grid_size_val else DEFAULT_GRID_SIZE
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

    def _on_document_mutated(self, tab: DocumentTab) -> None:
        """Handle document mutation from commands.

        This is called directly by commands via the canvas mutation callback.
        Centralizes all the effects of a document change.
        """
        self._mark_dirty(tab)
        self._update_warnings()
        self._refresh_flow_visualization(tab)
        self._update_undo_redo_state()

    def _refresh_flow_visualization(self, tab: DocumentTab) -> None:
        """Refresh flow visualization after document changes."""
        if not tab.canvas:
            return

        # Re-solve flows
        tab.flow_solver = FlowSolver(tab.document)
        tab.flow_solver.solve()

        # Update visualization if enabled
        if self.show_bottlenecks_action.isChecked() or self.show_flow_rates_action.isChecked():
            tab.canvas.update_flow_visualization()

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
            # Select and center on the building
            canvas.scene().clearSelection()
            for item in canvas.scene().items():
                from satisfactory_planner.ui.items import BuildingItem

                if isinstance(item, BuildingItem) and item.building.id == element_id:
                    item.setSelected(True)
                    canvas.centerOn(item)
                    break
        elif element_id in doc.belts:
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
        path, _ = QFileDialog.getSaveFileName(self, "Save Layout", "", "Layout Files (*.layout)")
        if path:
            state = self.dock_manager.saveState()
            Path(path).write_bytes(state.data())

    def _load_layout(self) -> None:
        """Load a panel layout."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Layout", "", "Layout Files (*.layout)")
        if path:
            state = Path(path).read_bytes()
            self.dock_manager.restoreState(state)

    def _zoom_in(self) -> None:
        """Zoom in on current canvas."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.scale(1.2, 1.2)

    def _zoom_out(self) -> None:
        """Zoom out on current canvas."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.scale(1 / 1.2, 1 / 1.2)

    def _zoom_fit(self) -> None:
        """Fit all items in view on current canvas."""
        if self.current_tab and self.current_tab.canvas:
            canvas = self.current_tab.canvas
            scene_rect = canvas.scene().itemsBoundingRect()
            if not scene_rect.isEmpty():
                # Add some padding
                scene_rect.adjust(-50, -50, 50, 50)
                canvas.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _on_grid_size_changed(self, text: str) -> None:
        """Handle grid size dropdown change."""
        try:
            size = int(text)
            for tab in self.tabs:
                if tab.canvas:
                    tab.canvas._grid_size = size
        except ValueError:
            pass

    def _toggle_room_creation(self, checked: bool) -> None:
        """Toggle room creation mode on current canvas."""
        if not self.current_tab or not self.current_tab.canvas:
            return

        from satisfactory_planner.ui.canvas import ToolMode

        if checked:
            self.current_tab.canvas.set_tool_mode(ToolMode.CREATE_ROOM)
        else:
            self.current_tab.canvas.set_tool_mode(ToolMode.SELECT)

    def _on_tool_mode_changed(self, mode: object) -> None:
        """Handle tool mode changes from canvas."""
        from satisfactory_planner.ui.canvas import ToolMode

        # Update Room button state without retriggering the toggle
        if mode != ToolMode.CREATE_ROOM:
            self.create_room_action.blockSignals(True)
            self.create_room_action.setChecked(False)
            self.create_room_action.blockSignals(False)

    def _dissolve_room(self) -> None:
        """Dissolve the selected room, restoring buildings to the parent scene."""
        if not self.current_tab or not self.current_tab.canvas:
            return

        from satisfactory_planner.ui.commands.room_commands import DissolveRoomCommand
        from satisfactory_planner.ui.items import RoomItem

        canvas = self.current_tab.canvas
        selected = canvas.scene().selectedItems()

        # Find selected room item
        room_item = None
        for item in selected:
            if isinstance(item, RoomItem):
                room_item = item
                break

        if not room_item:
            return

        # Create and execute dissolve command
        cmd = DissolveRoomCommand(
            placement_id=room_item.placement.id,
            canvas=canvas,
        )
        self.current_tab.command_stack.execute(cmd)

    def _unlink_room(self) -> None:
        """Unlink the selected room placement (make it an independent copy)."""
        if not self.current_tab or not self.current_tab.canvas:
            return

        from satisfactory_planner.ui.commands import DelinkRoomCommand
        from satisfactory_planner.ui.items import RoomItem

        canvas = self.current_tab.canvas
        selected = canvas.scene().selectedItems()

        # Find selected room item
        room_item = None
        for item in selected:
            if isinstance(item, RoomItem):
                room_item = item
                break

        if not room_item:
            return

        # Check if room has multiple placements (otherwise nothing to unlink)
        placements = self.current_tab.document.get_placements_for_room(room_item.room.id)
        if len(placements) <= 1:
            QMessageBox.information(
                self,
                "Cannot Unlink",
                "This room has only one instance. Nothing to unlink.",
            )
            return

        # Create and execute delink command
        cmd = DelinkRoomCommand(
            placement_id=room_item.placement.id,
            canvas=canvas,
            old_room_id=room_item.room.id,
        )
        self.current_tab.command_stack.execute(cmd)

    def _save_blueprint(self) -> None:
        """Save the selected room as a blueprint."""
        if not self.current_tab or not self.current_tab.canvas:
            return

        from satisfactory_planner.core import save_blueprint
        from satisfactory_planner.ui.items import RoomItem

        canvas = self.current_tab.canvas
        selected = canvas.scene().selectedItems()

        # Find selected room item
        room_item = None
        for item in selected:
            if isinstance(item, RoomItem):
                room_item = item
                break

        if not room_item:
            return

        # Save to blueprint library
        save_blueprint(room_item.room)

        # Refresh the library panel
        self.library_panel.refresh_blueprints()

        # Notify user
        QMessageBox.information(
            self,
            "Blueprint Saved",
            f"Blueprint '{room_item.room.name}' saved to library.",
        )

    def _on_blueprint_selected(self, room: object) -> None:
        """Handle blueprint selection from library - enter placement mode."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.set_blueprint_placement_mode(room)  # type: ignore[arg-type]

    def _update_selection_actions(self) -> None:
        """Update toolbar actions based on current selection."""
        if not self.current_tab or not self.current_tab.canvas:
            self.unlink_blueprint_action.setEnabled(False)
            self.create_blueprint_action.setEnabled(False)
            return

        from satisfactory_planner.ui.items import RoomItem

        canvas = self.current_tab.canvas
        selected = canvas.scene().selectedItems()

        # Check selection for room-related actions
        can_unlink = False
        can_save_blueprint = False

        for item in selected:
            if isinstance(item, RoomItem):
                can_save_blueprint = True
                placements = self.current_tab.document.get_placements_for_room(item.room.id)
                if len(placements) > 1:
                    can_unlink = True
                break

        self.unlink_blueprint_action.setEnabled(can_unlink)
        self.create_blueprint_action.setEnabled(can_save_blueprint)
        self.dissolve_room_action.setEnabled(can_save_blueprint)  # Can dissolve any room

    def _toggle_efficiency_overlay(self, enabled: bool) -> None:
        """Toggle efficiency overlay on buildings."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.set_show_efficiency(enabled)
            if enabled:
                self.current_tab.canvas.update_flow_visualization()

    def _toggle_flow_rates(self, enabled: bool) -> None:
        """Toggle flow rate display on belts."""
        if self.current_tab and self.current_tab.canvas:
            self.current_tab.canvas.set_show_flow_rates(enabled)
            if enabled:
                self.current_tab.canvas.update_flow_visualization()

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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
