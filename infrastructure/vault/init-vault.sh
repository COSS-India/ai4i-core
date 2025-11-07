#!/bin/bash

# Vault initialization script
# This script initializes Vault with the KV v2 secrets engine
# It is executed when the Vault container starts

set -e

echo "Initializing Vault..."

# Wait for Vault to be ready
echo "Waiting for Vault to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if vault status > /dev/null 2>&1; then
        echo "Vault is ready!"
        break
    fi
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts: Vault not ready yet, waiting..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "ERROR: Vault did not become ready after $max_attempts attempts"
    exit 1
fi

# Check if KV v2 secrets engine is already enabled at 'secret' mount point
if vault secrets list | grep -q "^secret/"; then
    echo "KV secrets engine already enabled at 'secret' mount point"
else
    echo "Enabling KV v2 secrets engine at 'secret' mount point..."
    vault secrets enable -version=2 -path=secret kv || {
        echo "ERROR: Failed to enable KV v2 secrets engine"
        exit 1
    }
    echo "KV v2 secrets engine enabled successfully"
fi

# Verify the mount point
echo "Verifying KV v2 secrets engine configuration..."
vault secrets list

echo "Vault initialization completed successfully!"

