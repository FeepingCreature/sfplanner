"""Tests for flow solver."""

from satisfactory_planner.core.flow_solver import FlowSolver, WarningType
from satisfactory_planner.core.models import Belt, Building, BuildingType, Document


class TestFlowSolver:
    """Tests for the flow solver."""

    def test_no_warnings_empty_document(self) -> None:
        """Empty document has no warnings."""
        doc = Document()
        solver = FlowSolver(doc)

        warnings = solver.solve()
        assert len(warnings) == 0

    def test_disconnected_belt_missing_source(self) -> None:
        """Detects belt with missing source building."""
        doc = Document()

        # Belt references non-existent source
        belt = Belt(
            id="belt1",
            tier=1,
            source_building_id="nonexistent",
            source_port_index=0,
            dest_building_id="b1",
            dest_port_index=0,
        )
        doc.add_belt(belt)

        # Add destination building
        doc.add_building(Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0))

        solver = FlowSolver(doc)
        warnings = solver.solve()

        assert len(warnings) >= 1
        assert any(w.type == WarningType.DISCONNECTED_BELT for w in warnings)

    def test_disconnected_belt_missing_dest(self) -> None:
        """Detects belt with missing destination building."""
        doc = Document()

        # Add source building
        doc.add_building(Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0))

        # Belt references non-existent destination
        belt = Belt(
            id="belt1",
            tier=1,
            source_building_id="b1",
            source_port_index=0,
            dest_building_id="nonexistent",
            dest_port_index=0,
        )
        doc.add_belt(belt)

        solver = FlowSolver(doc)
        warnings = solver.solve()

        assert len(warnings) >= 1
        assert any(w.type == WarningType.DISCONNECTED_BELT for w in warnings)

    def test_valid_connection_no_warnings(self) -> None:
        """Valid belt connection produces no disconnected warnings."""
        doc = Document()

        b1 = Building(id="b1", building_type=BuildingType.CONSTRUCTOR, x=0, y=0)
        b2 = Building(id="b2", building_type=BuildingType.CONSTRUCTOR, x=100, y=0)
        doc.add_building(b1)
        doc.add_building(b2)

        belt = Belt(
            id="belt1",
            tier=1,
            source_building_id="b1",
            source_port_index=0,
            dest_building_id="b2",
            dest_port_index=0,
        )
        doc.add_belt(belt)

        solver = FlowSolver(doc)
        warnings = solver.solve()

        # Should not have disconnected belt warnings
        assert not any(w.type == WarningType.DISCONNECTED_BELT for w in warnings)
