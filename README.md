# Satisfactory Production Planner

A PyQt6-based GUI tool for planning and optimizing factory layouts in Satisfactory (or similar production games).

## Features

- **Manual Recipe Definition**: Define custom recipes with input/output items and rates
- **Production Calculation**: Automatically calculate required buildings from target outputs
- **Network Generation**: Generate splitter/merger networks to connect buildings
- **Layout Optimization**: Minimize belt crossings and total belt length using randomized search

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
cd satisfactory_planner
python main.py
```

## Architecture

### Models

- **Item**: Simple item types
- **Recipe**: Transformation from inputs to outputs with rates (items/min)
- **ProductionGraph**: Abstract graph of what recipes are needed and how they connect
- **NetworkGraph**: Physical layout including splitters, mergers, and belt connections

### Algorithms

- **Requirements Calculation**: Work backwards from targets to determine building counts
- **Splitter/Merger Generation**: Create physical network with belt logistics
- **Layout Algorithm**: Layered graph layout (Sugiyama-style) with crossing minimization
- **Optimization**: Random restart search over topology and layout jointly

### Belt Tiers

| Tier | Capacity (items/min) |
|------|---------------------|
| 1    | 60                  |
| 2    | 120                 |
| 3    | 180                 |
| 4    | 240                 |
| 5    | 300                 |
| 6    | 360                 |

## How It Works

1. **Define Recipes**: Add your recipes with their input/output rates
2. **Set Targets**: Specify what you want to produce and at what rate
3. **Calculate**: The planner determines how many of each building you need
4. **Optimize**: The layout optimizer tries many random configurations to find one with minimal crossings

The key insight is that the splitter/merger network topology is not unique - there are many ways to connect the same buildings. The optimizer explores this space along with different layouts to find a good solution.
