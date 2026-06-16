#!/usr/bin/env bash

set -euo pipefail

echo "========================================"
echo " Installing AI4I Dependencies"
echo "========================================"

sudo apt-get update

sudo apt-get install -y \
    wget \
    unzip \
    jq \
    build-essential \
    software-properties-common

#
# Python 3.11
#

if ! command -v python3.11 >/dev/null 2>&1; then

    echo "Installing Python 3.11..."

    sudo add-apt-repository ppa:deadsnakes/ppa -y

    sudo apt-get update

    sudo apt-get install -y \
        python3.11 \
        python3.11-venv \
        python3.11-dev

else

    echo "Python 3.11 already installed"

fi

#
# Docker
#

if ! command -v docker >/dev/null 2>&1; then

    echo "Installing Docker..."

    curl -fsSL https://get.docker.com | sudo sh

    sudo usermod -aG docker "$USER"

    echo ""
    echo "Docker installed."
    echo "You may need to log out and log back in for docker group changes."
    echo ""

else

    echo "Docker already installed"

fi

#
# Docker Compose
#

if ! docker compose version >/dev/null 2>&1; then

    echo "Installing Docker Compose..."

    sudo apt-get install -y docker-compose-plugin

else

    echo "Docker Compose already installed"

fi

#
# Node.js 20+
#

NODE_OK=false

if command -v node >/dev/null 2>&1; then

    NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)

    if [ "$NODE_MAJOR" -ge 20 ]; then
        NODE_OK=true
    fi

fi

if [ "$NODE_OK" = false ]; then

    echo "Installing Node.js 20..."

    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -

    sudo apt-get install -y nodejs

else

    echo "Node.js 20+ already installed"

fi

echo ""
echo "========================================"
echo " Dependency Installation Complete"
echo "========================================"
echo ""

python3.11 --version
node --version
npm --version

docker --version

docker compose version