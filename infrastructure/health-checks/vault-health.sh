#!/bin/bash

# Vault health check script
# This script checks if Vault is healthy and operational

set -e

echo "Checking Vault health..."

# Check if Vault is accessible
if ! vault status > /dev/null 2>&1; then
    echo "Vault is not accessible or not initialized"
    exit 1
fi

# Get Vault status
VAULT_STATUS=$(vault status 2>&1)

# Check if Vault is sealed
if echo "$VAULT_STATUS" | grep -q "Sealed.*true"; then
    echo "Vault is sealed"
    exit 1
fi

# Check if Vault is initialized
if echo "$VAULT_STATUS" | grep -q "Initialized.*false"; then
    echo "Vault is not initialized"
    exit 1
fi

# Verify KV v2 secrets engine is enabled
if ! vault secrets list | grep -q "^secret/"; then
    echo "KV secrets engine not enabled at 'secret' mount point"
    exit 1
fi

echo "Vault is healthy and operational"
exit 0

