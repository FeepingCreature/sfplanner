"""Tests for flow graph builder."""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from builder import (
    Belt,
    Building,
    Document,
    FatalErrorType,
    build_flow_graph,
)
from models import NodeType
from recipes import BuildingType


class TestBuildFlowGraph:
    """Tests for build_flow_graph function."""

    def test_empty_document(self):
        """Empty document should produce empty graph."""
        doc = Document()
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        assert len(result.graph.nodes) == 0
        assert len(result.graph.edges) == 0

    def test_single_building_no_connections(self):
        """Single building without connections doesn't need recipe."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id=None,  # No recipe, but no connections
                )
            }
        )
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        assert len(result.graph.nodes) == 1

    def test_simple_chain(self):
        """Smelter -> Constructor chain should work."""
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
                    tier=1,
                )
            },
        )
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        assert len(result.graph.nodes) == 2
        assert len(result.graph.edges) == 1

        # Check edge properties
        edge = result.graph.edges["belt1"]
        assert edge.item_id == "Iron Ingot"
        assert edge.capacity == 60  # Tier 1


class TestDisconnectedBelt:
    """Tests for disconnected belt detection."""

    def test_belt_missing_source(self):
        """Belt with no source should be fatal error."""
        doc = Document(
            buildings={
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                )
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id=None,
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)

        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].error_type == FatalErrorType.DISCONNECTED_BELT
        assert result.errors[0].element_id == "belt1"

    def test_belt_missing_dest(self):
        """Belt with no destination should be fatal error."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                )
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id=None,
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)

        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].error_type == FatalErrorType.DISCONNECTED_BELT

    def test_belt_source_not_found(self):
        """Belt referencing non-existent source should be fatal error."""
        doc = Document(
            buildings={
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Iron Plate",
                )
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="nonexistent",
                    source_port_index=0,
                    dest_building_id="constructor1",
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)

        assert not result.success
        assert result.errors[0].error_type == FatalErrorType.DISCONNECTED_BELT


class TestRecipeNotSet:
    """Tests for missing recipe detection."""

    def test_connected_building_no_recipe(self):
        """Connected production building without recipe should be fatal error."""
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
                    recipe_id=None,  # No recipe!
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

        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].error_type == FatalErrorType.RECIPE_NOT_SET
        assert result.errors[0].element_id == "constructor1"

    def test_splitter_no_recipe_ok(self):
        """Splitter doesn't need a recipe."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                ),
                "splitter1": Building(
                    id="splitter1",
                    building_type=BuildingType.SPLITTER,
                    recipe_id=None,  # Splitters don't have recipes
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter1",
                    source_port_index=0,
                    dest_building_id="splitter1",
                    dest_port_index=0,
                )
            },
        )
        result = build_flow_graph(doc)

        assert result.success


class TestItemMismatch:
    """Tests for item type mismatch detection."""

    def test_mismatched_items(self):
        """Belt connecting different item types should be fatal error."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",  # Outputs Iron Ingot
                ),
                "constructor1": Building(
                    id="constructor1",
                    building_type=BuildingType.CONSTRUCTOR,
                    recipe_id="Screw",  # Inputs Iron Rod, not Iron Ingot!
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

        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].error_type == FatalErrorType.ITEM_MISMATCH
        assert "Iron Ingot" in result.errors[0].message
        assert "Iron Rod" in result.errors[0].message


class TestMergerTypeConflict:
    """Tests for merger with mixed item types."""

    def test_merger_mixed_items(self):
        """Merger with different input item types should be fatal error."""
        doc = Document(
            buildings={
                "smelter_iron": Building(
                    id="smelter_iron",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                ),
                "smelter_copper": Building(
                    id="smelter_copper",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Copper Ingot",
                ),
                "merger1": Building(
                    id="merger1",
                    building_type=BuildingType.MERGER,
                ),
            },
            belts={
                "belt1": Belt(
                    id="belt1",
                    source_building_id="smelter_iron",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=0,
                ),
                "belt2": Belt(
                    id="belt2",
                    source_building_id="smelter_copper",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=1,
                ),
            },
        )
        result = build_flow_graph(doc)

        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].error_type == FatalErrorType.MERGER_TYPE_CONFLICT
        assert result.errors[0].element_id == "merger1"

    def test_merger_same_items_ok(self):
        """Merger with same input item types should work."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                ),
                "smelter2": Building(
                    id="smelter2",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
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
                ),
                "belt2": Belt(
                    id="belt2",
                    source_building_id="smelter2",
                    source_port_index=0,
                    dest_building_id="merger1",
                    dest_port_index=1,
                ),
            },
        )
        result = build_flow_graph(doc)

        assert result.success


class TestClockSpeed:
    """Tests for clock speed scaling."""

    def test_clock_speed_affects_ports(self):
        """Clock speed should scale port rates."""
        doc = Document(
            buildings={
                "smelter1": Building(
                    id="smelter1",
                    building_type=BuildingType.SMELTER,
                    recipe_id="Iron Ingot",
                    clock_speed=2.0,  # Double speed
                )
            }
        )
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        node = result.graph.nodes["smelter1"]

        # Iron Ingot recipe: 30/min input, 30/min output
        # At 2x clock: 60/min each
        assert node.inputs[0].rate == 60.0
        assert node.outputs[0].rate == 60.0


class TestNodeTypes:
    """Tests for correct node type assignment."""

    def test_miner_node_type(self):
        """Miners should have MINER node type."""
        doc = Document(
            buildings={
                "miner1": Building(
                    id="miner1",
                    building_type=BuildingType.MINER_MK1,
                )
            }
        )
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        assert result.graph.nodes["miner1"].node_type == NodeType.MINER

    def test_splitter_node_type(self):
        """Splitters should have SPLITTER node type."""
        doc = Document(
            buildings={
                "splitter1": Building(
                    id="splitter1",
                    building_type=BuildingType.SPLITTER,
                )
            }
        )
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        assert result.graph.nodes["splitter1"].node_type == NodeType.SPLITTER

    def test_merger_node_type(self):
        """Mergers should have MERGER node type."""
        doc = Document(
            buildings={
                "merger1": Building(
                    id="merger1",
                    building_type=BuildingType.MERGER,
                )
            }
        )
        result = build_flow_graph(doc)

        assert result.success
        assert result.graph is not None
        assert result.graph.nodes["merger1"].node_type == NodeType.MERGER

    def test_producer_node_type(self):
        """Production buildings should have PRODUCER node type."""
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
        assert result.graph is not None
        assert result.graph.nodes["smelter1"].node_type == NodeType.PRODUCER
