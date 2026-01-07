"""
Panel System Spike - Testing PyQtAds for Blender-style docking

Run with: python spikes/panel_system/main.py
"""

import sys
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, 
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QFileDialog
)
from PySide6.QtCore import Qt

import PySide6QtAds as ads


class LibraryPanel(QWidget):
    """Mock library panel with draggable items."""
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Library</b>"))
        
        self.list = QListWidget()
        for item in ["Smelter", "Constructor", "Assembler", "Manufacturer", 
                     "Splitter", "Merger", "Miner Mk.1"]:
            self.list.addItem(QListWidgetItem(item))
        layout.addWidget(self.list)


class PropertiesPanel(QWidget):
    """Mock properties panel for selected item."""
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Properties</b>"))
        layout.addWidget(QLabel("Recipe: Iron Ingot"))
        layout.addWidget(QLabel("Clock Speed: 100%"))
        layout.addWidget(QLabel("Power: 4 MW"))
        layout.addStretch()


class WarningsPanel(QWidget):
    """Mock warnings panel."""
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Warnings</b>"))
        
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(
            "⚠ Motors 4.3 < 5.0 required\n"
            "  └─ Rotors 7.1 < 10.0 required\n"
            "     └─ Belt at capacity (780/min)\n\n"
            "⚠ Disconnected belt at (120, 340)\n"
        )
        layout.addWidget(self.text)


class CanvasPanel(QWidget):
    """Mock canvas area."""
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel("<center><h2>Canvas Area</h2><p>(QGraphicsView goes here)</p></center>")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.setMinimumSize(400, 300)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Panel System Spike - PyQtAds")
        self.resize(1200, 800)
        
        # Initialize the dock manager
        ads.CDockManager.setConfigFlag(ads.CDockManager.FocusHighlighting, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.DockAreaHasTabsMenuButton, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.OpaqueSplitterResize, True)
        
        self.dock_manager = ads.CDockManager(self)
        self.setCentralWidget(self.dock_manager)
        
        # Create dock widgets
        self._create_panels()
        
        # Add save/load buttons to menu
        self._create_menu()
    
    def _create_panels(self):
        # Central canvas (non-closable)
        canvas_dock = ads.CDockWidget("Canvas")
        canvas_dock.setWidget(CanvasPanel())
        canvas_dock.setFeature(ads.CDockWidget.DockWidgetClosable, False)
        central_area = self.dock_manager.setCentralWidget(canvas_dock)
        central_area.setAllowedAreas(ads.DockWidgetArea.OuterDockAreas)
        
        # Library panel - left
        library_dock = ads.CDockWidget("Library")
        library_dock.setWidget(LibraryPanel())
        library_dock.setMinimumSizeHintMode(ads.CDockWidget.MinimumSizeHintFromContent)
        self.dock_manager.addDockWidget(ads.DockWidgetArea.LeftDockWidgetArea, library_dock)
        
        # Properties panel - right
        props_dock = ads.CDockWidget("Properties")
        props_dock.setWidget(PropertiesPanel())
        self.dock_manager.addDockWidget(ads.DockWidgetArea.RightDockWidgetArea, props_dock)
        
        # Warnings panel - tabbed with properties
        warnings_dock = ads.CDockWidget("Warnings")
        warnings_dock.setWidget(WarningsPanel())
        self.dock_manager.addDockWidget(ads.DockWidgetArea.RightDockWidgetArea, warnings_dock)
    
    def _create_menu(self):
        menu = self.menuBar().addMenu("Layout")
        
        save_action = menu.addAction("Save Layout...")
        save_action.triggered.connect(self._save_layout)
        
        load_action = menu.addAction("Load Layout...")
        load_action.triggered.connect(self._load_layout)
        
        menu.addSeparator()
        
        reset_action = menu.addAction("Reset to Default")
        reset_action.triggered.connect(self._reset_layout)
        
        # View menu to show/hide panels
        view_menu = self.menuBar().addMenu("View")
        for dock_widget in self.dock_manager.dockWidgetsMap().values():
            view_menu.addAction(dock_widget.toggleViewAction())
    
    def _save_layout(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Layout", "", "Layout Files (*.layout)"
        )
        if path:
            state = self.dock_manager.saveState()
            Path(path).write_bytes(state.data())
            print(f"Saved layout to {path}")
    
    def _load_layout(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Layout", "", "Layout Files (*.layout)"
        )
        if path:
            state = Path(path).read_bytes()
            self.dock_manager.restoreState(state)
            print(f"Loaded layout from {path}")
    
    def _reset_layout(self):
        # Recreate default layout
        # For a real app, we'd store the initial state and restore it
        print("Reset layout (not fully implemented in spike)")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
