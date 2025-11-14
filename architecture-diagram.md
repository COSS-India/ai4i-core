# Ai4V-C Microservices Architecture Diagram

## Visual ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    AI4V-C MICROSERVICES PLATFORM                                │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    EXTERNAL LAYER                                               │
│  ┌─────────────┐    ┌─────────────────────────────────────────────────────────────────────┐    │
│  │     👤      │    │                    📱 Client Applications                            │    │
│  │   Users     │────│              (Web, Mobile, API Clients)                             │    │
│  └─────────────┘    └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    FRONTEND LAYER                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                    🌐 Simple UI Frontend (Next.js 13 + TypeScript)                     │    │
│  │                              Port: 3000                                                │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │    │
│  │  │   🎤 ASR    │ │   🔊 TTS    │ │   🌐 NMT    │ │  📊 Real-time│ │  🔧 Settings│      │    │
│  │  │  Interface  │ │  Interface  │ │  Interface  │ │  Streaming  │ │   Panel     │      │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │    │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  API GATEWAY LAYER                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                    🚪 API Gateway Service (FastAPI + httpx)                            │    │
│  │                              Port: 8080                                                │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │    │
│  │  │ 🔐 Auth     │ │ ⚡ Rate     │ │ 🛣️  Request │ │ ⚖️  Load    │ │ 🔄 Service  │      │    │
│  │  │ Middleware  │ │ Limiting    │ │ Routing     │ │ Balancing   │ │ Discovery   │      │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │    │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  CORE SERVICES LAYER                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐│
│  │ 🔐 Auth     │ │ ⚙️  Config  │ │ 📊 Metrics  │ │ 📡 Telemetry│ │ 🚨 Alerting │ │ 📈 Dashboard││
│  │ Service     │ │ Service     │ │ Service     │ │ Service     │ │ Service     │ │ Service     ││
│  │ Port: 8081  │ │ Port: 8082  │ │ Port: 8083  │ │ Port: 8084  │ │ Port: 8085  │ │ Port: 8090  ││
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘│
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 AI/ML SERVICES LAYER                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────────────────┐  │
│  │ 🎤 ASR      │ │ 🔊 TTS      │ │ 🌐 NMT      │ │         🤖 Triton Inference Server      │  │
│  │ Service     │ │ Service     │ │ Service     │ │        (GPU-Accelerated Models)         │  │
│  │ Port: 8087  │ │ Port: 8088  │ │ Port: 8089  │ │     - ASR Models (22+ Languages)       │  │
│  │             │ │             │ │             │ │     - TTS Models (Multiple Voices)      │  │
│  │ • Audio     │ │ • Voice     │ │ • Language  │ │     - NMT Models (Bidirectional)       │  │
│  │   Processing│ │   Management│ │   Detection │ │     - Real-time Inference               │  │
│  │ • Streaming │ │ • Audio Gen │ │ • Translation│ │     - Batch Processing                 │  │
│  │ • VAD       │ │ • SSML      │ │ • Quality   │ │     - Dynamic Batching                  │  │
│  │ • ITN       │ │ • Streaming │ │   Metrics   │ │                                        │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              MIDDLEWARE & CACHING LAYER                                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────────────────┐  │
│  │ 💾 Redis    │ │ 📨 Kafka    │ │ 🐘 Zookeeper│ │              Caching Strategy            │  │
│  │ Cache       │ │ Message     │ │ Coordination│ │                                        │  │
│  │ Port: 6381  │ │ Broker      │ │ Port: 2181  │ │  • API Keys (300s TTL)                 │  │
│  │             │ │ Port: 9093  │ │             │ │  • Rate Limiting Counters              │  │
│  │ • API Key   │ │             │ │ • Kafka     │ │  • Session Storage                      │  │
│  │   Cache     │ │ • Event     │ │   Coordination│ │  • Service Registry                    │  │
│  │ • Rate      │ │   Streaming │ │ • Service   │ │  • Model Metadata Cache                 │  │
│  │   Limiting  │ │ • Message   │ │   Discovery │ │  • Real-time Data                       │  │
│  │ • Session   │ │   Queuing   │ │ • Load      │ │                                        │  │
│  │   Storage   │ │ • Service   │ │   Balancing │ │                                        │  │
│  │ • Service   │ │   Comm      │ │ • Failover  │ │                                        │  │
│  │   Registry  │ │ • Real-time │ │   Management│ │                                        │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  DATA STORAGE LAYER                                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────────────────┐  │
│  │ 🗄️ PostgreSQL│ │ 📈 InfluxDB │ │ 🔍 Elasticsearch│ │            Data Organization           │  │
│  │ Primary DB  │ │ Time Series │ │ Search &    │ │                                        │  │
│  │ Port: 5434  │ │ Port: 8089  │ │ Analytics   │ │  • Users & Authentication              │  │
│  │             │ │             │ │ Port: 9203  │ │  • API Keys & Sessions                 │  │
│  │ • Users     │ │ • Metrics   │ │             │ │  • Request/Response Logs               │  │
│  │ • API Keys  │ │ • Performance│ │ • Logs      │ │  • ASR/TTS/NMT Results                │  │
│  │ • Sessions  │ │ • Monitoring│ │ • Search    │ │  • Time Series Metrics                 │  │
│  │ • Requests  │ │ • Analytics │ │ • Analytics │ │  • Full-text Search                    │  │
│  │ • Results   │ │ • Dashboards│ │ • Telemetry │ │  • Real-time Analytics                 │  │
│  │ • Audit     │ │ • Alerts    │ │ • Events    │ │  • Performance Monitoring              │  │
│  │   Logs      │ │ • Reports   │ │ • Monitoring│ │                                        │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 EXTERNAL INTEGRATIONS                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────────────────┐  │
│  │ 📊 Grafana  │ │ 🔍 Prometheus│ │ 🚨 AlertManager│ │            Monitoring Stack            │  │
│  │ Dashboards  │ │ Metrics     │ │ Alerts      │ │                                        │  │
│  │             │ │ Collection  │ │ Management  │ │  • Real-time Dashboards                │  │
│  │ • Visual    │ │             │ │             │ │  • Performance Metrics                 │  │
│  │   Analytics │ │ • Service   │ │ • Threshold  │ │  • Service Health Monitoring          │  │
│  │ • KPI       │ │   Discovery │ │   Alerts    │ │  • Resource Utilization                │  │
│  │   Tracking  │ │ • Health    │ │ • Escalation│ │  • Custom Dashboards                   │  │
│  │ • Custom    │ │   Checks    │ │ • Notifications│ │  • Historical Data Analysis           │  │
│  │   Dashboards│ │ • Resource  │ │ • Integration│ │                                        │  │
│  │ • Reports   │ │   Monitoring│ │   with PagerDuty│ │                                        │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    NETWORK ARCHITECTURE                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                    🌐 Microservices Network (172.25.0.0/16)                           │    │
│  │                                                                                         │    │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │    │
│  │  │   Frontend  │◄──►│   Gateway   │◄──►│   Services  │◄──►│   Storage   │              │    │
│  │  │   (3000)    │    │   (8080)    │    │ (8081-8090) │    │ (5434,6381) │              │    │
│  │  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘              │    │
│  │         │                   │                   │                   │                  │    │
│  │         │                   │                   │                   │                  │    │
│  │         ▼                   ▼                   ▼                   ▼                  │    │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │    │
│  │  │   WebSocket │    │   Load      │    │   Service   │    │   Data      │              │    │
│  │  │   Streaming │    │   Balancer  │    │   Registry  │    │   Pipeline  │              │    │
│  │  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘              │    │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Visual Mermaid Architecture Diagram (Reference Style)

