"""Print dialog with automatic tile packing for factory blueprints.

The print system automatically partitions large factory layouts into tiles
that pack efficiently onto a printed page, maximizing readability.

Algorithm overview:
1. Graph Partitioning: DFS explores cutting belts to create tile partitions
   - Each partition has a "crossing cost" (number of cut belts)
   - Prune partitions exceeding max_crossings setting
2. Rectangle Packing: Greedy bottom-left placement with random restarts
   - Try multiple orderings (by area, random shuffles)
   - Pack tiles preserving aspect ratios
   - Compute uniform zoom to fit page
3. Rendering: Draw each tile with crossing stubs for cut belts
   - Stubs show item name + number (e.g., "Iron Ore #1")
   - Stubs point toward nearest tile edge
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPen
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Document


# =============================================================================
# Data structures for packing algorithm
# =============================================================================


@dataclass
class Tile:
    """A tile in the packed layout, representing a partition of buildings."""

    building_ids: frozenset[str]
    """IDs of buildings in this tile."""

    bounds: QRectF
    """Bounding box in original scene coordinates."""

    @property
    def aspect_ratio(self) -> float:
        """Width / height ratio."""
        if self.bounds.height() == 0:
            return 1.0
        return self.bounds.width() / self.bounds.height()


@dataclass
class CrossingStub:
    """A belt that crosses between tiles, rendered as a labeled stub."""

    belt_id: str
    """Original belt ID."""

    item_name: str | None
    """Item being transported, if known from flow analysis."""

    crossing_id: int
    """Numeric ID for this crossing (1, 2, 3...)."""

    source_tile_index: int
    """Index of tile containing the source building."""

    dest_tile_index: int
    """Index of tile containing the destination building."""

    source_port_pos: QPointF
    """Position of source port in scene coordinates."""

    dest_port_pos: QPointF
    """Position of destination port in scene coordinates."""


@dataclass
class Partition:
    """A partitioning of the factory into tiles."""

    tiles: list[Tile]
    """The tiles in this partition."""

    crossings: list[CrossingStub]
    """Belts that cross between tiles."""

    @property
    def crossing_count(self) -> int:
        """Number of cut belts."""
        return len(self.crossings)


@dataclass
class PackedTile:
    """A tile with its position in the packed layout."""

    tile: Tile
    """The original tile."""

    packed_bounds: QRectF
    """Position and size in packed layout coordinates."""


@dataclass
class PackedLayout:
    """A complete packed layout ready for rendering."""

    tiles: list[PackedTile]
    """Tiles with their packed positions."""

    crossings: list[CrossingStub]
    """Crossing stubs to render."""

    total_bounds: QRectF
    """Bounding box of the entire packed layout."""

    zoom: float
    """Zoom factor to fit page (higher = more readable)."""


@dataclass
class PartitionCandidate:
    """A candidate partition during DFS exploration."""

    cut_edges: frozenset[str]
    """Belt IDs that are cut."""

    components: list[frozenset[str]]
    """Connected components (sets of building IDs)."""


# =============================================================================
# Graph partitioning algorithm
# =============================================================================


def _get_building_bounds(document: Document, building_id: str) -> QRectF:
    """Get bounding box for a building or room placement."""
    # Check top-level buildings
    building = document.buildings.get(building_id)
    if building:
        return QRectF(building.x, building.y, building.width, building.height)

    # Check room placements
    placement = document.room_placements.get(building_id)
    if placement:
        room = document.rooms.get(placement.room_id)
        if room:
            return QRectF(placement.x, placement.y, room.width or 100, room.height or 100)

    return QRectF(0, 0, 50, 50)  # Fallback


def _build_adjacency(
    document: Document,
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """Build adjacency info from document.

    Returns:
        Tuple of (node_ids, edges) where edges are (belt_id, source_id, dest_id).
        Rooms/placements are treated as single nodes.
    """
    nodes: set[str] = set()
    edges: list[tuple[str, str, str]] = []

    # Collect top-level buildings
    for building in document.buildings.values():
        nodes.add(building.id)

    # Collect room placements as single nodes
    for placement in document.room_placements.values():
        nodes.add(placement.id)

    # Collect edges from top-level belts
    for belt in document.belts.values():
        source_id = belt.source_building_id
        dest_id = belt.dest_building_id

        # Map building IDs to their containing placement if any
        source_node = _get_containing_node(document, source_id)
        dest_node = _get_containing_node(document, dest_id)

        if source_node and dest_node and source_node != dest_node:
            edges.append((belt.id, source_node, dest_node))

    return nodes, edges


def _get_containing_node(document: Document, building_id: str) -> str | None:
    """Get the node ID that contains a building.

    For top-level buildings, returns the building ID.
    For buildings inside rooms, returns the placement ID.
    """
    # Check if it's a top-level building
    if building_id in document.buildings:
        return building_id

    # Check if it's a room placement
    for placement in document.room_placements.values():
        if placement.id == building_id:
            return placement.id
        # Check buildings inside the room
        room = document.rooms.get(placement.room_id)
        if room and building_id in room.buildings:
            return placement.id

    return None


def _connected_components(
    nodes: set[str], edges: list[tuple[str, str, str]], cut_edges: frozenset[str]
) -> list[frozenset[str]]:
    """Find connected components with given edges removed."""
    # Build adjacency list excluding cut edges
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for belt_id, src, dst in edges:
        if belt_id not in cut_edges:
            adj[src].add(dst)
            adj[dst].add(src)

    # BFS to find components
    visited: set[str] = set()
    components: list[frozenset[str]] = []

    for start in nodes:
        if start in visited:
            continue
        component: set[str] = set()
        queue = [start]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            queue.extend(adj[node] - visited)
        if component:
            components.append(frozenset(component))

    return components


def generate_partitions(
    document: Document, max_crossings: int, max_candidates: int = 100
) -> list[Partition]:
    """Generate candidate partitions using DFS edge cutting.

    Args:
        document: The factory document.
        max_crossings: Maximum number of belt crossings allowed.
        max_candidates: Maximum number of partitions to generate.

    Returns:
        List of valid partitions, always including the trivial single-tile case.
    """
    nodes, edges = _build_adjacency(document)

    if not nodes:
        return []

    candidates: list[PartitionCandidate] = []

    def dfs(cut_edges: frozenset[str], edge_index: int) -> None:
        """DFS to explore edge cutting combinations."""
        if len(candidates) >= max_candidates:
            return

        if len(cut_edges) > max_crossings:
            return

        components = _connected_components(nodes, edges, cut_edges)
        candidate = PartitionCandidate(cut_edges=cut_edges, components=components)
        candidates.append(candidate)

        # Try cutting each remaining edge
        for i in range(edge_index, len(edges)):
            belt_id = edges[i][0]
            dfs(cut_edges | {belt_id}, i + 1)

    # Start DFS
    dfs(frozenset(), 0)

    # Convert candidates to Partitions with geometric info
    partitions: list[Partition] = []
    for candidate in candidates:
        tiles = []
        for component in candidate.components:
            # Compute bounding box for this component
            bounds = QRectF()
            for building_id in component:
                b_bounds = _get_building_bounds(document, building_id)
                bounds = b_bounds if bounds.isEmpty() else bounds.united(b_bounds)

            # Add padding for belt stubs
            padding = 30
            bounds.adjust(-padding, -padding, padding, padding)

            tiles.append(Tile(building_ids=component, bounds=bounds))

        # Create crossing stubs
        crossings: list[CrossingStub] = []
        crossing_id = 1
        for belt_id in candidate.cut_edges:
            # Find the belt and its endpoints
            belt = document.belts.get(belt_id)
            if not belt:
                continue

            source_node = _get_containing_node(document, belt.source_building_id)
            dest_node = _get_containing_node(document, belt.dest_building_id)

            # Find which tiles contain source and dest
            source_tile_idx = -1
            dest_tile_idx = -1
            for idx, tile in enumerate(tiles):
                if source_node in tile.building_ids:
                    source_tile_idx = idx
                if dest_node in tile.building_ids:
                    dest_tile_idx = idx

            if source_tile_idx >= 0 and dest_tile_idx >= 0:
                # Get port positions
                source_building = document.buildings.get(belt.source_building_id)
                dest_building = document.buildings.get(belt.dest_building_id)

                source_pos = QPointF(0, 0)
                dest_pos = QPointF(0, 0)

                if source_building:
                    px, py = source_building.output_port_pos(belt.source_port_index)
                    source_pos = QPointF(px, py)

                if dest_building:
                    px, py = dest_building.input_port_pos(belt.dest_port_index)
                    dest_pos = QPointF(px, py)

                crossings.append(
                    CrossingStub(
                        belt_id=belt_id,
                        item_name=None,  # TODO: Get from flow analysis
                        crossing_id=crossing_id,
                        source_tile_index=source_tile_idx,
                        dest_tile_index=dest_tile_idx,
                        source_port_pos=source_pos,
                        dest_port_pos=dest_pos,
                    )
                )
                crossing_id += 1

        partitions.append(Partition(tiles=tiles, crossings=crossings))

    return partitions


# =============================================================================
# Rectangle packing algorithm
# =============================================================================


@dataclass
class _PackingState:
    """State during greedy packing."""

    placed: list[QRectF] = field(default_factory=list)
    """Already placed rectangles."""


def _try_place_bottom_left(state: _PackingState, width: float, height: float) -> QRectF:
    """Find bottom-left position for a rectangle using proper 2D bin packing.

    Tries candidate positions at corners of existing rectangles.
    """
    if not state.placed:
        # First rectangle goes at origin
        print(f"DEBUG pack: First rect {width:.0f}x{height:.0f} at origin")
        return QRectF(0, 0, width, height)

    best_pos: QPointF | None = None
    best_score = float("inf")  # Lower is better (y first, then x)

    # Candidate positions: corners formed by existing rects
    candidates: set[tuple[float, float]] = {(0.0, 0.0)}

    for rect in state.placed:
        # Right edge of this rect, at y=0
        candidates.add((rect.right(), 0.0))
        # Left edge (x=0), below this rect
        candidates.add((0.0, rect.bottom()))
        # Corners formed by combinations of rects
        for other in state.placed:
            candidates.add((rect.right(), other.bottom()))
            candidates.add((other.right(), rect.bottom()))

    print(f"DEBUG pack: Placing {width:.0f}x{height:.0f}, candidates: {len(candidates)}")

    for x, y in candidates:
        candidate = QRectF(x, y, width, height)

        # Check if this position overlaps any placed rect
        # Use a small epsilon to avoid floating point issues
        overlaps = False
        for placed in state.placed:
            # Check for real intersection (not just touching)
            if (
                candidate.left() < placed.right() - 0.1
                and candidate.right() > placed.left() + 0.1
                and candidate.top() < placed.bottom() - 0.1
                and candidate.bottom() > placed.top() + 0.1
            ):
                overlaps = True
                break

        if not overlaps:
            # Score: prefer lower y, then lower x (bottom-left)
            score = y * 10000 + x
            if score < best_score:
                best_score = score
                best_pos = QPointF(x, y)
                print(f"DEBUG pack:   Valid pos ({x:.0f}, {y:.0f}) score={score:.0f}")

    if best_pos is None:
        # Fallback: place to the right of everything
        max_right = max(r.right() for r in state.placed)
        best_pos = QPointF(max_right, 0)
        print(f"DEBUG pack:   Fallback to ({best_pos.x():.0f}, 0)")

    print(f"DEBUG pack:   -> Placed at ({best_pos.x():.0f}, {best_pos.y():.0f})")
    return QRectF(best_pos.x(), best_pos.y(), width, height)


def pack_tiles(
    tiles: list[Tile], page_aspect: float, num_attempts: int = 10
) -> PackedLayout | None:
    """Pack tiles onto a page using greedy bottom-left with random restarts.

    Args:
        tiles: Tiles to pack.
        page_aspect: Target page width/height ratio.
        num_attempts: Number of random orderings to try.

    Returns:
        Best packed layout, or None if no tiles.
    """
    if not tiles:
        return None

    best_layout: PackedLayout | None = None
    best_zoom = 0.0

    # Generate orderings to try
    orderings: list[list[int]] = []

    # Sorted by area (largest first)
    by_area = sorted(
        range(len(tiles)),
        key=lambda i: tiles[i].bounds.width() * tiles[i].bounds.height(),
        reverse=True,
    )
    orderings.append(by_area)

    # Sorted by height (tallest first)
    by_height = sorted(range(len(tiles)), key=lambda i: tiles[i].bounds.height(), reverse=True)
    orderings.append(by_height)

    # Random shuffles
    indices = list(range(len(tiles)))
    for _ in range(num_attempts - 2):
        shuffled = indices.copy()
        random.shuffle(shuffled)
        orderings.append(shuffled)

    # Try each ordering
    for ordering in orderings:
        state = _PackingState()
        packed_tiles: list[PackedTile] = []

        for idx in ordering:
            tile = tiles[idx]
            width = tile.bounds.width()
            height = tile.bounds.height()

            # Place using bottom-left
            packed_rect = _try_place_bottom_left(state, width, height)
            state.placed.append(packed_rect)
            packed_tiles.append(PackedTile(tile=tile, packed_bounds=packed_rect))

        # Compute total bounds
        total_bounds = QRectF()
        for pt in packed_tiles:
            if total_bounds.isEmpty():
                total_bounds = pt.packed_bounds
            else:
                total_bounds = total_bounds.united(pt.packed_bounds)

        # Compute zoom to fit page
        if total_bounds.width() > 0 and total_bounds.height() > 0:
            packed_aspect = total_bounds.width() / total_bounds.height()
            # Width-limited vs height-limited
            zoom = page_aspect / packed_aspect if packed_aspect > page_aspect else 1.0

            # Actual zoom is inverse of how much we need to shrink
            # Larger total_bounds = lower zoom
            zoom = 1.0 / max(total_bounds.width(), total_bounds.height())

            if zoom > best_zoom:
                best_zoom = zoom
                best_layout = PackedLayout(
                    tiles=packed_tiles,
                    crossings=[],  # Will be filled in by caller
                    total_bounds=total_bounds,
                    zoom=zoom,
                )

    return best_layout


def find_best_packing(
    document: Document,
    page_aspect: float,
    max_crossings: int,
) -> PackedLayout | None:
    """Find the best partition and packing for a document.

    Args:
        document: The factory document.
        page_aspect: Target page width/height ratio.
        max_crossings: Maximum belt crossings allowed.

    Returns:
        Best packed layout, or None if document is empty.
    """
    partitions = generate_partitions(document, max_crossings)

    if not partitions:
        return None

    best_layout: PackedLayout | None = None
    best_zoom = 0.0

    for partition in partitions:
        layout = pack_tiles(partition.tiles, page_aspect)
        if layout and layout.zoom > best_zoom:
            best_zoom = layout.zoom
            layout.crossings = partition.crossings
            best_layout = layout

    return best_layout


# =============================================================================
# Scene rendering utilities
# =============================================================================


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


# =============================================================================
# New packed print preview dialog
# =============================================================================


class PackedPrintPreviewDialog(QDialog):
    """Print preview dialog with automatic tile packing.

    Provides a toolbar with:
    - Color/Monochrome toggle
    - Max crossings spinbox
    - Include title checkbox
    - Refresh button
    """

    def __init__(
        self,
        document: Document,
        scene: QGraphicsScene,
        parent: QWidget | None = None,
        document_title: str = "Factory Blueprint",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Print Preview - {document_title}")
        self.setModal(True)
        self.resize(1200, 900)

        self._document = document
        self._scene = scene
        self._document_title = document_title
        self._layout: PackedLayout | None = None

        # Settings
        self._black_white = True
        self._max_crossings = 2
        self._include_title = True
        self._margin_mm = 10

        self._setup_ui()
        self._refresh_layout()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QToolBar()
        layout.addWidget(toolbar)

        # Monochrome toggle
        self._bw_checkbox = QCheckBox("Monochrome")
        self._bw_checkbox.setChecked(self._black_white)
        self._bw_checkbox.toggled.connect(self._on_settings_changed)
        toolbar.addWidget(self._bw_checkbox)

        toolbar.addSeparator()

        # Max crossings
        toolbar.addWidget(QLabel(" Max crossings: "))
        self._crossings_spin = QSpinBox()
        self._crossings_spin.setRange(0, 20)
        self._crossings_spin.setValue(self._max_crossings)
        self._crossings_spin.valueChanged.connect(self._on_settings_changed)
        toolbar.addWidget(self._crossings_spin)

        toolbar.addSeparator()

        # Include title
        self._title_checkbox = QCheckBox("Include title")
        self._title_checkbox.setChecked(self._include_title)
        self._title_checkbox.toggled.connect(self._on_settings_changed)
        toolbar.addWidget(self._title_checkbox)

        toolbar.addSeparator()

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_layout)
        toolbar.addWidget(refresh_btn)

        # Printer setup
        # Use ScreenResolution for preview - it will use HighResolution when actually printing
        self._printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        self._printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        self._printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        margins = QMarginsF(self._margin_mm, self._margin_mm, self._margin_mm, self._margin_mm)
        self._printer.setPageMargins(margins, QPageLayout.Unit.Millimeter)

        # Print preview widget (not dialog - we want to embed it)
        self._preview = QPrintPreviewWidget(self._printer, self)
        self._preview.paintRequested.connect(self._render_preview)
        # Set a reasonable zoom level for the preview
        self._preview.setZoomMode(QPrintPreviewWidget.ZoomMode.FitInView)
        layout.addWidget(self._preview)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        print_btn = QPushButton("Print")
        print_btn.clicked.connect(self._do_print)
        button_layout.addWidget(print_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _on_settings_changed(self) -> None:
        """Handle settings changes."""
        self._black_white = self._bw_checkbox.isChecked()
        self._max_crossings = self._crossings_spin.value()
        self._include_title = self._title_checkbox.isChecked()
        self._refresh_layout()

    def _refresh_layout(self) -> None:
        """Regenerate the packed layout."""
        # Get page aspect ratio
        page_rect = self._printer.pageRect(QPrinter.Unit.Millimeter)
        page_aspect = (
            page_rect.width() / page_rect.height()
            if page_rect.height() > 0
            else 1.414  # A4 landscape
        )

        print(f"DEBUG: Refreshing layout with max_crossings={self._max_crossings}")
        self._layout = find_best_packing(self._document, page_aspect, self._max_crossings)
        if self._layout:
            print(
                f"DEBUG: Got layout with {len(self._layout.tiles)} tiles, {len(self._layout.crossings)} crossings"
            )
        else:
            print("DEBUG: No layout generated")

        # QPrintPreviewWidget has updatePreview() method
        self._preview.updatePreview()

    def _render_preview(self, printer: QPrinter) -> None:
        """Render callback for print preview."""
        if self._layout is None:
            # No layout - draw error message
            painter = QPainter(printer)
            painter.drawText(100, 100, "No layout generated - document may be empty")
            painter.end()
            return

        self._render_packed_layout(printer)

    def _render_packed_layout(self, printer: QPrinter) -> None:
        """Render the packed layout to the printer."""
        painter = QPainter(printer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        layout = self._layout
        assert layout is not None

        # Reserve space for title
        # Note: For high-res printers, we need to scale font size relative to page dimensions
        # A 14pt font at 300dpi would be tiny; we need to scale based on logical page size
        title_height = 0.0
        if self._include_title:
            # Title height as fraction of page (about 3%)
            title_height = page_rect.height() * 0.03
            font = painter.font()
            # Font size proportional to title height (in device pixels)
            font.setPixelSize(max(12, int(title_height * 0.6)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0))
            title_rect = QRectF(page_rect.x(), page_rect.y(), page_rect.width(), title_height)
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self._document_title)

        # Calculate render area
        render_rect = QRectF(
            page_rect.x(),
            page_rect.y() + title_height,
            page_rect.width(),
            page_rect.height() - title_height,
        )

        # Calculate scale to fit packed layout in render area
        if layout.total_bounds.width() > 0 and layout.total_bounds.height() > 0:
            scale = min(
                render_rect.width() / layout.total_bounds.width(),
                render_rect.height() / layout.total_bounds.height(),
            )
        else:
            scale = 1.0

        # Center the layout
        scaled_width = layout.total_bounds.width() * scale
        scaled_height = layout.total_bounds.height() * scale
        offset_x = render_rect.x() + (render_rect.width() - scaled_width) / 2
        offset_y = render_rect.y() + (render_rect.height() - scaled_height) / 2

        # Render each tile
        for packed_tile in layout.tiles:
            self._render_tile(
                painter,
                packed_tile,
                layout,
                scale,
                offset_x,
                offset_y,
            )

        painter.end()

    # Debug tile colors for visualizing packing
    _TILE_COLORS = [
        QColor(255, 200, 200, 80),  # Light red
        QColor(200, 255, 200, 80),  # Light green
        QColor(200, 200, 255, 80),  # Light blue
        QColor(255, 255, 200, 80),  # Light yellow
        QColor(255, 200, 255, 80),  # Light magenta
        QColor(200, 255, 255, 80),  # Light cyan
    ]

    def _render_tile(
        self,
        painter: QPainter,
        packed_tile: PackedTile,
        layout: PackedLayout,
        scale: float,
        offset_x: float,
        offset_y: float,
    ) -> None:
        """Render a single tile."""
        tile = packed_tile.tile
        packed_bounds = packed_tile.packed_bounds
        tile_idx = layout.tiles.index(packed_tile)

        # Calculate target rect on page
        target_rect = QRectF(
            offset_x + (packed_bounds.x() - layout.total_bounds.x()) * scale,
            offset_y + (packed_bounds.y() - layout.total_bounds.y()) * scale,
            packed_bounds.width() * scale,
            packed_bounds.height() * scale,
        )

        # Draw tile background with debug color
        bg_color = self._TILE_COLORS[tile_idx % len(self._TILE_COLORS)]
        painter.fillRect(target_rect, bg_color)

        # Draw tile border
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.drawRect(target_rect)

        # Render scene content for this tile
        # IMPORTANT: We can't just render tile.bounds region because tiles may overlap
        # in scene coordinates. We need to hide items not in this tile, render, then restore.
        self._render_tile_filtered(painter, tile, target_rect)

        # TODO: Fix crossing stub rendering - currently broken
        # Render crossing stubs for this tile
        # for crossing in layout.crossings:
        #     self._render_crossing_stub(
        #         painter, crossing, packed_tile, layout, scale, offset_x, offset_y
        #     )

    def _render_tile_filtered(self, painter: QPainter, tile: Tile, target_rect: QRectF) -> None:
        """Render only the items belonging to this tile.

        We temporarily hide scene items not in this tile, render, then restore.
        This handles the case where tiles overlap in scene coordinates.
        """
        from PySide6.QtWidgets import QGraphicsItem

        from satisfactory_planner.ui.items.belt_item import BeltItem
        from satisfactory_planner.ui.items.building_item import BuildingItem
        from satisfactory_planner.ui.items.room_item import RoomItem

        # Collect items to hide (those not in this tile)
        items_to_hide: list[QGraphicsItem] = []

        for item in self._scene.items():
            # Skip child items - they're controlled by their parent
            if item.parentItem() is not None:
                continue

            # Determine if this item belongs to the tile
            should_hide = False

            # BuildingItem has .building.id
            if isinstance(item, BuildingItem):
                item_id = item.building.id
                should_hide = item_id not in tile.building_ids
            # RoomItem has .placement.id
            elif isinstance(item, RoomItem):
                item_id = item.placement.id
                should_hide = item_id not in tile.building_ids
            # BeltItem has .belt.id
            elif isinstance(item, BeltItem):
                belt = item.belt
                # Belt belongs to tile if BOTH endpoints are in the tile
                source_node = _get_containing_node(self._document, belt.source_building_id)
                dest_node = _get_containing_node(self._document, belt.dest_building_id)
                source_in = source_node and source_node in tile.building_ids
                dest_in = dest_node and dest_node in tile.building_ids
                # Hide if neither endpoint is in tile
                should_hide = not source_in and not dest_in
                # Also hide crossing belts (one end in, one end out) - they get stubs
                if source_in != dest_in:
                    should_hide = True

            if should_hide and item.isVisible():
                items_to_hide.append(item)
                item.setVisible(False)

        try:
            # Debug logging
            print(f"DEBUG: Tile bounds (scene coords): {tile.bounds}")
            print(f"DEBUG: Tile building_ids: {tile.building_ids}")
            print(f"DEBUG: Target rect (page coords): {target_rect}")
            print(f"DEBUG: Items hidden: {len(items_to_hide)}")

            # Render directly to painter - let Qt handle resolution scaling
            # This works better for preview (screen res) vs print (high res)
            self._scene.render(painter, target_rect, tile.bounds)

        finally:
            # Restore visibility
            for item in items_to_hide:
                item.setVisible(True)

    def _render_crossing_stub(
        self,
        painter: QPainter,
        crossing: CrossingStub,
        packed_tile: PackedTile,
        layout: PackedLayout,
        scale: float,
        offset_x: float,
        offset_y: float,
    ) -> None:
        """Render a crossing stub (belt exit/entry point)."""
        tile = packed_tile.tile
        tile_idx = layout.tiles.index(packed_tile)

        # Check if this crossing involves this tile
        is_source = crossing.source_tile_index == tile_idx
        is_dest = crossing.dest_tile_index == tile_idx

        if not is_source and not is_dest:
            return

        # Get the port position and tile bounds
        port_pos = crossing.source_port_pos if is_source else crossing.dest_port_pos

        # Find closest point on tile edge
        edge_point = self._closest_edge_point(port_pos, tile.bounds)

        # Transform to page coordinates
        packed_bounds = packed_tile.packed_bounds

        def to_page(p: QPointF) -> QPointF:
            """Transform scene point to page coordinates."""
            # First, get position relative to tile bounds
            rel_x = (p.x() - tile.bounds.x()) / tile.bounds.width()
            rel_y = (p.y() - tile.bounds.y()) / tile.bounds.height()
            # Then map to packed bounds
            packed_x = packed_bounds.x() + rel_x * packed_bounds.width()
            packed_y = packed_bounds.y() + rel_y * packed_bounds.height()
            # Finally scale to page
            return QPointF(
                offset_x + (packed_x - layout.total_bounds.x()) * scale,
                offset_y + (packed_y - layout.total_bounds.y()) * scale,
            )

        page_port = to_page(port_pos)
        page_edge = to_page(edge_point)

        # Draw the stub line (dashed)
        pen = QPen(QColor(0, 0, 0), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(page_port, page_edge)

        # Draw arrow at edge
        painter.setPen(QPen(QColor(0, 0, 0), 2, Qt.PenStyle.SolidLine))
        if is_source:
            # Outgoing arrow at edge
            self._draw_arrow(painter, page_port, page_edge)
        else:
            # Incoming arrow from edge
            self._draw_arrow(painter, page_edge, page_port)

        # Draw label
        label = crossing.item_name or ""
        label = f"{label} #{crossing.crossing_id}" if label else f"#{crossing.crossing_id}"

        font = QFont()
        # Scale font size based on scale factor (roughly 8pt equivalent)
        font.setPixelSize(max(8, int(12 * scale)))
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))

        # Position label near edge point
        label_width = 100 * scale
        label_height = 20 * scale
        label_rect = QRectF(
            page_edge.x() + 5, page_edge.y() - label_height / 2, label_width, label_height
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft, label)

    def _closest_edge_point(self, point: QPointF, rect: QRectF) -> QPointF:
        """Find the closest point on the rectangle edge to the given point."""
        # Clamp point to be inside rect first
        px = max(rect.left(), min(rect.right(), point.x()))
        py = max(rect.top(), min(rect.bottom(), point.y()))

        # Find distances to each edge
        dist_left = abs(px - rect.left())
        dist_right = abs(px - rect.right())
        dist_top = abs(py - rect.top())
        dist_bottom = abs(py - rect.bottom())

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

        if min_dist == dist_left:
            return QPointF(rect.left(), py)
        elif min_dist == dist_right:
            return QPointF(rect.right(), py)
        elif min_dist == dist_top:
            return QPointF(px, rect.top())
        else:
            return QPointF(px, rect.bottom())

    def _draw_arrow(self, painter: QPainter, start: QPointF, end: QPointF, size: float = 8) -> None:
        """Draw an arrow from start to end."""
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)

        if length < 0.001:
            return

        # Normalize
        dx /= length
        dy /= length

        # Arrow head points
        angle = math.pi / 6  # 30 degrees
        ax1 = end.x() - size * (dx * math.cos(angle) - dy * math.sin(angle))
        ay1 = end.y() - size * (dy * math.cos(angle) + dx * math.sin(angle))
        ax2 = end.x() - size * (dx * math.cos(angle) + dy * math.sin(angle))
        ay2 = end.y() - size * (dy * math.cos(angle) - dx * math.sin(angle))

        painter.drawLine(end, QPointF(ax1, ay1))
        painter.drawLine(end, QPointF(ax2, ay2))

    def _do_print(self) -> None:
        """Execute the print."""
        # Create a high-resolution printer for actual printing
        print_printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        # Copy page layout from preview printer
        print_printer.setPageLayout(self._printer.pageLayout())

        # Open native print dialog
        print_dialog = QPrintDialog(print_printer, self)
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            # Render to the high-res printer
            self._render_preview(print_printer)
            self.accept()


# =============================================================================
# Public API
# =============================================================================


def print_scene_packed(
    document: Document,
    scene: QGraphicsScene,
    parent: QWidget | None = None,
    document_title: str = "Factory Blueprint",
) -> None:
    """Open packed print preview dialog.

    This is the new entry point that replaces print_scene().
    It automatically partitions and packs the factory for optimal printing.

    Args:
        document: The factory document (for graph analysis).
        scene: The QGraphicsScene to render.
        parent: Parent widget for the dialog.
        document_title: Title to display on the print.
    """
    dialog = PackedPrintPreviewDialog(document, scene, parent, document_title)
    dialog.exec()
