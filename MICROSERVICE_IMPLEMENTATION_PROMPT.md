# 🚀 Comprehensive Microservice Architecture Implementation Prompt
## Building Enterprise-Grade AI/ML Microservices from Dhruva Platform 2.0

### 📋 **PROMPT OVERVIEW**
Create a comprehensive microservice architecture following the Dhruva Platform's Frontend-Backend Communication Flow pattern, implementing the 6-step communication process with enterprise-grade API services and capabilities. This implementation will migrate existing monolithic ASR, TTS, and NMT services from Dhruva-Platform-2 into scalable microservices.

---

## 🎯 **CORE REQUIREMENTS**

### **Architecture Pattern**: Frontend-Backend Communication Flow (6 Steps)
1. **User Interface Layer** → **API Configuration Layer**
2. **API Configuration Layer** → **HTTP Transport Layer** 
3. **HTTP Transport Layer** → **Backend API Layer**
4. **Backend API Layer** → **Service Layer** (Business Logic)
5. **Service Layer** → **Repository Layer** (Data Access)
6. **Repository Layer** → **Database Layer** (Data Persistence)

### **Required Microservices**:
1. **API Gateway Service** (Central entry point) - ✅ **EXISTING**
2. **Authentication & Authorization Service** (Identity management) - ✅ **EXISTING**
3. **Configuration Management Service** (Centralized config) - ✅ **EXISTING**
4. **ASR Microservice** (Speech-to-Text) - 🆕 **TO IMPLEMENT**
5. **TTS Microservice** (Text-to-Speech) - 🆕 **TO IMPLEMENT**
6. **NMT Microservice** (Neural Machine Translation) - 🆕 **TO IMPLEMENT**
7. **Simple UI Frontend** (Testing Interface) - 🆕 **TO IMPLEMENT**

---

## 🏗️ **DETAILED IMPLEMENTATION SPECIFICATIONS**

### **1. API Gateway Service** ✅ **EXISTING**
```yaml
Service Name: api-gateway-service
Port: 8080
Status: IMPLEMENTED
Capabilities:
  - ✅ Request routing and load balancing
  - ✅ Rate limiting and throttling
  - ✅ Authentication and authorization
  - ✅ Request/response transformation
  - ✅ API versioning management
```

### **2. Authentication & Authorization Service** ✅ **EXISTING**
```yaml
Service Name: auth-service
Port: 8081
Status: IMPLEMENTED
Capabilities:
  - ✅ User authentication (API Key, JWT)
  - ✅ Role-Based Access Control (RBAC)
  - ✅ API key management
  - ✅ Session management
  - ✅ Multi-tenant support
```

### **3. Configuration Management Service** ✅ **EXISTING**
```yaml
Service Name: config-service
Port: 8082
Status: IMPLEMENTED
Capabilities:
  - ✅ Environment-specific configurations
  - ✅ Feature flags
  - ✅ Service discovery
  - ✅ Dynamic configuration updates
```

---

## 🆕 **NEW MICROSERVICES TO IMPLEMENT**

### **4. ASR Microservice** 🆕 **TO IMPLEMENT**
```yaml
Service Name: asr-service
Port: 8087
Technology Stack:
  - Framework: FastAPI
  - Database: PostgreSQL (auth_db schema)
  - Cache: Redis
  - Model Serving: Triton Inference Server
  - Audio Processing: librosa, soundfile
  - Streaming: WebSocket support
```

**Capabilities to Implement**:
- ✅ **Speech-to-Text Conversion**
  - Support for 22+ Indian languages
  - Real-time streaming ASR
  - Batch processing
  - Audio format support (WAV, MP3, FLAC)
  - Language detection and validation

- ✅ **Audio Processing**
  - Audio preprocessing and normalization
  - Chunking for long audio files
  - VAD (Voice Activity Detection)
  - Audio quality validation

- ✅ **Model Management**
  - Multiple ASR model support
  - Model versioning
  - A/B testing capabilities
  - Performance monitoring

- ✅ **API Endpoints**
  - `/api/v1/asr/inference` - Batch inference
  - `/api/v1/asr/stream` - WebSocket streaming
  - `/api/v1/asr/models` - Model management
  - `/api/v1/asr/health` - Health check

