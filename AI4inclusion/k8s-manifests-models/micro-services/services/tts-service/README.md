# TTS Service (Text-to-Speech)

Microservice for converting text to speech using Triton Inference Server.

## Features

- Batch TTS inference
- Support for 22+ Indian languages
- Multiple voice options (male/female)
- Multiple audio format support (WAV, MP3, OGG, PCM)
- Audio duration adjustment
- Text chunking for long inputs
- SSML support (basic)

## Architecture

```
Client → API Gateway → TTS Service → Triton Server
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

All TTS inference endpoints require API key authentication. Include your API key in the request header:

```bash
curl -X POST http://localhost:8088/api/v1/tts/inference \
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

### Request Logging

All authenticated requests are logged to the database with:
- User ID
- API key ID
- Session ID (if applicable)
- Request metadata (model, voice, language, text length)
- Processing time
- Status (processing, completed, failed)

Logs are stored in `tts_requests` and `tts_results` tables for auditing and analytics.

## Usage

Start service: `uvicorn main:app --host 0.0.0.0 --port 8088`

## API Endpoints

- `POST /api/v1/tts/inference` - Batch inference
- `GET /api/v1/tts/models` - List models
- `GET /api/v1/tts/voices` - List available voices
- `GET /api/v1/tts/voices/{voice_id}` - Get voice details
- `GET /api/v1/tts/voices/language/{language}` - List voices for language
- `GET /streaming/info` - Get streaming endpoint information
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /live` - Liveness check

## Voice Management

### Overview
The TTS service provides a voice catalog with multiple voices for different languages and genders. Each voice is associated with a specific TTS model and supports one or more languages.

### Available Voices

The service currently supports 6 voices across 3 model families:

1. **Dravidian Languages** (Kannada, Malayalam, Tamil, Telugu):
   - `indic-tts-coqui-dravidian-female` - Female voice
   - `indic-tts-coqui-dravidian-male` - Male voice

2. **Indo-Aryan Languages** (Hindi, Bengali, Gujarati, Marathi, Punjabi):
   - `indic-tts-coqui-indo_aryan-female` - Female voice
   - `indic-tts-coqui-indo_aryan-male` - Male voice

3. **Miscellaneous Languages** (English, Bodo, Manipuri):
   - `indic-tts-coqui-misc-female` - Female voice
   - `indic-tts-coqui-misc-male` - Male voice

### Voice Selection Endpoints

#### List All Voices

```bash
curl -X GET http://localhost:8088/api/v1/tts/voices
```

**Response:**
```json
{
  "voices": [
    {
      "voice_id": "indic-tts-coqui-dravidian-female",
      "name": "Dravidian Female Voice",
      "gender": "female",
      "age": "adult",
      "languages": ["kn", "ml", "ta", "te"],
      "model_id": "indic-tts-coqui-dravidian",
      "sample_rate": 22050,
      "description": "Female voice for Dravidian languages",
      "is_active": true
    }
  ],
  "total": 6,
  "filtered": 6
}
```

#### Filter Voices by Language

```bash
curl -X GET "http://localhost:8088/api/v1/tts/voices?language=ta"
```

#### Filter Voices by Gender

```bash
curl -X GET "http://localhost:8088/api/v1/tts/voices?gender=female"
```

#### Get Voice Details

```bash
curl -X GET http://localhost:8088/api/v1/tts/voices/indic-tts-coqui-dravidian-female
```

#### Get Voices for Language

```bash
curl -X GET http://localhost:8088/api/v1/tts/voices/language/ta
```

## WebSocket Streaming

### Overview
The TTS service supports real-time text-to-speech streaming via Socket.IO WebSocket protocol. This enables low-latency audio generation for live text streams.

### Connection

**Endpoint**: `ws://localhost:8088/socket.io/tts`

**Query Parameters**:
- `serviceId` (required): TTS model identifier (e.g., 'indic-tts-coqui-dravidian')
- `voice_id` (required): Voice identifier (e.g., 'indic-tts-coqui-dravidian-female')
- `language` (required): Language code (e.g., 'ta', 'hi', 'en')
- `gender` (required): Voice gender ('male' or 'female')
- `samplingRate` (optional): Audio sample rate in Hz (default: 22050)
- `audioFormat` (optional): Output audio format ('wav', 'mp3', 'ogg', default: 'wav')
- `apiKey` (optional): API key for authentication

**Example Connection URL**:
```
ws://localhost:8088/socket.io/tts?serviceId=indic-tts-coqui-dravidian&voice_id=indic-tts-coqui-dravidian-female&language=ta&gender=female&audioFormat=mp3
```

### Events

#### Client → Server Events

1. **`start`** - Initialize streaming session
   - Payload: `{config: {responseFrequencyInMs: 2000, audioFormat: "mp3"}}` (optional)
   - Response: Server emits `ready` event

2. **`data`** - Send text chunk
   - Payload: `{text: str, isFinal: bool, disconnectStream: bool}`
   - `text`: Text to synthesize
   - `isFinal`: Whether this is the final text chunk (triggers synthesis)
   - `disconnectStream`: Whether to close stream after this chunk