```mermaid
graph LR
    %% Client and Identity Provider
    CLIENT[Client<br/>Web/Mobile Apps<br/>Port: 3000]
    IDENTITY[Identity Provider<br/>Auth Service<br/>Port: 8081]
    
    %% API Gateway (Central Hub)
    GATEWAY[API Gateway<br/>FastAPI + httpx<br/>Port: 8080<br/>Auth + Routing + Load Balancing]
    
    %% Microservices Cluster
    subgraph MICROSERVICES["Microservices"]
        AUTH_SVC[Auth Service<br/>Port: 8081]
        CONFIG_SVC[Config Service<br/>Port: 8082]
        METRICS_SVC[Metrics Service<br/>Port: 8083]
        TELEMETRY_SVC[Telemetry Service<br/>Port: 8084]
        ALERTING_SVC[Alerting Service<br/>Port: 8085]
        DASHBOARD_SVC[Dashboard Service<br/>Port: 8090]
        ASR_SVC[ASR Service<br/>Port: 8087]
        TTS_SVC[TTS Service<br/>Port: 8088]
        NMT_SVC[NMT Service<br/>Port: 8089]
    end
    
    %% External Services
    TRITON[Triton Inference Server<br/>GPU Models<br/>22+ Languages]
    
    %% Supporting Infrastructure
    STATIC[Static Content<br/>Next.js Assets]
    CDN[CDN<br/>Content Delivery]
    MANAGEMENT[Management<br/>Docker Compose<br/>Service Orchestration]
    SERVICE_DISCOVERY[Service Discovery<br/>Redis Registry<br/>Port: 6381]
    
    %% Data Storage
    POSTGRES[PostgreSQL<br/>Primary Database<br/>Port: 5434]
    REDIS[Redis Cache<br/>Sessions & API Keys<br/>Port: 6381]
    INFLUXDB[InfluxDB<br/>Time Series Data<br/>Port: 8089]
    ELASTICSEARCH[Elasticsearch<br/>Search & Analytics<br/>Port: 9203]
    KAFKA[Kafka<br/>Event Streaming<br/>Port: 9093]
    
    %% Monitoring
    GRAFANA[Grafana<br/>Dashboards]
    PROMETHEUS[Prometheus<br/>Metrics Collection]
    
    %% Main Flow
    CLIENT --> IDENTITY
    CLIENT --> GATEWAY
    IDENTITY --> GATEWAY
    GATEWAY --> MICROSERVICES
    
    %% Microservices to External Services
    ASR_SVC --> TRITON
    TTS_SVC --> TRITON
    NMT_SVC --> TRITON
    
    %% Static Content Flow
    STATIC --> CDN
    CDN --> CLIENT
    
    %% Management Flow
    MANAGEMENT --> SERVICE_DISCOVERY
    MANAGEMENT --> MICROSERVICES
    SERVICE_DISCOVERY --> MICROSERVICES
    
    %% Data Connections
    AUTH_SVC --> POSTGRES
    AUTH_SVC --> REDIS
    CONFIG_SVC --> POSTGRES
    CONFIG_SVC --> REDIS
    CONFIG_SVC --> KAFKA
    METRICS_SVC --> POSTGRES
    METRICS_SVC --> REDIS
    METRICS_SVC --> INFLUXDB
    TELEMETRY_SVC --> POSTGRES
    TELEMETRY_SVC --> REDIS
    TELEMETRY_SVC --> ELASTICSEARCH
    TELEMETRY_SVC --> KAFKA
    ALERTING_SVC --> POSTGRES
    ALERTING_SVC --> REDIS
    ALERTING_SVC --> KAFKA
    DASHBOARD_SVC --> POSTGRES
    DASHBOARD_SVC --> REDIS
    DASHBOARD_SVC --> INFLUXDB
    ASR_SVC --> POSTGRES
    ASR_SVC --> REDIS
    TTS_SVC --> POSTGRES
    TTS_SVC --> REDIS
    NMT_SVC --> POSTGRES
    NMT_SVC --> REDIS
    
    %% Monitoring Connections
    METRICS_SVC --> GRAFANA
    METRICS_SVC --> PROMETHEUS
    TELEMETRY_SVC --> ELASTICSEARCH
    
    %% Styling to match reference image
    classDef client fill:#e3f2fd,stroke:#1976d2,stroke-width:2px,color:#000
    classDef identity fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000
    classDef gateway fill:#fff3e0,stroke:#f57c00,stroke-width:3px,color:#000
    classDef microservice fill:#e8f5e8,stroke:#388e3c,stroke-width:2px,color:#000
    classDef external fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#000
    classDef infrastructure fill:#e0f2f1,stroke:#00796b,stroke-width:2px,color:#000
    classDef data fill:#f1f8e9,stroke:#689f38,stroke-width:2px,color:#000
    classDef monitoring fill:#f5f5f5,stroke:#616161,stroke-width:2px,color:#000
    
    class CLIENT client
    class IDENTITY identity
    class GATEWAY gateway
    class AUTH_SVC,CONFIG_SVC,METRICS_SVC,TELEMETRY_SVC,ALERTING_SVC,DASHBOARD_SVC,ASR_SVC,TTS_SVC,NMT_SVC microservice
    class TRITON external
    class STATIC,CDN,MANAGEMENT,SERVICE_DISCOVERY infrastructure
    class POSTGRES,REDIS,INFLUXDB,ELASTICSEARCH,KAFKA data
    class GRAFANA,PROMETHEUS monitoring
```

