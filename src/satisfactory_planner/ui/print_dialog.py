"""Print dialog for rendering factory blueprints in black/white style."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class PrintOptionsDialog(QDialog):
    """Dialog for print options before showing print preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Print Options")
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Black and white option
        self.bw_checkbox = QCheckBox("Black && White (printer-friendly)")
        self.bw_checkbox.setChecked(True)
        layout.addWidget(self.bw_checkbox)

        # Include title option
        self.title_checkbox = QCheckBox("Include document title")
        self.title_checkbox.setChecked(True)
        layout.addWidget(self.title_checkbox)

        # Margin setting
        margin_layout = QHBoxLayout()
        margin_layout.addWidget(QLabel("Margin (mm):"))
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setValue(10)
        margin_layout.addWidget(self.margin_spin)
        margin_layout.addStretch()
        layout.addLayout(margin_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def is_black_white(self) -> bool:
        """Return whether black/white mode is selected."""
        return self.bw_checkbox.isChecked()

    def include_title(self) -> bool:
        """Return whether to include document title."""
        return self.title_checkbox.isChecked()

    def margin_mm(self) -> int:
        """Return margin in millimeters."""
        return self.margin_spin.value()


def render_scene_to_image(
    scene: QGraphicsScene,
    width: int = 2000,
    black_white: bool = True,
) -> QImage:
    """Render a graphics scene to an image.

    Args:
        scene: The QGraphicsScene to render
        width: Target width in pixels (height scales proportionally)
        black_white: Whether to convert to grayscale

    Returns:
        QImage with the rendered scene
    """
    # Get scene bounds
    scene_rect = scene.itemsBoundingRect()
    if scene_rect.isEmpty():
        # Empty scene - return small blank image
        return QImage(100, 100, QImage.Format.Format_RGB32)

    # Add padding
    padding = 50
    scene_rect.adjust(-padding, -padding, padding, padding)

    # Calculate dimensions maintaining aspect ratio
    aspect = scene_rect.height() / scene_rect.width()
    height = int(width * aspect)

    # Create image with white background
    if black_white:
        image = QImage(width, height, QImage.Format.Format_Grayscale8)
    else:
        image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)

    # Render scene to image
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    if black_white:
        # For B&W, we render in color first then convert
        # Create a color image first
        color_image = QImage(width, height, QImage.Format.Format_RGB32)
        color_image.fill(Qt.GlobalColor.white)
        color_painter = QPainter(color_image)
        color_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        scene.render(color_painter, QRectF(0, 0, width, height), scene_rect)
        color_painter.end()

        # Convert to grayscale
        grayscale = color_image.convertToFormat(QImage.Format.Format_Grayscale8)

        # Copy to our output image
        painter.drawImage(0, 0, grayscale)
    else:
        scene.render(painter, QRectF(0, 0, width, height), scene_rect)

    painter.end()
    return image


def print_scene(
    scene: QGraphicsScene,
    parent: QWidget | None = None,
    document_title: str = "Factory Blueprint",
    black_white: bool = True,
    include_title: bool = True,
    margin_mm: int = 10,
) -> None:
    """Open print preview dialog for the scene.

    Args:
        scene: The QGraphicsScene to print
        parent: Parent widget for dialogs
        document_title: Title to display on the print
        black_white: Whether to render in black/white
        include_title: Whether to include the title on the print
        margin_mm: Margin in millimeters
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)

    # Set margins
    margins = QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm)
    printer.setPageMargins(margins, QPageLayout.Unit.Millimeter)

    def render_preview(preview_printer: QPrinter) -> None:
        """Render callback for print preview."""
        _render_to_printer(
            preview_printer,
            scene,
            document_title if include_title else None,
            black_white,
        )

    # Show print preview dialog
    preview = QPrintPreviewDialog(printer, parent)
    preview.setWindowTitle(f"Print Preview - {document_title}")
    preview.paintRequested.connect(render_preview)
    preview.exec()


def _render_to_printer(
    printer: QPrinter,
    scene: QGraphicsScene,
    title: str | None,
    black_white: bool,
) -> None:
    """Render scene to printer.

    Args:
        printer: The printer to render to
        scene: The QGraphicsScene to render
        title: Optional title to draw at top
        black_white: Whether to render in black/white
    """
    painter = QPainter(printer)

    # Get printable area
    page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)

    # Reserve space for title if needed
    title_height = 0
    if title:
        title_height = 50  # pixels for title
        painter.setFont(painter.font())
        font = painter.font()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))
        title_rect = QRectF(
            page_rect.x(),
            page_rect.y(),
            page_rect.width(),
            title_height,
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)

    # Calculate scene render area (below title)
    render_rect = QRectF(
        page_rect.x(),
        page_rect.y() + title_height,
        page_rect.width(),
        page_rect.height() - title_height,
    )

    # Get scene bounds
    scene_rect = scene.itemsBoundingRect()
    if scene_rect.isEmpty():
        painter.end()
        return

    # Add padding to scene
    padding = 20
    scene_rect.adjust(-padding, -padding, padding, padding)

    if black_white:
        # Render to intermediate image, convert to grayscale, then draw
        # Calculate appropriate resolution
        scale = min(
            render_rect.width() / scene_rect.width(),
            render_rect.height() / scene_rect.height(),
        )
        img_width = int(scene_rect.width() * scale)
        img_height = int(scene_rect.height() * scale)

        # Cap image size to avoid memory issues
        max_dim = 4000
        if img_width > max_dim or img_height > max_dim:
            ratio = min(max_dim / img_width, max_dim / img_height)
            img_width = int(img_width * ratio)
            img_height = int(img_height * ratio)

        # Render scene to color image
        color_image = QImage(img_width, img_height, QImage.Format.Format_RGB32)
        color_image.fill(Qt.GlobalColor.white)
        img_painter = QPainter(color_image)
        img_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        img_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        scene.render(img_painter, QRectF(0, 0, img_width, img_height), scene_rect)
        img_painter.end()

        # Convert to grayscale
        grayscale = color_image.convertToFormat(QImage.Format.Format_Grayscale8)

        # Draw centered in render area
        x_offset = render_rect.x() + (render_rect.width() - img_width) / 2
        y_offset = render_rect.y() + (render_rect.height() - img_height) / 2
        painter.drawImage(int(x_offset), int(y_offset), grayscale)
    else:
        # Render scene directly, maintaining aspect ratio
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Calculate scaled rect maintaining aspect ratio
        scale = min(
            render_rect.width() / scene_rect.width(),
            render_rect.height() / scene_rect.height(),
        )
        scaled_width = scene_rect.width() * scale
        scaled_height = scene_rect.height() * scale

        # Center in render area
        target_rect = QRectF(
            render_rect.x() + (render_rect.width() - scaled_width) / 2,
            render_rect.y() + (render_rect.height() - scaled_height) / 2,
            scaled_width,
            scaled_height,
        )

        scene.render(painter, target_rect, scene_rect)

    painter.end()
