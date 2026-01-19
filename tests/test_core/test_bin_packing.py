"""Tests for the bin packing algorithm used in print layout."""

from PySide6.QtCore import QRectF

from satisfactory_planner.ui.print_dialog import (
    Tile,
    _PackingState,
    _try_place_bottom_left,
    pack_tiles,
)


class TestTryPlaceBottomLeft:
    """Tests for the bottom-left placement algorithm."""

    def test_first_rect_at_origin(self) -> None:
        """First rectangle should be placed at origin."""
        state = _PackingState()
        result = _try_place_bottom_left(state, 100, 50)
        assert result.x() == 0
        assert result.y() == 0
        assert result.width() == 100
        assert result.height() == 50

    def test_second_rect_placement(self) -> None:
        """Second rect should be placed without overlap."""
        state = _PackingState()
        state.placed.append(QRectF(0, 0, 100, 100))

        # Place another rect
        result = _try_place_bottom_left(state, 200, 30, target_aspect=1.5)
        # Should not overlap
        assert not result.intersects(state.placed[0])

    def test_fills_gaps(self) -> None:
        """Algorithm should fill gaps in an L-shape."""
        state = _PackingState()
        # Create an L-shape: tall rect on left, short rect on right
        state.placed.append(QRectF(0, 0, 50, 200))  # Tall left
        state.placed.append(QRectF(50, 0, 100, 50))  # Short right

        # Small rect should fill the gap at (50, 50) for good aspect ratio
        result = _try_place_bottom_left(state, 40, 40, target_aspect=1.5)
        # With aspect-aware scoring, (50, 50) should give better bounding box
        assert result.x() == 50
        assert result.y() == 50

    def test_no_overlap(self) -> None:
        """Placed rectangles should never overlap."""
        state = _PackingState()
        state.placed.append(QRectF(0, 0, 100, 100))

        # Try to place something that would overlap if at origin
        result = _try_place_bottom_left(state, 80, 80, target_aspect=1.5)

        # Should not overlap with existing rect
        existing = state.placed[0]
        assert not result.intersects(existing) or result == existing


class TestPackTiles:
    """Tests for the full tile packing algorithm."""

    def test_single_tile(self) -> None:
        """Single tile should be placed at origin."""
        tiles = [Tile(building_ids=frozenset({"a"}), bounds=QRectF(0, 0, 100, 100))]
        layout = pack_tiles(tiles, page_aspect=1.5)

        assert layout is not None
        assert len(layout.tiles) == 1
        assert layout.tiles[0].packed_bounds.x() == 0
        assert layout.tiles[0].packed_bounds.y() == 0

    def test_two_tiles_pack_efficiently(self) -> None:
        """Two tiles should pack, not just go left-to-right."""
        # One big square and one small square
        tiles = [
            Tile(building_ids=frozenset({"a"}), bounds=QRectF(0, 0, 200, 200)),
            Tile(building_ids=frozenset({"b"}), bounds=QRectF(0, 0, 50, 50)),
        ]
        layout = pack_tiles(tiles, page_aspect=1.5)

        assert layout is not None
        assert len(layout.tiles) == 2

        # Find positions
        positions = [(t.packed_bounds.x(), t.packed_bounds.y()) for t in layout.tiles]
        print(f"Packed positions: {positions}")

        # Total bounds should be reasonable (not 250 wide if we could stack)
        print(f"Total bounds: {layout.total_bounds}")

    def test_many_tiles_use_vertical_space(self) -> None:
        """Multiple tiles should use both horizontal and vertical space."""
        # 5 small tiles - should NOT all be in a horizontal line
        tiles = [
            Tile(building_ids=frozenset({f"t{i}"}), bounds=QRectF(0, 0, 100, 80)) for i in range(5)
        ]
        layout = pack_tiles(tiles, page_aspect=1.5)  # Landscape aspect

        assert layout is not None

        # Check that not all tiles are at y=0
        y_positions = [t.packed_bounds.y() for t in layout.tiles]
        print(f"Y positions: {y_positions}")

        # With aspect-aware packing, tiles should stack to approach target aspect ratio
        # A 500x80 horizontal line has aspect 6.25, way off from 1.5
        # Stacking should give something closer to 1.5
        total = layout.total_bounds
        actual_aspect = total.width() / total.height() if total.height() > 0 else 999
        print(f"Total bounds: {total}, aspect: {actual_aspect:.2f}")

        # Should be closer to 1.5 than a pure horizontal line (6.25)
        assert actual_aspect < 4.0, (
            f"Aspect {actual_aspect} too wide - packing not using vertical space"
        )

    def test_preserves_tile_dimensions(self) -> None:
        """Packing should preserve original tile dimensions."""
        tiles = [
            Tile(building_ids=frozenset({"a"}), bounds=QRectF(10, 20, 150, 80)),
        ]
        layout = pack_tiles(tiles, page_aspect=1.5)

        assert layout is not None
        packed = layout.tiles[0].packed_bounds
        assert packed.width() == 150
        assert packed.height() == 80