## Reference-Style Microservices Architecture

```mermaid
graph LR
    %% Left Side - Client and Identity
    CLIENT[Client<br/>Web/Mobile Apps<br/>Next.js Frontend<br/>Port: 3000]
    IDENTITY[Identity Provider<br/>Auth Service<br/>JWT + API Keys<br/>Port: 8081]
    
    %% Center - API Gateway (Central Hub)
    GATEWAY[API Gateway<br/>FastAPI + httpx<br/>Port: 8080<br/>Authentication + Routing + Load Balancing + Rate Limiting]
    
    %% Right Side - Microservices Cluster
    subgraph MICROSERVICES["Microservices Cluster"]
        direction TB
        AUTH[Auth Service<br/>Port: 8081]
        CONFIG[Config Service<br/>Port: 8082]
        METRICS[Metrics Service<br/>Port: 8083]
        TELEMETRY[Telemetry Service<br/>Port: 8084]
        ALERTING[Alerting Service<br/>Port: 8085]
        DASHBOARD[Dashboard Service<br/>Port: 8090]
        ASR[ASR Service<br/>Port: 8087]
        TTS[TTS Service<br/>Port: 8088]
        NMT[NMT Service<br/>Port: 8089]
    end
    
    %% External Service (like Remote Service in reference)
    TRITON[Triton Inference Server<br/>GPU-Accelerated AI Models<br/>22+ Indian Languages<br/>Real-time Inference]
    
    %% Bottom Row - Supporting Infrastructure
    STATIC[Static Content<br/>Next.js Assets<br/>Images, CSS, JS]
    CDN[CDN<br/>Content Delivery Network<br/>Global Distribution]
    MANAGEMENT[Management<br/>Docker Compose<br/>Service Orchestration<br/>Health Checks]
    SERVICE_DISCOVERY[Service Discovery<br/>Redis Registry<br/>Load Balancing<br/>Port: 6381]
    
    %% Data Storage Layer
    POSTGRES[PostgreSQL<br/>Primary Database<br/>Users, API Keys, Results<br/>Port: 5434]
    REDIS[Redis Cache<br/>Sessions, API Keys<br/>Rate Limiting<br/>Port: 6381]
    INFLUXDB[InfluxDB<br/>Time Series Data<br/>Metrics, Performance<br/>Port: 8089]
    ELASTICSEARCH[Elasticsearch<br/>Search & Analytics<br/>Logs, Telemetry<br/>Port: 9203]
    KAFKA[Kafka<br/>Event Streaming<br/>Message Queuing<br/>Port: 9093]
    
    %% Monitoring Stack
    GRAFANA[Grafana<br/>Dashboards<br/>Visualization]
    PROMETHEUS[Prometheus<br/>Metrics Collection<br/>Monitoring]
    
    %% Main Request Flow (matching reference image)
    CLIENT --> IDENTITY
    CLIENT --> GATEWAY
    IDENTITY --> GATEWAY
    GATEWAY --> MICROSERVICES
    
    %% External Service Connection (like Remote Service in reference)
    ASR --> TRITON
    TTS --> TRITON
    NMT --> TRITON
    
    %% Static Content Flow (matching reference image)
    STATIC --> CDN
    CDN --> CLIENT
    
    %% Management Flow (matching reference image)
    MANAGEMENT --> SERVICE_DISCOVERY
    MANAGEMENT --> MICROSERVICES
    SERVICE_DISCOVERY --> MICROSERVICES
    
    %% Data Layer Connections
    AUTH --> POSTGRES
    AUTH --> REDIS
    CONFIG --> POSTGRES
    CONFIG --> REDIS
    CONFIG --> KAFKA
    METRICS --> POSTGRES
    METRICS --> REDIS
    METRICS --> INFLUXDB
    TELEMETRY --> POSTGRES
    TELEMETRY --> REDIS
    TELEMETRY --> ELASTICSEARCH
    TELEMETRY --> KAFKA
    ALERTING --> POSTGRES
    ALERTING --> REDIS
    ALERTING --> KAFKA
    DASHBOARD --> POSTGRES
    DASHBOARD --> REDIS
    DASHBOARD --> INFLUXDB
    ASR --> POSTGRES
    ASR --> REDIS
    TTS --> POSTGRES
    TTS --> REDIS
    NMT --> POSTGRES
    NMT --> REDIS
    
    %% Monitoring Connections
    METRICS --> GRAFANA
    METRICS --> PROMETHEUS
    TELEMETRY --> ELASTICSEARCH
    
    %% Styling to closely match reference image
    classDef client fill:#e3f2fd,stroke:#1976d2,stroke-width:2px,color:#000
    classDef identity fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000
    classDef gateway fill:#fff3e0,stroke:#f57c00,stroke-width:3px,color:#000
    classDef microservice fill:#e8f5e8,stroke:#388e3c,stroke-width:2px,color:#000
    classDef external fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#000
    classDef infrastructure fill:#e0f2f1,stroke:#00796b,stroke-width:2px,color:#000
    classDef data fill:#f1f8e9,stroke:#689f38,stroke-width:2px,color:#000
    classDef monitoring fill:#f5f5f5,stroke:#616161,stroke-width:2px,color:#000
    
    class CLIENT client
    class IDENTITY identity
    class GATEWAY gateway
    class AUTH,CONFIG,METRICS,TELEMETRY,ALERTING,DASHBOARD,ASR,TTS,NMT microservice
    class TRITON external
    class STATIC,CDN,MANAGEMENT,SERVICE_DISCOVERY infrastructure
    class POSTGRES,REDIS,INFLUXDB,ELASTICSEARCH,KAFKA data
    class GRAFANA,PROMETHEUS monitoring
```

