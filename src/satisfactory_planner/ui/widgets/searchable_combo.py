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
    - Items sorted alphabetically (within each group, see set_grouped_items)
    - Click item or press Enter to select
    """

    # Emitted when selection changes (includes None for cleared)
    selection_changed = Signal(object)  # Emits the item data

    # Sentinel used to mark non-selectable separator rows between groups
    _SEPARATOR = object()

    def __init__(self, parent: QWidget | None = None, placeholder: str = "Search..."):
        super().__init__(parent)

        # Groups of items for filtering; each group is alpha-sorted internally
        # and a separator is drawn between any two non-empty groups.
        self._groups: list[list[tuple[str, Any]]] = []  # (display_text, data)
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
        self.set_grouped_items([items], include_none=include_none, none_text=none_text)

    def set_grouped_items(
        self,
        groups: list[list[tuple[str, Any]]],
        include_none: bool = True,
        none_text: str = "(None)",
    ) -> None:
        """Set items organized into ordered groups.

        Each group is sorted alphabetically internally. A separator row is
        shown between any two groups that both have at least one item (after
        filtering too), so e.g. "valid" items can be shown before a
        separator followed by "other" items.

        Args:
            groups: Ordered list of groups, each a list of (display_text, data)
            include_none: Whether to include a "None" option at the very top
            none_text: Text to display for the None option
        """
        self._groups = [sorted(group, key=lambda x: x[0].lower()) for group in groups]
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

        first_group = True
        for group in self._groups:
            matches = [
                (display_text, data)
                for display_text, data in group
                if not filter_text or filter_lower in display_text.lower()
            ]
            if not matches:
                continue

            if not first_group:
                sep = QListWidgetItem("──────────")
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setData(Qt.ItemDataRole.UserRole, self._SEPARATOR)
                self._list_widget.addItem(sep)
            first_group = False

            for display_text, data in matches:
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, data)
                self._list_widget.addItem(item)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change - filter items."""
        self._repopulate_list(text)

    def _select_first_item(self) -> None:
        """Select the first item in the filtered list (on Enter)."""
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) is not self._SEPARATOR:
                self._on_item_clicked(item)
                return

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle item click - select and close popup."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is self._SEPARATOR:
            return
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

        # Find display text for this data (search across all groups)
        for group in self._groups:
            for display_text, item_data in group:
                if item_data == data:
                    self._display.setText(display_text)
                    return

        # Data not found in items - log warning
        total_items = sum(len(group) for group in self._groups)
        logger.warning(f"SearchableDropdown: data '{data}' not found in {total_items} items")
        self._display.setText(str(data))

    def get_current_data(self) -> Any:
        """Get the currently selected data."""
        return self._current_data


# Aliases for compatibility
SearchableComboBox = SearchableDropdown
FilterableListWidget = SearchableDropdown
