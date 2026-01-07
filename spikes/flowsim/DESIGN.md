# Flow Simulation Design

Extracted from SPEC.md - the flow simulation semantics for the Satisfactory Planner.

## Core Concepts

### Flow Graph vs Visual Graph

The visual graph (buildings, belts, rooms) is what the user sees and edits. The flow graph is a derived computation model that simulates item flow.

Key differences:
- **Visual**: Buildings have positions, belts have routing curves
- **Flow**: Only rates, connections, and item types matter

### Validation & Warnings

The system continuously validates the factory graph and flags:

1. **Leftover items** - Output not connected or exceeds downstream capacity
2. **Disconnected belts** - Belt missing source or destination  
3. **Resource underflow** - Input demand exceeds supply
4. **Belt overcapacity** - Flow rate exceeds belt tier capacity
5. **Production underflow** - Building can't produce at required rate

### Causal Chain Display

Clicking a warning shows the **causal chain**:
```
Motors 4.3 < 5
  └── Rotors 7.1 < 10
        └── Belt has insufficient iron ingots (at capacity 780/min)
```

## Flow Semantics

### Production Buildings (Smelter, Constructor, Assembler, etc.)

Each building with a recipe is both a **consumer** and **producer**:
- Consumes inputs at recipe rates (scaled by clock speed)
- Produces outputs at recipe rates (scaled by clock speed)

A building can only run at the rate limited by:
1. Minimum input availability (all inputs must be satisfied)
2. Output capacity (can outputs be consumed?)

### Splitters

- 1 input, 3 outputs
- Divides input flow across connected outputs
- **Equal split** (default): Each output gets 1/3 of input
- **Demand-based** (advanced): Outputs get proportional to downstream demand

### Mergers  

- 3 inputs, 1 output
- Combines all input flows into single output
- Total output = sum of all inputs
- No item type mixing allowed (all inputs must be same item)

### Miners

- 0 inputs, 1 output
- Pure source nodes
- Output rate determined by:
  - Miner tier (Mk.1/2/3)
  - Resource node purity (Impure/Normal/Pure)
  - Clock speed

### Ports (Room Boundaries)

- PORT_IN: External input to room (source from room's perspective)
- PORT_OUT: External output from room (sink from room's perspective)

## Belt Capacities

| Tier | Items/min |
|------|-----------|
| Mk.1 | 60        |
| Mk.2 | 120       |
| Mk.3 | 270       |
| Mk.4 | 480       |
| Mk.5 | 780       |
| Mk.6 | 1200      |

## Pipe Capacities (Fluids)

| Tier | m³/min |
|------|--------|
| Mk.1 | 300    |
| Mk.2 | 600    |

## Power Scaling

Power consumption scales with clock speed:
```
actual_power = base_power × (clock_speed ^ 1.6)
```

## Algorithm Sketch

### Forward Propagation (Source → Sink)

1. Identify all sources (miners, PORT_IN, buildings with no inputs)
2. For each source, push flow forward through graph
3. At splitters, divide flow
4. At mergers, accumulate flows
5. At production buildings, consume inputs and produce outputs
6. Track flow rate on each belt

### Constraint Detection

After propagation:
- **Underflow**: Any input port receiving less than recipe demands
- **Overflow**: Any output producing more than can be consumed
- **Belt overcapacity**: Any belt flow > belt tier capacity
- **Disconnected**: Any belt with missing source/dest building