## Simplified Pictorial Architecture

```mermaid
graph LR
    subgraph "🌍 User Interface"
        A[👤 User] --> B[📱 Web/Mobile App]
    end

    subgraph "🎨 Frontend Layer"
        B --> C[🌐 Next.js UI<br/>Port 3000]
    end

    subgraph "🚪 API Gateway"
        C --> D[🚪 API Gateway<br/>Port 8080<br/>Auth + Routing]
    end

    subgraph "⚙️ Core Services"
        D --> E[🔐 Auth<br/>Port 8081]
        D --> F[⚙️ Config<br/>Port 8082]
        D --> G[📊 Metrics<br/>Port 8083]
        D --> H[📡 Telemetry<br/>Port 8084]
        D --> I[🚨 Alerting<br/>Port 8085]
        D --> J[📈 Dashboard<br/>Port 8090]
    end

    subgraph "🤖 AI Services"
        D --> K[🎤 ASR<br/>Port 8087]
        D --> L[🔊 TTS<br/>Port 8088]
        D --> M[🌐 NMT<br/>Port 8089]
        K --> N[🤖 Triton Server]
        L --> N
        M --> N
    end

    subgraph "💾 Data Layer"
        E --> O[🗄️ PostgreSQL<br/>Port 5434]
        F --> O
        G --> P[📈 InfluxDB<br/>Port 8089]
        H --> Q[🔍 Elasticsearch<br/>Port 9203]
        K --> O
        L --> O
        M --> O
    end

    subgraph "🔄 Middleware"
        D --> R[💾 Redis<br/>Port 6381]
        H --> S[📨 Kafka<br/>Port 9093]
        S --> T[🐘 Zookeeper<br/>Port 2181]
    end

    subgraph "📊 Monitoring"
        G --> U[📊 Grafana]
        H --> V[🔍 Prometheus]
        I --> W[🚨 AlertManager]
    end

    classDef user fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    classDef frontend fill:#f3e5f5,stroke:#7b1fa2,stroke-width:3px
    classDef gateway fill:#fff3e0,stroke:#f57c00,stroke-width:3px
    classDef core fill:#e8f5e8,stroke:#388e3c,stroke-width:3px
    classDef ai fill:#fce4ec,stroke:#c2185b,stroke-width:3px
    classDef data fill:#e0f2f1,stroke:#00796b,stroke-width:3px
    classDef middleware fill:#f1f8e9,stroke:#689f38,stroke-width:3px
    classDef monitoring fill:#f5f5f5,stroke:#616161,stroke-width:3px

    class A,B user
    class C frontend
    class D gateway
    class E,F,G,H,I,J core
    class K,L,M,N ai
    class O,P,Q data
    class R,S,T middleware
    class U,V,W monitoring
```

