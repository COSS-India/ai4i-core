# Pipeline Service UI Implementation

## Overview
Successfully implemented the UI for the pipeline service, enabling Speech-to-Speech translation that chains ASR → NMT → TTS services.

## Files Created/Modified

### Frontend Files

#### New Files Created:
1. **`frontend/simple-ui/src/types/pipeline.ts`** - TypeScript types for pipeline requests and responses
2. **`frontend/simple-ui/src/services/pipelineService.ts`** - API client for pipeline service
3. **`frontend/simple-ui/src/hooks/usePipeline.ts`** - Custom React hook for pipeline functionality
4. **`frontend/simple-ui/src/pages/pipeline.tsx`** - Main pipeline page UI component

#### Modified Files:
1. **`frontend/simple-ui/src/components/common/Sidebar.tsx`** - Added pipeline navigation item
2. **`frontend/simple-ui/src/pages/_app.tsx`** - Added pipeline to layout routes
3. **`frontend/simple-ui/src/services/api.ts`** - Added pipeline endpoints
4. **`frontend/simple-ui/src/config/constants.ts`** - Added pipeline API endpoints

## Features Implemented

### 1. Pipeline Page (`/pipeline`)
- Source and target language selection
- ASR, NMT, and TTS service selection
- Audio recording functionality with microphone
- Audio file upload support
- Real-time processing indicator
- Results display with:
  - Transcribed text (source)
  - Translated text (target)
  - Synthesized audio player
  - Word count statistics

### 2. usePipeline Hook
- Audio recording management
- Blob to base64 conversion
- File upload processing
- Pipeline inference execution
- Error handling with toast notifications
- Loading state management

### 3. Pipeline Service API Client
- `runPipelineInference()` - Execute pipeline with ASR → NMT → TTS
- `getPipelineInfo()` - Get service capabilities
- `checkPipelineHealth()` - Health check endpoint

### 4. Navigation Integration
- Pipeline added to sidebar with GitNetwork icon
- Route protection and layout integration

## Pipeline Flow

1. **User Input**: Record audio or upload audio file
2. **ASR Task**: Convert audio to text (source language)
3. **Translation Task**: Translate text to target language
4. **TTS Task**: Synthesize speech from translated text
5. **Results**: Display source text, translated text, and audio player

## API Integration

The pipeline service expects the following request format:

```typescript
{
  pipelineTasks: [
    { taskType: 'asr', config: { serviceId, language, audioFormat } },
    { taskType: 'translation', config: { serviceId, language } },
    { taskType: 'tts', config: { serviceId, language, gender } }
  ],
  inputData: {
    audio: [{ audioContent: base64String }]
  }
}
```

## Backend Service

The pipeline service backend is already implemented in:
- `services/pipeline-service/main.py` - FastAPI application
- `services/pipeline-service/routers/pipeline_router.py` - API endpoints
- `services/pipeline-service/services/pipeline_service.py` - Orchestration logic
- `services/pipeline-service/utils/http_client.py` - Service client

## Usage

1. Navigate to `/pipeline` in the application
2. Select source and target languages
3. Choose ASR, NMT, and TTS services (or use defaults)
4. Either:
   - Click "Start Recording" to record audio
   - Or click "Choose Audio File" to upload an audio file
5. The pipeline will automatically process the audio
6. View results: transcribed text, translated text, and synthesized audio

## Reference Implementation

The implementation is based on the Dhruva Platform-2 reference UI found in:
- `dhruva-references/Dhruva-Platform-2/client/pages/pipeline.tsx`

## Testing

To test the pipeline:
1. Ensure all services (ASR, NMT, TTS, Pipeline) are running
2. Start the frontend application
3. Navigate to the pipeline page
4. Select languages and try recording or uploading audio
5. Verify the pipeline executes successfully and displays results

## Configuration

Default service IDs can be configured in the pipeline page:
- ASR: `dhruva-asr`
- NMT: `dhruva-nmt`
- TTS: `dhruva-tts`

Users can select from available services dynamically loaded from each service's models/voices endpoints.

