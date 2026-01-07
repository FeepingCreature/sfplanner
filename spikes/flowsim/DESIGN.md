# Flow Simulation Design

Extracted from SPEC.md - the flow simulation semantics for the Satisfactory Planner.

## Approach: Linear Programming

We use `scipy.optimize.linprog` to solve factory flow as a linear program:

- **Variables**: Flow rate on each edge (belt/pipe)
- **Equality constraints**: Flow conservation at each node (inputs = outputs)
- **Inequality constraints**: Belt/pipe capacity limits
- **Objective**: Maximize flow to preferred outputs (for priority splitters)

LP handles cycles naturally (it's solving simultaneous equations), respects capacity
constraints, and computes steady-state flows in a single pass.

## Error Categories

### Fatal Errors (Cannot Build Model)

These prevent constructing a valid LP model:

- **Item type mismatch** - Belt connects ports with different item types
- **Merger type conflict** - Merger inputs have different item types
- **Disconnected belt** - Belt missing source or destination building
- **Recipe not set** - Connected production building has no recipe assigned
- **Sourceless cycle** - A loop with no external input (no steady state exists)

Fatal errors are detected during model construction, before solving.

### Warnings (Underflow)

These indicate the factory will run suboptimally:

- **Underflow** - Demand exceeds supply somewhere in the chain

Warnings are computed by backchaining from unsatisfied demands to find the root cause.
Production buildings with unconnected outputs are treated as implicit sinks (we assume
the user wants them running at full speed).

Clicking a warning shows the **causal chain**:
```
Motors 4.3 < 5/min demanded
  └── Rotors 7.1 < 10/min demanded
        └── Iron Ingots: belt at capacity (780/min)
```

### Info (Optimization Hints)

All constraints satisfied, but useful information:

- **Spare capacity** - Splitter output has unused capacity (shown on hover)
- **Belt overcapacity** - Flow would exceed belt tier if unconstrained (see below)

#### Input Node Consumption Verification

Item input nodes (PORT_IN, Miners) can specify min/max expected consumption.
By default, min=max=output_rate, meaning "this input should be fully consumed."
If actual consumption differs, it's flagged as info.

## Belt Overcapacity Detection

Belt overcapacity is special: we want to show where items would back up in-game,
but also what the "ideal" flow would be.

**Algorithm:**

1. **Solve ideal** - Solve LP *without* belt capacity constraints → get desired flows
2. **Detect overcapacity** - Compare ideal flows to belt capacities
3. **Filter upstream** - For each overcapacity belt, walk upstream along the item flow
   chain. If a preceding belt also has overcapacity, suppress the downstream warning.
   Only show the *first* bottleneck (where items actually stack up in-game).

This gives users actionable info: "upgrade THIS belt" rather than flooding them with
every downstream belt that's affected by the same bottleneck.

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

## Algorithm Summary

### Phase 1: Model Construction & Validation

1. Build graph from document (buildings, belts, rooms)
2. Validate item types on all connections → fatal errors if mismatched
3. Check all connected buildings have recipes → fatal error if missing
4. Detect disconnected belts → fatal error
5. Detect sourceless cycles → fatal error

If any fatal errors, stop and report them.

### Phase 2: LP Solve (Ideal Flows)

1. Create flow variable for each edge
2. Add equality constraints: flow conservation at each node
3. Add objective: maximize flow to preferred outputs (for priority splitters)
4. Solve with `scipy.optimize.linprog` (no capacity constraints)
5. Result: ideal flow rates assuming infinite belt capacity

### Phase 3: Overcapacity Detection

1. Compare ideal flows to belt capacities
2. For each overcapacity belt, walk upstream along item flow chain
3. If upstream belt also overcapacity, suppress downstream warning
4. Report only the *first* bottleneck in each chain

### Phase 4: Underflow Detection

1. For each production building, check if inputs meet recipe demands
2. Backchain from unsatisfied demands to find root cause
3. Build causal chain for warning display

### Phase 5: Info Collection

1. Check input nodes for expected consumption vs actual
2. Check splitters for spare capacity on open outputs
3. Compute power estimates (side calculation)
