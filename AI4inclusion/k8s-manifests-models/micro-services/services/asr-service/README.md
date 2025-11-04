# ASR Service (Automatic Speech Recognition)

Microservice for converting speech to text using Triton Inference Server.

## Features

- Batch ASR inference
- Real-time WebSocket streaming
- Support for 22+ Indian languages
- Multiple audio format support (WAV, MP3, FLAC)
- Audio preprocessing (VAD, denoising)
- Post-processing (ITN, punctuation)
- N-best token output
- Multiple transcription formats (transcript, SRT, WebVTT)

## Architecture

```
Client → API Gateway → ASR Service → Triton Server
```

Layered architecture: Routers → Services → Repositories → Database

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Triton Inference Server
- Docker (optional)

## Installation

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment: `cp env.template .env`
4. Run migrations (if needed)

## Configuration

See `env.template` for all available environment variables.

## Authentication & Authorization

### API Key Authentication

All ASR inference endpoints require API key authentication. Include your API key in the request header:

```bash
curl -X POST http://localhost:8087/api/v1/asr/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**Supported Header Formats:**
- `Authorization: Bearer <api_key>`
- `Authorization: ApiKey <api_key>`
- `Authorization: <api_key>`

### Rate Limiting

API requests are rate-limited per API key:
- **60 requests per minute**
- **1000 requests per hour**
- **10000 requests per day**

When rate limit is exceeded, you'll receive a `429 Too Many Requests` response with a `Retry-After` header.

**Rate Limit Headers:**
- `X-RateLimit-Limit-Minute`: Maximum requests per minute
- `X-RateLimit-Remaining-Minute`: Remaining requests in current minute
- `X-RateLimit-Limit-Hour`: Maximum requests per hour
- `X-RateLimit-Remaining-Hour`: Remaining requests in current hour

### Error Responses

**401 Unauthorized** - Missing or invalid API key:
```json
{
  "detail": {
    "message": "Invalid API key",
    "code": "AUTHENTICATION_ERROR",
    "timestamp": 1234567890.123
  }
}
```

**403 Forbidden** - Insufficient permissions:
```json
{
  "detail": {
    "message": "Not authorized",
    "code": "AUTHORIZATION_ERROR",
    "timestamp": 1234567890.123
  }
}
```

**429 Too Many Requests** - Rate limit exceeded:
```json
{
  "detail": {
    "message": "Rate limit exceeded",
    "code": "RATE_LIMIT_EXCEEDED",
    "timestamp": 1234567890.123
  }
}
```

### WebSocket Streaming Authentication

For WebSocket streaming, include API key as query parameter:

```javascript
const socket = io('http://localhost:8087/socket.io/asr', {
  transports: ['websocket'],
  query: {
    serviceId: 'vakyansh-asr-en',
    language: 'en',
    samplingRate: 16000,
    apiKey: 'YOUR_API_KEY'  // Add API key here
  }
});
```

### Request Logging

All authenticated requests are logged to the database with:
- User ID
- API key ID
- Session ID (if applicable)
- Request metadata (model, language, duration)
- Processing time
- Status (processing, completed, failed)

Logs are stored in `asr_requests` and `asr_results` tables for auditing and analytics.

## Usage

Start service: `uvicorn main:app --host 0.0.0.0 --port 8087`

## API Endpoints

- `POST /api/v1/asr/inference` - Batch inference
- `GET /api/v1/asr/models` - List models
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /live` - Liveness check
- `GET /streaming/info` - WebSocket streaming information

## WebSocket Streaming

### Overview
The ASR service supports real-time speech-to-text streaming via Socket.IO WebSocket protocol. This enables low-latency transcription for live audio streams.

### Connection

**Endpoint**: `ws://localhost:8087/socket.io/asr`

**Query Parameters**:
- `serviceId` (required): ASR model identifier (e.g., 'vakyansh-asr-en')
- `language` (required): Language code (e.g., 'en', 'hi', 'ta')
- `samplingRate` (required): Audio sample rate in Hz (e.g., 16000)
- `apiKey` (optional): API key for authentication
- `preProcessors` (optional): JSON array of preprocessors (e.g., '["vad"]')
- `postProcessors` (optional): JSON array of postprocessors (e.g., '["itn","punctuation"]')

**Example Connection URL**:
```
ws://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000
```

### Events

#### Client → Server Events

1. **`start`** - Initialize streaming session
   - Payload: `{config: {responseFrequencyInMs: 2000}}` (optional)
   - Response: Server emits `ready` event

