#!/bin/bash
# Build script for packaging the file-tools application

echo "Building file-tools application..."

# Install dependencies
pip install -e .

# Install PyInstaller if not already installed
pip install pyinstaller

# Create the executable using PyInstaller
pyinstaller file-tools.spec

echo "Build completed! The executable is in the dist/ folder."