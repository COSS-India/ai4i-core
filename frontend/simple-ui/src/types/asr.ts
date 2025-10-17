// TypeScript type definitions for ASR service

import { Language, LanguagePair } from './common';

// ASR Inference Request
export interface ASRInferenceRequest {
  audio: Array<{
    audioContent: string;
  }>;
  config: {
    language: {
      sourceLanguage: string;
    };
    serviceId: string;
    audioFormat: string;
    encoding: string;
    samplingRate: number;
  };
  controlConfig?: {
    dataTracking?: boolean;
  };
}

// ASR Inference Response
export interface ASRInferenceResponse {
  output: Array<{
    source: string;
    nBestTokens?: any;
  }>;
}

// ASR Streaming Configuration
export interface ASRStreamingConfig {
  serviceId: string;
  language: string;
  samplingRate: number;
  apiKey?: string;
  preProcessors?: string[];
  postProcessors?: string[];
}

// ASR Streaming Response
export interface ASRStreamingResponse {
  transcript: string;
  isFinal: boolean;
  confidence?: number;
  timestamp: number;
}

// ASR Model
export interface ASRModel {
  model_id: string;
  languages: string[];
  description: string;
}

// ASR Service Health Response
export interface ASRHealthResponse {
  status: string;
  components: {
    [key: string]: {
      status: string;
      details?: any;
    };
  };
}

// ASR Service Models Response
export interface ASRModelsResponse {
  models: ASRModel[];
}

// ASR Hook State
export interface ASRHookState {
  language: string;
  sampleRate: number;
  inferenceMode: 'rest' | 'streaming';
  recording: boolean;
  fetching: boolean;
  fetched: boolean;
  audioText: string;
  responseWordCount: number;
  requestTime: string;
  recorder: any;
  audioStream: MediaStream | null;
  timer: number;
  error: string | null;
}

// ASR Hook Methods
export interface ASRHookMethods {
  startRecording: () => void;
  stopRecording: () => void;
  handleFileUpload: (file: File) => void;
  performInference: (audioContent: string) => Promise<void>;
  setLanguage: (language: string) => void;
  setSampleRate: (sampleRate: number) => void;
  setInferenceMode: (mode: 'rest' | 'streaming') => void;
  clearResults: () => void;
  resetTimer: () => void;
}

// ASR Hook Return Type
export type UseASRReturn = ASRHookState & ASRHookMethods;

// ASR Component Props
export interface AudioRecorderProps {
  onAudioReady: (audioBase64: string) => void;
  isRecording: boolean;
  onRecordingChange: (recording: boolean) => void;
  sampleRate: number;
  disabled?: boolean;
}

export interface AudioPlayerProps {
  audioSrc: string;
  showVisualization?: boolean;
  onPlay?: () => void;
  onPause?: () => void;
  onEnded?: () => void;
}

export interface ASRResultsProps {
  transcript: string;
  wordCount: number;
  responseTime: number;
  confidence?: number;
  onCopy?: () => void;
  onDownload?: () => void;
}

// ASR Streaming Hook State
export interface ASRStreamingState {
  isConnected: boolean;
  isStreaming: boolean;
  transcript: string;
  finalTranscript: string;
  error: string | null;
}

// ASR Streaming Hook Methods
export interface ASRStreamingMethods {
  startStreaming: () => void;
  stopStreaming: () => void;
  sendAudioData: (audioData: ArrayBuffer) => void;
  clearTranscript: () => void;
}

// ASR Streaming Hook Return Type
export type UseASRStreamingReturn = ASRStreamingState & ASRStreamingMethods;
