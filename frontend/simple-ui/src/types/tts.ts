// TypeScript type definitions for TTS service

import { Gender, SampleRate, AudioFormat } from './common';

// Re-export common types for convenience
export type { Gender, SampleRate, AudioFormat };

// TTS Inference Request
export interface TTSInferenceRequest {
  input: Array<{
    source: string;
    audioDuration?: number;
  }>;
  config: {
    language: {
      sourceLanguage: string;
    };
    serviceId: string;
    gender: string;
    samplingRate: number;
    audioFormat: string;
  };
  controlConfig?: {
    dataTracking?: boolean;
  };
}

// TTS Inference Response
export interface TTSInferenceResponse {
  audio: Array<{
    audioContent: string;
    audioUri?: string;
  }>;
  config?: {
    language: any;
    audioFormat: string;
    encoding: string;
    samplingRate: number;
    audioDuration?: number;
  };
}

// TTS Streaming Configuration
export interface TTSStreamingConfig {
  serviceId: string;
  voice_id: string;
  language: string;
  gender: string;
  samplingRate: number;
  audioFormat: string;
  apiKey?: string;
}

// TTS Streaming Response
export interface TTSStreamingResponse {
  audioContent: string;
  isFinal: boolean;
  duration?: number;
  timestamp: number;
  format: string;
}

// Voice Model
export interface Voice {
  voice_id: string;
  name: string;
  gender: Gender;
  age: 'young' | 'adult' | 'senior';
  languages: string[];
  model_id: string;
  sample_rate: number;
  description?: string;
  is_active: boolean;
}

// Voice List Response
export interface VoiceListResponse {
  voices: Voice[];
  total: number;
  filtered: number;
}

// TTS Service Health Response
export interface TTSHealthResponse {
  status: string;
  components: {
    [key: string]: {
      status: string;
      details?: any;
    };
  };
}

// TTS Hook State
export interface TTSHookState {
  language: string;
  gender: Gender;
  audioFormat: AudioFormat;
  samplingRate: SampleRate;
  inputText: string;
  audio: string;
  fetching: boolean;
  fetched: boolean;
  requestWordCount: number;
  requestTime: string;
  audioDuration: number;
  error: string | null;
}

// TTS Hook Methods
export interface TTSHookMethods {
  performInference: (text: string) => Promise<void>;
  setInputText: (text: string) => void;
  setLanguage: (language: string) => void;
  setGender: (gender: Gender) => void;
  setAudioFormat: (format: AudioFormat) => void;
  setSamplingRate: (rate: SampleRate) => void;
  clearResults: () => void;
  playAudio: () => void;
  pauseAudio: () => void;
  downloadAudio: () => void;
}

// TTS Hook Return Type
export type UseTTSReturn = TTSHookState & TTSHookMethods;

// TTS Component Props
export interface TextInputProps {
  value: string;
  onChange: (text: string) => void;
  language: string;
  maxLength?: number;
  placeholder?: string;
  disabled?: boolean;
}

export interface VoiceSelectorProps {
  language: string;
  gender: Gender;
  audioFormat: AudioFormat;
  samplingRate: SampleRate;
  onLanguageChange: (language: string) => void;
  onGenderChange: (gender: Gender) => void;
  onFormatChange: (format: AudioFormat) => void;
  onSampleRateChange: (rate: SampleRate) => void;
  availableLanguages: string[];
  availableVoices?: Voice[];
  loading?: boolean;
}

export interface TTSResultsProps {
  audioSrc: string;
  wordCount: number;
  responseTime: number;
  audioDuration: number;
  onPlay?: () => void;
  onPause?: () => void;
  onDownload?: () => void;
}

// TTS Streaming Hook State
export interface TTSStreamingState {
  isConnected: boolean;
  isStreaming: boolean;
  audioChunks: string[];
  currentAudio: string;
  error: string | null;
}

// TTS Streaming Hook Methods
export interface TTSStreamingMethods {
  startStreaming: (text: string) => void;
  stopStreaming: () => void;
  clearAudio: () => void;
}

// TTS Streaming Hook Return Type
export type UseTTSStreamingReturn = TTSStreamingState & TTSStreamingMethods;

// TTS Voice Filter Options
export interface VoiceFilterOptions {
  language?: string;
  gender?: Gender;
  age?: 'young' | 'adult' | 'senior';
  isActive?: boolean;
}

// TTS Audio Player State
export interface AudioPlayerState {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  playbackRate: number;
}
