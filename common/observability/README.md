# Dhruva Observability Package

> **Enterprise-grade monitoring and metrics collection for Dhruva Platform deployments**



---

## 📍 Quick Info

| Property | Value |
|----------|-------|
| **Location** | `server/observability/` |
| **Integration** | `server/main.py` (lines 34-61) |
| **Status** | ✅ Already integrated and working |
| **Supported Organizations** | `irctc`, `kisanmitra`, `bashadaan`, `beml` |
| **Metrics Endpoint** | `/enterprise/metrics` |
| **Health Endpoint** | `/enterprise/health` |

---

## 🎯 What Is This?

The Dhruva Observability Package provides comprehensive monitoring, metrics tracking, and real-time analytics for Dhruva platform deployments. It enables multi-tenant metrics collection, SLA tracking, and business analytics through Prometheus and Grafana.


## ✨ Key Features

- **Multi-tenant metrics collection** with organization-level isolation
- **Automatic service detection** (Translation, TTS, ASR, LLM, NER, etc.)
- **Real-time monitoring** via Prometheus and Grafana
- **Business metrics** - tokens, characters, audio seconds processed
- **Easy integration** - 3 lines of code to get started

---

## 📋 Prerequisites

### ⚠️ CRITICAL: Organization Identification Required

**Before using this package, you MUST implement organization extraction.** The system needs to identify which organization/tenant each request belongs to.

#### Option 1: JWT Token with Organization Claims (Recommended)

Add organization information to your JWT tokens:

```python
payload = {
    "sub": "user@example.com",
    "organization": "your-organization-name",  # Required!
    "name": "Organization Display Name",
    "exp": 1234567890
}
```

The middleware checks for these fields in order: `organization`, `org`, `name`, `company`

#### Option 2: Database Mapping

Store organization with API keys in your database and modify the middleware's organization extraction logic.

#### ⚠️ Current Mock Implementation

The package includes a **mock organization extractor** that uses hash-based mapping to assign organizations. **You MUST replace this** with proper implementation:

```python
# In server/observability/middleware.py (lines 126-135)
def _get_organization_from_api_key(api_key: str) -> str:
    """Map API key to organization name using consistent hashing."""
    organizations = ["irctc", "kisanmitra", "bashadaan", "beml"]
    hash_value = int(hashlib.md5(api_key.encode()).hexdigest(), 16)
    org_index = hash_value % len(organizations)
    return organizations[org_index]
```

**⚠️ CRITICAL REQUIREMENT**: 
- **Any API login/request MUST have an organization** that matches one of: `irctc`, `kisanmitra`, `bashadaan`, or `beml`
- If using JWT tokens, ensure the `organization` field contains one of these values
- To add new organizations, update the hardcoded list in `observability/middleware.py` (line 129)

### System Requirements

- **Python 3.8+**
- **Dependencies**: All required packages are in `server/requirements.txt` and will be installed during Docker build
  - `prometheus-client==0.15.0` (metrics collection)
  - `pyjwt==2.6.0` (JWT token parsing)
  - `psutil==5.9.5` (system metrics)
  - `fastapi==0.93.0` (web framework)
- **Prometheus** (assumed to be already running)
- **Grafana** (assumed to be already running)

---

## 🚀 Quick Start

### 1. Package Location & Integration

The observability package is already included in your server:
```bash
server/observability/
```

**How It's Used**: The observability plugin is integrated in `server/main.py`:

```python
# In server/main.py (lines 34-61)
from observability import ObservabilityPlugin

# Initialize and register the plugin
if OBSERVABILITY_AVAILABLE:
    try:
        enterprise = ObservabilityPlugin()
        enterprise.register_plugin(app)
        logger.info("✅ Dhruva Observability Plugin initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Dhruva Observability Plugin: {e}")
```

**What It Does**:
- Automatically intercepts all API requests via middleware
- Extracts organization from JWT tokens or API keys
- Tracks metrics (requests, duration, errors, business metrics)
- Exposes metrics at `/enterprise/metrics` for Prometheus

**Dependencies**: All required dependencies are listed in `server/requirements.txt` and will be automatically installed when you build the Docker image using `server/Dockerfile`.

### 2. Verify Supported Organizations

The observability package currently supports these organizations:
- `irctc`
- `kisanmitra`
- `bashadaan`
- `beml`

