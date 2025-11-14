# Simple UI - AI Services Testing Interface

A modern, responsive Next.js-based web interface for testing ASR, TTS, and NMT microservices. Built with TypeScript, Chakra UI, and React Query for optimal performance and user experience.

## Features

- **Modern, Responsive UI** - Built with Chakra UI for consistent design and mobile-first approach
- **Real-time ASR** - Microphone recording and file upload with waveform visualization
- **TTS with Multiple Voices** - Text-to-speech with various voice options and audio formats
- **NMT Translation** - Neural machine translation between 22+ Indian languages
- **WebSocket Streaming** - Real-time streaming support for ASR and TTS services
- **API Key Management** - Secure API key storage and management
- **Request/Response Visualization** - Detailed statistics and performance metrics
- **Audio Waveform Visualization** - Canvas-based audio visualization using Web Audio API

## Technology Stack

- **Framework**: Next.js 13.1.1 with TypeScript 4.9.4
- **UI Library**: Chakra UI 2.4.6 with custom orange theme
- **State Management**: React Query 4.24.6 for server state
- **HTTP Client**: Axios 1.2.2 with interceptors
- **WebSocket**: Socket.IO Client 4.5.4
- **Audio Processing**: Recorder.js for audio recording
- **Icons**: React Icons 4.7.1
- **Styling**: Emotion with CSS-in-JS

## Prerequisites

- Node.js 18+ and npm/yarn
- API Gateway service running on port 8080
- Microphone access for ASR recording
- Modern web browser with Web Audio API support

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Ai4V-C/frontend/simple-ui
   ```

2. **Install dependencies**
   ```bash
   npm install
   # or
   yarn install
   ```

3. **Configure environment**
   ```bash
   cp .env.template .env
   ```

4. **Update environment variables**
   ```bash
   # .env
   NEXT_PUBLIC_API_URL=http://localhost:8080
   ```

## Development

1. **Start the development server**
   ```bash
   npm run dev
   # or
   yarn dev
   ```

2. **Open your browser**
   Navigate to [http://localhost:3000](http://localhost:3000)

3. **Set up API key**
   - Click on the menu in the top-right corner
   - Select "Manage API Key"
   - Enter your API key for the microservices

## Production Build

1. **Build the application**
   ```bash
   npm run build
   # or
   yarn build
   ```

2. **Start the production server**
   ```bash
   npm start
   # or
   yarn start
   ```

## Docker Deployment

1. **Build the Docker image**
   ```bash
   docker build -t simple-ui:latest .
   ```

2. **Run the container**
   ```bash
   docker run -p 3000:3000 \
     -e NEXT_PUBLIC_API_URL=http://api-gateway:8080 \
     simple-ui:latest
   ```

3. **Using Docker Compose**
   ```yaml
   version: '3.8'
   services:
     simple-ui:
       build: .
       ports:
         - "3000:3000"
       environment:
         - NEXT_PUBLIC_API_URL=http://api-gateway:8080
       depends_on:
         - api-gateway
   ```

## Project Structure

```
src/
├── components/           # Reusable UI components
│   ├── common/          # Common components (Layout, Header, etc.)
│   ├── asr/             # ASR-specific components
│   ├── tts/             # TTS-specific components
│   └── nmt/             # NMT-specific components
├── hooks/               # Custom React hooks
├── services/            # API service clients
├── types/               # TypeScript type definitions
├── utils/               # Utility functions
├── config/              # Configuration constants
├── styles/              # Global styles
└── pages/               # Next.js pages
```

## Usage Guide

### Setting Up API Key

1. Navigate to any service page
2. Click the menu button in the top-right corner
3. Select "Manage API Key"
4. Enter your API key (minimum 20 characters)
5. Click "Save"

### Using ASR (Speech Recognition)

1. **Navigate to ASR page** (`/asr`)
2. **Configure settings**:
   - Select inference mode (REST or Streaming)
   - Choose language from 22+ supported languages
   - Set sample rate (8000, 16000, or 48000 Hz)
3. **Record audio**:
   - Click "Start Recording" to use microphone
   - Click "Stop Recording" when finished
   - Or upload an audio file using "Choose File"
4. **View results**:
   - Transcript appears in the results panel
   - View word count, response time, and confidence
   - Play back the audio with waveform visualization

### Using TTS (Text-to-Speech)

1. **Navigate to TTS page** (`/tts`)
2. **Configure voice settings**:
   - Select language and gender
   - Choose audio format (WAV, MP3, FLAC, OGG, PCM)
   - Set sampling rate
3. **Enter text**:
   - Type or paste text (max 512 characters)
   - Character counter shows remaining characters
4. **Generate audio**:
   - Click "Generate Audio" button
   - Wait for processing to complete
5. **Play and download**:
   - Use built-in audio player controls
   - Download the generated audio file

### Using NMT (Translation)

1. **Navigate to NMT page** (`/nmt`)
2. **Select language pair**:
   - Choose source and target languages
   - Use swap button to reverse the pair
3. **Enter text**:
   - Type text in the source language
   - Character limit: 512 characters
4. **Translate**:
   - Click "Translate" button
   - View translation in the output area
5. **Manage results**:
   - Copy source or translated text
   - Swap texts between input and output
   - View translation statistics

## API Integration

### API Gateway Routing

The application connects to an API Gateway service that routes requests to individual microservices:

- **ASR Service**: `POST /api/v1/asr/inference`
- **TTS Service**: `POST /api/v1/tts/inference`
- **NMT Service**: `POST /api/v1/nmt/inference`

### Authentication

All API requests include an Authorization header:
```
Authorization: Bearer <api_key>
```

### Request/Response Format

#### ASR Request
```json
{
  "audio": [{"audioContent": "base64_encoded_audio"}],
  "config": {
    "language": {"sourceLanguage": "en"},
    "serviceId": "ai4bharat/asr-wav2vec2-indian-english",
    "audioFormat": "wav",
    "encoding": "base64",
    "samplingRate": 16000
  }
}
```

#### TTS Request
```json
{
  "input": [{"source": "Hello world"}],
  "config": {
    "language": {"sourceLanguage": "en"},
    "serviceId": "ai4bharat/indic-tts",
    "gender": "female",
    "samplingRate": 22050,
    "audioFormat": "wav"
  }
}
```

#### NMT Request
```json
{
  "input": [{"source": "Hello"}],
  "config": {
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    "serviceId": "ai4bharat/indictrans-v2-all-gpu"
  }
}
```

## Development Guide

### Adding New Components

1. Create component file in appropriate directory
2. Define TypeScript interfaces for props
3. Use Chakra UI components for styling
4. Export as default component

### Creating New Pages

1. Create page file in `src/pages/`
2. Use Next.js `Head` component for SEO
3. Wrap content with `ContentLayout` component
4. Implement responsive design with Chakra UI Grid

### Using React Query Hooks

```typescript
import { useQuery, useMutation } from '@tanstack/react-query';