## Complete System Architecture

```mermaid
graph TB
    %% External Layer
    subgraph "External Layer"
        USER[👤 User]
        CLIENT[📱 Client Applications]
    end

    %% Frontend Layer
    subgraph "Frontend Layer"
        UI[🌐 Simple UI Frontend<br/>Next.js 13 + TypeScript<br/>Port: 3000]
        UI_COMPONENTS[📦 UI Components<br/>- ASR Interface<br/>- TTS Interface<br/>- NMT Interface<br/>- Real-time Streaming]
    end

    %% API Gateway Layer
    subgraph "API Gateway Layer"
        GATEWAY[🚪 API Gateway Service<br/>FastAPI + httpx<br/>Port: 8080]
        GATEWAY_MIDDLEWARE[🔧 Gateway Middleware<br/>- Authentication<br/>- Rate Limiting<br/>- Request Routing<br/>- Load Balancing]
    end

    %% Core Services Layer
    subgraph "Core Services Layer"
        AUTH[🔐 Auth Service<br/>FastAPI<br/>Port: 8081]
        CONFIG[⚙️ Config Service<br/>FastAPI<br/>Port: 8082]
        METRICS[📊 Metrics Service<br/>FastAPI<br/>Port: 8083]
        TELEMETRY[📡 Telemetry Service<br/>FastAPI<br/>Port: 8084]
        ALERTING[🚨 Alerting Service<br/>FastAPI<br/>Port: 8085]
        DASHBOARD[📈 Dashboard Service<br/>FastAPI + Streamlit<br/>Port: 8090/8501]
    end

    %% AI/ML Services Layer
    subgraph "AI/ML Services Layer"
        ASR[🎤 ASR Service<br/>FastAPI + Triton<br/>Port: 8087]
        TTS[🔊 TTS Service<br/>FastAPI + Triton<br/>Port: 8088]
        NMT[🌐 NMT Service<br/>FastAPI + Triton<br/>Port: 8089]
    end

    %% Middleware & Caching Layer
    subgraph "Middleware & Caching Layer"
        REDIS[💾 Redis Cache<br/>Port: 6381<br/>- API Key Cache<br/>- Rate Limiting<br/>- Session Storage<br/>- Service Registry]
        KAFKA[📨 Apache Kafka<br/>Port: 9093<br/>- Event Streaming<br/>- Message Queuing<br/>- Service Communication]
        ZOOKEEPER[🐘 Zookeeper<br/>Port: 2181<br/>- Kafka Coordination]
    end

    %% Data Storage Layer
    subgraph "Data Storage Layer"
        POSTGRES[🗄️ PostgreSQL<br/>Port: 5434<br/>- User Management<br/>- API Keys<br/>- Request Logging<br/>- Results Storage]
        INFLUXDB[📈 InfluxDB<br/>Port: 8089<br/>- Time Series Data<br/>- Metrics Storage<br/>- Performance Data]
        ELASTICSEARCH[🔍 Elasticsearch<br/>Port: 9203<br/>- Log Storage<br/>- Search & Analytics<br/>- Telemetry Data]
    end

    %% Model Serving Layer
    subgraph "Model Serving Layer"
        TRITON[🤖 Triton Inference Server<br/>- ASR Models<br/>- TTS Models<br/>- NMT Models<br/>- GPU Acceleration]
    end

    %% External Integrations
    subgraph "External Integrations"
        MONITORING[📊 Monitoring Stack<br/>- Grafana<br/>- Prometheus<br/>- AlertManager]
        LOGGING[📝 Logging Stack<br/>- ELK Stack<br/>- Log Aggregation]
    end

    %% Connection Flows
    USER --> CLIENT
    CLIENT --> UI
    UI --> UI_COMPONENTS
    UI_COMPONENTS --> GATEWAY

    GATEWAY --> GATEWAY_MIDDLEWARE
    GATEWAY_MIDDLEWARE --> AUTH
    GATEWAY_MIDDLEWARE --> CONFIG
    GATEWAY_MIDDLEWARE --> METRICS
    GATEWAY_MIDDLEWARE --> TELEMETRY
    GATEWAY_MIDDLEWARE --> ALERTING
    GATEWAY_MIDDLEWARE --> DASHBOARD
    GATEWAY_MIDDLEWARE --> ASR
    GATEWAY_MIDDLEWARE --> TTS
    GATEWAY_MIDDLEWARE --> NMT

    %% Service Dependencies
    AUTH --> REDIS
    AUTH --> POSTGRES
    CONFIG --> REDIS
    CONFIG --> POSTGRES
    CONFIG --> KAFKA
    METRICS --> REDIS
    METRICS --> POSTGRES
    METRICS --> INFLUXDB
    TELEMETRY --> REDIS
    TELEMETRY --> POSTGRES
    TELEMETRY --> ELASTICSEARCH
    TELEMETRY --> KAFKA
    ALERTING --> REDIS
    ALERTING --> POSTGRES
    ALERTING --> KAFKA
    DASHBOARD --> REDIS
    DASHBOARD --> POSTGRES
    DASHBOARD --> INFLUXDB

    %% AI/ML Service Dependencies
    ASR --> REDIS
    ASR --> POSTGRES
    ASR --> TRITON
    TTS --> REDIS
    TTS --> POSTGRES
    TTS --> TRITON
    NMT --> REDIS
    NMT --> POSTGRES
    NMT --> TRITON

    %% Infrastructure Dependencies
    KAFKA --> ZOOKEEPER

    %% Monitoring Connections
    METRICS --> MONITORING
    TELEMETRY --> LOGGING
    ALERTING --> MONITORING

    %% Styling
    classDef frontend fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef gateway fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef core fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef ai fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef middleware fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef storage fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    classDef model fill:#f1f8e9,stroke:#33691e,stroke-width:2px
    classDef external fill:#f5f5f5,stroke:#424242,stroke-width:2px

    class UI,UI_COMPONENTS frontend
    class GATEWAY,GATEWAY_MIDDLEWARE gateway
    class AUTH,CONFIG,METRICS,TELEMETRY,ALERTING,DASHBOARD core
    class ASR,TTS,NMT ai
    class REDIS,KAFKA,ZOOKEEPER middleware
    class POSTGRES,INFLUXDB,ELASTICSEARCH storage
    class TRITON model
    class USER,CLIENT,MONITORING,LOGGING external
```