2. **`data`** - Send audio chunk
   - Payload: `{audioData: bytes, isSpeaking: bool, disconnectStream: bool}`
   - `audioData`: Raw PCM audio bytes (int16)
   - `isSpeaking`: Whether user is currently speaking (for VAD)
   - `disconnectStream`: Whether to close stream after this chunk

3. **`disconnect`** - Close connection
   - No payload required

#### Server → Client Events

1. **`ready`** - Stream is ready to receive audio
   - Emitted after `start` event

2. **`response`** - Partial or final transcript
   - Payload: `{transcript: str, isFinal: bool, confidence: float, timestamp: float, language: str}`
   - `isFinal`: True if this is the final transcript for current segment

3. **`error`** - Error occurred
   - Payload: `{error: str, code: str, timestamp: float}`

4. **`terminate`** - Stream terminated
   - Emitted when stream is closed

### Usage Example (Python Client)

```python
import socketio
import pyaudio

# Create Socket.IO client
sio = socketio.Client()

# Event handlers
@sio.on('ready')
def on_ready():
    print('Stream ready, starting audio capture...')
    start_audio_capture()

@sio.on('response')
def on_response(data):
    print(f"Transcript: {data['transcript']} (final={data['isFinal']})")

@sio.on('error')
def on_error(data):
    print(f"Error: {data['error']}")

# Connect
url = 'http://localhost:8087/socket.io/asr'
params = {
    'serviceId': 'vakyansh-asr-en',
    'language': 'en',
    'samplingRate': 16000
}
sio.connect(url, transports=['websocket'], query_string=params)

# Start streaming
sio.emit('start')

# Send audio chunks
def send_audio_chunk(audio_bytes, is_speaking):
    sio.emit('data', {
        'audioData': audio_bytes,
        'isSpeaking': is_speaking,
        'disconnectStream': False
    })

# Disconnect
sio.emit('data', {
    'audioData': b'',
    'isSpeaking': False,
    'disconnectStream': True
})
sio.disconnect()
```

### Usage Example (JavaScript Client)

```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:8087/socket.io/asr', {
  transports: ['websocket'],
  query: {
    serviceId: 'vakyansh-asr-en',
    language: 'en',
    samplingRate: 16000
  }
});

socket.on('connect', () => {
  console.log('Connected to ASR streaming service');
  socket.emit('start');
});

socket.on('ready', () => {
  console.log('Stream ready');
  // Start capturing audio from microphone
  startAudioCapture();
});

socket.on('response', (data) => {
  console.log(`Transcript: ${data.transcript} (final=${data.isFinal})`);
});

socket.on('error', (data) => {
  console.error(`Error: ${data.error}`);
});

// Send audio chunk
function sendAudioChunk(audioData, isSpeaking) {
  socket.emit('data', {
    audioData: audioData,
    isSpeaking: isSpeaking,
    disconnectStream: false
  });
}

// Disconnect
function disconnect() {
  socket.emit('data', {
    audioData: new ArrayBuffer(0),
    isSpeaking: false,
    disconnectStream: true
  });
}
```

### Configuration

**Response Frequency**: Control how often partial transcripts are emitted
- Default: 2000ms (2 seconds)
- Configurable via `STREAMING_RESPONSE_FREQUENCY_MS` environment variable
- Can be updated per-session via `start` event payload

**VAD (Voice Activity Detection)**:
- Automatically detects speech segments
- Triggers inference when silence is detected
- Enable via `preProcessors=["vad"]` query parameter

**Buffer Management**:
- Audio chunks are accumulated in server-side buffer
- Inference runs at configured frequency or when buffer is full
- Buffer is cleared after silence detection or manual reset

### Performance Considerations

- **Latency**: Typical end-to-end latency is 500-1000ms
- **Throughput**: Each worker can handle ~100 concurrent streams
- **Audio Format**: PCM int16 recommended for best performance
- **Sample Rate**: 16kHz recommended (8kHz-48kHz supported)

### Troubleshooting

**Connection Issues**:
- Ensure Socket.IO client uses `websocket` transport
- Check query parameters are properly URL-encoded
- Verify Triton server is accessible

**Audio Quality Issues**:
- Use correct sample rate (16kHz recommended)
- Ensure audio is mono (stereo will be converted)
- Check audio format is PCM int16

**Latency Issues**:
- Reduce `responseFrequencyInMs` for faster updates
- Enable VAD for better segmentation
- Check network latency between client and server

## Docker Deployment

Build image: `docker build -t asr-service:latest .`
Run container: `docker run -p 8087:8087 --env-file .env asr-service:latest`

## License

MIT License
