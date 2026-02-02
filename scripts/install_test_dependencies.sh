#!/bin/bash
#
# Install dependencies for MCP testing
#

echo "Installing test dependencies..."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

echo "Python version: $(python3 --version)"
echo ""

# Install python-jose
echo "Installing python-jose[cryptography]..."
python3 -m pip install --user python-jose[cryptography] 2>&1 | grep -v "already satisfied" || true

echo ""
echo "✓ Dependencies installed"
echo ""
echo "You can now generate test JWT tokens with:"
echo "  python3 scripts/generate_test_jwt.py"
