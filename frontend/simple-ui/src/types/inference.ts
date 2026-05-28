/**
 * Inference API request/response types for AI4I services.
 *
 * Aligned with the unified inference envelope (text `input`, `audio`, or `image`
 * plus `config`). Responses use an `output` array for most tasks; TTS returns `audio`.
 *
 * Types are intentionally loose so backend schema changes do not require frontend
 * Zod updates. Use optional known fields for IDE hints; extra keys are allowed.
 *
 * @see https://dev.ai4inclusion.org/inference/docs#/
 */

/** Arbitrary JSON object from inference APIs (config blobs, SMR metadata, etc.). */
export type InferenceJson = Record<string, unknown>;

export interface InferenceControlConfig {
  dataTracking?: boolean;
  timeout_ms?: number;
  priority?: string;
  cache_result?: boolean;
  [key: string]: unknown;
}

// ── Input items ─────────────────────────────────────────────────────────────

export interface InferenceTextInput {
  source: string;
  audioDuration?: number;
  [key: string]: unknown;
}

export interface InferenceAudioInput {
  audioContent?: string;
  audioUri?: string;
  [key: string]: unknown;
}

export interface InferenceImageInput {
  imageContent?: string | null;
  imageUri?: string | null;
  [key: string]: unknown;
}

// ── Config (service-specific fields allowed via index signature) ───────────

export interface InferenceLanguageConfig {
  sourceLanguage: string;
  targetLanguage?: string;
  sourceScriptCode?: string;
  targetScriptCode?: string;
  [key: string]: unknown;
}

export interface InferenceServiceConfig {
  serviceId?: string;
  language?: InferenceLanguageConfig;
  /** TTS / ASR */
  gender?: string;
  audioFormat?: string;
  samplingRate?: number;
  encoding?: string;
  preProcessors?: string[];
  postProcessors?: string[];
  transcriptionFormat?: string;
  bestTokenCount?: number;
  textDetection?: boolean;
  isSentence?: boolean;
  numSuggestions?: number;
  inputLanguage?: string;
  outputLanguage?: string;
  [key: string]: unknown;
}

// ── Request envelopes ───────────────────────────────────────────────────────

export interface TextInferenceRequest {
  input: InferenceTextInput[];
  config: InferenceServiceConfig;
  controlConfig?: InferenceControlConfig;
}

export interface AudioInferenceRequest {
  audio: InferenceAudioInput[];
  config: InferenceServiceConfig;
  controlConfig?: InferenceControlConfig;
}

export interface ImageInferenceRequest {
  image: InferenceImageInput[];
  config: InferenceServiceConfig;
  controlConfig?: InferenceControlConfig;
}

export type InferenceRequest =
  | TextInferenceRequest
  | AudioInferenceRequest
  | ImageInferenceRequest;

// ── Response envelopes ────────────────────────────────────────────────────────

/** One element in the `output` array; shape varies by task. */
export interface InferenceOutputItem {
  source?: string;
  target?: string;
  /** ASR services often return transcribed text here (with `source` empty). */
  transcript?: string;
  [key: string]: unknown;
}

/** Standard inference response (ASR, NMT, LLM, OCR, NER, LD, etc.). */
export interface InferenceResponse {
  output: InferenceOutputItem[];
  config?: InferenceJson;
  smr_response?: InferenceJson;
}

export interface InferenceAudioOutputItem {
  audioContent: string;
  audioUri?: string;
  [key: string]: unknown;
}

/** TTS returns synthesized audio in `audio`, not `output`. */
export interface TtsInferenceResponse {
  audio: InferenceAudioOutputItem[];
  config?: InferenceJson;
  smr_response?: InferenceJson;
}

// ── Common output item shapes (optional hints only) ─────────────────────────

export interface SourceTextOutputItem extends InferenceOutputItem {
  source?: string;
}

export interface SourceTargetOutputItem extends InferenceOutputItem {
  source?: string;
  target?: string;
}

export interface NBestToken {
  word?: string;
  tokens?: Array<Record<string, number>>;
  [key: string]: unknown;
}

export interface AsrOutputItem extends SourceTextOutputItem {
  transcript?: string;
  nBestTokens?: NBestToken[] | unknown;
}

/** Read ASR text from an output item (`transcript` preferred, then `source`). */
export function getAsrTranscriptText(item?: InferenceOutputItem | null): string {
  if (!item) return '';
  const { transcript, source } = item;
  if (typeof transcript === 'string' && transcript.length > 0) return transcript;
  if (typeof source === 'string') return source;
  return '';
}

