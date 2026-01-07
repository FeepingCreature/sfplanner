"""Warnings panel for displaying validation issues."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
)

from satisfactory_planner.core import Document, FlowSolver, WarningType

if TYPE_CHECKING:
    pass


# Icons/prefixes for warning types
WARNING_ICONS = {
    WarningType.DISCONNECTED_BELT: "🔌",
    WarningType.RESOURCE_UNDERFLOW: "📉",
    WarningType.PRODUCTION_UNDERFLOW: "⚠️",
    WarningType.LEFTOVER_ITEMS: "📦",
    WarningType.BELT_OVERCAPACITY: "🚫",
}


class WarningsPanel(QWidget):
    """Panel for displaying factory validation warnings."""

    # Emitted when a warning is clicked (to navigate to the element)
    warning_clicked = Signal(str)  # Element ID

    def __init__(
        self,
        document: Document,
        flow_solver: FlowSolver,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.document = document
        self.flow_solver = flow_solver

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Style the panel with background and rounded corners
        self.setStyleSheet("""
            WarningsPanel {
                background-color: #2d2d30;
                border-radius: 6px;
            }
            QTreeWidget {
                background-color: #252528;
                border: none;
                border-radius: 4px;
            }
        """)

        # Summary label
        self.summary_label = QLabel("No warnings")
        layout.addWidget(self.summary_label)

        # Warnings tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Warning"])
        self.tree.setRootIsDecorated(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

    def set_document(self, document: Document, flow_solver: FlowSolver) -> None:
        """Set a new document."""
        self.document = document
        self.flow_solver = flow_solver
        self.refresh()

    def refresh(self) -> None:
        """Refresh the warnings list."""
        self.tree.clear()

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

        # Create tree items
        for warning_type, type_warnings in by_type.items():
            icon = WARNING_ICONS.get(warning_type, "⚠️")
            type_item = QTreeWidgetItem([f"{icon} {warning_type.value} ({len(type_warnings)})"])

            for warning in type_warnings:
                warning_item = QTreeWidgetItem([warning.message])
                warning_item.setData(0, Qt.UserRole, warning.element_id)
                type_item.addChild(warning_item)

                # TODO: Add causal chain as nested items
                # if warning.details and "chain" in warning.details:
                #     for chain_item in warning.details["chain"]:
                #         ...

            self.tree.addTopLevelItem(type_item)
            type_item.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle clicking on a warning."""
        element_id = item.data(0, Qt.UserRole)
        if element_id:
            self.warning_clicked.emit(element_id)