## Detailed Service Communication Flow

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Simple UI
    participant GW as API Gateway
    participant AUTH as Auth Service
    participant REDIS as Redis Cache
    participant ASR as ASR Service
    participant POSTGRES as PostgreSQL
    participant TRITON as Triton Server

    U->>UI: Upload Audio File
    UI->>GW: POST /api/v1/asr/inference
    GW->>GW: Extract API Key
    GW->>REDIS: Check API Key Cache
    alt Cache Miss
        REDIS-->>GW: Key Not Found
        GW->>AUTH: Validate API Key
        AUTH->>POSTGRES: Query api_keys table
        POSTGRES-->>AUTH: Return key details
        AUTH-->>GW: Key validation result
        GW->>REDIS: Cache API key (TTL: 300s)
    else Cache Hit
        REDIS-->>GW: Return cached key
    end
    GW->>GW: Check Rate Limits
    GW->>ASR: Forward ASR Request
    ASR->>POSTGRES: Log asr_requests
    ASR->>TRITON: Send audio for inference
    TRITON-->>ASR: Return transcript
    ASR->>POSTGRES: Store asr_results
    ASR-->>GW: Return transcript
    GW-->>UI: Return ASR response
    UI-->>U: Display transcript
```

## Data Flow Architecture

```mermaid
graph LR
    subgraph "Request Flow"
        A[User Request] --> B[UI Frontend]
        B --> C[API Gateway]
        C --> D[Service Router]
        D --> E[Target Service]
    end

    subgraph "Authentication Flow"
        F[API Key] --> G[Redis Cache]
        G --> H{Key Found?}
        H -->|Yes| I[Validate Key]
        H -->|No| J[Query PostgreSQL]
        J --> K[Cache Key]
        K --> I
        I --> L[Authorize Request]
    end

    subgraph "Data Processing Flow"
        M[Audio/Text Input] --> N[Service Processing]
        N --> O[Triton Inference]
        O --> P[Post Processing]
        P --> Q[Store Results]
        Q --> R[Return Response]
    end

    subgraph "Caching Strategy"
        S[API Keys] --> T[Redis - 300s TTL]
        U[Rate Limits] --> V[Redis Counters]
        W[Model Metadata] --> X[In-Memory Cache]
    end

    subgraph "Monitoring Flow"
        Y[Service Metrics] --> Z[InfluxDB]
        AA[Logs] --> BB[Elasticsearch]
        CC[Events] --> DD[Kafka]
        DD --> EE[Alerting Service]
    end