**Important**: 
- All API requests must include an organization matching one of the above
- JWT tokens must have `organization` field with one of these values
- To add new organizations, update `server/observability/middleware.py` line 129

### 3. Configure Environment Variables

**Option A: Add to `.env` file** (Recommended)
```bash
# Required - Observability Plugin
OBSERVE_UTIL_ENABLED=true

# Optional - Paths
OBSERVE_UTIL_METRICS_PATH=/enterprise/metrics
OBSERVE_UTIL_HEALTH_PATH=/enterprise/health

# Optional - Debug and Metrics Collection
OBSERVE_UTIL_DEBUG=true
OBSERVE_UTIL_COLLECT_SYSTEM_METRICS=true
OBSERVE_UTIL_COLLECT_GPU_METRICS=true
OBSERVE_UTIL_COLLECT_DB_METRICS=true
```

**Option B: Export in shell**
```bash
export OBSERVE_UTIL_ENABLED=true
export OBSERVE_UTIL_DEBUG=true
# ... (add other variables as needed)
```

### 4. Integrate with FastAPI (Already Done!)

The observability plugin is **already integrated** in `server/main.py`. No additional code needed!

```python
# server/main.py (lines 34-61)
from observability import ObservabilityPlugin

enterprise = ObservabilityPlugin()
enterprise.register_plugin(app)
```

This automatically:
- ✅ Registers middleware to intercept requests
- ✅ Creates `/enterprise/metrics` endpoint
- ✅ Creates `/enterprise/health` endpoint
- ✅ Creates `/enterprise/config` endpoint

### 5. Build Docker Image

Navigate to the `server/` directory and build the Docker image. This will automatically:
- Include the `server/observability/` package
- Install all dependencies from `server/requirements.txt`

```bash
# Navigate to server directory and build the image
cd server
docker build -t dhruva-platform-server:latest-pg15 .
cd ..
```

**Note**: The observability package is automatically included in the Docker build. No additional installation steps needed.

### 6. Verify Installation

Once your application is running, verify the observability plugin is working:

```bash
# Verify metrics endpoint is working
curl http://localhost:8000/enterprise/metrics

# Check plugin status
curl http://localhost:8000/enterprise/health

# View server logs to confirm observability plugin loaded
docker logs dhruva-platform-server | grep -i observability
```

---

## 🔧 Configuration

### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSERVE_UTIL_ENABLED` | Yes | `false` | Enable/disable the plugin |
| `OBSERVE_UTIL_DEBUG` | No | `false` | Enable debug logging |
| `OBSERVE_UTIL_METRICS_PATH` | No | `/enterprise/metrics` | Metrics endpoint path |
| `OBSERVE_UTIL_HEALTH_PATH` | No | `/enterprise/health` | Health check endpoint |
| `OBSERVE_UTIL_COLLECT_SYSTEM_METRICS` | No | `true` | Collect system metrics (CPU, memory) |
| `OBSERVE_UTIL_COLLECT_GPU_METRICS` | No | `true` | Collect GPU usage metrics |
| `OBSERVE_UTIL_COLLECT_DB_METRICS` | No | `true` | Collect database connection metrics |

---

## 📡 Available Endpoints

Once registered, the plugin automatically creates these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/enterprise/metrics` | GET | Prometheus metrics (scraped by Prometheus) |
| `/enterprise/health` | GET | Health check and plugin status |
| `/enterprise/config` | GET | Current plugin configuration |

---

## 🔍 Grafana Configuration

**Prerequisites**: Grafana and Prometheus should already be running and accessible.

### Configure Prometheus to Scrape Metrics

Add this scrape configuration to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "dhruva-enterprise-observability"
    scrape_interval: 5s
    static_configs:
      - targets: ["dhruva-platform-server:8000"]
    metrics_path: "/enterprise/metrics"
```

### Setup Grafana Dashboard (Per Organization)

1. **Login to Grafana** (e.g., `http://your-grafana-url:3000`)

2. **Create Organization**: 
   - Go to Server Admin → Organizations → New Organization
   - Enter organization name (e.g., "IRCTC", "KisanMitra")
   - Click "Create"

3. **Switch to the Organization**:
   - Server Admin → Organizations → [Your Org] → Switch To

