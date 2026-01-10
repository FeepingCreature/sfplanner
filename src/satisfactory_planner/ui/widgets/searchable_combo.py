"""Searchable combo box widget with filtering."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FilterableListWidget(QWidget):
    """A text field + list widget with incremental filtering.

    Features:
    - Type to filter items incrementally
    - Items sorted alphabetically
    - Clear selection option
    """

    # Emitted when selection changes (includes None for cleared)
    selection_changed = Signal(object)  # Emits the item data

    def __init__(self, parent: QWidget | None = None, placeholder: str = "Search..."):
        super().__init__(parent)

        # Store items for filtering
        self._all_items: list[tuple[str, Any]] = []  # (display_text, data)
        self._include_none = True
        self._none_text = "(None)"
        self._updating = False

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Search field
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(placeholder)
        self._search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_edit)

        # List widget
        self._list_widget = QListWidget()
        self._list_widget.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list_widget)

    def set_items(
        self,
        items: list[tuple[str, Any]],
        include_none: bool = True,
        none_text: str = "(None)",
    ) -> None:
        """Set the items in the list.

        Args:
            items: List of (display_text, data) tuples
            include_none: Whether to include a "None" option at the top
            none_text: Text to display for the None option
        """
        self._updating = True

        # Sort items alphabetically by display text
        sorted_items = sorted(items, key=lambda x: x[0].lower())

        # Store for filtering
        self._all_items = sorted_items
        self._include_none = include_none
        self._none_text = none_text

        # Populate list
        self._repopulate_list()

        self._updating = False

    def _repopulate_list(self, filter_text: str = "") -> None:
        """Repopulate the list, optionally filtering by text."""
        self._list_widget.clear()

        filter_lower = filter_text.lower()

        if self._include_none and (
            not filter_text or self._none_text.lower().startswith(filter_lower)
        ):
            item = QListWidgetItem(self._none_text)
            item.setData(Qt.ItemDataRole.UserRole, None)
            self._list_widget.addItem(item)

        for display_text, data in self._all_items:
            if not filter_text or filter_lower in display_text.lower():
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, data)
                self._list_widget.addItem(item)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change - filter items."""
        current_data = self.get_current_data()
        self._repopulate_list(text)
        # Try to restore selection
        if current_data is not None:
            self.set_current_data(current_data)

    def _on_item_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        """Handle item selection change."""
        if self._updating:
            return

        data = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.selection_changed.emit(data)

    def set_current_data(self, data: Any) -> None:
        """Set current selection by data value."""
        self._updating = True
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == data:
                self._list_widget.setCurrentItem(item)
                break
        self._updating = False

    def get_current_data(self) -> Any:
        """Get the currently selected data."""
        current = self._list_widget.currentItem()
        if current:
            return current.data(Qt.ItemDataRole.UserRole)
        return None

    def clear_filter(self) -> None:
        """Clear the search filter."""
        self._search_edit.clear()


# Keep the old name as an alias for compatibility during transition
SearchableComboBox = FilterableListWidget
