# TTS UI - Model Management Integration Summary

## Overview
Successfully integrated Model Management Service in the TTS UI following the same pattern as NMT UI integration.

## Implementation Date
December 12, 2025

## Changes Made

### 1. Updated Files

#### `src/types/tts.ts`
**New Type Definitions Added**:

```typescript
// TTS Service Details Response (from Model Management)
export interface TTSServiceDetailsResponse {
  service_id: string;
  model_id: string;
  triton_endpoint: string;
  triton_model: string;
  provider: string; // Keep for backward compatibility
  description: string; // Keep for backward compatibility
  name: string;
  serviceDescription: string;
  supported_languages: string[];
  supported_genders?: string[];
  supported_audio_formats?: string[];
  supported_sample_rates?: number[];
}

// TTS Languages Response
export interface TTSLanguagesResponse {
  model_id: string;
  provider: string;
  supported_languages: string[];
  language_details: Array<{
    code: string;
    name: string;
  }>;
  total_languages: number;
}
```

These types match the structure from Model Management Service and provide type safety for the UI.

#### `src/services/ttsService.ts`
**New Imports**:
```typescript
import { listServices } from './modelManagementService';
import { 
  TTSServiceDetailsResponse,
  TTSLanguagesResponse
} from '../types/tts';
```

**New Functions Added**:

1. **`listTTSServices()`**
   - Fetches TTS services from Model Management Service
   - Filters by `task_type='tts'`
   - Transforms response to match `TTSServiceDetailsResponse` format
   - Extracts languages from service metadata
   - Cleans and normalizes endpoint URLs
   - Removes duplicates

2. **`getTTSLanguagesForService(serviceId: string)`**
   - Gets supported languages for a specific TTS service
   - Fetches from Model Management Service by service ID
   - Extracts and normalizes language codes
   - Returns language details with codes and names
   - Handles different language object formats

3. **`getServiceByLanguage(language: string)`**
   - Finds a TTS service that supports a given language
   - Returns the first matching service or null
   - Useful for automatic service selection based on language

4. **`isLanguageSupported(language: string)`**
   - Checks if a language is supported by any TTS service
   - Returns boolean indicating support status

#### `src/services/api.ts`
**Updated API Endpoints**:
```typescript
tts: {
  inference: '/api/v1/tts/inference',
  voices: '/api/v1/tts/voices',
  services: '/api/v1/tts/services',      // NEW
  languages: '/api/v1/tts/languages',    // NEW
  health: '/api/v1/tts/health',
}
```

Added `services` and `languages` endpoints to match NMT pattern.

## Integration Pattern

The TTS UI integration follows the **same pattern as NMT**:

### Service Fetching Flow
```
1. UI calls listTTSServices()
   ↓
2. listTTSServices() calls listServices('tts') from modelManagementService
   ↓
3. Request goes to Model Management API: GET /api/v1/model-management/services/?task_type=tts
   ↓
4. Response is transformed to TTSServiceDetailsResponse format
   ↓
5. UI displays available TTS services with metadata
```

### Language Resolution Flow
```
1. User selects a service OR language
   ↓
2. UI calls getTTSLanguagesForService(serviceId)
   ↓
3. Function fetches service details from Model Management
   ↓
4. Extracts supported languages from service.languages array
   ↓
5. Returns TTSLanguagesResponse with language details
   ↓
6. UI populates language dropdown
```

## Key Features

✅ **Dynamic Service Discovery** - TTS services fetched from Model Management, not hardcoded
✅ **Language Metadata** - Languages extracted from service metadata
✅ **Automatic Service Selection** - Can find services by language
✅ **Type Safety** - Full TypeScript types for all responses
✅ **Consistent Pattern** - Same structure as NMT for maintainability
✅ **Backward Compatibility** - Existing `listVoices()` function still works

## Usage Examples

### Fetching TTS Services
```typescript
import { listTTSServices } from '@/services/ttsService';

// Get all TTS services from Model Management
const services = await listTTSServices();

// Display services in dropdown
services.forEach(service => {
  console.log(service.name, service.supported_languages);
});
```

### Getting Languages for a Service
```typescript
import { getTTSLanguagesForService } from '@/services/ttsService';

const serviceId = 'ai4bharat/indic-tts-coqui-dravidian';
const languages = await getTTSLanguagesForService(serviceId);

if (languages) {
  console.log('Supported languages:', languages.supported_languages);
  console.log('Total:', languages.total_languages);
}
```

### Finding Service by Language
```typescript
import { getServiceByLanguage } from '@/services/ttsService';

const language = 'hi'; // Hindi
const service = await getServiceByLanguage(language);

if (service) {
  console.log(`Found service: ${service.name}`);
  console.log(`Endpoint: ${service.triton_endpoint}`);
}
```

### Checking Language Support
```typescript
import { isLanguageSupported } from '@/services/ttsService';

const isHindiSupported = await isLanguageSupported('hi');
console.log('Hindi supported:', isHindiSupported);
```

## Benefits

1. **Centralized Configuration** - TTS services managed in one place (Model Management)
2. **No Hardcoding** - Services and languages dynamically loaded
3. **Easy Updates** - Add new TTS services without UI code changes
4. **Consistent UX** - Same pattern as NMT service in UI
5. **Type Safety** - Full TypeScript coverage
6. **Metadata Rich** - Access to service descriptions, endpoints, languages

