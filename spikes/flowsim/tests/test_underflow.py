"""Tests for underflow detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from warnings import detect_underflow

from builder import Belt, Building, Document, build_flow_graph
from models import WarningType
from recipes import BuildingType
from solver import solve_flows


class TestUnderflow:
    """Tests for underflow detection."""

    def test_no_underflow_balanced(self):
        """No warnings when supply meets demand."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min out
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # 30/min in
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_underflow(solved)
        assert len(warnings) == 0

    def test_unconnected_input(self):
        """Warning when input port has no belt."""
        doc = Document(
            buildings={
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # needs 30/min Iron Ingot
                )
            },
            belts={},  # No belts!
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_underflow(solved)
        assert len(warnings) == 1
        assert warnings[0].warning_type == WarningType.RESOURCE_UNDERFLOW
        assert "not connected" in warnings[0].message

    def test_undersupply_warning(self):
        """Warning when supply < demand."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min out
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                    clock_speed=2.0,  # 60/min in demand!
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_underflow(solved)
        assert len(warnings) == 1
        assert warnings[0].warning_type == WarningType.RESOURCE_UNDERFLOW
        assert warnings[0].element_id == "constructor1"

    def test_causal_chain_production(self):
        """Causal chain includes production underflow."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min out
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                    clock_speed=2.0,  # needs 60/min
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_underflow(solved)
        assert len(warnings) == 1

        # Check causal chain
        caused_by = warnings[0].caused_by
        assert len(caused_by) >= 1
        assert caused_by[0].warning_type == WarningType.PRODUCTION_UNDERFLOW
        assert "smelter1" in caused_by[0].message


class TestMultiInputUnderflow:
    """Tests for buildings with multiple inputs."""

    def test_assembler_one_input_missing(self):
        """Assembler with one input missing."""
        # Reinforced Iron Plate needs: Iron Plate (30/min) + Screw (60/min)
        doc = Document(
            buildings={
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # 20/min out
                ),
                "assembler1": Building(
                    id="assembler1",
                    building_type=BuildingType.ASSEMBLER,
                    recipe_id="Reinforced Iron Plate",  # needs 30 plates + 60 screws
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="constructor1",
                    source_port_index=0,
                    dest_building_id="assembler1",
                    dest_port_index=0,  # Iron Plate input
                )
                # No belt for Screw input!
            },
        )
        result = build_flow_graph(doc)
        solved = solve_flows(result.graph)

        warnings = detect_underflow(solved)

        # Should have warnings for both inputs
        # Input 0: undersupplied (20 < 30)
        # Input 1: not connected
        assert len(warnings) >= 1
        types = {w.warning_type for w in warnings}
        assert WarningType.RESOURCE_UNDERFLOW in types
