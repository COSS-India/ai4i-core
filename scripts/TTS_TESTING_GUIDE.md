# TTS Testing Guide

This guide explains how to test TTS (Text-to-Speech) functionality via both REST API and MCP (Model Context Protocol).

## Overview

TTS can be accessed in two ways:
1. **Direct REST API**: Programmatic calls to TTS service
2. **Via MCP**: Natural language queries through LLM service that automatically invoke TTS tool

## Prerequisites

1. Ensure services are running:
   ```bash
   sudo docker compose ps | grep -E "(tts-service|mcp-server|llm-service)"
   ```

2. Check TTS service health:
   ```bash
   curl http://localhost:8088/api/v1/tts/health
   ```

3. Check MCP server health:
   ```bash
   curl http://localhost:8094/api/v1/health
   ```

## Testing Methods

### 1. Test TTS via REST API (Direct)

**Script**: `./scripts/test_tts_rest_api.sh`

**Usage**:
```bash
# Default test (English, "Hello how are you")
./scripts/test_tts_rest_api.sh

# Custom text
./scripts/test_tts_rest_api.sh "नमस्ते, आप कैसे हैं?" hi

# Custom text and language
./scripts/test_tts_rest_api.sh "Hello world" en
```

**What it does**:
- Sends direct POST request to TTS service
- Endpoint: `http://localhost:8088/api/v1/tts/inference`
- Returns audio in base64 format

**Expected Response**:
```json
{
  "output": [
    {
      "source": "Hello how are you",
      "audioContent": "<base64_encoded_audio>",
      "audioFormat": "wav",
      "samplingRate": 22050
    }
  ]
}
```

### 2. Test TTS via MCP (Direct Tool Invocation)

**Script**: `./scripts/test_tts_via_mcp.sh`

**Usage**:
```bash
# Default test
./scripts/test_tts_via_mcp.sh

# Custom text
./scripts/test_tts_via_mcp.sh "Hello world" en
```

**What it does**:
- Sends request to MCP server to invoke `tts_synthesize` tool
- Endpoint: `http://localhost:8094/api/v1/tools/tts_synthesize/invoke`
- MCP server forwards request to TTS service

**Expected Response**:
```json
{
  "toolName": "tts_synthesize",
  "result": {
    "output": [
      {
        "source": "Hello how are you",
        "audioContent": "<base64_encoded_audio>",
        "audioFormat": "wav",
        "samplingRate": 22050
      }
    ]
  },
  "duration": 2.5,
  "requestId": "..."
}
```

### 3. Test TTS via Natural Language Query (LLM Service)

**Script**: `./scripts/test_tts_natural_language.sh`

**Usage**:
```bash
# Default query
./scripts/test_tts_natural_language.sh

# Custom query
./scripts/test_tts_natural_language.sh "convert this text to voice \"Hello world\""
```

**What it does**:
1. Sends natural language query to LLM service
2. LLM service detects TTS intent using query parser
3. LLM service invokes TTS tool via MCP
4. Returns TTS result

**Supported Query Patterns**:
- `"convert this text to voice \"Hello how are you?\""`
- `"text to speech Hello world"`
- `"speak this text Hello"`
- `"generate audio from text \"Hello\""`

**Expected Response**:
```json
{
  "output": [
    {
      "source": "convert this text to voice \"Hello how are you?\"",
      "target": "TTS audio generated successfully. Audio length: 12345 characters (base64)"
    }
  ]
}
```

## Troubleshooting

### TTS Service Not Responding

1. Check Triton connection:
   ```bash
   sudo ./scripts/test_triton_endpoints.sh
   ```

2. Check TTS service logs:
   ```bash
   sudo docker compose logs tts-service --tail 50
   ```

3. Restart TTS service:
   ```bash
   sudo docker compose restart tts-service
   ```

### MCP Server Not Responding

1. Check MCP server health:
   ```bash
   curl http://localhost:8094/api/v1/health
   ```

2. Check MCP server logs:
   ```bash
   sudo docker compose logs mcp-server --tail 50
   ```

3. Verify TTS tool is registered:
   ```bash
   curl http://localhost:8094/api/v1/tools | jq '.tools[] | select(.name=="tts_synthesize")'
   ```

### Natural Language Query Not Working

1. Check LLM service logs:
   ```bash
   sudo docker compose logs llm-service --tail 50
   ```

2. Verify MCP integration is enabled:
   - Check feature flags in LLM service
   - Verify MCP client is initialized

3. Test query parser directly:
   ```python
   from utils.query_parser import get_query_parser
   parser = get_query_parser()
   intent, params = parser.parse("convert this text to voice \"Hello\"")
   print(intent, params)  # Should output: tts {'text': 'Hello', 'sourceLanguage': 'en'}
   ```

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ├─────────────────────────────────────┐
       │                                       │
       ▼                                       ▼
┌─────────────┐                      ┌─────────────┐
│ LLM Service │                      │ TTS Service │
│             │                      │             │
│ Query Parser│                      │ Direct REST │
│     ↓       │                      │   API Call  │
│ MCP Client  │                      └─────────────┘
│     ↓       │
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ MCP Server  │
│             │
│ TTS Tool    │
│     ↓       │
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ TTS Service │
└─────────────┘
```

## Next Steps

1. Test all three methods to ensure TTS works end-to-end
2. Verify audio quality and format
3. Test with different languages (hi, ta, te, etc.)
4. Monitor performance and latency
5. Check error handling and fallback behavior
