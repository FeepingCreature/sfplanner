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

    def test_splitter_merger_chain_propagation(self) -> None:
        """Item types propagate through chains of splitters/mergers."""
        doc = Document()

        # Layout: Miner -> Splitter -> Splitter -> Smelter x2 -> Merger -> Merger -> Sink
        # This tests that item types flow through multiple logistics nodes

        # Source: Miner producing Iron Ore
        miner = Building(
            id="miner", building_type=BuildingType.MINER, x=0, y=0, recipe_id="iron_ore"
        )
        doc.add_building(miner)

        # Chain of splitters
        splitter1 = Building(id="split1", building_type=BuildingType.SPLITTER, x=100, y=0)
        splitter2 = Building(id="split2", building_type=BuildingType.SPLITTER, x=200, y=0)
        doc.add_building(splitter1)
        doc.add_building(splitter2)

        # Two smelters
        smelter1 = Building(
            id="smelt1", building_type=BuildingType.SMELTER, x=300, y=-50, recipe_id="iron_ingot"
        )
        smelter2 = Building(
            id="smelt2", building_type=BuildingType.SMELTER, x=300, y=50, recipe_id="iron_ingot"
        )
        doc.add_building(smelter1)
        doc.add_building(smelter2)

        # Chain of mergers
        merger1 = Building(id="merge1", building_type=BuildingType.MERGER, x=400, y=0)
        merger2 = Building(id="merge2", building_type=BuildingType.MERGER, x=500, y=0)
        doc.add_building(merger1)
        doc.add_building(merger2)

        # Sink
        sink = Building(
            id="sink", building_type=BuildingType.SINK, x=600, y=0, recipe_id="iron_ingot"
        )
        doc.add_building(sink)

        # Connect: miner -> split1 -> split2 -> smelters -> merge1 -> merge2 -> sink
        doc.add_belt(
            Belt(
                id="b1",
                tier=1,
                source_building_id="miner",
                source_port_index=0,
                dest_building_id="split1",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b2",
                tier=1,
                source_building_id="split1",
                source_port_index=0,
                dest_building_id="split2",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b3",
                tier=1,
                source_building_id="split2",
                source_port_index=0,
                dest_building_id="smelt1",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b4",
                tier=1,
                source_building_id="split2",
                source_port_index=1,
                dest_building_id="smelt2",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b5",
                tier=1,
                source_building_id="smelt1",
                source_port_index=0,
                dest_building_id="merge1",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b6",
                tier=1,
                source_building_id="smelt2",
                source_port_index=0,
                dest_building_id="merge1",
                dest_port_index=1,
            )
        )
        doc.add_belt(
            Belt(
                id="b7",
                tier=1,
                source_building_id="merge1",
                source_port_index=0,
                dest_building_id="merge2",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b8",
                tier=1,
                source_building_id="merge2",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc)
        warnings = solver.solve()

        # Debug: print warnings if test fails
        for w in warnings:
            if "Conflicting constraints" in w.message:
                print(f"WARNING: {w.message}")

        # Should solve successfully - no "conflicting constraints" error
        assert not any("Conflicting constraints" in w.message for w in warnings), (
            f"Got warnings: {[w.message for w in warnings]}"
        )

        # Should have flow rates on belts
        flow_rate = solver.get_flow_rate("b1")
        assert flow_rate is not None
        assert flow_rate > 0
