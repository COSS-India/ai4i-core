#!/bin/bash
#
# Resolve Port 8094 Conflict
# Finds and fixes port allocation issues
#

set -euo pipefail

PORT=8094
CONTAINER_NAME="ai4v-mcp-server"

echo "Resolving Port $PORT Conflict"
echo "=============================="
echo ""

# Check if container exists and is running
echo "1. Checking for existing MCP server container..."
if sudo docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "   ✓ MCP server container is RUNNING"
    echo ""
    echo "   Container status:"
    sudo docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    echo "   The MCP server is already running! You don't need to start it again."
    echo ""
    echo "   To verify it's working:"
    echo "   curl http://localhost:${PORT}/health"
    echo ""
    exit 0
elif sudo docker ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "   ⚠ MCP server container exists but is STOPPED"
    echo ""
    echo "   Removing stopped container..."
    sudo docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
    echo "   ✓ Removed stopped container"
fi

# Check for any container using port 8094
echo ""
echo "2. Checking for any container using port $PORT..."
PORT_USERS=$(sudo docker ps --format "{{.Names}}" --filter "publish=$PORT" 2>/dev/null || true)

if [ -n "$PORT_USERS" ]; then
    echo "   ⚠ Found containers using port $PORT:"
    echo "$PORT_USERS" | while read -r container; do
        echo "   - $container"
        echo "   Stopping and removing $container..."
        sudo docker stop "$container" 2>/dev/null || true
        sudo docker rm -f "$container" 2>/dev/null || true
        echo "   ✓ Removed $container"
    done
else
    echo "   ✓ No containers found using port $PORT"
fi

# Check for stopped containers
echo ""
echo "3. Checking for stopped containers..."
STOPPED=$(sudo docker ps -a --format "{{.Names}}" --filter "name=mcp" 2>/dev/null || true)

if [ -n "$STOPPED" ]; then
    echo "   Found stopped MCP-related containers:"
    echo "$STOPPED" | while read -r container; do
        echo "   - $container"
        echo "   Removing $container..."
        sudo docker rm -f "$container" 2>/dev/null || true
        echo "   ✓ Removed $container"
    done
else
    echo "   ✓ No stopped MCP containers found"
fi

# Final check
echo ""
echo "4. Verifying port $PORT is free..."
if sudo docker ps --format "{{.Ports}}" | grep -q ":$PORT"; then
    echo "   ⚠ Port $PORT is still in use!"
    echo ""
    echo "   Containers using port $PORT:"
    sudo docker ps --format "table {{.Names}}\t{{.Ports}}" | grep "$PORT"
    echo ""
    echo "   Please manually stop these containers:"
    sudo docker ps --format "{{.Names}}" | grep -v "NAMES" | while read -r container; do
        if sudo docker port "$container" 2>/dev/null | grep -q "$PORT"; then
            echo "   sudo docker stop $container"
        fi
    done
    exit 1
else
    echo "   ✓ Port $PORT is now free"
fi

echo ""
echo "=========================================="
echo "Port conflict resolved!"
echo ""
echo "You can now start MCP server with:"
echo "  cd ai4i-core"
echo "  sudo docker compose up -d mcp-server"
echo ""