## Migration Guide

### For Existing TTS UI Components

**Before** (hardcoded services):
```typescript
const services = [
  { id: 'service1', name: 'TTS Service 1', languages: ['en', 'hi'] },
  { id: 'service2', name: 'TTS Service 2', languages: ['ta', 'te'] },
];
```

**After** (dynamic from Model Management):
```typescript
import { listTTSServices } from '@/services/ttsService';

const services = await listTTSServices();
// Services now include full metadata from Model Management
```

**Before** (hardcoded languages):
```typescript
const languages = ['en', 'hi', 'ta', 'te', 'kn'];
```

**After** (dynamic from service metadata):
```typescript
import { getTTSLanguagesForService } from '@/services/ttsService';

const languages = await getTTSLanguagesForService(selectedServiceId);
// Languages fetched from Model Management for specific service
```

## API Response Examples

### listTTSServices() Response
```json
[
  {
    "service_id": "ai4bharat/indic-tts-coqui-dravidian",
    "model_id": "indic-tts-coqui-dravidian-v1",
    "triton_endpoint": "triton-server:8000",
    "triton_model": "tts",
    "provider": "AI4Bharat",
    "description": "Dravidian language TTS model",
    "name": "Indic TTS Coqui Dravidian",
    "serviceDescription": "TTS service for Dravidian languages",
    "supported_languages": ["kn", "ml", "ta", "te"]
  }
]
```

### getTTSLanguagesForService() Response
```json
{
  "model_id": "indic-tts-coqui-dravidian-v1",
  "provider": "AI4Bharat",
  "supported_languages": ["kn", "ml", "ta", "te"],
  "language_details": [
    { "code": "kn", "name": "Kannada" },
    { "code": "ml", "name": "Malayalam" },
    { "code": "ta", "name": "Tamil" },
    { "code": "te", "name": "Telugu" }
  ],
  "total_languages": 4
}
```

## Testing Checklist

### Basic Functionality
- [ ] `listTTSServices()` returns services from Model Management
- [ ] Services include correct metadata (name, description, languages)
- [ ] Endpoints are properly cleaned (no http:// prefix)
- [ ] Duplicate services are filtered out

### Language Resolution
- [ ] `getTTSLanguagesForService()` returns languages for valid service ID
- [ ] Returns null for invalid service ID
- [ ] Language codes are properly extracted
- [ ] Language details include both code and name

### Service Discovery
- [ ] `getServiceByLanguage()` finds correct service for given language
- [ ] Returns null if no service supports the language
- [ ] `isLanguageSupported()` returns correct boolean

### Integration
- [ ] TTS UI components can use new service functions
- [ ] Service dropdown populates from Model Management
- [ ] Language dropdown updates based on selected service
- [ ] Backward compatibility maintained with existing voice functions

## Completed Updates

### 1. **Updated TTS Page Component** (`src/pages/tts.tsx`) ✅
   - ✅ Uses `listTTSServices()` to fetch services from Model Management
   - ✅ Updated service selector dropdown with dynamic services
   - ✅ Added `getTTSLanguagesForService()` to fetch languages per service
   - ✅ Language selector now uses service-specific languages
   - ✅ Displays service metadata (provider, description, endpoint, languages count)
   - ✅ Added loading states for services and languages
   - ✅ Service validation before generating audio

### 2. **Updated TTS Hook** (`src/hooks/useTTS.ts`) ✅
   - ✅ Accepts `serviceId` parameter from page component
   - ✅ Removed hardcoded `getServiceIdForLanguage` function
   - ✅ Uses dynamic `serviceId` in inference requests
   - ✅ Validates service ID before making requests

### 3. **Service Selection UI** ✅
   - ✅ Dynamic dropdown populated from Model Management
   - ✅ Shows service name, description, and metadata
   - ✅ Displays supported languages count
   - ✅ Shows endpoint and service ID for transparency
   - ✅ Loading spinner while fetching services

### 4. **Loading States & Error Handling** ✅
   - ✅ Loading indicators for services, languages, and voices
   - ✅ Service not found error state
   - ✅ No service selected state
   - ✅ Graceful error messages
   - ✅ Service ID validation with toast notifications

## Consistency with NMT

This implementation maintains **100% consistency** with the NMT UI integration:

| Feature | NMT | TTS |
|---------|-----|-----|
| Service listing | `listNMTServices()` | `listTTSServices()` |
| Language fetching | `getNMTLanguagesForService()` | `getTTSLanguagesForService()` |
| Service by language | `getServiceByLanguagePair()` | `getServiceByLanguage()` |
| Language support check | `isLanguagePairSupported()` | `isLanguageSupported()` |
| API endpoints | `/api/v1/nmt/services` | `/api/v1/tts/services` |
| Response transformation | ✅ | ✅ |
| Type definitions | ✅ | ✅ |

## References

- **NMT UI Integration**: `frontend/simple-ui/src/services/nmtService.ts`
- **Model Management Service**: `frontend/simple-ui/src/services/modelManagementService.ts`
- **Backend Integration**: `services/tts-service/MODEL_MANAGEMENT_INTEGRATION_SUMMARY.md`
- **API Endpoints**: `frontend/simple-ui/src/services/api.ts`