```

## Technology Stack Summary

### Frontend Layer
- **Next.js 13** with TypeScript
- **Chakra UI** for components
- **TanStack React Query** for state management
- **Axios** for API communication
- **WebSocket** for real-time streaming

### API Gateway Layer
- **FastAPI** with async/await
- **httpx** for service communication
- **Redis** for caching and rate limiting
- **Service discovery** and load balancing

### Core Services
- **FastAPI** microservices
- **PostgreSQL** for data persistence
- **Redis** for caching and sessions
- **Kafka** for event streaming

### AI/ML Services
- **FastAPI** with Triton integration
- **Triton Inference Server** for model serving
- **librosa/soundfile** for audio processing
- **WebSocket** for real-time streaming

### Data Storage
- **PostgreSQL** (Primary database)
- **Redis** (Caching and sessions)
- **InfluxDB** (Time series metrics)
- **Elasticsearch** (Logs and search)

### Infrastructure
- **Docker Compose** for orchestration
- **Kafka + Zookeeper** for messaging
- **Health checks** for all services
- **Network isolation** with custom bridge

## Port Allocation

| Service | Port | Purpose |
|---------|------|---------|
| Simple UI | 3000 | Frontend interface |
| API Gateway | 8080 | Central entry point |
| Auth Service | 8081 | Authentication |
| Config Service | 8082 | Configuration management |
| Metrics Service | 8083 | Metrics collection |
| Telemetry Service | 8084 | Telemetry data |
| Alerting Service | 8085 | Alert management |
| Dashboard Service | 8090/8501 | Monitoring dashboard |
| ASR Service | 8087 | Speech-to-Text |
| TTS Service | 8088 | Text-to-Speech |
| NMT Service | 8089 | Neural Translation |
| PostgreSQL | 5434 | Primary database |
| Redis | 6381 | Caching layer |
| InfluxDB | 8089 | Time series DB |
| Elasticsearch | 9203 | Search engine |
| Kafka | 9093 | Message broker |
| Zookeeper | 2181 | Kafka coordination |

## Security Architecture

```mermaid
graph TB
    subgraph "Security Layers"
        A[API Key Authentication] --> B[JWT Token Validation]
        B --> C[Role-Based Access Control]
        C --> D[Rate Limiting]
        D --> E[Request Validation]
        E --> F[Data Encryption]
    end

    subgraph "Security Components"
        G[Auth Middleware] --> H[API Key Cache]
        I[Rate Limiter] --> J[Redis Counters]
        K[Input Validator] --> L[Pydantic Models]
        M[Encryption] --> N[HTTPS/TLS]
    end

    A --> G
    B --> G
    C --> I
    D --> I
    E --> K
    F --> M
```

This architecture provides a comprehensive, scalable, and maintainable microservices platform for AI/ML services with proper separation of concerns, caching strategies, and monitoring capabilities.
