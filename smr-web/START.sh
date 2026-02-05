#!/bin/bash
# Quick start script for SMR Web Interface

echo "🚀 Starting SMR Web Interface Server..."
echo ""

# Check if we're in the right directory
if [ ! -f "index.html" ]; then
    echo "❌ Error: index.html not found!"
    echo "   Please run this script from the smr-web directory"
    exit 1
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found!"
    echo "   Please install Python 3"
    exit 1
fi

# Check if services are running
echo "📡 Checking services..."
cd ~/SMR/ai4i-core

if docker compose ps | grep -q "policy-engine.*Up"; then
    echo "✅ Policy Engine: Running"
else
    echo "⚠️  Policy Engine: Not running (may cause errors)"
fi

if docker compose ps | grep -q "api-gateway.*Up"; then
    echo "✅ API Gateway: Running"
else
    echo "⚠️  API Gateway: Not running (may cause errors)"
fi

if docker compose ps | grep -q "smart-router.*Up"; then
    echo "✅ Smart Router: Running"
else
    echo "⚠️  Smart Router: Not running (may cause errors)"
fi

if docker compose ps | grep -q "tts-service.*Up"; then
    echo "✅ TTS Service: Running"
else
    echo "⚠️  TTS Service: Not running (may cause errors)"
fi

echo ""
echo "🌐 Starting HTTP server..."
echo ""

# Go back to smr-web directory and start server
cd ~/SMR/ai4i-core/smr-web
python3 server.py