4. **Create Prometheus Data Source**:
   - Go to Configuration → Data Sources → Add data source
   - Select **Prometheus**
   - Configure:
     - **Name**: `Prometheus-[OrgName]` (e.g., `Prometheus-IRCTC`)
     - **URL**: Your Prometheus URL (e.g., `http://prometheus:9090`)
   - Click **Save & Test**
   - **Important**: Note the **UID** from the browser URL
     - Example: `http://grafana:3000/datasources/edit/P1809F7CD0C75ACF3`
     - UID = `P1809F7CD0C75ACF3`

5. **Update Dashboard JSON**:
   - Locate dashboard JSON file: `grafana/provisioning/dashboards/*.json`
   - Find and replace all instances of: `"uid": "OLD_UID"`
   - With your actual data source UID: `"uid": "P1809F7CD0C75ACF3"`

6. **Import Dashboard**: 
   - Go to Dashboards → Import
   - Upload the modified JSON file
   - Click "Import"

**Repeat these steps for each client organization!**

---

## ✅ Verification Checklist

### Server Verification

```bash
# Check server is running
curl http://localhost:8000/health

# Check observability health endpoint
curl http://localhost:8000/enterprise/health

# Check metrics endpoint (should return Prometheus format metrics)
curl http://localhost:8000/enterprise/metrics

# Check configuration
curl http://localhost:8000/enterprise/config
```

### Prometheus Verification

Ensure Prometheus is scraping the metrics endpoint:
```bash
# Check Prometheus targets (adjust URL to your Prometheus instance)
curl http://your-prometheus-url:9090/api/v1/targets
```

Look for the `dhruva-enterprise-observability` job showing as **UP**.

### Grafana Verification

**In Grafana:**
- ✅ Organization created for each client
- ✅ Data source connected (green checkmark on "Save & Test")
- ✅ Dashboard imported successfully
- ✅ Dashboard shows data (not "No data")
- ✅ Metrics filtered for correct organization

---

## 📚 Documentation

### Available Documentation Files

| Document | Purpose |
|----------|---------|
| `OBSERVABILITY_COMPLETE_GUIDE.md` | Comprehensive guide (all docs combined) |
| `OBSERVABILITY_QUICK_SETUP_GUIDE.md` | Fast setup steps |
| `OBSERVABILITY_TECHNICAL_DOCUMENTATION.md` | Detailed technical reference |
| `OBSERVABILITY_ARCHITECTURE_DIAGRAM.md` | Visual architecture diagrams |
| `LOCAL_OBSERVABILITY_SETUP.md` | Local development setup |
| `ORGANIZATION_EXTRACTION_IMPLEMENTATION_GUIDE.md` | How to implement organization extraction |

---

## 🎓 Quick Example

### How It's Already Integrated

The observability package is **already integrated** in your `server/main.py`:

```python
# server/main.py (simplified)
from fastapi import FastAPI
from observability import ObservabilityPlugin

app = FastAPI()

# Observability plugin automatically registers during startup
try:
    enterprise = ObservabilityPlugin()
    enterprise.register_plugin(app)
    logger.info("✅ Dhruva Observability Plugin initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize Dhruva Observability Plugin: {e}")

# Your existing Dhruva API routes work unchanged
# All requests are automatically tracked!
```

### Example API Request Flow

```bash
# Client makes a request with JWT token
curl -X POST "http://localhost:8000/translation/v1" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{"input": [{"source": "Hello World"}]}'
```

### What Happens Automatically

1. **Middleware intercepts** the request at `/translation/v1`
2. **Extracts organization** from JWT token → reads `organization` field (e.g., `irctc`)
3. **Validates organization** → must be one of: `irctc`, `kisanmitra`, `bashadaan`, `beml`
4. **Detects service type** → URL contains `/translation/` → service = `translation`
5. **Counts characters** → "Hello World" = 11 characters
6. **Processes request** → passes to actual Dhruva translation handler
7. **Tracks metrics** → request count, duration, characters translated
8. **Updates Prometheus** → metrics available at `/enterprise/metrics`
9. **Grafana displays** → organization-filtered dashboard shows the data

---

## 🔐 Security Considerations

### Production Requirements