3. **`disconnect`** - Close connection
   - No payload required

#### Server → Client Events

1. **`ready`** - Stream is ready to receive text
   - Emitted after `start` event

2. **`response`** - Audio chunk generated
   - Payload: `{audioContent: str, isFinal: bool, duration: float, timestamp: float, format: str}`
   - `audioContent`: Base64-encoded audio data
   - `isFinal`: True if this is the final audio chunk
   - `duration`: Audio duration in seconds
   - `format`: Audio format (wav/mp3/ogg)

3. **`error`** - Error occurred
   - Payload: `{error: str, code: str, timestamp: float}`

4. **`terminate`** - Stream terminated
   - Emitted when stream is closed

### Usage Example (Python Client)

```python
import socketio
import base64
import wave

# Create Socket.IO client
sio = socketio.Client()

# Event handlers
@sio.on('ready')
def on_ready():
    print('Stream ready, sending text...')
    # Send text for synthesis
    sio.emit('data', {
        'text': 'வணக்கம், இது ஒரு சோதனை',
        'isFinal': True,
        'disconnectStream': False
    })

@sio.on('response')
def on_response(data):
    print(f"Received audio chunk (final={data['isFinal']}, duration={data['duration']}s)")
    
    # Decode base64 audio
    audio_bytes = base64.b64decode(data['audioContent'])
    
    # Save to file
    with open(f"output_{data['timestamp']}.{data['format']}", 'wb') as f:
        f.write(audio_bytes)
    
    # Disconnect after final chunk
    if data['isFinal']:
        sio.emit('data', {
            'text': '',
            'isFinal': True,
            'disconnectStream': True
        })

@sio.on('error')
def on_error(data):
    print(f"Error: {data['error']}")

# Connect
url = 'http://localhost:8088/socket.io/tts'
params = {
    'serviceId': 'indic-tts-coqui-dravidian',
    'voice_id': 'indic-tts-coqui-dravidian-female',
    'language': 'ta',
    'gender': 'female',
    'audioFormat': 'mp3'
}
sio.connect(url, transports=['websocket'], query_string=params)

# Start streaming
sio.emit('start')

# Wait for completion
sio.wait()
```

### Usage Example (JavaScript Client)

```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:8088/socket.io/tts', {
  transports: ['websocket'],
  query: {
    serviceId: 'indic-tts-coqui-dravidian',
    voice_id: 'indic-tts-coqui-dravidian-female',
    language: 'ta',
    gender: 'female',
    audioFormat: 'mp3'
  }
});

socket.on('connect', () => {
  console.log('Connected to TTS streaming service');
  socket.emit('start');
});

socket.on('ready', () => {
  console.log('Stream ready');
  // Send text for synthesis
  socket.emit('data', {
    text: 'வணக்கம், இது ஒரு சோதனை',
    isFinal: true,
    disconnectStream: false
  });
});

socket.on('response', (data) => {
  console.log(`Received audio: ${data.duration}s (final=${data.isFinal})`);
  
  // Decode base64 and play audio
  const audioBlob = base64ToBlob(data.audioContent, `audio/${data.format}`);
  const audioUrl = URL.createObjectURL(audioBlob);
  const audio = new Audio(audioUrl);
  audio.play();
  
  // Disconnect after final chunk
  if (data.isFinal) {
    socket.emit('data', {
      text: '',
      isFinal: true,
      disconnectStream: true
    });
  }
});

socket.on('error', (data) => {
  console.error(`Error: ${data.error}`);
});

function base64ToBlob(base64, mimeType) {
  const byteCharacters = atob(base64);
  const byteArrays = [];
  for (let i = 0; i < byteCharacters.length; i++) {
    byteArrays.push(byteCharacters.charCodeAt(i));
  }
  return new Blob([new Uint8Array(byteArrays)], { type: mimeType });
}
```

### Configuration

**Response Frequency**: Control how often audio chunks are emitted
- Default: 2000ms (2 seconds)
- Configurable via `STREAMING_RESPONSE_FREQUENCY_MS` environment variable
- Can be updated per-session via `start` event payload

**Text Chunking**:
- Long text (>400 characters) is automatically chunked
- Each chunk is synthesized separately
- Audio chunks are emitted as they're generated

**Audio Format Conversion**:
- Supports WAV, MP3, OGG output formats
- Conversion happens on-the-fly using pydub
- Specify format via `audioFormat` query parameter

### Performance Considerations

- **Latency**: Typical end-to-end latency is 1-2 seconds
- **Throughput**: Each worker can handle ~50 concurrent streams
- **Audio Format**: WAV recommended for best performance (no conversion overhead)
- **Sample Rate**: 22050 Hz recommended (native TTS output rate)

### Troubleshooting

**Connection Issues**:
- Ensure Socket.IO client uses `websocket` transport
- Check query parameters are properly URL-encoded
- Verify Triton server is accessible
- Validate voice_id exists in voice catalog

