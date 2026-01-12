"""Warnings panel for displaying validation issues."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from satisfactory_planner.core import Document, FlowSolver, ItemKey, Warning, WarningType

if TYPE_CHECKING:
    pass


# Icons/prefixes for warning types
WARNING_ICONS = {
    WarningType.DISCONNECTED_BELT: "🔌",
    WarningType.INPUT_MISSING: "❓",
    WarningType.RESOURCE_UNDERFLOW: "📉",
    WarningType.PRODUCTION_UNDERFLOW: "⚠️",
    WarningType.LEFTOVER_ITEMS: "📦",
    WarningType.BELT_OVERCAPACITY: "🚫",
    WarningType.ITEM_MISMATCH: "❌",
    WarningType.RECIPE_NOT_SET: "📋",
}

# Human-readable names for warning types
WARNING_TYPE_NAMES = {
    WarningType.DISCONNECTED_BELT: "Disconnected Belts",
    WarningType.INPUT_MISSING: "Missing Inputs",
    WarningType.RESOURCE_UNDERFLOW: "Resource Underflow",
    WarningType.PRODUCTION_UNDERFLOW: "Production Underflow",
    WarningType.LEFTOVER_ITEMS: "Unused Outputs",
    WarningType.BELT_OVERCAPACITY: "Belt Overcapacity",
    WarningType.ITEM_MISMATCH: "Item Mismatch",
    WarningType.RECIPE_NOT_SET: "Recipe Not Set",
}


class WarningsPanel(QWidget):
    """Panel for displaying factory validation warnings."""

    # Emitted when a warning is clicked (to navigate to the element)
    warning_clicked = Signal(ItemKey)  # ItemKey for the element

    def __init__(
        self,
        document: Document,
        flow_solver: FlowSolver | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.document = document
        self.flow_solver = flow_solver

        self._setup_ui()

        # Set size policy so we don't expand greedily
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def _setup_ui(self) -> None:
        """Create the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Summary label
        self.summary_label = QLabel("No warnings")
        layout.addWidget(self.summary_label)

        # Warnings tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setWordWrap(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

    def sizeHint(self) -> QSize:
        """Return preferred size - small height so properties panel gets more space."""
        return QSize(250, 150)

    def set_document(self, document: Document, flow_solver: FlowSolver) -> None:
        """Set a new document."""
        self.document = document
        self.flow_solver = flow_solver
        self.refresh()

    def refresh(self) -> None:
        """Refresh the warnings list."""
        self.tree.clear()

        if not self.flow_solver:
            return
        warnings = self.flow_solver.solve()

        if not warnings:
            self.summary_label.setText("✅ No warnings")
            return

        self.summary_label.setText(f"⚠️ {len(warnings)} warning(s)")

        # Group warnings by type
        by_type: dict[WarningType, list[object]] = {}
        for warning in warnings:
            if warning.type not in by_type:
                by_type[warning.type] = []
            by_type[warning.type].append(warning)

        # Sort warnings by severity (highest first)
        sorted_types = sorted(
            by_type.items(),
            key=lambda x: max((w.severity for w in x[1]), default=0),  # type: ignore[attr-defined]
            reverse=True,
        )

        # Create tree items
        for warning_type, type_warnings in sorted_types:
            icon = WARNING_ICONS.get(warning_type, "⚠️")
            type_name = WARNING_TYPE_NAMES.get(warning_type, warning_type.value)
            type_item = QTreeWidgetItem([f"{icon} {type_name} ({len(type_warnings)})"])

            for w in type_warnings:
                self._add_warning_item(type_item, w)  # type: ignore[arg-type]

            self.tree.addTopLevelItem(type_item)
            type_item.setExpanded(True)

        # Resize column to fit content
        self.tree.resizeColumnToContents(0)

    def _add_warning_item(self, parent: QTreeWidgetItem, warning: Warning) -> None:
        """Add a warning item with its causal chain as nested children."""
        # Format the message with human-readable element name
        message = self._format_warning_message(warning)
        warning_item = QTreeWidgetItem([message])
        warning_item.setData(0, Qt.ItemDataRole.UserRole, warning.item_key)
        warning_item.setToolTip(0, message)  # Show full text on hover
        parent.addChild(warning_item)

        # Add causal chain as nested children
        for cause in warning.caused_by:
            self._add_warning_item(warning_item, cause)

    def _format_warning_message(self, warning: Warning) -> str:
        """Format a warning message with human-readable element names."""
        # Get human-readable name for the element
        element_name = self._get_element_name(warning.item_key)

        # Prepend element name if we have one and it's not already in the message
        if element_name:
            return f"{element_name}: {warning.message}"
        return warning.message

    def _get_element_name(self, item_key: ItemKey) -> str | None:
        """Get a human-readable name for an element."""
        if not item_key:
            return None

        element_id = item_key.element_id

        # Check if it's a building
        building = self.document.buildings.get(element_id)
        if building:
            name = building.building_type.value
            if building.recipe_id:
                # Add recipe name if available
                if self.flow_solver:
                    recipe = self.flow_solver._recipes.get(building.recipe_id)
                    if recipe:
                        return f"{name} ({recipe.name})"
            elif building.item_id:
                # For miners/sources, show item
                return f"{name} ({building.item_id})"
            return name

        # Check if it's a belt
        belt = self.document.belts.get(element_id)
        if belt:
            # Try to get source and dest building names
            src = self.document.buildings.get(belt.source_building_id)
            dst = self.document.buildings.get(belt.dest_building_id)
            if src and dst:
                src_name = src.building_type.value
                dst_name = dst.building_type.value
                return f"Belt ({src_name} → {dst_name})"
            return "Belt"

        # Check rooms
        if item_key.placement_id:
            placement = self.document.room_placements.get(item_key.placement_id)
            if placement:
                room = self.document.rooms.get(placement.room_id)
                if room:
                    return f"Room '{room.name}'"

        return None

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle clicking on a warning."""
        item_key = item.data(0, Qt.ItemDataRole.UserRole)
        if item_key:
            self.warning_clicked.emit(item_key)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Copy warning message to clipboard on double-click."""
        text = item.text(0)
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            # Brief visual feedback in summary
            old_text = self.summary_label.text()
            self.summary_label.setText("📋 Copied to clipboard!")
            # Restore after a moment (using single-shot timer)
            from PySide6.QtCore import QTimer

            QTimer.singleShot(1500, lambda: self.summary_label.setText(old_text))