export interface NerEntity {
  text: string;
  label: string;
  start: number;
  end: number;
  [key: string]: unknown;
}

export interface NerOutputItem extends SourceTextOutputItem {
  entities?: NerEntity[];
  tokens?: Array<Record<string, unknown>>;
  nerPrediction?: Array<Record<string, unknown>>;
}

/** Normalized entity for NER UI display. */
export interface NerEntityDisplay {
  text: string;
  label: string;
  start: number;
  end: number;
}

function mapNerTokenRecord(t: Record<string, unknown>): NerEntityDisplay | null {
  const text = String(t.text ?? t.token ?? '').trim();
  const label = String(t.entityType ?? t.label ?? t.tag ?? '').trim();
  const start =
    typeof t.startPos === 'number'
      ? t.startPos
      : typeof t.start === 'number'
        ? t.start
        : typeof t.tokenStartIndex === 'number'
          ? t.tokenStartIndex
          : 0;
  const end =
    typeof t.endPos === 'number'
      ? t.endPos
      : typeof t.end === 'number'
        ? t.end
        : typeof t.tokenEndIndex === 'number'
          ? t.tokenEndIndex
          : 0;
  if (!text || !label || label === 'O') return null;
  return { text, label, start, end };
}

function nerEntitiesFromItem(item: Record<string, unknown>): NerEntityDisplay[] {
  const tokens = item.tokens;
  if (Array.isArray(tokens)) {
    return tokens
      .map((t) => (t && typeof t === 'object' ? mapNerTokenRecord(t as Record<string, unknown>) : null))
      .filter((e): e is NerEntityDisplay => e != null);
  }

  const entities = item.entities;
  if (Array.isArray(entities)) {
    return entities
      .map((e) => {
        if (!e || typeof e !== 'object') return null;
        const o = e as Record<string, unknown>;
        return mapNerTokenRecord({
          text: o.text,
          label: o.label,
          start: o.start,
          end: o.end,
        });
      })
      .filter((x): x is NerEntityDisplay => x != null);
  }

  const nerPrediction = item.nerPrediction;
  if (Array.isArray(nerPrediction)) {
    return nerPrediction
      .map((pred) => {
        if (!pred || typeof pred !== 'object') return null;
        const p = pred as Record<string, unknown>;
        const tag = String(p.tag ?? '').trim();
        if (!tag || tag === 'O') return null;
        return mapNerTokenRecord({
          text: p.token,
          label: tag,
          start: p.tokenStartIndex,
          end: p.tokenEndIndex,
        });
      })
      .filter((x): x is NerEntityDisplay => x != null);
  }

  return [];
}

/**
 * Extract NER entities from inference response (`output[]`, or top-level item).
 */
export function parseNerEntities(response: unknown): NerEntityDisplay[] {
  if (!response || typeof response !== 'object') return [];
  const r = response as Record<string, unknown>;

  if (Array.isArray(r.output) && r.output.length > 0) {
    return nerEntitiesFromItem(r.output[0] as Record<string, unknown>);
  }

  if (r.source || r.tokens || r.entities || r.nerPrediction) {
    return nerEntitiesFromItem(r);
  }

  return [];
}

export interface LanguagePrediction {
  langCode: string;
  scriptCode: string;
  langScore: number;
  language: string;
  [key: string]: unknown;
}

export interface LanguageDetectionOutputItem extends SourceTextOutputItem {
  /** Array of predictions, or a JSON string / single object from some API versions. */
  langPrediction?: LanguagePrediction[] | string | Record<string, unknown>;
}

/**
 * Normalize language-detection `langPrediction` (array, JSON string, or single object).
 */
export function parseLanguagePredictions(raw: unknown): LanguagePrediction[] {
  if (raw == null) return [];

  let value: unknown = raw;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return [];
    try {
      value = JSON.parse(trimmed);
    } catch {
      return [];
    }
  }

  const toPrediction = (item: unknown): LanguagePrediction | null => {
    if (!item || typeof item !== 'object') return null;
    const o = item as Record<string, unknown>;
    const langCode = String(o.langCode ?? o.lang_code ?? o.code ?? '').trim();
    const scriptCode = String(o.scriptCode ?? o.script_code ?? o.script ?? 'N/A').trim();
    const langScore =
      typeof o.langScore === 'number'
        ? o.langScore
        : typeof o.lang_score === 'number'
          ? o.lang_score
          : typeof o.score === 'number'
            ? o.score
            : typeof o.confidence === 'number'
              ? o.confidence
              : 0;
    const language = String(
      o.language ?? o.lang ?? o.languageName ?? (langCode || 'Unknown')
    ).trim();
    if (!langCode && language === 'Unknown') return null;
    return { langCode, scriptCode, langScore, language };
  };

  if (Array.isArray(value)) {
    return value.map(toPrediction).filter((p): p is LanguagePrediction => p != null);
  }

  const single = toPrediction(value);
  return single ? [single] : [];
}

