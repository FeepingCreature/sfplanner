"""Tests for belt overcapacity detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from builder import Belt, Building, Document, build_flow_graph
from detectors import detect_overcapacity
from models import WarningType
from recipes import BuildingType
from solver import solve_flows


class TestOvercapacity:
    """Tests for overcapacity detection."""

    def test_no_overcapacity(self):
        """No warnings when belt has sufficient capacity."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                    tier=1,  # 60/min capacity, flow is 30
                )
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_overcapacity(solved)
        assert len(warnings) == 0

    def test_single_overcapacity(self):
        """Warning when belt exceeds capacity."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=3.0,  # 90/min output
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                    clock_speed=3.0,  # 90/min input
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                    tier=1,  # 60/min capacity, but 90/min flow!
                )
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_overcapacity(solved)
        assert len(warnings) == 1
        assert warnings[0].warning_type == WarningType.BELT_OVERCAPACITY
        assert warnings[0].element_id == "belt1"

    def test_chain_filters_downstream(self):
        """Only first bottleneck in chain is reported."""
        # smelter -> belt1 (overcap) -> splitter -> belt2 (also overcap) -> constructor
        # Only belt1 should be reported
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=3.0,  # 90/min
                ),
                "splitter1": Building(
                    id="splitter1",
                    building_type=BuildingType.SPLITTER,
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                    clock_speed=3.0,  # 90/min
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="splitter1",
                    dest_port_index=0,
                    tier=1,  # 60/min - overcap
                ),
                "belt2": Belt(
                    id="belt2",
                    source_building_id="splitter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                    tier=1,  # 60/min - also overcap, but downstream
                ),
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_overcapacity(solved)

        # Should only report belt1 (the first bottleneck)
        assert len(warnings) == 1
        assert warnings[0].element_id == "belt1"

    def test_parallel_both_reported(self):
        """Parallel overcapacity belts are both reported."""
        # Two smelters, each with their own overcap belt, merging
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=3.0,
                ),
                "smelter2": Building(
                    id="smelter2",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=3.0,
                ),
                "merger1": Building(
                    id="merger1",
                    building_type=BuildingType.MERGER,
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=0,
                    tier=1,  # overcap
                ),
                "belt2": Belt(
                    id="belt2",
                    source_building_id="smelter2",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=1,
                    tier=1,  # also overcap
                ),
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_overcapacity(solved)

        # Both should be reported (parallel, not chained)
        assert len(warnings) == 2
        element_ids = {w.element_id for w in warnings}
        assert element_ids == {"belt1", "belt2"}