1. ✅ **JWT Signature Verification**: Implement proper token verification (don't use `verify_signature=False`)
2. ✅ **JWT Secret Security**: Use a secure secret key for JWT validation
3. ✅ **Organization Isolation**: Verify metrics don't leak between organizations
4. ✅ **Access Control**: Ensure proper RBAC in Grafana organizations
5. ✅ **Network Security**: Restrict access to metrics endpoint if needed

---

## 📦 Package Structure

```
Dhruva-Platform-2/
├── server/                      # Server directory
│   ├── observability/           # Observability package (THIS PACKAGE)
│   │   ├── __init__.py              # Package initialization
│   │   ├── plugin.py                # Main ObservabilityPlugin class
│   │   ├── middleware.py            # FastAPI middleware (request tracking)
│   │   ├── metrics.py               # MetricsCollector (50+ metrics)
│   │   ├── config.py                # PluginConfig (environment variables)
│   │   ├── adapters/                # Framework adapters (Flask, Django, etc.)
│   │   │   ├── __init__.py
│   │   │   ├── flask_adapter.py     # Flask integration (optional)
│   │   │   ├── django_adapter.py    # Django integration (optional)
│   │   │   ├── generic_adapter.py   # Generic framework support
│   │   │   └── manual_adapter.py    # Manual metrics tracking
│   │   └── README.md                # This file
│   ├── requirements.txt         # Dependencies (includes observability deps)
│   ├── Dockerfile               # Docker build (includes observability package)
│   └── main.py                  # FastAPI app (register plugin here)
│
└── ...                          # Other project files (managed separately)
```

**Key Files:**
- `server/observability/` - The observability package (this directory)
- `server/requirements.txt` - Contains all dependencies including `prometheus-client`, `pyjwt`, `psutil`
- `server/Dockerfile` - Builds the server image with observability package included
- `server/main.py` - Where the observability plugin is registered (lines 34-61)

---

## 🚨 Important Notes

### Before Deploying to Production

1. **MUST IMPLEMENT** organization extraction from JWT tokens
2. **MUST ENSURE** API requests include organization matching one of: `irctc`, `kisanmitra`, `bashadaan`, `beml`
3. **MUST CONFIGURE** proper JWT secret and verification  
4. **MUST CREATE** Grafana organizations for each client
5. **MUST CREATE** Prometheus data sources in each Grafana organization
6. **MUST UPDATE** dashboard JSON files with correct data source UIDs
7. **MUST CONFIGURE** Prometheus to scrape `/enterprise/metrics` endpoint

### Known Limitations

- **Manual Grafana setup required** for each organization
- **Dashboard JSON must be updated** with data source UIDs before import
- **Mock organization extractor** must be replaced with real implementation

---

## 📞 Support

### Getting Help

1. **Enable debug mode**: `export OBSERVE_UTIL_DEBUG=true`
2. **Check logs**: `docker logs dhruva-platform-server`
3. **Refer to documentation**: See `OBSERVABILITY_COMPLETE_GUIDE.md`

### Common Commands

```bash
# View all metrics
curl http://localhost:8000/enterprise/metrics

# View observability plugin status
curl http://localhost:8000/enterprise/health

# View observability configuration
curl http://localhost:8000/enterprise/config

# View server logs
docker logs -f dhruva-platform-server

# Check for observability-related logs (when DEBUG=true)
docker logs dhruva-platform-server | grep -E "🔍|🔑|✅|⚠️"
```

---

## 📄 License

Part of the Dhruva Platform

---

## 🔄 Version Information

- **Package Version**: 1.0.3
- **Last Updated**: October 2025
- **Framework**: FastAPI (native support)
- **Python**: 3.8+

---

## 🎯 Next Steps

1. ✅ **Check `server/main.py`** - Observability plugin is already integrated
2. ✅ **Verify organizations** - Ensure your API uses: `irctc`, `kisanmitra`, `bashadaan`, or `beml`
3. ✅ **Implement organization extraction** - Add `organization` field to JWT tokens
4. ✅ **Set environment variables** - Update `.env` file or environment configuration
5. ✅ **Build Docker image**:
   ```bash
   cd server
   docker build -t dhruva-platform-server:latest-pg15 .
   cd ..
   ```
6. ✅ **Start your application** - Use your deployment method
7. ✅ **Verify installation** - Check `/enterprise/metrics` and `/enterprise/health` endpoints
8. ✅ **Configure Prometheus** - Add scrape config for `/enterprise/metrics` endpoint
9. ✅ **Create Grafana organizations** - One for each client
10. ✅ **Configure data sources** - Create Prometheus data source per organization
11. ✅ **Import dashboards** - Update JSON with correct data source UIDs
12. ✅ **Verify metrics** - Check dashboards show organization-filtered data


