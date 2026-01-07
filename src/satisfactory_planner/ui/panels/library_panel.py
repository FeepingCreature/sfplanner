"""Library panel for selecting buildings to place."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from satisfactory_planner.core import (
    BUILDING_COLORS,
    BUILDING_METADATA,
    LOGISTICS_DISPLAY_SIZE,
    BuildingType,
)

# Building info: (description, extra_info)
BUILDING_INFO: dict[BuildingType, tuple[str, str]] = {
    BuildingType.SMELTER: ("Smelts ore into ingots", "1 in → 1 out"),
    BuildingType.FOUNDRY: ("Alloy smelting", "2 in → 1 out"),
    BuildingType.CONSTRUCTOR: ("Basic crafting", "1 in → 1 out"),
    BuildingType.ASSEMBLER: ("Two-part assembly", "2 in → 1 out"),
    BuildingType.MANUFACTURER: ("Complex crafting", "4 in → 1 out"),
    BuildingType.REFINERY: ("Fluid processing", "2 in → 2 out"),
    BuildingType.PACKAGER: ("Fluid packaging", "2 in → 2 out"),
    BuildingType.BLENDER: ("Fluid blending", "4 in → 2 out"),
    BuildingType.MINER_MK1: ("60/min base rate", "Extracts ore"),
    BuildingType.MINER_MK2: ("120/min base rate", "Extracts ore"),
    BuildingType.MINER_MK3: ("240/min base rate", "Extracts ore"),
    BuildingType.SPLITTER: ("1 → 3 split", "Divides belt"),
    BuildingType.MERGER: ("3 → 1 merge", "Combines belts"),
}


def _get_building_color(building_type: BuildingType) -> QColor:
    """Get QColor for a building type from the core color definitions."""
    rgb = BUILDING_COLORS.get(building_type, (150, 150, 150))
    return QColor(rgb[0], rgb[1], rgb[2])


# Item dimensions
ICON_SIZE = 36
ITEM_HEIGHT = 52
ITEM_PADDING = 4


class BuildingItemDelegate(QStyledItemDelegate):
    """Custom delegate for 3-line building items with icon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def sizeHint(self, option: QStyleOptionViewItem, index: object) -> QSize:
        """Return appropriate size for building items."""
        # Check if this is a building item (has UserRole data)
        building_type = index.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if building_type:
            return QSize(option.rect.width(), ITEM_HEIGHT)  # type: ignore[attr-defined]
        # Category headers use default size
        return super().sizeHint(option, index)  # type: ignore[arg-type]

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: object) -> None:
        """Paint the building item with icon, name, and info."""
        building_type = index.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]

        if not building_type:
            # Category header - use default painting
            super().paint(painter, option, index)  # type: ignore[arg-type]
            return

        painter.save()

        # Draw selection/hover background using palette colors
        palette = option.palette  # type: ignore[attr-defined]
        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
            painter.fillRect(option.rect, palette.highlight())  # type: ignore[attr-defined]
        elif option.state & QStyle.StateFlag.State_MouseOver:  # type: ignore[attr-defined]
            # Slightly lighter/darker than background for hover
            hover_color = palette.base().color()
            hover_color = (
                hover_color.lighter(110)
                if hover_color.lightness() < 128
                else hover_color.darker(110)
            )
            painter.fillRect(option.rect, hover_color)  # type: ignore[attr-defined]

        rect = option.rect.adjusted(ITEM_PADDING, ITEM_PADDING, -ITEM_PADDING, -ITEM_PADDING)  # type: ignore[attr-defined]

        # Draw building icon (colored square with mini building preview)
        icon_rect = QRect(rect.left(), rect.top(), ICON_SIZE, ICON_SIZE)
        self._draw_building_icon(painter, icon_rect, building_type)

        # Text area to the right of icon
        text_left = icon_rect.right() + ITEM_PADDING * 2
        text_rect = QRect(text_left, rect.top(), rect.right() - text_left, rect.height())

        # Line 1: Building name (bold)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(palette.text().color())

        name_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), 16)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            building_type.value,
        )

        # Line 2: Description (smaller, dimmer)
        info = BUILDING_INFO.get(building_type, ("", ""))
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        dim_color = palette.text().color()
        dim_color.setAlphaF(0.7)
        painter.setPen(dim_color)

        desc_rect = QRect(text_rect.left(), text_rect.top() + 16, text_rect.width(), 14)
        painter.drawText(
            desc_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, info[0]
        )

        # Line 3: Port info (even smaller, dimmer)
        font.setPointSize(7)
        painter.setFont(font)
        dimmer_color = palette.text().color()
        dimmer_color.setAlphaF(0.5)
        painter.setPen(dimmer_color)

        port_rect = QRect(text_rect.left(), text_rect.top() + 30, text_rect.width(), 12)
        painter.drawText(
            port_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, info[1]
        )

        painter.restore()

    def _draw_building_icon(
        self, painter: QPainter, rect: QRect, building_type: BuildingType
    ) -> None:
        """Draw a mini building preview as the icon."""
        color = _get_building_color(building_type)

        # Draw building body
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255), 1))

        # Use full icon rect for the building shape
        building_rect = rect.adjusted(2, 2, -2, -2)
        painter.drawRect(building_rect)

        # Draw ports
        meta = BUILDING_METADATA.get(building_type, (80, 60, 1, 1))
        num_inputs = meta[2]
        num_outputs = meta[3]

        port_radius = 3

        # Input ports (left side, yellow)
        painter.setBrush(QBrush(QColor(230, 180, 50)))
        painter.setPen(QPen(QColor(200, 150, 30), 1))

        if building_type == BuildingType.SPLITTER:
            # Single input on left
            py = building_rect.center().y()
            painter.drawEllipse(
                building_rect.left() - port_radius,
                int(py) - port_radius,
                port_radius * 2,
                port_radius * 2,
            )
        elif building_type == BuildingType.MERGER:
            # 3 inputs: top, left, bottom
            positions = [
                (building_rect.center().x(), building_rect.top()),
                (building_rect.left(), building_rect.center().y()),
                (building_rect.center().x(), building_rect.bottom()),
            ]
            for px, py in positions:
                painter.drawEllipse(
                    int(px) - port_radius, int(py) - port_radius, port_radius * 2, port_radius * 2
                )
        else:
            # Standard inputs on left
            for i in range(num_inputs):
                spacing = building_rect.height() / (num_inputs + 1)
                py = int(building_rect.top() + spacing * (i + 1))
                painter.drawEllipse(
                    building_rect.left() - port_radius,
                    int(py) - port_radius,
                    port_radius * 2,
                    port_radius * 2,
                )

        # Output ports (right side, green)
        painter.setBrush(QBrush(QColor(100, 200, 100)))
        painter.setPen(QPen(QColor(70, 170, 70), 1))

        if building_type == BuildingType.MERGER:
            # Single output on right
            py = building_rect.center().y()
            painter.drawEllipse(
                building_rect.right() - port_radius,
                int(py) - port_radius,
                port_radius * 2,
                port_radius * 2,
            )
        elif building_type == BuildingType.SPLITTER:
            # 3 outputs: top, right, bottom
            positions = [
                (building_rect.center().x(), building_rect.top()),
                (building_rect.right(), building_rect.center().y()),
                (building_rect.center().x(), building_rect.bottom()),
            ]
            for px, py in positions:
                painter.drawEllipse(
                    int(px) - port_radius, int(py) - port_radius, port_radius * 2, port_radius * 2
                )
        else:
            # Standard outputs on right
            for i in range(num_outputs):
                spacing = building_rect.height() / (num_outputs + 1)
                py = int(building_rect.top() + spacing * (i + 1))
                painter.drawEllipse(
                    building_rect.right() - port_radius,
                    int(py) - port_radius,
                    port_radius * 2,
                    port_radius * 2,
                )