**Audio Quality Issues**:
- Use correct sample rate (22050 Hz recommended)
- Check audio format is supported (wav/mp3/ogg)
- Verify voice supports the target language

**Latency Issues**:
- Reduce `responseFrequencyInMs` for faster updates
- Use WAV format to avoid conversion overhead
- Check network latency between client and server
- Consider using shorter text chunks

## Request/Response Examples

### Basic TTS Request

```bash
curl -X POST http://localhost:8088/api/v1/tts/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {
        "source": "Hello, this is a test of the text-to-speech service."
      }
    ],
    "config": {
      "serviceId": "indic-tts-coqui-misc",
      "language": {
        "sourceLanguage": "en"
      },
      "gender": "female",
      "audioFormat": "wav",
      "samplingRate": 22050
    }
  }'
```

### TTS Response

```json
{
  "audio": [
    {
      "audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",
      "audioUri": null
    }
  ],
  "config": {
    "language": {
      "sourceLanguage": "en"
    },
    "audioFormat": "wav",
    "encoding": "base64",
    "samplingRate": 22050,
    "audioDuration": 3.5
  }
}
```

### Multiple Text Inputs

```bash
curl -X POST http://localhost:8088/api/v1/tts/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {
        "source": "First sentence to synthesize."
      },
      {
        "source": "Second sentence to synthesize."
      }
    ],
    "config": {
      "serviceId": "indic-tts-coqui-misc",
      "language": {
        "sourceLanguage": "en"
      },
      "gender": "male",
      "audioFormat": "mp3",
      "samplingRate": 22050
    }
  }'
```

### Duration Adjustment

```bash
curl -X POST http://localhost:8088/api/v1/tts/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {
        "source": "This text will be spoken in exactly 5 seconds.",
        "audioDuration": 5.0
      }
    ],
    "config": {
      "serviceId": "indic-tts-coqui-misc",
      "language": {
        "sourceLanguage": "en"
      },
      "gender": "female",
      "audioFormat": "wav",
      "samplingRate": 22050
    }
  }'
```

### Hindi TTS Example

```bash
curl -X POST http://localhost:8088/api/v1/tts/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {
        "source": "नमस्ते, यह एक परीक्षण है।"
      }
    ],
    "config": {
      "serviceId": "indic-tts-coqui-indo_aryan",
      "language": {
        "sourceLanguage": "hi"
      },
      "gender": "female",
      "audioFormat": "wav",
      "samplingRate": 22050
    }
  }'
```

## Supported Models

### Dravidian Languages
- **Model**: `indic-tts-coqui-dravidian`
- **Languages**: Kannada (kn), Malayalam (ml), Tamil (ta), Telugu (te)
- **Voices**: male, female

### Indo-Aryan Languages
- **Model**: `indic-tts-coqui-indo_aryan`
- **Languages**: Hindi (hi), Bengali (bn), Gujarati (gu), Marathi (mr), Punjabi (pa)
- **Voices**: male, female

### Miscellaneous Languages
- **Model**: `indic-tts-coqui-misc`
- **Languages**: English (en), Bodo (brx), Manipuri (mni)
- **Voices**: male, female

## Audio Formats

- **WAV**: Uncompressed audio (default)
- **MP3**: Compressed audio
- **OGG**: Open source compressed audio
- **PCM**: Raw PCM data (s16le)

## Text Processing

### Text Chunking
Long text (>400 characters) is automatically split into smaller chunks for optimal processing.

### SSML Support (Basic)
Basic SSML tags are supported:
- `<speak>`: Root element
- `<prosody rate="slow">`: Speech rate control
- `<prosody pitch="high">`: Pitch control
- `<prosody volume="loud">`: Volume control

### Language Detection
Automatic language detection based on Unicode script ranges.

## Performance Considerations

- **Latency**: Typical end-to-end latency is 1-3 seconds
- **Throughput**: Each worker can handle ~50 concurrent requests
- **Text Length**: Maximum 5000 characters per input
- **Audio Duration**: Maximum 300 seconds per output

## Docker Deployment

Build image: `docker build -t tts-service:latest .`
Run container: `docker run -p 8088:8088 --env-file .env tts-service:latest`

## Development

### Running Tests
```bash
pytest tests/
```

### Code Formatting
```bash
black .
flake8 .
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Troubleshooting

### Common Issues

**Audio Quality Issues**:
- Use correct sample rate (22050 Hz recommended)
- Check audio format compatibility
- Verify text is properly encoded

**Performance Issues**:
- Reduce text length per request
- Use appropriate audio format
- Check Triton server performance

**Authentication Issues**:
- Verify API key is valid and active
- Check rate limits
- Ensure proper header format

### Logs

Check service logs for detailed error information:
```bash
docker logs tts-service
```

## License

MIT License

## Credits

- Dhruva Platform for the original implementation
- AI4Bharat for the Indic TTS models
- Coqui TTS for the underlying technology
