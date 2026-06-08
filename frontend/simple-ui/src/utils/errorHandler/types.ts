export interface ErrorInfo {
  title: string;
  message: string;
  showOnlyMessage?: boolean;
}

export type ErrorHandlerService =
  | "asr"
  | "tts"
  | "nmt"
  | "pipeline"
  | "ocr"
  | "transliteration"
  | "language-detection"
  | "speaker-diarization"
  | "audio-language-detection"
  | "ner";

export type ErrorCatalogEntry = { title: string; description: string };
export type ErrorCatalog = Record<string, ErrorCatalogEntry>;

export type ErrorDetail = Record<string, unknown>;
