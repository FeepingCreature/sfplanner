# Production Limit Detection: Thoughts and Ideas

## The Problem

When a building is producing below its maximum rate, we want to show the user *why*. Currently we report "input underflow" warnings, but this can be misleading:

**Example:** A Smelter feeds a Constructor that feeds a Sink. The Sink belt is undersized (60/min capacity but Constructor wants to output 100/min). The LP correctly reduces Constructor output to 60/min. But because of recipe ratio constraints, the Constructor's *input* is also reduced proportionally. 

Current behavior: We see "Iron Plate: 60 < 100/min demanded" on the Constructor - an input underflow warning. But that's misleading! The real issue is downstream (belt bottleneck), not upstream.

## Why This Happens

The LP solver enforces recipe ratio constraints as equalities:
```
input_flow * output_rate = output_flow * input_rate
```

When the output is constrained (by downstream demand or belt capacity), the LP *must* reduce the input proportionally to maintain the ratio. This is mathematically correct, but makes it look like an input problem when it's really an output problem.

## Idea 1: Dual Variables / Shadow Prices

In LP, every constraint has a "dual variable" (shadow price) that indicates how much the objective would improve if that constraint were relaxed by one unit. A constraint is "binding" (active) if its dual is non-zero.

**The insight:** If we could access dual variables, we could see which constraints are actually limiting each variable:
- If the "output <= downstream_demand" constraint has a non-zero dual → output-limited
- If the "input <= supply" constraint has a non-zero dual → input-limited
- If a belt capacity constraint has non-zero dual → belt bottleneck

**Challenge:** Our pure-Python simplex solver (linprog.py) doesn't currently expose dual variables. We'd need to extend it.

## Idea 2: Constraint Tagging

Tag each constraint with metadata about what it represents:
```python
@dataclass
class TaggedConstraint:
    row: list[float]
    rhs: float
    tag: str  # e.g., "downstream_demand:node123:output0"
```

After solving, check which constraints are tight (LHS ≈ RHS). If the tight constraint is tagged "downstream_demand", it's output-limited.

**Advantage:** Doesn't require LP solver changes, just bookkeeping.

**Challenge:** Need to track constraint-to-row mapping through the solve.

## Idea 3: Perturbation Analysis

After solving, perturb each constraint slightly and re-solve to see which changes affect the variable of interest:
1. Solve normally
2. For a building with reduced flow, try relaxing its output constraint
3. If flow increases → was output-limited
4. Try relaxing its input constraint
5. If flow increases → was input-limited

**Advantage:** Works with any solver as a black box.

**Challenge:** Multiple LP solves = slower. May be acceptable for diagnostics.

## Idea 4: Trace Back from Efficiency

We already compute `_find_limiting_factor()` which looks at duty cycle. Could extend this:

1. For each building below 100% efficiency
2. Check if output flow == downstream demand (output-limited)
3. Check if output flow == belt capacity (belt-limited)  
4. Check if input flow < available supply (input-limited)
5. Only report input underflow if it's actually the binding constraint

**Current gap:** We don't currently track "available supply" vs "consumed supply" separately.

## Idea 5: Two-Pass Comparison (Extended)

We already do a two-pass solve (with/without belt limits) for bottleneck detection. Could extend this:

1. Pass 1: Solve with no constraints → theoretical max for each edge
2. Pass 2: Solve with output constraints only → output-limited flows
3. Pass 3: Solve with input constraints only → input-limited flows
4. Compare to identify which type of constraint is binding

**Challenge:** More LP solves, more complex logic.

## Recommendation

**Start with Idea 4 (Trace Back from Efficiency)** as it requires no LP solver changes:

```python
def _is_output_limited(model, node, outgoing) -> bool:
    """Check if a producer is output-limited rather than input-limited."""
    for i, out_edge in enumerate(outgoing):
        actual_output = flows.get(out_edge.id, 0)
        intended_output = node.outputs[i].rate
        
        if actual_output < intended_output:
            # Output is reduced - why?
            dest_node = graph.nodes[edge.dest_node_id]
            downstream_demand = _get_downstream_demand(dest_node, edge.item_name)
            
            # If actual output matches downstream demand, it's output-limited
            if downstream_demand and abs(actual_output - downstream_demand) < tolerance:
                return True
                
            # If actual output matches belt capacity, it's belt-limited
            if abs(actual_output - edge.capacity) < tolerance:
                return True  # Belt-limited is a form of output-limited
    
    return False
```

**Key insight:** Don't report input underflow if the building is output-limited. The reduced input is a *consequence* of the output limit, not the *cause* of reduced production.

## Future: Dual Variables

If we want more precise diagnostics, extend `linprog.py` to return dual variables:

```python
@dataclass
class LPResult:
    solution: list[float]
    objective: float
    duals: dict[int, float]  # constraint_index → shadow price
```

Then tag constraints and use duals to identify binding constraints directly.

## Open Questions

1. How do we handle chains? (A limits B limits C - which is the "root cause"?)
2. Should we show multiple limiting factors if they're tied?
3. How do we present this to users? (Different warning types? Causal chains?)
4. What about cycles in the constraint graph?