// Query hook
const { data, isLoading, error } = useQuery({
  queryKey: ['data-key'],
  queryFn: fetchDataFunction,
  staleTime: 5 * 60 * 1000,
});

// Mutation hook
const mutation = useMutation({
  mutationFn: mutateFunction,
  onSuccess: (data) => {
    // Handle success
  },
  onError: (error) => {
    // Handle error
  },
});
```

### Styling with Chakra UI

```typescript
import { Box, Text, Button } from '@chakra-ui/react';

const MyComponent = () => (
  <Box p={4} bg="orange.100" borderRadius="md">
    <Text color="gray.800" fontSize="lg">
      Hello World
    </Text>
    <Button colorScheme="orange" size="md">
      Click me
    </Button>
  </Box>
);
```

## Troubleshooting

### Common Issues

1. **CORS Errors**
   - Ensure API Gateway is configured to allow requests from the frontend domain
   - Check CORS headers in the API Gateway configuration

2. **API Connection Issues**
   - Verify API Gateway is running on the correct port
   - Check `NEXT_PUBLIC_API_URL` environment variable
   - Ensure API key is valid and properly set

3. **Microphone Permission Denied**
   - Check browser permissions for microphone access
   - Ensure HTTPS is used in production (required for microphone access)
   - Try refreshing the page and granting permission again

4. **Audio Playback Issues**
   - Check browser audio settings
   - Ensure audio format is supported by the browser
   - Try different audio formats in TTS settings

5. **Build Errors**
   - Clear `.next` directory and rebuild
   - Check for TypeScript errors
   - Ensure all dependencies are installed

### Performance Optimization

1. **Image Optimization**
   - Use Next.js Image component for optimized images
   - Compress images before adding to public directory

2. **Bundle Size**
   - Use dynamic imports for large components
   - Remove unused dependencies
   - Enable tree shaking

3. **Caching**
   - Configure appropriate cache headers
   - Use React Query for client-side caching
   - Implement service worker for offline support

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Credits

- **AI4Bharat** - For providing the ASR, TTS, and NMT services
- **Dhruva Platform** - For reference implementation patterns
- **Chakra UI** - For the component library
- **Next.js** - For the React framework
- **React Query** - For data fetching and caching

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review the API documentation
3. Check the browser console for error messages
4. Verify network connectivity and API service status