**Database Schema Integration**:
```sql
-- Use existing auth_db schema for:
-- - users table (user authentication)
-- - api_keys table (API key validation)
-- - sessions table (session management)

-- Add ASR-specific tables:
CREATE TABLE asr_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id),
    api_key_id INTEGER REFERENCES api_keys(id),
    session_id INTEGER REFERENCES sessions(id),
    model_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,
    audio_duration FLOAT,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE asr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES asr_requests(id),
    transcript TEXT NOT NULL,
    confidence_score FLOAT,
    word_timestamps JSONB,
    language_detected VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### **5. TTS Microservice** 🆕 **TO IMPLEMENT**
```yaml
Service Name: tts-service
Port: 8088
Technology Stack:
  - Framework: FastAPI
  - Database: PostgreSQL (auth_db schema)
  - Cache: Redis
  - Model Serving: Triton Inference Server
  - Audio Generation: TTS models
  - Audio Processing: librosa, soundfile
```

**Capabilities to Implement**:
- ✅ **Text-to-Speech Conversion**
  - Support for 22+ Indian languages
  - Multiple voice options (male/female)
  - SSML support for advanced speech control
  - Audio format output (WAV, MP3, OGG)

- ✅ **Voice Management**
  - Multiple voice model support
  - Voice cloning capabilities
  - Voice quality optimization
  - Gender and age-specific voices

- ✅ **Audio Generation**
  - High-quality audio synthesis
  - Real-time streaming TTS
  - Batch processing
  - Audio post-processing

- ✅ **API Endpoints**
  - `/api/v1/tts/inference` - Batch inference
  - `/api/v1/tts/stream` - WebSocket streaming
  - `/api/v1/tts/voices` - Voice management
  - `/api/v1/tts/health` - Health check

**Database Schema Integration**:
```sql
-- Add TTS-specific tables:
CREATE TABLE tts_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id),
    api_key_id INTEGER REFERENCES api_keys(id),
    session_id INTEGER REFERENCES sessions(id),
    model_id VARCHAR(100) NOT NULL,
    voice_id VARCHAR(50) NOT NULL,
    language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tts_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES tts_requests(id),
    audio_file_path TEXT NOT NULL,
    audio_duration FLOAT,
    sample_rate INTEGER,
    bit_rate INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### **6. NMT Microservice** 🆕 **TO IMPLEMENT**
```yaml
Service Name: nmt-service
Port: 8089
Technology Stack:
  - Framework: FastAPI
  - Database: PostgreSQL (auth_db schema)
  - Cache: Redis
  - Model Serving: Triton Inference Server
  - Translation: Neural Machine Translation models
  - Text Processing: tokenization, normalization
```

**Capabilities to Implement**:
- ✅ **Neural Machine Translation**
  - Support for 22+ Indian languages
  - Bidirectional translation
  - Batch translation
  - Domain-specific models

- ✅ **Translation Management**
  - Multiple translation model support
  - Model versioning
  - Quality scoring
  - Translation confidence metrics

- ✅ **Text Processing**
  - Text normalization
  - Language detection
  - Tokenization
  - Post-processing

- ✅ **API Endpoints**
  - `/api/v1/nmt/inference` - Batch inference
  - `/api/v1/nmt/stream` - WebSocket streaming
  - `/api/v1/nmt/models` - Model management
  - `/api/v1/nmt/health` - Health check

**Database Schema Integration**:
```sql
-- Add NMT-specific tables:
CREATE TABLE nmt_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id),
    api_key_id INTEGER REFERENCES api_keys(id),
    session_id INTEGER REFERENCES sessions(id),
    model_id VARCHAR(100) NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE nmt_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES nmt_requests(id),
    translated_text TEXT NOT NULL,
    confidence_score FLOAT,
    source_text TEXT,
    language_detected VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### **7. Simple UI Frontend** 🆕 **TO IMPLEMENT**
```yaml
Service Name: simple-ui-frontend
Port: 3000
Technology Stack:
  - Framework: Next.js 13 with TypeScript
  - UI Library: Chakra UI + Framer Motion
  - State Management: TanStack React Query
  - API Client: Axios with interceptors
  - Audio Handling: Web Audio API
  - Real-time: Socket.IO client
