#!/bin/bash

set -e

PLUGIN_NAME="virtughan_qgis"
BUILD_DIR="build"
DIST_DIR="dist"
ZIP_NAME="virtughan-qgis-plugin.zip"

echo "Building QGIS plugin package..."

rm -rf "$BUILD_DIR"
rm -rf "$DIST_DIR"
mkdir -p "$BUILD_DIR/$PLUGIN_NAME"
mkdir -p "$DIST_DIR"

echo "Activating uv environment..."
source .venv/bin/activate

echo "Generating metadata.txt from pyproject.toml..."
python generate_metadata.py

echo "Copying plugin files..."
cp -r virtughan_qgis/* "$BUILD_DIR/$PLUGIN_NAME/"

echo "Copying license and documentation..."
cp LICENSE.txt "$BUILD_DIR/$PLUGIN_NAME/"

if [ -d "static" ]; then
    cp -r static "$BUILD_DIR/$PLUGIN_NAME/"
fi

echo "Cleaning build artifacts..."
find "$BUILD_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$BUILD_DIR" -name "*.pyo" -delete 2>/dev/null || true
find "$BUILD_DIR" -name ".DS_Store" -delete 2>/dev/null || true

echo "Creating zip package..."
cd "$BUILD_DIR"
zip -r "../$DIST_DIR/$ZIP_NAME" "$PLUGIN_NAME"
cd ..

echo "Build complete!"
echo "Plugin package: $DIST_DIR/$ZIP_NAME"
echo "Install in QGIS: Plugins > Manage and Install Plugins > Install from ZIP"
