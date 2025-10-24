# Docker Management Scripts

This directory contains comprehensive scripts for managing Docker containers in the microservices architecture.

## Scripts Overview

### 1. `docker-manager.sh` - Full-Featured Manager
The main script with comprehensive Docker management capabilities.

### 2. `docker-quick.sh` - Quick Commands
Simplified interface for common operations.

### 3. `restart-service.sh` - Legacy Script
Original restart script (still functional).

## Quick Start

### Using Quick Commands (Recommended for daily use)

```bash
# Start everything
./scripts/docker-quick.sh up

# Start only microservices for development
./scripts/docker-quick.sh dev

# Update specific service
./scripts/docker-quick.sh nmt

# Check status
./scripts/docker-quick.sh status

# Show logs
./scripts/docker-quick.sh logs
```

### Using Full Manager (Advanced operations)

```bash
# Start all services with smart rebuild detection
./scripts/docker-manager.sh start all

# Force rebuild specific services
./scripts/docker-manager.sh rebuild api-gateway-service nmt-service --force-rebuild

# Update all microservices in parallel
./scripts/docker-manager.sh update microservices --parallel

# Check health of specific services
./scripts/docker-manager.sh health nmt-service api-gateway-service
```

## Common Workflows

### 1. Development Workflow
```bash
# Start development environment
./scripts/docker-quick.sh dev

# Make code changes, then update specific service
./scripts/docker-quick.sh nmt

# Check logs
./scripts/docker-quick.sh logs
```

### 2. Full Environment Management
```bash
# Start everything
./scripts/docker-quick.sh up

# Update all services after code changes
./scripts/docker-quick.sh update

# Check status
./scripts/docker-quick.sh status
```

### 3. Service-Specific Updates
```bash
# Update NMT service after code changes
./scripts/docker-quick.sh nmt

# Update API Gateway
./scripts/docker-quick.sh gateway

# Update all microservices
./scripts/docker-quick.sh all
```

## Advanced Features

### Smart Rebuild Detection
The scripts automatically detect when services need rebuilding based on:
- Changes to Dockerfile
- Changes to requirements.txt
- Force rebuild flag

### Environment File Validation
The scripts check for required environment files:
- Main `.env` file
- Service-specific `.env` files

### Parallel Operations
Use `--parallel` flag for faster operations (more resource intensive):
```bash
./scripts/docker-manager.sh update microservices --parallel
```

### Service Groups
- `all` - All services
- `microservices` - Only microservices (excludes infrastructure)
- `infrastructure` - Only infrastructure services (postgres, redis, etc.)

## Available Services

### Microservices
- `api-gateway-service`
- `auth-service`
- `config-service`
- `metrics-service`
- `telemetry-service`
- `alerting-service`
- `dashboard-service`
- `nmt-service`
- `asr-service`
- `tts-service`
- `simple-ui-frontend`

### Infrastructure Services
- `postgres`
- `redis`
- `influxdb`
- `elasticsearch`
- `kafka`
- `zookeeper`

## Environment Setup

### Required Files
1. Main `.env` file in project root
2. Service-specific `.env` files in each service directory

### Environment Templates
Copy from `.env.template` files:
```bash
cp .env.template .env
cp services/nmt-service/.env.template services/nmt-service/.env
# ... repeat for other services
```

## Troubleshooting

### Common Issues

1. **Container name conflicts**
   ```bash
   ./scripts/docker-manager.sh clean
   ```

2. **Environment file missing**
   ```bash
   # Skip env check temporarily
   ./scripts/docker-manager.sh start all --skip-env
   ```

3. **Force rebuild when needed**
   ```bash
   ./scripts/docker-manager.sh rebuild <service> --force-rebuild
   ```

### Debugging

Use verbose mode for detailed output:
```bash
./scripts/docker-manager.sh start all --verbose
```

## Migration from Old Scripts

### From `restart-service.sh`
```bash
# Old way
./scripts/restart-service.sh nmt-service --build

# New way
./scripts/docker-quick.sh nmt
# or
./scripts/docker-manager.sh rebuild nmt-service
```

## Best Practices

1. **Use quick commands for daily development**
2. **Use full manager for complex operations**
3. **Always check status after operations**
4. **Use parallel flag for multiple services when system resources allow**
5. **Clean up Docker resources regularly**

## Examples

### Complete Development Session
```bash
# Start development environment
./scripts/docker-quick.sh dev

# Make changes to NMT service
# ... edit code ...

# Update NMT service
./scripts/docker-quick.sh nmt

# Check if it's working
./scripts/docker-quick.sh status

# View logs if needed
./scripts/docker-quick.sh logs
```

### Production Deployment
```bash
# Update all services
./scripts/docker-manager.sh update all --parallel

# Check health
./scripts/docker-manager.sh health all

# Monitor logs
./scripts/docker-manager.sh logs all
```
