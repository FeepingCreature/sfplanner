#!/bin/bash
# Build release binary for the current platform
# For cross-platform builds, use GitHub Actions (push a v* tag or trigger manually)

set -e

echo "Installing build dependencies..."
pip install nuitka patchelf 2>/dev/null || pip install nuitka

echo "Building with pyside6-deploy..."
pyside6-deploy -c pysidedeploy.spec

echo ""
echo "Build complete! Output:"
ls -la satisfactory-planner* 2>/dev/null || ls -la *.app 2>/dev/null || echo "Check current directory for output"