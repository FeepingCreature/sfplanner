# Flow Simulation Spike

Developing the flow simulation engine for Satisfactory Planner.

## Purpose

The flow simulator computes actual item flow rates through a factory graph, detecting:
- Resource underflow (demand > supply)
- Leftover items (production > consumption)
- Belt overcapacity
- Disconnected elements

## Running

```bash
cd spikes/flowsim
python main.py
```

## Files

- `DESIGN.md` - Flow semantics and algorithm design (extracted from SPEC.md)
- `recipes.py` - Recipe and item definitions  
- `models.py` - Flow graph models (FlowNode, FlowEdge, FlowGraph, Warning)
- `main.py` - Entry point and examples
- `solver.py` - Flow simulation solver (TBD)

## Key Concepts

See `DESIGN.md` for full details. Summary:

### Flow Graph vs Visual Graph

The visual graph (buildings, belts) is what the user sees. The flow graph is a derived
computation model - it only cares about rates, connections, and item types.

### Node Types

- **MINER** / **PORT_IN**: Sources (produce items)
- **PORT_OUT** / **SINK**: Sinks (consume items)  
- **PRODUCER**: Production buildings with recipes (consume + produce)
- **SPLITTER**: 1 input -> 3 outputs (divides flow)
- **MERGER**: 3 inputs -> 1 output (combines flow)

### Flow Simulation

Forward propagation from sources to sinks, tracking:
- Actual flow rate on each edge
- Node efficiency (actual vs desired rate)
- Constraint violations (underflow, overcapacity, etc.)
