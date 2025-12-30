#!/bin/bash
 
set -e
 
echo "🔹 Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y
 
echo "🔹 Installing required packages..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release
 
echo "🔹 Adding Docker’s official GPG key..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
 
echo "🔹 Setting up Docker repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
 
echo "🔹 Installing Docker Engine & Docker Compose..."
sudo apt-get update -y
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
 
echo "🔹 Enabling and starting Docker service..."
sudo systemctl enable docker
sudo systemctl start docker
 
echo "🔹 Adding current user to docker group..."
sudo usermod -aG docker $USER
 
echo "🔹 Docker version:"
docker --version
 
echo "🔹 Docker Compose version:"
docker compose version
 
echo "✅ Docker & Docker Compose installation completed."
echo "⚠️  Please log out and log back in (or reboot) to use Docker without sudo."