class BuildingTreeItem(QTreeWidgetItem):
    """Tree item for a building type with rich display."""

    def __init__(self, building_type: BuildingType) -> None:
        super().__init__()
        self.building_type = building_type

        info = BUILDING_INFO.get(building_type, ("", ""))
        meta = BUILDING_METADATA.get(building_type, (80, 60, 1, 1))

        # Main text is the building name (used by delegate)
        self.setText(0, building_type.value)
        # Store extra info for tooltip
        self.setToolTip(0, f"{info[0]}\n{info[1]}\nSize: {meta[0]}x{meta[1]}")
        self.setData(0, Qt.ItemDataRole.UserRole, building_type)
        # Set size hint for this item
        self.setSizeHint(0, QSize(200, ITEM_HEIGHT))


class LibraryPanel(QWidget):
    """Panel for selecting buildings to place on the canvas."""

    # Emitted when a building type is selected for placement
    building_selected = Signal(object)  # BuildingType or None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Single tree view for all buildings
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

        # Production category
        production_item = QTreeWidgetItem(["Production"])
        production_item.setFlags(production_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        font = production_item.font(0)
        font.setBold(True)
        production_item.setFont(0, font)

        for bt in [
            BuildingType.SMELTER,
            BuildingType.FOUNDRY,
            BuildingType.CONSTRUCTOR,
            BuildingType.ASSEMBLER,
            BuildingType.MANUFACTURER,
            BuildingType.REFINERY,
            BuildingType.PACKAGER,
            BuildingType.BLENDER,
        ]:
            production_item.addChild(BuildingTreeItem(bt))

        self.tree.addTopLevelItem(production_item)
        production_item.setExpanded(True)

        # Extraction category
        extraction_item = QTreeWidgetItem(["Extraction"])
        extraction_item.setFlags(extraction_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        extraction_item.setFont(0, font)

        for bt in [
            BuildingType.MINER_MK1,
            BuildingType.MINER_MK2,
            BuildingType.MINER_MK3,
        ]:
            extraction_item.addChild(BuildingTreeItem(bt))

        self.tree.addTopLevelItem(extraction_item)
        extraction_item.setExpanded(True)

        # Logistics category
        logistics_item = QTreeWidgetItem(["Logistics"])
        logistics_item.setFlags(logistics_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        logistics_item.setFont(0, font)

        for bt in [
            BuildingType.SPLITTER,
            BuildingType.MERGER,
        ]:
            logistics_item.addChild(BuildingTreeItem(bt))

        self.tree.addTopLevelItem(logistics_item)
        logistics_item.setExpanded(True)

        # Blueprints category (placeholder)
        blueprints_item = QTreeWidgetItem(["Blueprints"])
        blueprints_item.setFlags(blueprints_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        blueprints_item.setFont(0, font)

        placeholder = QTreeWidgetItem(["(No saved blueprints)"])
        placeholder.setFlags(
            placeholder.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsDragEnabled
        )
        blueprints_item.addChild(placeholder)

        self.tree.addTopLevelItem(blueprints_item)
        blueprints_item.setExpanded(True)

        # Set custom delegate for rich item rendering
        self.tree.setItemDelegate(BuildingItemDelegate(self.tree))
        self.tree.setMouseTracking(True)  # Enable hover effects

        # Connect signals
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.startDrag = self._start_drag  # type: ignore[method-assign]

        layout.addWidget(self.tree)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle building selection - attach to cursor."""
        building_type = item.data(0, Qt.ItemDataRole.UserRole)
        if building_type:
            self.building_selected.emit(building_type)

    def _start_drag(self, supported_actions: Qt.DropAction) -> None:
        """Start drag operation with building type."""
        item = self.tree.currentItem()
        if not item:
            return

        building_type = item.data(0, Qt.ItemDataRole.UserRole)
        if not building_type:
            return

        # Create drag with building type data
        drag = QDrag(self.tree)
        mime_data = QMimeData()
        mime_data.setText(building_type.value)
        mime_data.setData("application/x-building-type", building_type.value.encode())
        drag.setMimeData(mime_data)

        # Create full building preview pixmap
        pixmap = self._create_building_pixmap(building_type)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec(Qt.DropAction.CopyAction)

    def _create_building_pixmap(self, building_type: BuildingType) -> QPixmap:
        """Create a pixmap showing the full building with ports."""
        meta = BUILDING_METADATA.get(building_type, (80, 60, 1, 1))

        # Use display size (smaller for logistics)
        if building_type in (BuildingType.SPLITTER, BuildingType.MERGER):
            w, h = LOGISTICS_DISPLAY_SIZE, LOGISTICS_DISPLAY_SIZE
        else:
            w, h = meta[0], meta[1]

        num_inputs = meta[2]
        num_outputs = meta[3]

        # Add padding for ports
        padding = 12
        pixmap = QPixmap(w + padding * 2, h + padding * 2)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Building rect (centered in pixmap)
        bx, by = padding, padding

        # Draw building body
        color = _get_building_color(building_type)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawRect(bx, by, w, h)

        # Draw building name
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont()
        font.setPointSize(7 if building_type in (BuildingType.SPLITTER, BuildingType.MERGER) else 8)
        painter.setFont(font)

        name = building_type.value
        if building_type == BuildingType.SPLITTER:
            name = "SPL"
        elif building_type == BuildingType.MERGER:
            name = "MRG"

        painter.drawText(QRect(bx, by, w, h), Qt.AlignmentFlag.AlignCenter, name)

        # Port styling
        port_radius = 6
        arrow_size = 4

        # Helper to draw port with arrow
        def draw_port(px: int, py: int, is_output: bool, angle: float) -> None:
            # Port circle
            if is_output:
                painter.setBrush(QBrush(QColor(100, 200, 100)))
                painter.setPen(QPen(QColor(70, 170, 70), 1))
            else:
                painter.setBrush(QBrush(QColor(230, 180, 50)))
                painter.setPen(QPen(QColor(200, 150, 30), 1))

            painter.drawEllipse(
                px - port_radius, py - port_radius, port_radius * 2, port_radius * 2
            )

            # Arrow
            import math

            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            rad = math.radians(angle)

            # Arrow points in direction of flow
            tip_x = px + math.cos(rad) * (port_radius - 2)
            tip_y = py + math.sin(rad) * (port_radius - 2)
            base_x = px - math.cos(rad) * (port_radius - 3)
            base_y = py - math.sin(rad) * (port_radius - 3)

            # Draw arrow line
            painter.drawLine(int(base_x), int(base_y), int(tip_x), int(tip_y))

            # Arrow head
            head_angle1 = rad + math.radians(140)
            head_angle2 = rad - math.radians(140)
            h1x = tip_x + math.cos(head_angle1) * arrow_size
            h1y = tip_y + math.sin(head_angle1) * arrow_size
            h2x = tip_x + math.cos(head_angle2) * arrow_size
            h2y = tip_y + math.sin(head_angle2) * arrow_size
            painter.drawLine(int(tip_x), int(tip_y), int(h1x), int(h1y))
            painter.drawLine(int(tip_x), int(tip_y), int(h2x), int(h2y))

        # Draw ports based on building type
        if building_type == BuildingType.SPLITTER:
            # 1 input left, 3 outputs (top, right, bottom)
            draw_port(bx, by + h // 2, False, 180)
            draw_port(bx + w // 2, by, True, 270)
            draw_port(bx + w, by + h // 2, True, 0)
            draw_port(bx + w // 2, by + h, True, 90)
        elif building_type == BuildingType.MERGER:
            # 3 inputs (top, left, bottom), 1 output right
            draw_port(bx + w // 2, by, False, 270)
            draw_port(bx, by + h // 2, False, 180)
            draw_port(bx + w // 2, by + h, False, 90)
            draw_port(bx + w, by + h // 2, True, 0)
        else:
            # Standard: inputs left, outputs right
            for i in range(num_inputs):
                spacing = h / (num_inputs + 1)
                py = by + int(spacing * (i + 1))
                draw_port(bx, py, False, 180)

            for i in range(num_outputs):
                spacing = h / (num_outputs + 1)
                py = by + int(spacing * (i + 1))
                draw_port(bx + w, py, True, 0)

        painter.end()
        return pixmap
