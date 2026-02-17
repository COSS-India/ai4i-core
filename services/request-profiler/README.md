# RequestProfiler - Translation Request Profiler

A production-ready microservice for profiling translation requests. Provides multi-signal analysis including domain classification, complexity scoring, language detection, and entity extraction to help route requests to the optimal translation model.

**Supported Languages**: Hindi, Bengali, Tamil, Telugu, Kannada, Assamese
**Supported Domains**: Medical, Legal, Technical, Finance, Casual, General
**Status**: ✅ Production Ready | **Version**: 2.0.0

## 🚀 Installation

### Docker (Recommended)

**Prerequisites**: Docker 24.0+ and Docker Compose v2

```bash
git clone <repository-url>
cd RequestProfiler
docker compose up -d
```

Verify the service is running:
```bash
curl http://localhost:8000/api/v1/health
# Response: {"status": "healthy", "models_loaded": true, "timestamp": "..."}
```

The API will be available at `http://localhost:8000`

### Local Development

**Prerequisites**: Python 3.9+

```bash
git clone <repository-url>
cd RequestProfiler
pip install -r requirements.txt
python3 -m uvicorn request_profiler.main:app --reload
```

For detailed deployment instructions, see [DEPLOYMENT_GUIDE.md](mdfiles/DEPLOYMENT_GUIDE.md).

## 📖 API Endpoints

### Interactive Documentation
Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Core Endpoints

#### 1. Profile Single Text
**POST** `/api/v1/profile`

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world this is a test"}'
```

**Response:**
```json
{
  "request_id": "ac14f2ec-098e-45f7-983b-ffb1aea3d509",
  "profile": {
    "domain": {
      "label": "medical",
      "confidence": 0.28,
      "top_3": [{"label": "medical", "confidence": 0.28}, ...]
    },
    "scores": {
      "complexity_score": 0.23,
      "complexity_level": "LOW"
    },
    "language": {"primary": "en", "num_languages": 1},
    "structure": {"entity_density": 0.17, "terminology_density": 0.0}
  }
}
```

**Validation:**
- Text: 1-50,000 characters, minimum 2 words
- Status codes: 200 (success), 422 (validation error), 500 (server error)

#### 2. Profile Batch
**POST** `/api/v1/profile/batch`

```bash
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["text one", "text two"]}'
```

**Limits:** Maximum 50 texts per batch

#### 3. Health Check
**GET** `/api/v1/health`

```bash
curl http://localhost:8000/api/v1/health
```

**Response:**
```json
{
  "status": "healthy",
  "models_loaded": true,
  "timestamp": "2026-02-12T08:05:49.034519Z"
}
```

For complete API documentation, see [API_EXAMPLES.md](mdfiles/API_EXAMPLES.md).

## 🧪 Testing

Run the automated test suite:
```bash
python3 scripts/test_docker_deployment.py
```

Expected output: All 6/6 tests pass with average response time ~33ms (target: <500ms)

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   FastAPI Application                     │
├──────────────────────────────────────────────────────────┤
│  API Endpoints: /profile, /profile/batch, /health        │
├──────────────────────────────────────────────────────────┤
│              Request Profiler Core                        │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Domain    │  │  Complexity  │  │   Language   │    │
│  │ Classifier  │  │  Regressor   │  │   Detector   │    │
│  └─────────────┘  └──────────────┘  └──────────────┘    │
├──────────────────────────────────────────────────────────┤
│           Feature Extraction & ML Models                  │
│  Text Stats │ Vocabulary │ Syntax │ Semantics │ Entities │
└──────────────────────────────────────────────────────────┘
```

**Complexity Scoring** (0.0-1.0 scale):
- Vocabulary Sophistication (40%)
- Syntactic Complexity (30%)
- Semantic Complexity (20%)
- Text Length (10%)

**Complexity Levels:**
- `LOW`: score < 0.5
- `HIGH`: score ≥ 0.5

## 🔍 Troubleshooting

For common issues and solutions, see [TROUBLESHOOTING.md](mdfiles/TROUBLESHOOTING.md).

**Quick Checks:**
```bash
# Verify service is running
curl http://localhost:8000/api/v1/health

# Check Docker logs
docker compose logs profiler

# View Prometheus metrics
curl http://localhost:8000/metrics
```

## 📁 Project Structure

```
RequestProfiler/
├── request_profiler/          # Main application
│   ├── main.py               # FastAPI app
│   ├── profiler.py           # Core profiler logic
│   ├── schemas.py            # Request/response models
│   ├── features.py           # Feature extraction
│   ├── complexity_utils.py   # Complexity scoring
│   └── config.py             # Configuration
│
├── models/                    # Pre-trained ML models
│   ├── domain_pipeline.pkl
│   ├── complexity_regressor.pkl
│   └── lid.176.ftz
│
├── scripts/                   # Utility scripts
│   ├── test_docker_deployment.py
│   └── train_models.py
│
├── Dockerfile                 # Multi-stage Docker build
├── docker-compose.yml         # Docker Compose config
├── requirements.txt           # Dependencies
└── README.md                  # This file
```

## 🔐 Security

- **Input Validation**: Text limited to 50,000 characters, minimum 2 words
- **Batch Limits**: Maximum 50 texts per batch
- **Rate Limiting**: 100 requests/minute per IP (configurable)
- **Error Handling**: Comprehensive validation with proper HTTP status codes

For production deployment, see [DEPLOYMENT_GUIDE.md](mdfiles/DEPLOYMENT_GUIDE.md).

## 📚 Documentation

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Ensure all tests pass: `python3 scripts/test_docker_deployment.py`
5. Commit and push your changes
6. Open a Pull Request


## 🙏 Acknowledgments

- **fastText** for language detection
- **scikit-learn** for ML models
- **FastAPI** for the web framework

---

**Version**: 2.0.0 | **Last Updated**: 2026-02-12 | **Status**: ✅ Production Ready


