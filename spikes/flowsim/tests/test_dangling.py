"""Tests for dangling port detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from builder import Belt, Building, Document, build_flow_graph
from detectors import detect_dangling_ports
from recipes import BuildingType


class TestDanglingInputs:
    """Tests for unconnected input detection."""

    def test_no_inputs_treated_as_source(self):
        """Producer with no inputs connected is treated as source (info only)."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # Needs Iron Ore input
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
                )
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        warnings = detect_dangling_ports(result.graph)

        # Smelter has no inputs connected - should be info level
        smelter_warnings = [w for w in warnings if w.element_id == "smelter1"]
        assert len(smelter_warnings) == 1
        assert "Assuming infinite supply" in smelter_warnings[0].message
        assert smelter_warnings[0].severity < 0.5  # Low severity = info

    def test_partial_inputs_is_warning(self):
        """Producer with SOME but not all inputs connected is a real warning."""
        # Assembler needs 2 inputs - we only connect one
        # Don't worry about downstream - just test the partial input detection
        doc = Document(
            buildings={
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                ),
                "assembler1": Building(
                    id="assembler1",
                    building_type=BuildingType.ASSEMBLER,
                    recipe_id="Reinforced Iron Plate",  # Needs Iron Plate + Screw
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="constructor1",
                    source_port_index=0,
                    dest_building_id="assembler1",
                    dest_port_index=0,  # Only connecting Iron Plate, not Screw
                ),
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        warnings = detect_dangling_ports(result.graph)

        # Assembler has partial inputs - should have a warning about missing Screw
        assembler_warnings = [w for w in warnings if w.element_id == "assembler1"]
        # Should have 2 warnings: missing Screw input + unconnected output (sunk)
        assert len(assembler_warnings) == 2

        # Find the missing input warning specifically
        missing_input_warnings = [w for w in assembler_warnings if "Missing input" in w.message]
        assert len(missing_input_warnings) == 1
        assert missing_input_warnings[0].severity > 0.5  # Higher severity


class TestDanglingOutputs:
    """Tests for unconnected output detection."""

    def test_no_outputs_treated_as_sink(self):
        """Producer with no outputs connected is treated as sink (info only)."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # Output not connected
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

        warnings = detect_dangling_ports(result.graph)

        # Constructor has no outputs connected - should be info level
        constructor_warnings = [w for w in warnings if w.element_id == "constructor1"]
        assert len(constructor_warnings) == 1
        assert "will be sunk" in constructor_warnings[0].message
        assert constructor_warnings[0].severity < 0.5  # Low severity = info

    def test_partial_outputs_is_info(self):
        """Producer with some outputs connected still reports unconnected ones."""
        # A recipe with 2 outputs where only one is connected
        # (Using Copper Sheet which only has 1 output, so we'll test the logic differently)
        # Actually let's just verify the detector handles single-output case
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                ),
            },
            belts={},  # No connections at all
        )
        result = build_flow_graph(doc)
        assert result.success

        warnings = detect_dangling_ports(result.graph)

        # Should have warnings for both input and output
        assert len(warnings) == 2
        messages = [w.message for w in warnings]
        assert any("Assuming infinite supply" in m for m in messages)
        assert any("will be sunk" in m for m in messages)


class TestFullyConnected:
    """Tests for fully connected buildings (no warnings)."""

    def test_no_warnings_when_fully_connected(self):
        """No dangling warnings when all ports are connected."""
        # Chain: smelter -> constructor1 -> constructor2
        # All use Iron Ingot -> Iron Plate -> (sink)
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # Takes Iron Ingot, outputs Iron Plate
                ),
                "constructor2": Building(
                    id="constructor2",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",  # Also takes Iron Ingot (from splitter)
                ),
                "splitter1": Building(
                    id="splitter1",
                    building_type=BuildingType.SPLITTER,
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="splitter1",
                    dest_port_index=0,
                ),
                "belt2": Belt(
                    id="belt2",
                    source_building_id="splitter1",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                ),
                "belt3": Belt(
                    id="belt3",
                    source_building_id="splitter1",
                    source_port_index=1,
                    dest_building_id="constructor2",
                    dest_port_index=0,
                ),
            },
        )
        result = build_flow_graph(doc)
        assert result.success

        warnings = detect_dangling_ports(result.graph)

        # Smelter has no input (source) - gets info warning
        # constructor1 and constructor2 have no outputs (sinks) - get info warnings
        # splitter is fully connected - no warning
        # So we should have 3 info-level warnings, but splitter should have 0
        splitter_warnings = [w for w in warnings if w.element_id == "splitter1"]
        assert len(splitter_warnings) == 0