```

**Capabilities to Implement**:
- ✅ **Service Testing Interface**
  - ASR testing with audio upload/recording
  - TTS testing with text input and voice selection
  - NMT testing with language pair selection
  - Real-time streaming capabilities

- ✅ **User Interface**
  - Modern, responsive design
  - Audio visualization
  - Progress indicators
  - Error handling and feedback

- ✅ **Integration Features**
  - API key management
  - Session management
  - Request/response logging
  - Performance metrics display

---

## 📁 **FOLDER STRUCTURE IMPLEMENTATION**

### **ASR Microservice Structure**
```
Ai4V-C/services/asr-service/
├── Dockerfile
├── requirements.txt
├── main.py
├── env.template
├── models/
│   ├── __init__.py
│   ├── asr_request.py
│   ├── asr_response.py
│   └── audio_processing.py
├── services/
│   ├── __init__.py
│   ├── asr_service.py
│   ├── audio_service.py
│   ├── model_service.py
│   └── streaming_service.py
├── repositories/
│   ├── __init__.py
│   ├── asr_repository.py
│   └── user_repository.py
├── routers/
│   ├── __init__.py
│   ├── inference_router.py
│   ├── streaming_router.py
│   └── health_router.py
└── utils/
    ├── __init__.py
    ├── audio_utils.py
    ├── validation_utils.py
    └── triton_client.py
```

### **TTS Microservice Structure**
```
Ai4V-C/services/tts-service/
├── Dockerfile
├── requirements.txt
├── main.py
├── env.template
├── models/
│   ├── __init__.py
│   ├── tts_request.py
│   ├── tts_response.py
│   └── voice_management.py
├── services/
│   ├── __init__.py
│   ├── tts_service.py
│   ├── voice_service.py
│   ├── audio_generation_service.py
│   └── streaming_service.py
├── repositories/
│   ├── __init__.py
│   ├── tts_repository.py
│   └── user_repository.py
├── routers/
│   ├── __init__.py
│   ├── inference_router.py
│   ├── streaming_router.py
│   └── health_router.py
└── utils/
    ├── __init__.py
    ├── audio_utils.py
    ├── validation_utils.py
    └── triton_client.py
```

### **NMT Microservice Structure**
```
Ai4V-C/services/nmt-service/
├── Dockerfile
├── requirements.txt
├── main.py
├── env.template
├── models/
│   ├── __init__.py
│   ├── nmt_request.py
│   ├── nmt_response.py
│   └── translation_models.py
├── services/
│   ├── __init__.py
│   ├── nmt_service.py
│   ├── translation_service.py
│   ├── language_service.py
│   └── streaming_service.py
├── repositories/
│   ├── __init__.py
│   ├── nmt_repository.py
│   └── user_repository.py
├── routers/
│   ├── __init__.py
│   ├── inference_router.py
│   ├── streaming_router.py
│   └── health_router.py
└── utils/
    ├── __init__.py
    ├── text_utils.py
    ├── validation_utils.py
    └── triton_client.py
