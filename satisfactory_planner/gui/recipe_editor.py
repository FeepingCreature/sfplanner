"""Recipe editor dialog."""

from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QDoubleSpinBox,
    QMessageBox, QWidget,
)
from PyQt6.QtCore import Qt

from ..models.recipe import Recipe


class ItemRateTable(QWidget):
    """Table widget for editing item -> rate mappings."""
    
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(label))
        header_layout.addStretch()
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedWidth(30)
        self.add_btn.clicked.connect(self._add_row)
        header_layout.addWidget(self.add_btn)
        
        self.remove_btn = QPushButton("-")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.clicked.connect(self._remove_row)
        header_layout.addWidget(self.remove_btn)
        
        layout.addLayout(header_layout)
        
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Item", "Rate/min"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 80)
        self.table.setMinimumHeight(100)
        layout.addWidget(self.table)
    
    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        
        rate_spin = QDoubleSpinBox()
        rate_spin.setRange(0, 10000)
        rate_spin.setDecimals(2)
        rate_spin.setValue(0)
        self.table.setCellWidget(row, 1, rate_spin)
    
    def _remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
    
    def get_data(self) -> dict[str, float]:
        """Get the item -> rate mapping."""
        data = {}
        for row in range(self.table.rowCount()):
            item_widget = self.table.item(row, 0)
            rate_widget = self.table.cellWidget(row, 1)
            
            if item_widget and rate_widget:
                item = item_widget.text().strip()
                rate = rate_widget.value()
                if item and rate > 0:
                    data[item] = rate
        return data
    
    def set_data(self, data: dict[str, float]):
        """Set the item -> rate mapping."""
        self.table.setRowCount(0)
        for item, rate in data.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item))
            
            rate_spin = QDoubleSpinBox()
            rate_spin.setRange(0, 10000)
            rate_spin.setDecimals(2)
            rate_spin.setValue(rate)
            self.table.setCellWidget(row, 1, rate_spin)


class RecipeEditorDialog(QDialog):
    """Dialog for creating/editing recipes."""
    
    def __init__(self, recipe: Optional[Recipe] = None, parent=None):
        super().__init__(parent)
        
        self.recipe = recipe
        self.setWindowTitle("Edit Recipe" if recipe else "New Recipe")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        self._setup_ui()
        
        if recipe:
            self._load_recipe(recipe)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Name field
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)
        
        self.desc_edit = QLineEdit()
        form.addRow("Description:", self.desc_edit)
        layout.addLayout(form)
        
        # Inputs table
        self.inputs_table = ItemRateTable("Inputs")
        layout.addWidget(self.inputs_table)
        
        # Outputs table
        self.outputs_table = ItemRateTable("Outputs")
        layout.addWidget(self.outputs_table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_recipe(self, recipe: Recipe):
        self.name_edit.setText(recipe.name)
        self.desc_edit.setText(recipe.description)
        self.inputs_table.set_data(recipe.inputs)
        self.outputs_table.set_data(recipe.outputs)
    
    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Recipe name is required.")
            return
        
        inputs = self.inputs_table.get_data()
        outputs = self.outputs_table.get_data()
        
        if not outputs:
            QMessageBox.warning(self, "Error", "Recipe must have at least one output.")
            return
        
        self.recipe = Recipe(
            name=name,
            inputs=inputs,
            outputs=outputs,
            description=self.desc_edit.text().strip(),
        )
        self.accept()
    
    def get_recipe(self) -> Optional[Recipe]:
        return self.recipe
