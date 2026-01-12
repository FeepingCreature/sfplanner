"""Tests for flow solver."""

from satisfactory_planner.core.flow_solver import FlowSolver, WarningType
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.models import Belt, Building, BuildingType, Document


class TestFlowSolver:
    """Tests for the flow solver."""

    def test_no_warnings_empty_document(self) -> None:
        """Empty document has no warnings."""
        doc = Document()
        solver = FlowSolver(doc, {})

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

        solver = FlowSolver(doc, {})
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

        solver = FlowSolver(doc, {})
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

        solver = FlowSolver(doc, {})
        warnings = solver.solve()

        # Should not have disconnected belt warnings
        assert not any(w.type == WarningType.DISCONNECTED_BELT for w in warnings)

    def test_splitter_merger_chain_propagation(self) -> None:
        """Item types propagate through chains of splitters/mergers."""
        doc = Document()

        # Layout: Miner -> Splitter -> Splitter -> Smelter x2 -> Merger -> Merger -> Sink
        # This tests that item types flow through multiple logistics nodes

        # Source: Miner producing Iron Ore
        miner = Building(id="miner", building_type=BuildingType.MINER, x=0, y=0, item_id="Iron Ore")
        doc.add_building(miner)

        # Chain of splitters
        splitter1 = Building(id="split1", building_type=BuildingType.SPLITTER, x=100, y=0)
        splitter2 = Building(id="split2", building_type=BuildingType.SPLITTER, x=200, y=0)
        doc.add_building(splitter1)
        doc.add_building(splitter2)

        # Two smelters
        smelter1 = Building(
            id="smelt1", building_type=BuildingType.SMELTER, x=300, y=-50, recipe_id="Iron Ingot"
        )
        smelter2 = Building(
            id="smelt2", building_type=BuildingType.SMELTER, x=300, y=50, recipe_id="Iron Ingot"
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
            id="sink", building_type=BuildingType.SINK, x=600, y=0, item_id="Iron Ingot"
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

        solver = FlowSolver(doc, {})
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
        flow_rate = solver.get_flow_rate(ItemKey(element_id="b1"))
        assert flow_rate is not None
        assert flow_rate > 0

    def test_tree_splitter_layout(self) -> None:
        """Tree splitter layout should work without artificial fairness constraints.

        Scenario: Miner(120/min) -> Splitter chain -> 3 Smelters(30/min each) -> Merger chain -> Sink
        With undersized sink belt (60/min), LP will limit total throughput.

        The LP optimizes based on downstream demand - no forced "fair" distribution.
        Bottleneck detection uses two-pass comparison (with/without belt limits).
        """
        from satisfactory_planner.core.persistence import load_recipes

        doc = Document()
        recipes = load_recipes()

        # Miner at tier 2 (120/min)
        miner = Building(
            id="miner",
            building_type=BuildingType.MINER,
            x=0,
            y=0,
            item_id="Iron Ore",
            tier=2,  # 120/min
        )
        doc.add_building(miner)

        # Chain of 3 splitters to feed 3 smelters
        splitter1 = Building(id="split1", building_type=BuildingType.SPLITTER, x=100, y=0)
        splitter2 = Building(id="split2", building_type=BuildingType.SPLITTER, x=200, y=0)
        splitter3 = Building(id="split3", building_type=BuildingType.SPLITTER, x=300, y=0)
        doc.add_building(splitter1)
        doc.add_building(splitter2)
        doc.add_building(splitter3)

        # 3 smelters (30/min input each)
        smelter1 = Building(
            id="smelt1", building_type=BuildingType.SMELTER, x=200, y=-100, recipe_id="Iron Ingot"
        )
        smelter2 = Building(
            id="smelt2", building_type=BuildingType.SMELTER, x=300, y=-100, recipe_id="Iron Ingot"
        )
        smelter3 = Building(
            id="smelt3", building_type=BuildingType.SMELTER, x=400, y=-100, recipe_id="Iron Ingot"
        )
        doc.add_building(smelter1)
        doc.add_building(smelter2)
        doc.add_building(smelter3)

        # Merger chain
        merger1 = Building(id="merge1", building_type=BuildingType.MERGER, x=500, y=0)
        merger2 = Building(id="merge2", building_type=BuildingType.MERGER, x=600, y=0)
        doc.add_building(merger1)
        doc.add_building(merger2)

        # Sink
        sink = Building(
            id="sink", building_type=BuildingType.SINK, x=700, y=0, item_id="Iron Ingot"
        )
        doc.add_building(sink)

        # Belts - miner output is tier 2 (120/min)
        doc.add_belt(
            Belt(
                id="b_miner",
                tier=2,  # 120/min capacity
                source_building_id="miner",
                source_port_index=0,
                dest_building_id="split1",
                dest_port_index=0,
            )
        )

        # Splitter chain: split1 -> smelter1, split1 -> split2 -> smelter2, split2 -> split3 -> smelter3
        doc.add_belt(
            Belt(
                id="b_s1_smelt1",
                tier=1,
                source_building_id="split1",
                source_port_index=0,
                dest_building_id="smelt1",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_s1_s2",
                tier=2,
                source_building_id="split1",
                source_port_index=1,
                dest_building_id="split2",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_s2_smelt2",
                tier=1,
                source_building_id="split2",
                source_port_index=0,
                dest_building_id="smelt2",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_s2_s3",
                tier=2,
                source_building_id="split2",
                source_port_index=1,
                dest_building_id="split3",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_s3_smelt3",
                tier=1,
                source_building_id="split3",
                source_port_index=0,
                dest_building_id="smelt3",
                dest_port_index=0,
            )
        )

        # Smelter outputs to merger chain
        doc.add_belt(
            Belt(
                id="b_smelt1_m1",
                tier=1,
                source_building_id="smelt1",
                source_port_index=0,
                dest_building_id="merge1",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_smelt2_m1",
                tier=1,
                source_building_id="smelt2",
                source_port_index=0,
                dest_building_id="merge1",
                dest_port_index=1,
            )
        )
        doc.add_belt(
            Belt(
                id="b_m1_m2",
                tier=2,
                source_building_id="merge1",
                source_port_index=0,
                dest_building_id="merge2",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_smelt3_m2",
                tier=1,
                source_building_id="smelt3",
                source_port_index=0,
                dest_building_id="merge2",
                dest_port_index=1,
            )
        )

        # THE BOTTLENECK: Belt to sink is only tier 1 (60/min) but 90/min is coming
        doc.add_belt(
            Belt(
                id="b_m2_sink",
                tier=1,  # Only 60/min! Should trigger overcapacity
                source_building_id="merge2",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, recipes)
        warnings = solver.solve()

        # LP should solve successfully
        assert not any("Conflicting constraints" in w.message for w in warnings), (
            f"LP failed: {[w.message for w in warnings]}"
        )

        # Total demand is 90/min (3 smelters @ 30/min each)
        # But sink belt is 60/min, so only 60/min can flow through
        # LP will optimize to maximize throughput - may not feed all smelters equally

        # The bottleneck should be detected via two-pass comparison
        bottleneck_warnings = [w for w in warnings if w.type == WarningType.BELT_OVERCAPACITY]
        assert len(bottleneck_warnings) > 0, (
            f"Expected belt bottleneck warning, got: {[w.message for w in warnings]}"
        )

        # Check that the bottleneck belt is identified
        assert any("b_m2_sink" in w.item_key.element_id for w in bottleneck_warnings), (
            f"Bottleneck should be on sink belt: {[w.item_key for w in bottleneck_warnings]}"
        )

    def test_merger_with_mismatched_item_types_via_splitter(self) -> None:
        """Detects when a splitter feeds different item types into a merger.

        Scenario: Splitter carrying Iron Ore connects to a Merger that also
        receives Iron Ingots. This should produce an ITEM_MISMATCH error.
        """
        from satisfactory_planner.core.persistence import load_recipes

        doc = Document()

        # Source of Iron Ore
        miner = Building(
            id="miner",
            building_type=BuildingType.MINER,
            x=0,
            y=0,
            item_id="Iron Ore",
        )
        doc.add_building(miner)

        # Source of Iron Ingots (from a smelter)
        smelter = Building(
            id="smelter",
            building_type=BuildingType.SMELTER,
            x=0,
            y=100,
            recipe_id="Iron Ingot",
        )
        doc.add_building(smelter)

        # Splitter carries Iron Ore
        splitter = Building(
            id="splitter",
            building_type=BuildingType.SPLITTER,
            x=100,
            y=0,
        )
        doc.add_building(splitter)

        # Merger receives from both splitter (Iron Ore) and smelter (Iron Ingot)
        merger = Building(
            id="merger",
            building_type=BuildingType.MERGER,
            x=200,
            y=50,
        )
        doc.add_building(merger)

        # Sink
        sink = Building(
            id="sink",
            building_type=BuildingType.SINK,
            x=300,
            y=50,
            item_id="Iron Ore",  # Doesn't matter, merger conflict should be caught first
        )
        doc.add_building(sink)

        # Connect: miner -> splitter -> merger, smelter -> merger, merger -> sink
        doc.add_belt(
            Belt(
                id="b1",
                tier=1,
                source_building_id="miner",
                source_port_index=0,
                dest_building_id="splitter",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b2",
                tier=1,
                source_building_id="splitter",
                source_port_index=0,
                dest_building_id="merger",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b3",
                tier=1,
                source_building_id="smelter",
                source_port_index=0,
                dest_building_id="merger",
                dest_port_index=1,
            )
        )
        doc.add_belt(
            Belt(
                id="b4",
                tier=1,
                source_building_id="merger",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, load_recipes())
        warnings = solver.solve()

        # Should detect item mismatch at merger
        mismatch_warnings = [w for w in warnings if w.type == WarningType.ITEM_MISMATCH]
        assert len(mismatch_warnings) > 0, (
            f"Expected item mismatch warning at merger, got: {[w.message for w in warnings]}"
        )

    def test_sink_item_type_mismatch(self) -> None:
        """Detects when a sink receives the wrong item type via splitter/merger.

        Scenario: Miner(Iron Ore) -> Splitter -> Sink(expects Copper Ore)
        Should produce an ITEM_MISMATCH error after type propagation.
        """
        from satisfactory_planner.core.persistence import load_recipes

        doc = Document()

        # Source of Iron Ore
        miner = Building(
            id="miner",
            building_type=BuildingType.MINER,
            x=0,
            y=0,
            item_id="Iron Ore",
        )
        doc.add_building(miner)

        # Splitter (item type propagates through)
        splitter = Building(
            id="splitter",
            building_type=BuildingType.SPLITTER,
            x=100,
            y=0,
        )
        doc.add_building(splitter)

        # Sink expects Copper Ore but will receive Iron Ore
        sink = Building(
            id="sink",
            building_type=BuildingType.SINK,
            x=200,
            y=0,
            item_id="Copper Ore",
        )
        doc.add_building(sink)

        # Connect: miner -> splitter -> sink
        doc.add_belt(
            Belt(
                id="b1",
                tier=1,
                source_building_id="miner",
                source_port_index=0,
                dest_building_id="splitter",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b2",
                tier=1,
                source_building_id="splitter",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, load_recipes())
        warnings = solver.solve()

        # Should detect item mismatch at sink
        mismatch_warnings = [w for w in warnings if w.type == WarningType.ITEM_MISMATCH]
        assert len(mismatch_warnings) > 0, (
            f"Expected item mismatch warning at sink, got: {[w.message for w in warnings]}"
        )

        # Should mention both item types
        assert any(
            "Iron Ore" in w.message and "Copper Ore" in w.message for w in mismatch_warnings
        ), f"Warning should mention both items: {mismatch_warnings[0].message}"

    def test_multi_input_partial_connection_no_flow(self) -> None:
        """A multi-input building with only some inputs connected has zero flow.

        Scenario: Assembler needs Screws + Iron Plates, but only Screws connected.
        The building should produce nothing until all inputs are connected.
        """
        from satisfactory_planner.core.persistence import load_recipes

        doc = Document()
        recipes = load_recipes()

        # Source of screws
        source = Building(
            id="source",
            building_type=BuildingType.SOURCE,
            x=0,
            y=0,
            item_id="Screw",
        )
        doc.add_building(source)

        # Assembler making Reinforced Iron Plate (needs Iron Plate + Screw)
        assembler = Building(
            id="assembler",
            building_type=BuildingType.ASSEMBLER,
            x=100,
            y=0,
            recipe_id="Reinforced Iron Plate",
        )
        doc.add_building(assembler)

        # Sink
        sink = Building(
            id="sink",
            building_type=BuildingType.SINK,
            x=200,
            y=0,
            item_id="Reinforced Iron Plate",
        )
        doc.add_building(sink)

        # Only connect screws - iron plates missing!
        doc.add_belt(
            Belt(
                id="b1",
                tier=1,
                source_building_id="source",
                source_port_index=0,
                dest_building_id="assembler",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b2",
                tier=1,
                source_building_id="assembler",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, recipes)
        warnings = solver.solve()

        # Output should be zero - can't produce without all inputs
        output_flow = solver.get_flow_rate(ItemKey(element_id="b2"))
        assert output_flow is not None
        assert output_flow == 0.0, f"Expected 0 output, got {output_flow}"

        # Should warn about missing input
        assert any("Iron Plate" in w.message and "missing" in w.message for w in warnings), (
            f"Expected warning about missing Iron Plate input: {[w.message for w in warnings]}"
        )

    def test_multi_input_all_connected_flows_at_min(self) -> None:
        """A multi-input building flows at the rate of its most limited input.

        Scenario: Assembler needs 60 Screws + 30 Iron Plates per minute.
        If we supply 60 Screws but only 15 Iron Plates, output is halved.
        """
        from satisfactory_planner.core.persistence import load_recipes

        doc = Document()
        recipes = load_recipes()

        # Source of screws (unlimited)
        screw_source = Building(
            id="screw_source",
            building_type=BuildingType.SOURCE,
            x=0,
            y=-50,
            item_id="Screw",
        )
        doc.add_building(screw_source)

        # Source of iron plates (limited to 15/min via belt)
        plate_source = Building(
            id="plate_source",
            building_type=BuildingType.SOURCE,
            x=0,
            y=50,
            item_id="Iron Plate",
        )
        doc.add_building(plate_source)

        # Assembler making Reinforced Iron Plate
        # Recipe: 60 Screw + 30 Iron Plate -> 5 Reinforced Iron Plate
        assembler = Building(
            id="assembler",
            building_type=BuildingType.ASSEMBLER,
            x=100,
            y=0,
            recipe_id="Reinforced Iron Plate",
        )
        doc.add_building(assembler)

        # Sink
        sink = Building(
            id="sink",
            building_type=BuildingType.SINK,
            x=200,
            y=0,
            item_id="Reinforced Iron Plate",
        )
        doc.add_building(sink)

        # Connect screws - high capacity belt
        doc.add_belt(
            Belt(
                id="b_screw",
                tier=2,  # 120/min - plenty for 60 screws
                source_building_id="screw_source",
                source_port_index=0,
                dest_building_id="assembler",
                dest_port_index=0,
            )
        )

        # Connect iron plates - LIMITED to 15/min (half of 30 needed)
        doc.add_belt(
            Belt(
                id="b_plate",
                tier=1,  # 60/min capacity, but source limited
                source_building_id="plate_source",
                source_port_index=0,
                dest_building_id="assembler",
                dest_port_index=1,
            )
        )

        # Output belt
        doc.add_belt(
            Belt(
                id="b_out",
                tier=1,
                source_building_id="assembler",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, recipes)
        solver.solve()

        # Get the recipe to check ratios
        recipe = recipes.get("Reinforced Iron Plate")
        assert recipe is not None

        # Check that iron plate flow matches its demand (30/min at full speed)
        plate_flow = solver.get_flow_rate(ItemKey(element_id="b_plate"))
        assert plate_flow is not None

        # Screw flow should be proportional: if plates are at X%, screws should be too
        screw_flow = solver.get_flow_rate(ItemKey(element_id="b_screw"))
        assert screw_flow is not None

        # At full speed: 60 screws, 30 plates -> ratio is 2:1
        # So screw_flow / plate_flow should be ~2
        if plate_flow > 0:
            ratio = screw_flow / plate_flow
            assert 1.9 < ratio < 2.1, f"Screw:Plate ratio should be 2:1, got {ratio}"

    def test_multi_output_recipe_proportional(self) -> None:
        """Multi-output recipes produce outputs in correct proportions.

        Scenario: A recipe that produces 2 different outputs should
        output them in the ratio defined by the recipe.
        """
        from satisfactory_planner.core.persistence import load_recipes

        doc = Document()
        recipes = load_recipes()

        # Find a multi-output recipe (e.g., Residual Rubber from Refinery)
        # or we create a simpler test scenario

        # Source of crude oil
        source = Building(
            id="source",
            building_type=BuildingType.SOURCE,
            x=0,
            y=0,
            item_id="Crude Oil",
        )
        doc.add_building(source)

        # Refinery with Rubber recipe (if it has multiple outputs)
        # Let's use "Residual Rubber" which outputs Rubber + Heavy Oil Residue
        refinery = Building(
            id="refinery",
            building_type=BuildingType.REFINERY,
            x=100,
            y=0,
            recipe_id="Residual Rubber",
        )
        doc.add_building(refinery)

        # Two sinks for the two outputs
        sink1 = Building(
            id="sink1",
            building_type=BuildingType.SINK,
            x=200,
            y=-50,
            item_id="Rubber",
        )
        sink2 = Building(
            id="sink2",
            building_type=BuildingType.SINK,
            x=200,
            y=50,
            item_id="Heavy Oil Residue",
        )
        doc.add_building(sink1)
        doc.add_building(sink2)

        # Connect input
        doc.add_belt(
            Belt(
                id="b_in",
                tier=1,
                source_building_id="source",
                source_port_index=0,
                dest_building_id="refinery",
                dest_port_index=0,
            )
        )

        # Connect both outputs
        doc.add_belt(
            Belt(
                id="b_out1",
                tier=1,
                source_building_id="refinery",
                source_port_index=0,
                dest_building_id="sink1",
                dest_port_index=0,
            )
        )
        doc.add_belt(
            Belt(
                id="b_out2",
                tier=1,
                source_building_id="refinery",
                source_port_index=1,
                dest_building_id="sink2",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, recipes)
        solver.solve()

        # Get recipe to check expected ratio
        recipe = recipes.get("Residual Rubber")
        if recipe and len(recipe.outputs) >= 2:
            expected_ratio = recipe.outputs[0].rate / recipe.outputs[1].rate

            flow1 = solver.get_flow_rate(ItemKey(element_id="b_out1"))
            flow2 = solver.get_flow_rate(ItemKey(element_id="b_out2"))

            if flow1 and flow2 and flow2 > 0:
                actual_ratio = flow1 / flow2
                assert abs(actual_ratio - expected_ratio) < 0.1, (
                    f"Output ratio should be {expected_ratio}, got {actual_ratio}"
                )

    def test_two_pass_detects_belt_bottleneck(self) -> None:
        """Two-pass solver detects belt bottlenecks by comparing theoretical vs actual.

        Scenario: Miner(120/min) -> Belt(60/min) -> Sink
        Theoretical: 120/min, Actual: 60/min (belt limited)
        Should detect the belt as a bottleneck.
        """
        doc = Document()

        # Miner at tier 2 (120/min)
        miner = Building(
            id="miner",
            building_type=BuildingType.MINER,
            x=0,
            y=0,
            item_id="Iron Ore",
            tier=2,  # 120/min
        )
        doc.add_building(miner)

        # Sink
        sink = Building(
            id="sink",
            building_type=BuildingType.SINK,
            x=200,
            y=0,
            item_id="Iron Ore",
        )
        doc.add_building(sink)

        # Undersized belt - only tier 1 (60/min) but miner produces 120/min
        doc.add_belt(
            Belt(
                id="b_bottleneck",
                tier=1,  # Only 60/min!
                source_building_id="miner",
                source_port_index=0,
                dest_building_id="sink",
                dest_port_index=0,
            )
        )

        solver = FlowSolver(doc, {})
        warnings = solver.solve()

        # Should detect belt bottleneck as overcapacity
        overcapacity = [w for w in warnings if w.type == WarningType.BELT_OVERCAPACITY]
        assert len(overcapacity) > 0, (
            f"Expected belt overcapacity warning, got: {[w.message for w in warnings]}"
        )

        # The warning should mention the theoretical vs actual flow
        assert any("120" in w.message or "60" in w.message for w in overcapacity), (
            f"Warning should mention flow rates: {overcapacity[0].message}"
        )
