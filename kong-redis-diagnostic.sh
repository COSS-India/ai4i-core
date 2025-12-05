#!/bin/bash

SUDO_PASSWORD="user@123"

echo "=== Kong Redis Connection Diagnostic ==="

 

echo -e "\n1. Checking Redis container status:"

echo "$SUDO_PASSWORD" | sudo -S docker ps --filter "name=redis" --format "{{.Names}}: {{.Status}}"

 

echo -e "\n2. Testing DNS resolution from Kong:"

echo "$SUDO_PASSWORD" | sudo -S docker exec ai4v-kong-gateway getent hosts redis 2>&1 || echo "DNS resolution failed"

 

echo -e "\n3. Testing port connectivity:"

echo "$SUDO_PASSWORD" | sudo -S docker exec ai4v-kong-gateway sh -c "timeout 2 nc -zv redis 6379 2>&1" || echo "Port connection failed"

 

echo -e "\n4. Checking network membership:"

KONG_NET=$(echo "$SUDO_PASSWORD" | sudo -S docker inspect ai4v-kong-gateway --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')

REDIS_NET=$(echo "$SUDO_PASSWORD" | sudo -S docker inspect ai4v-redis --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')

if [ "$KONG_NET" = "$REDIS_NET" ]; then

  echo "   ✓ Both containers on same network"

else

  echo "   ✗ Containers on different networks!"

  echo "   Kong network: $KONG_NET"

  echo "   Redis network: $REDIS_NET"

fi

 

echo -e "\n5. Checking Redis password in Kong:"

echo "$SUDO_PASSWORD" | sudo -S docker exec ai4v-kong-gateway env | grep REDIS_PASSWORD || echo "   ✗ REDIS_PASSWORD not set in Kong"

 

echo -e "\n6. Recent Redis errors in Kong logs:"

echo "$SUDO_PASSWORD" | sudo -S docker compose -f docker-compose.kong.yml logs kong --tail=20 | grep -i "redis.*timeout\|redis.*failed" || echo "   ✓ No recent Redis errors"

 

echo -e "\n=== Diagnostic Complete ==="

