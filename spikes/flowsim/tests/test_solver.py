"""Tests for LP flow solver."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from builder import Belt, Building, Document, build_flow_graph
from recipes import BuildingType
from solver import solve_flows


class TestSolveFlows:
    """Tests for solve_flows function."""

    def test_empty_graph(self):
        """Empty graph should solve successfully."""
        doc = Document()
        result = build_flow_graph(doc)
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success
        assert len(solved.flows) == 0

    def test_single_producer(self):
        """Single producer with no connections has no flows."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                )
            }
        )
        result = build_flow_graph(doc)
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success
        assert len(solved.flows) == 0

    def test_simple_chain(self):
        """Smelter -> Constructor should have correct flow rates."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min in, 30/min out
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # 30/min in, 20/min out
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                    tier=5,  # High capacity so no constraint
                )
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success

        # Smelter outputs 30/min, Constructor needs 30/min
        assert solved.flows["belt1"] == 30.0

    def test_splitter_demand_driven(self):
        """Splitter should route flow based on downstream demand."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min out
                ),
                "splitter1": Building(
                    id="splitter1",
                    building_type=BuildingType.SPLITTER,
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Rod",  # 15/min in
                ),
                "constructor2": Building(
                    id="constructor2",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Rod",  # 15/min in
                ),
            },
            belts={
                "belt_in": Belt(
                    id="belt_in",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="splitter1",
                    dest_port_index=0,
                ),
                "belt_out1": Belt(
                    id="belt_out1",
                    source_building_id="splitter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                ),
                "belt_out2": Belt(
                    id="belt_out2",
                    source_building_id="splitter1",
                    source_port_index=1,
                    dest_building_id="constructor2",
                    dest_port_index=0,
                ),
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success

        # Input should be 30 (from smelter)
        # Each output should be 15 (both demand 15)
        assert solved.flows["belt_in"] == 30.0
        assert solved.flows["belt_out1"] == 15.0
        assert solved.flows["belt_out2"] == 15.0

    def test_splitter_unequal_demand(self):
        """Splitter routes more to higher-demand output."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=2.0,  # 60/min out
                ),
                "splitter1": Building(
                    id="splitter1",
                    building_type=BuildingType.SPLITTER,
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Rod",  # 15/min in (small demand)
                ),
                "constructor2": Building(
                    id="constructor2",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # 30/min in (larger demand)
                ),
            },
            belts={
                "belt_in": Belt(
                    id="belt_in",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="splitter1",
                    dest_port_index=0,
                ),
                "belt_out1": Belt(
                    id="belt_out1",
                    source_building_id="splitter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                ),
                "belt_out2": Belt(
                    id="belt_out2",
                    source_building_id="splitter1",
                    source_port_index=1,
                    dest_building_id="constructor2",
                    dest_port_index=0,
                ),
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success

        # Input is 60, outputs demand 15 and 30
        # Splitter routes based on demand: 15 to first, 30 to second
        assert solved.flows["belt_in"] == 60.0
        assert solved.flows["belt_out1"] == 15.0
        assert solved.flows["belt_out2"] == 30.0

    def test_merger_combines_flows(self):
        """Merger should combine input flows."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min out
                ),
                "smelter2": Building(
                    id="smelter2",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # 30/min out
                ),
                "merger1": Building(
                    id="merger1",
                    building_type=BuildingType.MERGER,
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # 30/min in (will be undersupplied)
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=0,
                ),
                "belt2": Belt(
                    id="belt2",
                    source_building_id="smelter2",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=1,
                ),
                "belt_out": Belt(
                    id="belt_out",
                    source_building_id="merger1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                ),
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success

        # Two smelters at 30/min each = 60/min merged
        # But constructor only needs 30/min, so output is 30
        # Due to demand-driven model, output matches demand
        assert solved.flows["belt_out"] == 30.0

    def test_clock_speed_scaling(self):
        """Clock speed should affect flow rates."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=2.0,  # 60/min out at 200%
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # 30/min in at 100%
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
        assert result.success

        solved = solve_flows(result.graph)
        assert solved.success

        # Constructor demands 30, that's what flows
        assert solved.flows["belt1"] == 30.0


class TestDutyCycle:
    """Tests for duty cycle / efficiency computation."""

    def test_full_duty_cycle(self):
        """Building at 100% when supply matches demand."""
        from models import LimitingFactor

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
                    recipe_id="Iron Plate",  # 30/min in - exact match
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

        # Find smelter efficiency
        smelter_eff = None
        for eff in solved.efficiencies.values():
            if "smelter" in eff.building_id:
                smelter_eff = eff
                break

        assert smelter_eff is not None
        assert smelter_eff.duty_cycle == 1.0
        assert smelter_eff.limiting_factor == LimitingFactor.NONE

    def test_downstream_limited(self):
        """Building at 50% when downstream only needs half."""
        from models import LimitingFactor

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
                    recipe_id="Iron Rod",  # 15/min in - only needs half
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

        # Find smelter efficiency
        smelter_eff = None
        for eff in solved.efficiencies.values():
            if "smelter" in eff.building_id:
                smelter_eff = eff
                break

        assert smelter_eff is not None
        assert smelter_eff.duty_cycle == 0.5
        assert smelter_eff.limiting_factor == LimitingFactor.DOWNSTREAM
        assert "15" in smelter_eff.limiting_details  # Shows actual consumption

    def test_input_starved(self):
        """Building at 50% when upstream can only provide half."""
        from models import LimitingFactor

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
                    clock_speed=2.0,  # 60/min in - needs more than smelter provides
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

        # Find constructor efficiency
        constructor_eff = None
        for eff in solved.efficiencies.values():
            if "constructor" in eff.building_id:
                constructor_eff = eff
                break

        assert constructor_eff is not None
        assert constructor_eff.duty_cycle == 0.5
        assert constructor_eff.limiting_factor == LimitingFactor.INPUT_STARVED

    def test_duty_cycle_chains(self):
        """Duty cycle propagates through chain."""
        from models import LimitingFactor

        # Smelter(30) -> Constructor(15) -> Assembler(needs Constructor output)
        # Constructor only needs 15, so Smelter is at 50%
        # Assembler gets whatever Constructor outputs
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
                    recipe_id="Iron Rod",  # 15/min in, 15/min out
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

        # Smelter at 50% (downstream limited)
        smelter_eff = None
        constructor_eff = None
        for eff in solved.efficiencies.values():
            if "smelter" in eff.building_id:
                smelter_eff = eff
            if "constructor" in eff.building_id:
                constructor_eff = eff

        assert smelter_eff is not None
        assert smelter_eff.duty_cycle == 0.5
        assert smelter_eff.limiting_factor == LimitingFactor.DOWNSTREAM

        # Constructor at 100% (getting exactly what it needs)
        assert constructor_eff is not None
        assert constructor_eff.duty_cycle == 1.0
        assert constructor_eff.limiting_factor == LimitingFactor.NONE
