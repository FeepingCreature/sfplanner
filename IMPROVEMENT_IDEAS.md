# Improvement Ideas

Future features that are currently out of scope but might be interesting later.

## Selection & Manipulation

### Multi-select rotation should rotate the whole selection
Currently, when multiple buildings are selected, rotating (via scroll wheel) only affects individual buildings around their own centers. It would be more intuitive if the entire selection rotated as a group around the selection's center point.

**Implementation approach:**
1. Compute center of bounding box of all selected buildings
2. On rotation, rotate each building's position around that shared center
3. Also rotate each building's individual rotation by the same amount
4. Would need to handle snap-to-grid after rotation completes

---

## Belt Routing

### Smart belt routing around obstacles
Belts currently use simple Dubins paths (circle-line-circle). Could add pathfinding to route around other buildings.

### Belt bundling / bus support
Allow multiple belts to be grouped into a "bus" that routes together as a unit.

---

## Blueprints

### Blueprint versioning
Track versions of blueprints so linked instances can show when they're out of date.

### Blueprint parameters
Allow blueprints to have configurable parameters (e.g., "input item type", "output rate target").

---

## Analysis

### Bottleneck highlighting
Visually highlight belts/buildings that are limiting throughput.

### "What if" mode
Temporarily modify clock speeds or belt tiers to see impact without committing changes.

---

## Import/Export

### Import from Satisfactory save file
Parse actual game saves to recreate factory layouts.

### Export to game blueprint mod format
Generate blueprints compatible with in-game blueprint mods.
