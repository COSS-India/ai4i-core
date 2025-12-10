// TypeScript type definitions for NMT service

import { LanguagePair } from './common';

// Re-export LanguagePair for convenience
export type { LanguagePair };

// NMT Inference Request
export interface NMTInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    language: {
      sourceLanguage: string;
      targetLanguage: string;
      sourceScriptCode?: string;
      targetScriptCode?: string;
    };
    serviceId: string;
  };
  controlConfig?: {
    dataTracking?: boolean;
  };
}

// NMT Inference Response
export interface NMTInferenceResponse {
  output: Array<{
    source: string;
    target: string;
  }>;
}

// NMT Model
export interface NMTModel {
  model_id: string;
  language_pairs: Array<{
    source: string;
    target: string;
  }>;
  description: string;
}

// Translation Result
export interface TranslationResult {
  source: string;
  target: string;
  confidence?: number;
  languageDetected?: string;
}

// NMT Service Health Response
export interface NMTHealthResponse {
  status: string;
  components: {
    [key: string]: {
      status: string;
      details?: any;
    };
  };
}

// NMT Service Models Response
export interface NMTModelsResponse {
  models: NMTModel[];
}

// NMT Hook State
export interface NMTHookState {
  languagePair: LanguagePair;
  selectedServiceId: string;
  inputText: string;
  translatedText: string;
  fetching: boolean;
  fetched: boolean;
  requestWordCount: number;
  responseWordCount: number;
  requestTime: string;
  error: string | null;
}

// NMT Hook Methods
export interface NMTHookMethods {
  performInference: (text: string) => Promise<void>;
  setInputText: (text: string) => void;
  setLanguagePair: (pair: LanguagePair) => void;
  setSelectedServiceId: (serviceId: string) => void;
  clearResults: () => void;
  swapLanguages: () => void;
}

// NMT Hook Return Type
export type UseNMTReturn = NMTHookState & NMTHookMethods;

// NMT Component Props
export interface LanguageSelectorProps {
  languagePair: LanguagePair;
  onLanguagePairChange: (pair: LanguagePair) => void;
  availableLanguagePairs: LanguagePair[];
  loading?: boolean;
}

export interface TextTranslatorProps {
  inputText: string;
  translatedText: string;
  onInputChange: (text: string) => void;
  onTranslate: () => void;
  isLoading: boolean;
  sourceLanguage: string;
  maxLength?: number;
  disabled?: boolean;
}

export interface TranslationResultsProps {
  sourceText: string;
  translatedText: string;
  requestWordCount: number;
  responseWordCount: number;
  responseTime: number;
  confidence?: number;
  onCopySource?: () => void;
  onCopyTranslation?: () => void;
  onSwapTexts?: () => void;
}

// NMT Language Pair Options
export interface LanguagePairOption {
  value: LanguagePair;
  label: string;
  sourceLabel: string;
  targetLabel: string;
}

// NMT Translation History
export interface TranslationHistoryItem {
  id: string;
  sourceText: string;
  translatedText: string;
  languagePair: LanguagePair;
  timestamp: number;
  confidence?: number;
}

// NMT Batch Translation Request
export interface NMTBatchInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    language: {
      sourceLanguage: string;
      targetLanguage: string;
      sourceScriptCode?: string;
      targetScriptCode?: string;
    };
    serviceId: string;
  };
  controlConfig?: {
    dataTracking?: boolean;
  };
}

// NMT Batch Translation Response
export interface NMTBatchInferenceResponse {
  output: Array<{
    source: string;
    target: string;
  }>;
}

// NMT Language Detection
export interface LanguageDetectionResult {
  language: string;
  confidence: number;
  isReliable: boolean;
}

// NMT Supported Languages Response
export interface SupportedLanguagesResponse {
  languages: Array<{
    code: string;
    name: string;
    scriptCode?: string;
  }>;
  languagePairs: Array<{
    source: string;
    target: string;
    sourceScriptCode?: string;
    targetScriptCode?: string;
  }>;
}

// NMT Languages Endpoint Response
export interface NMTLanguagesResponse {
  model_id: string;
  provider: string;
  supported_languages: string[];
  language_details: Array<{
    code: string;
    name: string;
  }>;
  total_languages: number;
}

// NMT Model Details Response
export interface NMTModelDetailsResponse {
  model_id: string;
  provider: string;
  supported_languages: string[];
  description: string;
  max_batch_size: number;
  supported_scripts: string[];
}

// NMT Service Details Response
export interface NMTServiceDetailsResponse {
  service_id: string;
  model_id: string;
  triton_endpoint: string;
  triton_model: string;
  provider: string; // Keep for backward compatibility
  description: string; // Keep for backward compatibility
  name: string;
  serviceDescription: string;
  supported_languages: string[];
  supported_language_pairs?: Array<{
    sourceLanguage: string;
    targetLanguage: string;
    sourceScriptCode?: string;
    targetScriptCode?: string;
  }>;
}
