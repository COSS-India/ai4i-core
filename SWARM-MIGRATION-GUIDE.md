# Docker Swarm Migration Guide

## Overview
Migrating from Docker Compose to Docker Swarm provides orchestration without Kubernetes complexity.

## Why Docker Swarm?

### Advantages Over Docker Compose
✅ Orchestration and scheduling  
✅ High availability  
✅ Rolling updates  
✅ Service discovery  
✅ Load balancing  
✅ Health checks & auto-restart  
✅ Secrets management  

### Advantages Over Kubernetes
✅ Simpler configuration  
✅ Lower learning curve  
✅ No additional infrastructure  
✅ Built into Docker  
✅ Easier to debug  
✅ Good for small-medium teams  

## Quick Start

### Initialize Swarm
```bash
# Initialize swarm (run on manager node)
docker swarm init

# Note the join token displayed
# Run this on worker nodes to join:
# docker swarm join --token <token> <manager-ip>:2377
```

### Stack Deploy
```bash
# Deploy entire stack
docker stack deploy -c docker-compose.yml dhruva

# Check services
docker service ls

# View logs
docker service logs dhruva_asr-service

# Scale services
docker service scale dhruva_asr-service=3
```

## Enhanced Docker Compose for Swarm

### Adding Swarm Features

**docker-compose.swarm.yml**
```yaml
version: '3.8'

services:
  api-gateway-service:
    image: dhruva/api-gateway:latest
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        delay: 10s
        order: start-first
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      placement:
        constraints:
          - node.role == manager
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
    networks:
      - dhruva-network
    secrets:
      - jwt_secret
      - postgres_password

  asr-service:
    image: dhruva/asr-service:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
      restart_policy:
        condition: on-failure
      placement:
        constraints:
          - node.labels.workload == compute
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    networks:
      - dhruva-network
    configs:
      - source: asr_config
        target: /app/config.yaml

networks:
  dhruva-network:
    driver: overlay
    attachable: true

secrets:
  jwt_secret:
    external: true
  postgres_password:
    external: true

configs:
  asr_config:
    external: true
    file: ./config/asr.yaml
```

## Setting Up Secrets

```bash
# Create secrets
echo "my-secret-jwt-key" | docker secret create jwt_secret -
echo "my-db-password" | docker secret create postgres_password -

# List secrets
docker secret ls

# Update secret
docker secret rm jwt_secret
echo "new-secret" | docker secret create jwt_secret -
```

## Rolling Updates

### Update Strategy
```yaml
deploy:
  update_config:
    parallelism: 1      # Update 1 replica at a time
    delay: 10s          # Wait 10s between updates
    failure_action: rollback  # Rollback on failure
    monitor: 60s        # Monitor for 60s
    max_failure_ratio: 0.3  # Allow 30% failure
    order: start-first   # Start new before stopping old
```

### Manual Update
```bash
# Update service
docker service update \
  --image dhruva/asr-service:v2 \
  dhruva_asr-service

# Rollback if needed
docker service rollback dhruva_asr-service
```

## Load Balancing

### Built-in Load Balancing
Swarm automatically load balances traffic across replicas:
```yaml
asr-service:
  image: dhruva/asr-service:latest
  deploy:
    replicas: 3  # Automatic load balancing
  ports:
    - "8087:8087"
```

### External Load Balancer
```yaml
asr-service:
  image: dhruva/asr-service:latest
  deploy:
    replicas: 3
    endpoint_mode: vip  # Virtual IP (default)
    # OR
    # endpoint_mode: dnsrr  # DNS round robin
```

## Health Checks

### Swarm Health Checks
```yaml
asr-service:
  image: dhruva/asr-service:latest
  deploy:
    replicas: 3
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8087/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
```

## Placement Constraints

### Node Labels
```bash
# Label nodes
docker node update --label-add workload=compute node1
docker node update --label-add workload=database node2

# Place services on specific nodes
services:
  asr-service:
    deploy:
      placement:
        constraints:
          - node.labels.workload == compute
          - node.platform.os == linux
```

## Multi-Host Networking

### Overlay Networks
```bash
# Create overlay network
docker network create \
  --driver overlay \
  --attachable \
  dhruva-network

# Deploy with network
docker stack deploy -c docker-compose.yml dhruva
```

## Monitoring

### Docker Service Status
```bash
# List all services
docker service ls

# Inspect service
docker service inspect dhruva_asr-service

# Service ps
docker service ps dhruva_asr-service

# Service logs
docker service logs -f dhruva_asr-service
```

### Swarm Metrics
```bash
# Install portainer (web UI)
docker stack deploy -c portainer-stack.yml portainer

# View at http://localhost:9000
```

## Backup & Recovery

### Backup Data
```bash
# Backup volumes
docker run --rm \
  -v dhruva_postgres-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz /data

# Backup swarm state
docker swarm backup.sh
```

### Restore
```bash
# Restore volume
docker run --rm \
  -v dhruva_postgres-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/postgres-backup.tar.gz -C /

# Initialize new swarm
docker swarm init
docker stack deploy -c docker-compose.yml dhruva
```

## Production Deployment

### Multi-Manager Setup
```bash
# On manager 1
docker swarm init

# On manager 2 & 3
docker swarm join-token manager  # Run on manager 1
# Copy token and run on manager 2 & 3

# Verify
docker node ls
```

### High Availability
```yaml
services:
  postgres:
    image: postgres:15-alpine
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
        max_attempts: 3
      placement:
        preferences:
          - spread: node.labels.zone  # Spread across zones
```

## Resource Limits

### CPU & Memory Limits
```yaml
asr-service:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 512M
```

## Comparison: Swarm vs Compose

| Feature | Docker Compose | Docker Swarm |
|---------|--------------|--------------|
| Orchestration | ❌ | ✅ |
| High Availability | ❌ | ✅ |
| Auto-restart | ❌ | ✅ |
| Rolling updates | ❌ | ✅ |
| Load balancing | ❌ | ✅ |
| Secrets management | ❌ | ✅ |
| Multi-host | ❌ | ✅ |
| Resource limits | Basic | Advanced |
| Service discovery | Basic | Automatic |

## Migration Checklist

- [ ] Initialize Docker Swarm
- [ ] Add worker nodes (if multi-host)
- [ ] Create secrets
- [ ] Update docker-compose.yml for Swarm
- [ ] Deploy stack
- [ ] Verify services
- [ ] Test rolling updates
- [ ] Setup monitoring
- [ ] Configure backups
- [ ] Document procedures

## Rollback to Compose

### If Needed
```bash
# Remove stack
docker stack rm dhruva

# Revert to compose
docker-compose up -d
```

## Advantages Summary

**Use Docker Swarm if:**
- ✅ Want orchestration without Kubernetes complexity
- ✅ Team is familiar with Docker
- ✅ Simple multi-host deployment
- ✅ Don't need advanced features (service mesh, etc.)
- ✅ Budget constraints (no cloud K8s costs)
- ✅ Good for up to 100 nodes

**Use Kubernetes if:**
- ✅ Complex requirements
- ✅ Need service mesh (Istio)
- ✅ Advanced scaling (HPA)
- ✅ Cloud-native features
- ✅ Multi-cloud deployment
- ✅ Enterprise requirements

## Next Steps

1. Initialize swarm on dev machine
2. Convert one service to Swarm
3. Test deployment
4. Migrate remaining services
5. Add worker nodes for HA
6. Setup monitoring (Portainer)
7. Document runbooks