export interface DiarizationSegment {
  start: number;
  end: number;
  speaker?: string;
  language?: string;
  text?: string;
  [key: string]: unknown;
}

export interface SegmentedOutputItem extends InferenceOutputItem {
  segments?: DiarizationSegment[];
}

export interface AudioLangDetectionOutputItem extends InferenceOutputItem {
  detectedLanguage?: string;
  language?: string;
  language_code?: string;
  languageCode?: string;
  confidence?: number;
  all_scores?: string | Record<string, unknown>;
}

export interface AudioLanguageDetectionResult {
  language: string;
  confidence: number | null;
  languageCode?: string;
}

/** Display label from API values like `"hi: Hindi"` or `"mai_Latn"`. */
function formatLanguageLabel(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return 'Unknown';
  const colonIdx = trimmed.indexOf(':');
  if (colonIdx >= 0) {
    const after = trimmed.slice(colonIdx + 1).trim();
    if (after) return after;
  }
  return trimmed;
}

/** Normalize audio language detection output (field names and stringified `all_scores`). */
export function parseAudioLanguageDetectionOutput(
  item?: InferenceOutputItem | null
): AudioLanguageDetectionResult {
  if (!item) return { language: 'Unknown', confidence: null };

  const confidence =
    typeof item.confidence === 'number' ? item.confidence : null;

  let allScores: Record<string, unknown> | null = null;
  const rawScores = item.all_scores;
  if (typeof rawScores === 'string') {
    try {
      allScores = JSON.parse(rawScores.trim()) as Record<string, unknown>;
    } catch {
      allScores = null;
    }
  } else if (rawScores && typeof rawScores === 'object') {
    allScores = rawScores as Record<string, unknown>;
  }

  const rawLanguage =
    (typeof item.language_code === 'string' && item.language_code) ||
    (typeof item.languageCode === 'string' && item.languageCode) ||
    (typeof allScores?.predicted_language === 'string' && allScores.predicted_language) ||
    (typeof item.detectedLanguage === 'string' && item.detectedLanguage) ||
    (typeof item.language === 'string' && item.language) ||
    '';

  const language = formatLanguageLabel(String(rawLanguage));
  const languageCode =
    typeof item.language_code === 'string'
      ? item.language_code
      : typeof item.languageCode === 'string'
        ? item.languageCode
        : undefined;

  return {
    language: language === 'Unknown' && !rawLanguage ? 'Unknown' : language,
    confidence,
    languageCode,
  };
}

// ── Service-specific request/response aliases ───────────────────────────────

export type ASRInferenceRequest = AudioInferenceRequest;
export type ASRInferenceResponse = InferenceResponse;

export type NMTInferenceRequest = TextInferenceRequest;
export type NMTInferenceResponse = InferenceResponse;

export type NMTBatchInferenceRequest = TextInferenceRequest;
export type NMTBatchInferenceResponse = InferenceResponse;

export type LLMInferenceRequest = TextInferenceRequest;
export type LLMInferenceResponse = InferenceResponse;

export type TTSInferenceRequest = TextInferenceRequest;
export type { TtsInferenceResponse as TTSInferenceResponse };

export type OCRInferenceRequest = ImageInferenceRequest;
export type OCRInferenceResponse = InferenceResponse;

export type NERInferenceRequest = TextInferenceRequest;
export type NERInferenceResponse = InferenceResponse;

export type TransliterationInferenceRequest = TextInferenceRequest;
export type TransliterationInferenceResponse = InferenceResponse;

export type LanguageDetectionInferenceRequest = TextInferenceRequest;
export type LanguageDetectionInferenceResponse = InferenceResponse;

export type SpeakerDiarizationInferenceRequest = AudioInferenceRequest;
export type SpeakerDiarizationInferenceResponse = InferenceResponse;

export type LanguageDiarizationInferenceRequest = AudioInferenceRequest;
export type LanguageDiarizationInferenceResponse = InferenceResponse;

export type AudioLanguageDetectionInferenceRequest = AudioInferenceRequest;
export type AudioLanguageDetectionInferenceResponse = InferenceResponse;

/** Wrapper returned by many service clients alongside timing headers. */
export interface InferenceTimedResult<T> {
  data: T;
  responseTime: number;
}
