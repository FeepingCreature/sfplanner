# Flow Simulation Spike

Developing the flow simulation engine for Satisfactory Planner.

## Purpose

The flow simulator computes actual item flow rates through a factory graph, detecting:
- Resource underflow (demand > supply)
- Leftover items (production > consumption)
- Belt overcapacity
- Disconnected elements

## Key Semantics

Unlike the visual graph, the flow graph has specific semantics:

1. **Every node has a defined item type** - A node carries exactly one item type
2. **Belts are edges, not nodes** - Belts connect production to consumption
3. **Splitters/Mergers have special flow rules**:
   - Splitter: Divides flow equally (or by demand) across outputs
   - Merger: Combines flows from all inputs
4. **Production buildings are sources/sinks** based on recipe
5. **Rooms/Ports act as flow boundaries**

## Running

```bash
python main.py
```

## Files

- `recipes.py` - Recipe and item definitions
- `flow_graph.py` - Flow graph construction and analysis (TBD)
- `main.py` - Entry point and examples