```

### **Simple UI Frontend Structure**
```
Ai4V-C/frontend/simple-ui/
├── package.json
├── next.config.js
├── tsconfig.json
├── tailwind.config.js
├── public/
│   ├── icons/
│   └── images/
├── src/
│   ├── components/
│   │   ├── asr/
│   │   │   ├── AudioRecorder.tsx
│   │   │   ├── AudioPlayer.tsx
│   │   │   └── ASRResults.tsx
│   │   ├── tts/
│   │   │   ├── TextInput.tsx
│   │   │   ├── VoiceSelector.tsx
│   │   │   └── TTSResults.tsx
│   │   ├── nmt/
│   │   │   ├── LanguageSelector.tsx
│   │   │   ├── TextTranslator.tsx
│   │   │   └── TranslationResults.tsx
│   │   └── common/
│   │       ├── Layout.tsx
│   │       ├── Header.tsx
│   │       ├── Sidebar.tsx
│   │       └── LoadingSpinner.tsx
│   ├── pages/
│   │   ├── index.tsx
│   │   ├── asr.tsx
│   │   ├── tts.tsx
│   │   ├── nmt.tsx
│   │   └── api/
│   │       ├── auth.ts
│   │       └── services.ts
│   ├── hooks/
│   │   ├── useASR.ts
│   │   ├── useTTS.ts
│   │   ├── useNMT.ts
│   │   └── useWebSocket.ts
│   ├── services/
│   │   ├── api.ts
│   │   ├── asrService.ts
│   │   ├── ttsService.ts
│   │   └── nmtService.ts
│   ├── types/
│   │   ├── asr.ts
│   │   ├── tts.ts
│   │   ├── nmt.ts
│   │   └── common.ts
│   └── utils/
│       ├── audioUtils.ts
│       ├── validationUtils.ts
│       └── constants.ts
└── Dockerfile
```

---

## 🔧 **IMPLEMENTATION STEPS**

### **Step 1: Database Schema Updates**
1. Update PostgreSQL schemas to include ASR, TTS, NMT tables
2. Create database migration scripts
3. Update seed data for new services

### **Step 2: ASR Microservice Implementation**
1. Create service folder structure
2. Implement core ASR service logic from Dhruva-Platform-2
3. Add WebSocket streaming support
4. Integrate with Triton Inference Server
5. Add comprehensive error handling and logging

### **Step 3: TTS Microservice Implementation**
1. Create service folder structure
2. Implement core TTS service logic from Dhruva-Platform-2
3. Add voice management capabilities
4. Integrate with Triton Inference Server
5. Add audio generation and processing

### **Step 4: NMT Microservice Implementation**
1. Create service folder structure
2. Implement core NMT service logic from Dhruva-Platform-2
3. Add language detection and validation
4. Integrate with Triton Inference Server
5. Add translation quality metrics

### **Step 5: Simple UI Frontend Implementation**
1. Create Next.js application structure
2. Implement ASR testing interface
3. Implement TTS testing interface
4. Implement NMT testing interface
5. Add real-time streaming capabilities

### **Step 6: Docker and Infrastructure Updates**
1. Update docker-compose.yml with new services
2. Create Dockerfiles for each microservice
3. Update health check scripts
4. Add service discovery configuration

### **Step 7: API Gateway Integration**
1. Update route mappings for new services
2. Add service discovery for ASR, TTS, NMT
3. Update load balancing configuration
4. Add rate limiting for new endpoints

---

## 📊 **MIGRATION FROM DHRUVA-PLATFORM-2**

### **Existing Code to Migrate**:

#### **ASR Service Migration**:
- **Source**: `Dhruva-Platform-2/server/module/services/service/inference_service.py` (lines 199-400)
- **Key Functions**:
  - `run_asr_triton_inference()`
  - `__run_asr_pre_processors()`
  - `__run_asr_post_processors()`
- **Streaming**: `Dhruva-Platform-2/server/asr_streamer.py`

#### **TTS Service Migration**:
- **Source**: `Dhruva-Platform-2/server/module/services/service/inference_service.py` (lines 500-700)
- **Key Functions**:
  - `run_tts_triton_inference()`
  - Audio generation and processing
- **Streaming**: `Dhruva-Platform-2/server/seq_streamer.py`

#### **NMT Service Migration**:
- **Source**: `Dhruva-Platform-2/server/module/services/service/inference_service.py` (lines 170-200)
- **Key Functions**:
  - `run_translation_triton_inference()`
  - Text processing and validation

#### **Frontend Migration**:
- **Source**: `Dhruva-Platform-2/client/pages/pipeline.tsx`
- **Key Components**:
  - Audio recording and playback
  - Language selection
  - Service integration

---

## 🚀 **DEPLOYMENT CONFIGURATION**

### **Updated docker-compose.yml**:
```yaml
# Add to existing docker-compose.yml
services:
  asr-service:
    build:
      context: ./services/asr-service
      dockerfile: Dockerfile
    container_name: dhruva-asr-service
    ports:
      - "8087:8087"
    environment:
      - ENV_FILE=.env
    env_file:
      - ./services/asr-service/.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - microservices-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8087/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  tts-service:
    build:
      context: ./services/tts-service
      dockerfile: Dockerfile
    container_name: dhruva-tts-service
    ports:
      - "8088:8088"
    environment:
      - ENV_FILE=.env
    env_file:
      - ./services/tts-service/.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - microservices-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  nmt-service:
    build:
      context: ./services/nmt-service
      dockerfile: Dockerfile
    container_name: dhruva-nmt-service
    ports:
      - "8089:8089"
    environment:
      - ENV_FILE=.env
    env_file:
      - ./services/nmt-service/.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - microservices-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8089/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  simple-ui-frontend:
    build:
      context: ./frontend/simple-ui
      dockerfile: Dockerfile
    container_name: dhruva-simple-ui
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://api-gateway-service:8080
    depends_on:
      api-gateway-service:
        condition: service_healthy
    networks:
      - microservices-network
    restart: unless-stopped
