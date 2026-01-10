"""Searchable combo box widget with filtering dropdown."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class _ClickableLineEdit(QLineEdit):
    """A read-only line edit that emits clicked signal."""

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class SearchableDropdown(QWidget):
    """A dropdown button that opens a popup with search + filtered list.

    Features:
    - Click to open dropdown popup
    - Type to filter items incrementally
    - Items sorted alphabetically
    - Click item or press Enter to select
    """

    # Emitted when selection changes (includes None for cleared)
    selection_changed = Signal(object)  # Emits the item data

    def __init__(self, parent: QWidget | None = None, placeholder: str = "Search..."):
        super().__init__(parent)

        # Store items for filtering
        self._all_items: list[tuple[str, Any]] = []  # (display_text, data)
        self._include_none = True
        self._none_text = "(None)"
        self._current_data: Any = None
        self._placeholder = placeholder

        # Main layout - just a button-like line edit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Display field (shows current selection, click to open)
        self._display = _ClickableLineEdit()
        self._display.setReadOnly(True)
        self._display.setPlaceholderText("Click to select...")
        self._display.clicked.connect(self._show_popup)
        layout.addWidget(self._display)

        # Popup widget (hidden by default)
        self._popup = QWidget(self, Qt.WindowType.Popup)
        self._popup.setMinimumWidth(200)
        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(4, 4, 4, 4)
        popup_layout.setSpacing(2)

        # Search field in popup
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(placeholder)
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._search_edit.returnPressed.connect(self._select_first_item)
        popup_layout.addWidget(self._search_edit)

        # List widget in popup
        self._list_widget = QListWidget()
        self._list_widget.setMaximumHeight(200)
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_clicked)
        popup_layout.addWidget(self._list_widget)

    def _show_popup(self) -> None:
        """Show the dropdown popup."""
        self._search_edit.clear()
        self._repopulate_list()

        # Position popup to overlay the display field (not below it)
        global_pos = self.mapToGlobal(self._display.geometry().topLeft())
        self._popup.move(global_pos)
        self._popup.setMinimumWidth(self.width())
        self._popup.show()

        # Focus the search field
        self._search_edit.setFocus()

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
        # Sort items alphabetically by display text
        sorted_items = sorted(items, key=lambda x: x[0].lower())

        # Store for filtering
        self._all_items = sorted_items
        self._include_none = include_none
        self._none_text = none_text

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
        self._repopulate_list(text)

    def _select_first_item(self) -> None:
        """Select the first item in the filtered list (on Enter)."""
        if self._list_widget.count() > 0:
            item = self._list_widget.item(0)
            if item:
                self._on_item_clicked(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle item click - select and close popup."""
        data = item.data(Qt.ItemDataRole.UserRole)
        display_text = item.text()

        self._current_data = data
        self._display.setText(display_text if data is not None else "")

        self._popup.hide()
        self.selection_changed.emit(data)

    def set_current_data(self, data: Any) -> None:
        """Set current selection by data value."""
        import logging

        logger = logging.getLogger(__name__)

        self._current_data = data

        if data is None:
            self._display.setText("")
            return

        # Find display text for this data
        for display_text, item_data in self._all_items:
            if item_data == data:
                self._display.setText(display_text)
                return

        # Data not found in items - log warning
        logger.warning(
            f"SearchableDropdown: data '{data}' not found in {len(self._all_items)} items"
        )
        self._display.setText(str(data))

    def get_current_data(self) -> Any:
        """Get the currently selected data."""
        return self._current_data


# Aliases for compatibility
SearchableComboBox = SearchableDropdown
FilterableListWidget = SearchableDropdown
