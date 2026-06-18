#!/usr/bin/env bash
#
# install-prereqs.sh — install the dev prerequisites (python3.11, node 20+,
# docker + compose v2, git) for the host's package manager.
#
# OS-agnostic by design (plan § 9, § 12): one script that detects apt / brew /
# apk rather than a separate file per OS. Windows contributors run this inside
# WSL2, where it takes the apt path.
#
set -euo pipefail

echo "========================================"
echo " Installing AI4I dev prerequisites"
echo "========================================"

have() { command -v "$1" >/dev/null 2>&1; }

node_major() {
    have node || { echo 0; return; }
    node -v | sed 's/^v//' | cut -d. -f1
}

# ── Refuse native Windows shells — use WSL2 ──────────────────────────────────
case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
        echo "Native Windows shell detected. Run this inside WSL2 (see SETUP_GUIDE.md § Windows)." >&2
        exit 1
        ;;
esac

# ── Detect package manager ───────────────────────────────────────────────────
PKG=""
if have apt-get; then
    PKG="apt"
elif have brew; then
    PKG="brew"
elif have apk; then
    PKG="apk"
else
    cat >&2 <<'EOF'
No supported package manager found (apt-get / brew / apk).
Install these manually, then re-run ./scripts/dev/up:
  - python3.11 (+ venv)
  - node >= 18 (20 recommended) + npm
  - docker + docker compose v2 plugin
  - git
EOF
    exit 1
fi

echo "Using package manager: $PKG"

# ── apt (Debian / Ubuntu / WSL2) ─────────────────────────────────────────────
install_apt() {
    sudo apt-get update
    sudo apt-get install -y wget unzip jq build-essential software-properties-common git

    if ! have python3.11; then
        echo "Installing Python 3.11..."
        sudo add-apt-repository ppa:deadsnakes/ppa -y
        sudo apt-get update
        sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
    fi

    if ! have docker; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com | sudo sh
        sudo usermod -aG docker "$USER"
        echo "NOTE: log out/in for the docker group change to take effect."
    fi

    if ! docker compose version >/dev/null 2>&1; then
        echo "Installing Docker Compose plugin..."
        sudo apt-get install -y docker-compose-plugin
    fi

    if [[ "$(node_major)" -lt 18 ]]; then
        echo "Installing Node.js 20..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
}

# ── brew (macOS) ─────────────────────────────────────────────────────────────
install_brew() {
    brew update
    brew install git jq wget

    if ! have python3.11; then
        echo "Installing Python 3.11..."
        brew install python@3.11
    fi

    if [[ "$(node_major)" -lt 18 ]]; then
        echo "Installing Node.js 20..."
        brew install node@20
    fi

    if ! have docker; then
        echo "Installing Docker Desktop (cask)..."
        brew install --cask docker
        echo "NOTE: launch Docker Desktop once so the daemon and 'docker compose' are available."
    fi
}

# ── apk (Alpine) ─────────────────────────────────────────────────────────────
install_apk() {
    sudo apk update
    sudo apk add git jq wget curl build-base

    if ! have python3.11; then
        echo "Installing Python 3.11..."
        sudo apk add python3 py3-virtualenv python3-dev
    fi

    if [[ "$(node_major)" -lt 18 ]]; then
        echo "Installing Node.js + npm..."
        sudo apk add nodejs npm
    fi

    if ! have docker; then
        echo "Installing Docker + compose..."
        sudo apk add docker docker-cli-compose
        echo "NOTE: enable/start the docker service (e.g. 'sudo service docker start')."
    fi
}

case "$PKG" in
    apt)  install_apt ;;
    brew) install_brew ;;
    apk)  install_apk ;;
esac

echo ""
echo "========================================"
echo " Prerequisite installation complete"
echo "========================================"
echo ""

python3.11 --version || true
node --version || true
npm --version || true
docker --version || true
docker compose version || true