```

---

## 🧪 **TESTING STRATEGY**

### **Unit Tests**:
- Service layer testing
- Repository layer testing
- Utility function testing
- Model validation testing

### **Integration Tests**:
- API endpoint testing
- Database integration testing
- Redis cache testing
- Triton server integration testing

### **End-to-End Tests**:
- Complete ASR workflow testing
- Complete TTS workflow testing
- Complete NMT workflow testing
- Frontend integration testing

### **Performance Tests**:
- Load testing for each microservice
- Streaming performance testing
- Database performance testing
- Memory usage monitoring

---

## 📈 **MONITORING AND OBSERVABILITY**

### **Metrics Collection**:
- Request/response metrics
- Processing time metrics
- Error rate metrics
- Resource utilization metrics

### **Logging**:
- Structured logging with correlation IDs
- Request/response logging
- Error logging with stack traces
- Performance logging

### **Health Checks**:
- Service health endpoints
- Database connectivity checks
- Redis connectivity checks
- Triton server connectivity checks

---

## 🔒 **SECURITY CONSIDERATIONS**

### **Authentication**:
- JWT token validation
- API key authentication
- Session management
- Rate limiting per user

### **Authorization**:
- Role-based access control
- Service-level permissions
- Resource-level permissions
- Audit logging

### **Data Protection**:
- Audio data encryption
- Text data sanitization
- Secure API communication
- Data retention policies

---

## 🎯 **SUCCESS CRITERIA**

### **Functional Requirements**:
- ✅ All ASR, TTS, NMT services working independently
- ✅ WebSocket streaming support
- ✅ Real-time frontend interface
- ✅ Complete API documentation
- ✅ Database integration working

### **Non-Functional Requirements**:
- ✅ Response time < 2 seconds for batch requests
- ✅ Streaming latency < 500ms
- ✅ 99.9% uptime
- ✅ Horizontal scaling capability
- ✅ Comprehensive error handling

### **Migration Requirements**:
- ✅ 100% feature parity with Dhruva-Platform-2
- ✅ Zero data loss during migration
- ✅ Backward compatibility maintained
- ✅ Performance improvements achieved

---

## 📚 **IMPLEMENTATION TIMELINE**

### **Week 1-2: Foundation Setup**
- Database schema updates
- Service folder structure creation
- Basic service scaffolding

### **Week 3-4: ASR Microservice**
- Core ASR service implementation
- WebSocket streaming
- Database integration

### **Week 5-6: TTS Microservice**
- Core TTS service implementation
- Voice management
- Audio generation

### **Week 7-8: NMT Microservice**
- Core NMT service implementation
- Language processing
- Translation quality metrics

### **Week 9-10: Frontend Development**
- Next.js application setup
- Service integration
- Real-time capabilities

### **Week 11-12: Testing & Deployment**
- Comprehensive testing
- Performance optimization
- Production deployment

---

## 🚀 **QUICK START COMMANDS**

### **1. Start Infrastructure**
```bash
cd /home/appala/Projects/AI4V-Core/Ai4V-C
docker-compose up -d postgres redis influxdb elasticsearch kafka
```

### **2. Start Core Services**
```bash
docker-compose up -d api-gateway-service auth-service config-service
```

### **3. Start AI/ML Services**
```bash
docker-compose up -d asr-service tts-service nmt-service
```

### **4. Start Frontend**
```bash
docker-compose up -d simple-ui-frontend
```

### **5. Verify All Services**
```bash
./scripts/health-check-all.sh
```

---

## 📞 **SUPPORT AND MAINTENANCE**

### **Documentation**:
- API documentation with Swagger/OpenAPI
- Service architecture diagrams
- Deployment guides
- Troubleshooting guides

### **Monitoring**:
- Grafana dashboards
- Prometheus metrics
- Alert management
- Performance monitoring

### **Maintenance**:
- Regular security updates
- Performance optimization
- Feature enhancements
- Bug fixes and patches

---

This comprehensive implementation prompt provides a complete roadmap for building enterprise-grade AI/ML microservices based on the existing Dhruva Platform 2.0, following modern microservice architecture patterns and best practices.
