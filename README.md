# Satisfactory Production Planner

A PyQt6-based visual production planner for the game [Satisfactory](https://www.satisfactorygame.com/). Design and optimize your factory layouts with automatic belt routing and crossing minimization.

![Screenshot](screenshot.png)

## AI Notice

This repo was written by Claude Opus 4.5 with [Forge](https://github.com/FeepingCreature/forge). Thanks, Opus!

## Features

- **Manual Recipe Definition**: Define your own recipes with arbitrary inputs/outputs and rates
- **Production Calculation**: Automatically determines building counts from target outputs
- **Physical Network Generation**: Creates splitter/merger networks to connect buildings
- **Layout Optimization**: Joint topology and layout optimization to minimize belt crossings
- **Visual Graph Display**: Interactive view with bezier-curved belts, color-coded by tier

## Installation

```bash
# Clone the repository
git clone https://github.com/FeepingCreature/sfplanner.git
cd sfplanner

# Install with pip
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt
```

## Usage

```bash
# Run the application
satisfactory-planner

# Or run directly
python -m satisfactory_planner.main
```

### Quick Start

1. **Add Recipes**: Click "Add Recipe" to define production recipes with inputs, outputs, and rates (items/min)
2. **Set Targets**: Use the Targets panel to specify what items you want to produce and at what rate
3. **Calculate**: Click "Calculate Requirements" to compute the production graph
4. **Optimize**: Click "Optimize Layout" to search for layouts with fewer belt crossings

### Recipe Persistence

Recipes are automatically saved to `~/.local/share/satisfactory-planner/recipes.json` (Linux) or the appropriate XDG data directory.

## How It Works

### Production Calculation

Given target outputs, the planner works backwards through recipes to determine:
- Which buildings are needed
- How many of each (can be fractional for partial utilization)
- What raw inputs are required

### Network Generation

The abstract production graph is converted to a physical network:
- Each building gets individual nodes (no "3x Smelter" - instead 3 separate smelter nodes)
- Splitters fan out from buildings with multiple consumers (1 in, 3 out)
- Mergers combine inputs from multiple producers (3 in, 1 out)
- Each recipe node has exactly one belt per item type

### Layout Optimization

The optimizer uses a three-phase approach:

1. **Phase 1**: Random search for topologies with minimal crossings and node collisions
2. **Phase 2**: Continue searching but now optimize belt length while maintaining crossing count
3. **Phase 3**: Local search polish with node swapping

Additional techniques:
- **Waypoint insertion**: Long edges get intermediate routing points
- **Layer randomization**: Splitters/mergers can shift into their own columns for better routing

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [Satisfactory](https://www.satisfactorygame.com/) by Coffee Stain Studios
- Built with [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
