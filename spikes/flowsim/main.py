#!/usr/bin/env python3
"""Flow simulation spike - entry point."""

from recipes import ITEMS, RECIPES


def main() -> None:
    """Entry point for flow simulation spike."""
    print("Flow Simulation Spike")
    print("=" * 40)

    print(f"\nLoaded {len(ITEMS)} items:")
    for item in ITEMS.values():
        fluid_tag = " (fluid)" if item.is_fluid else ""
        print(f"  - {item.name}{fluid_tag}")

    print(f"\nLoaded {len(RECIPES)} recipes:")
    for recipe in RECIPES.values():
        inputs = ", ".join(f"{i.rate}/min {i.item_id}" for i in recipe.inputs)
        outputs = ", ".join(f"{o.rate}/min {o.item_id}" for o in recipe.outputs)
        print(f"  - {recipe.name} ({recipe.building_type.value})")
        print(f"      {inputs} → {outputs}")

    # Example: scaled recipe
    print("\n" + "=" * 40)
    print("Example: Iron Ingot at 150% clock speed")
    scaled = RECIPES["Iron Ingot"].scaled(1.5)
    print(f"  Input:  {scaled.inputs[0].rate}/min {scaled.inputs[0].item_id}")
    print(f"  Output: {scaled.outputs[0].rate}/min {scaled.outputs[0].item_id}")
    print(f"  Power:  {scaled.power_mw:.1f} MW")


if __name__ == "__main__":
    main()
