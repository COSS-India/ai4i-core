// TypeScript type definitions for LLM service

// LLM Inference Request
export interface LLMInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
    inputLanguage?: string;
    outputLanguage?: string;
  };
  controlConfig?: {
    dataTracking?: boolean;
  };
}

// LLM Inference Response
export interface LLMInferenceResponse {
  output: Array<{
    source: string;
    target: string;
  }>;
}

// LLM Model
export interface LLMModel {
  model_id: string;
  provider: string;
  description: string;
  max_batch_size: number;
  supported_languages: string[];
}

// LLM Service Health Response
export interface LLMHealthResponse {
  status: string;
  service: string;
  version: string;
  redis: string;
  postgres: string;
  triton: string;
  timestamp: number;
}

// LLM Hook State
export interface LLMHookState {
  selectedModelId: string;
  inputLanguage: string;
  outputLanguage: string;
  inputText: string;
  outputText: string;
  nmtOutputText?: string;
  fetching: boolean;
  fetched: boolean;
  isDualMode: boolean;
  requestWordCount: number;
  responseWordCount: number;
  nmtResponseWordCount?: number;
  requestTime: string;
  nmtRequestTime?: string;
  error: string | null;
}

// LLM Hook Methods
export interface LLMHookMethods {
  performInference: (text: string) => Promise<void>;
  performDualInference: (text: string) => Promise<void>;
  setInputText: (text: string) => void;
  setInputLanguage: (lang: string) => void;
  setOutputLanguage: (lang: string) => void;
  setSelectedModelId: (modelId: string) => void;
  clearResults: () => void;
  swapLanguages: () => void;
}

// LLM Hook Return Type
export type UseLLMReturn = LLMHookState & LLMHookMethods;

// LLM Component Props
export interface LanguageSelectorProps {
  inputLanguage: string;
  outputLanguage: string;
  onInputLanguageChange: (lang: string) => void;
  onOutputLanguageChange: (lang: string) => void;
  availableLanguages: string[];
}

export interface TextInputProps {
  inputText: string;
  onInputChange: (text: string) => void;
  onProcess: () => void;
  isLoading: boolean;
  inputLanguage: string;
  maxLength?: number;
  disabled?: boolean;
}

export interface LLMResultsProps {
  sourceText: string;
  outputText: string;
  requestWordCount: number;
  responseWordCount: number;
  responseTime: number;
  onCopySource?: () => void;
  onCopyOutput?: () => void;
  onSwapTexts?: () => void;
}

