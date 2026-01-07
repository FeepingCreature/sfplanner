"""Settings dialog for application preferences."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QSpinBox,
    QWidget,
)

from satisfactory_planner.core import DEFAULT_GRID_SIZE


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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def load_settings(self, settings: QSettings) -> None:
        """Load settings into dialog."""
        font_family = str(settings.value("font_family", ""))
        if font_family:
            self.font_combo.setCurrentFont(font_family)
        font_size = settings.value("font_size", 10)
        self.font_size_spin.setValue(int(str(font_size)) if font_size else 10)
        grid_size = settings.value("grid_size", DEFAULT_GRID_SIZE)
        self.grid_size_spin.setValue(int(str(grid_size)) if grid_size else DEFAULT_GRID_SIZE)

    def save_settings(self, settings: QSettings) -> None:
        """Save dialog values to settings."""
        settings.setValue("font_family", self.font_combo.currentFont().family())
        settings.setValue("font_size", self.font_size_spin.value())
        settings.setValue("grid_size", self.grid_size_spin.value())
