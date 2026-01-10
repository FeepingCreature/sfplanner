"""Searchable combo box widget with filtering."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QLineEdit,
)


class SearchableComboBox(QComboBox):
    """A combo box with search/filter capability.

    Features:
    - Type to filter items
    - Items sorted alphabetically
    - Completion suggestions as you type
    - Clear selection option
    """

    # Emitted when selection changes (includes None for cleared)
    selection_changed = Signal(object)  # Emits the item data

    def __init__(self, parent=None, placeholder: str = "Search..."):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # Store items for filtering
        self._all_items: list[tuple[str, Any]] = []  # (display_text, data)
        self._placeholder = placeholder
        self._updating = False

        # Setup line edit
        line_edit = self.lineEdit()
        if line_edit:
            line_edit.setPlaceholderText(placeholder)
            line_edit.textEdited.connect(self._on_text_edited)

        # Setup completer for suggestions
        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(self._completer)

        # Connect selection
        self.currentIndexChanged.connect(self._on_index_changed)

    def set_items(
        self,
        items: list[tuple[str, Any]],
        include_none: bool = True,
        none_text: str = "(None)",
    ) -> None:
        """Set the items in the combo box.

        Args:
            items: List of (display_text, data) tuples
            include_none: Whether to include a "None" option at the top
            none_text: Text to display for the None option
        """
        self._updating = True

        # Sort items alphabetically by display text
        sorted_items = sorted(items, key=lambda x: x[0].lower())

        # Store for filtering
        self._all_items = sorted_items.copy()

        # Clear and repopulate
        self.clear()

        if include_none:
            self.addItem(none_text, None)

        for display_text, data in sorted_items:
            self.addItem(display_text, data)

        # Update completer model
        self._update_completer()

        self._updating = False

    def _update_completer(self) -> None:
        """Update the completer with current items."""
        from PySide6.QtCore import QStringListModel

        texts = [item[0] for item in self._all_items]
        model = QStringListModel(texts, self)
        self._completer.setModel(model)

    def _on_text_edited(self, text: str) -> None:
        """Handle text editing - filter items."""
        if self._updating:
            return

        # Show popup with filtered items
        self.showPopup()

    def _on_index_changed(self, index: int) -> None:
        """Handle index change."""
        if self._updating:
            return

        data = self.currentData()
        self.selection_changed.emit(data)

    def set_current_data(self, data: Any) -> None:
        """Set current selection by data value."""
        self._updating = True
        for i in range(self.count()):
            if self.itemData(i) == data:
                self.setCurrentIndex(i)
                break
        self._updating = False

    def get_current_data(self) -> Any:
        """Get the currently selected data."""
        return self.currentData()