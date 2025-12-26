# Services Port Mapping
## AI4I Core Microservices Architecture

**Last Updated:** Generated from docker-compose.yml  
**Format:** External Port:Internal Port (host:container)

---

## Infrastructure Services

| Service Name | External Port | Internal Port | Description |
|-------------|---------------|---------------|-------------|
| **PostgreSQL** | 5434 | 5432 | Main database |
| **PostgreSQL (Konga)** | 5435 | 5432 | Konga database |
| **Redis** | 6381 | 6379 | Cache and session store |
| **InfluxDB** | 8089 | 8086 | Time-series database for metrics |
| **Elasticsearch** | 9203 | 9200 | Search and analytics engine |
| **Zookeeper** | - | 2181 | Kafka coordination (internal only) |
| **Kafka** | 9093 | 9092 | Message broker |
| **Kong API Gateway** | 8000 | 8000 | API Gateway (HTTP) |
| **Kong API Gateway** | 8443 | 8443 | API Gateway (HTTPS) |
| **Kong Admin API** | 8001 | 8001 | Kong Admin API |
| **Kong Admin API** | 8444 | 8444 | Kong Admin API (HTTPS) |
| **Kong Manager (Konga)** | 8002 | 1337 | Kong management UI |
| **Unleash** | 4242 | 4242 | Feature flag service |

---

## Core Microservices

| Service Name | External Port | Internal Port | Description |
|-------------|---------------|---------------|-------------|
| **API Gateway Service** | 8080 | 8080 | Main API gateway |
| **Auth Service** | 8081 | 8081 | Authentication & authorization |
| **Config Service** | 8082 | 8082 | Configuration management |
| **Metrics Service** | 8083 | 8083 | Metrics collection |
| **Telemetry Service** | 8084 | 8084 | Telemetry & logging |
| **Alerting Service** | 8085 | 8085 | Alerting & notifications |
| **Dashboard Service** | 8090 | 8086 | Dashboard API |
| **Dashboard Service (Streamlit)** | 8501 | 8501 | Streamlit dashboard UI |

---

## AI/ML Microservices (10 Services)

| Service Name | External Port | Internal Port | Description |
|-------------|---------------|---------------|-------------|
| **ASR Service** | 8087 | 8087 | Automatic Speech Recognition |
| **TTS Service** | 8088 | 8088 | Text-to-Speech |
| **NMT Service** | 8091 | 8089 | Neural Machine Translation |
| **OCR Service** | 8099 | 8099 | Optical Character Recognition |
| **NER Service** | 9001 | 9001 | Named Entity Recognition |
| **LLM Service** | 8093 | 8090 | Large Language Model |
| **Pipeline Service** | 8092 | 8090 | AI Pipeline orchestration |
| **Transliteration Service** | 8097 | 8090 | Text transliteration |
| **Language Detection Service** | 8098 | 8090 | Text language detection |
| **Speaker Diarization Service** | 8095 | 8095 | Speaker identification |
| **Language Diarization Service** | 9002 | 9002 | Language identification in audio |
| **Audio Language Detection Service** | 8096 | 8096 | Audio language detection |

---

## Frontend Services

| Service Name | External Port | Internal Port | Description |
|-------------|---------------|---------------|-------------|
| **Simple UI Frontend** | 3000 | 3000 | Next.js frontend application |

---

## Observability Services

| Service Name | External Port | Internal Port | Description |
|-------------|---------------|---------------|-------------|
| **Prometheus** | 9090 | 9090 | Metrics collection & monitoring |
| **Grafana** | 3001 | 3000 | Visualization & dashboards |

---

## Summary Statistics

- **Total Services:** 30+
- **Infrastructure Services:** 12
- **Core Microservices:** 8
- **AI/ML Microservices:** 12
- **Frontend Services:** 1
- **Observability Services:** 2

---

## Port Range Summary

### Port Ranges Used:
- **3000-3001:** Frontend & Grafana
- **4242:** Unleash
- **5434-5435:** PostgreSQL databases
- **6381:** Redis
- **8000-8002:** Kong API Gateway & Manager
- **8080-8099:** Core & AI microservices
- **8443-8444:** Kong HTTPS
- **8501:** Streamlit
- **9001-9002:** NER & Language Diarization
- **9090:** Prometheus
- **9093:** Kafka
- **9203:** Elasticsearch

---

## Internal Service Communication

Services communicate internally using their **internal port** and **service name**:
- Example: `http://asr-service:8087` (not `localhost:8087`)
- Example: `http://auth-service:8081` (not `localhost:8081`)

---

## External Access

Services are accessed externally using their **external port**:
- Example: `http://localhost:8087` → ASR Service
- Example: `http://localhost:8080` → API Gateway Service
- Example: `http://localhost:8000` → Kong API Gateway

---

## Notes

1. **Port Conflicts:** Some services share the same internal port (8090) but have different external ports:
   - LLM Service: 8093:8090
   - Pipeline Service: 8092:8090
   - Transliteration Service: 8097:8090
   - Language Detection Service: 8098:8090

2. **Kong Gateway:** Most external traffic should go through Kong (port 8000) rather than directly to services.

3. **Health Checks:** Services expose health endpoints on their internal ports for container health checks.

4. **Network:** All services are on the `microservices-network` bridge network.
