// Pipeline types and interfaces

export type TaskType = 'asr' | 'translation' | 'tts' | 'transliteration';

export interface LanguageConfig {
  sourceLanguage: string;
  targetLanguage?: string;
  sourceScriptCode?: string;
  targetScriptCode?: string;
}

export interface AudioInput {
  audioContent: string;
}

export interface TextInput {
  source: string;
}

export interface PipelineTaskConfig {
  serviceId: string;
  language: LanguageConfig;
  audioFormat?: string;
  preProcessors?: string[];
  postProcessors?: string[];
  transcriptionFormat?: string;
  gender?: string;
  additionalParams?: Record<string, any>;
}

export interface PipelineTask {
  taskType: TaskType;
  config: PipelineTaskConfig;
}

export interface PipelineInferenceRequest {
  pipelineTasks: PipelineTask[];
  inputData: {
    input?: TextInput[];
    audio?: AudioInput[];
  };
  controlConfig?: Record<string, any>;
}

export interface PipelineTaskOutput {
  taskType: string;
  serviceId: string;
  output?: any[];
  audio?: any[];
  config?: any;
}

export interface PipelineInferenceResponse {
  pipelineResponse: PipelineTaskOutput[];
}

export interface PipelineStats {
  requestWordCount: number;
  responseWordCount: number;
  requestTime: string;
  audioDuration: number;
}

export interface PipelineResult {
  sourceText: string;
  targetText: string;
  audio: string;
  stats?: PipelineStats;
}
