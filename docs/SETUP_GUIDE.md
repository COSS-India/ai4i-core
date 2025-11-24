# Quick Setup Guide

A simple, step-by-step guide to get the AI4I Core platform running on your machine.

## Prerequisites

- **Docker** and **Docker Compose** installed
- **Git** installed
- At least **8GB RAM** and **20GB disk space**

## Step 1: Clone the Repository

```bash
git clone git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

## Step 2: Configure Environment Variables

### Root Environment File

```bash
cp env.template .env
```

Edit `.env` if needed (defaults should work for development).

### Service Environment Files

Copy the environment template for each service and the frontend:

```bash
# Services
cp services/api-gateway-service/env.template services/api-gateway-service/.env
cp services/auth-service/env.template services/auth-service/.env
cp services/config-service/env.template services/config-service/.env
cp services/asr-service/env.template services/asr-service/.env
cp services/tts-service/env.template services/tts-service/.env
cp services/nmt-service/env.template services/nmt-service/.env
cp services/pipeline-service/env.template services/pipeline-service/.env

# Frontend
cp frontend/simple-ui/env.template frontend/simple-ui/.env
```

**Note:** You can edit these `.env` files if you need to customize settings, but the defaults should work for initial setup.

## Step 3: Start All Services

Start all services using Docker Compose. This will automatically start all required infrastructure (PostgreSQL, Redis, etc.):

```bash
docker compose up -d api-gateway-service auth-service config-service asr-service tts-service nmt-service pipeline-service simple-ui-frontend
```

**Note:** The first time you run this, Docker will build the images, which may take 5-10 minutes. Subsequent starts will be much faster.

Wait for all services to be healthy (check with `docker compose ps`).

## Step 4: Initialize Database

Run the database initialization script to create all databases and tables. You can use any of these methods:

**Method 1 (Recommended - using wrapper script):**

```bash
./infrastructure/postgres/init-all-databases.sh
```

**Note:** If you get a "permission denied" error, you can run it with `bash`:
```bash
bash infrastructure/postgres/init-all-databases.sh
```

**Method 2 (Direct SQL execution):**

```bash
docker compose exec postgres psql -U dhruva_user -d dhruva_platform -f /docker-entrypoint-initdb.d/init-all-databases.sql
```

**Method 3 (Alternative - copy file first):**

If Method 2 doesn't work, copy the file into the container and run it:

```bash
docker compose cp infrastructure/postgres/init-all-databases.sql postgres:/tmp/init-all-databases.sql
docker compose exec postgres psql -U dhruva_user -d dhruva_platform -f /tmp/init-all-databases.sql
```

**Note:** The SQL file `infrastructure/postgres/init-all-databases.sql` contains everything needed to set up all databases, tables, and seed data in a single execution. The script now handles existing databases gracefully (errors are ignored if databases already exist).

This script will:
- Create all required databases (auth_db, config_db, unleash)
- Create all tables and schemas
- Set up indexes and triggers
- Insert seed data (default admin user, roles, permissions, etc.)

## Step 5: Verify Setup

Check that all services are running:

```bash
docker compose ps
```

All services should show as "Up" or "healthy".

## Step 6: Access the Platform

Once all services are running, you can access:

### Frontend & API

- **Simple UI Frontend**: http://localhost:3000
- **API Gateway**: http://localhost:8080
- **API Gateway Swagger**: http://localhost:8080/docs

### Service Swagger Documentation

- **ASR Service**: http://localhost:8087/docs
- **TTS Service**: http://localhost:8088/docs
- **NMT Service**: http://localhost:8091/docs (Note: port 8091, not 8089)

### Default Credentials

- **Admin User**: `admin@dhruva-platform.com`
- **Password**: `admin123`

## Troubleshooting

### Services not starting

1. Check logs: `docker compose logs <service-name>`
2. Verify environment files exist in each service directory
3. Check if ports are already in use: `netstat -tulpn | grep <port>`

### Database connection errors

1. Ensure PostgreSQL is running: `docker compose ps postgres`
2. Wait a few seconds after starting services for databases to initialize
3. Re-run the database initialization script if needed

### Port conflicts

If ports are already in use, you can modify the port mappings in `docker-compose.yml` or stop the conflicting services.

## Next Steps

- Explore the API using Swagger documentation
- Test the frontend at http://localhost:3000
- Review the [API Documentation](API_DOCUMENTATION.md) for detailed endpoint information
- Check [Deployment Guide](DEPLOYMENT.md) for production setup

## Stopping Services

To stop all services:

```bash
docker compose down
```

To stop and remove all data (volumes):

```bash
docker compose down -v
```

---

**Need Help?** Check the [Troubleshooting Guide](TROUBLESHOOTING.md) or open an issue on GitHub.

