/**
 * Single source of truth for service titles and descriptions.
 * Used by the home page cards and each service page hero to avoid duplication.
 */

export type ServiceId =
  | "asr"
  | "tts"
  | "nmt"
  | "llm"
  | "pipeline"
  | "ocr"
  | "transliteration"
  | "language-detection"
  | "speaker-diarization"
  | "language-diarization"
  | "audio-language-detection"
  | "ner";

export interface ServiceMeta {
  title: string;
  description: string;
}

export const SERVICE_METADATA: Record<ServiceId, ServiceMeta> = {
  asr: {
    title: "Automatic Speech Recognition (ASR)",
    description: "Convert spoken audio into accurate, readable text in Indic languages.",
  },
  tts: {
    title: "Text-to-Speech (TTS)",
    description: "Generate natural-sounding speech from text in Indic languages.",
  },
  nmt: {
    title: "Neural Machine Translation (NMT)",
    description: "Translate text instantly across Indic languages.",
  },
  llm: {
    title: "Large Language Model (LLM)",
    description: "Perform contextual translation and language tasks using advanced AI models.",
  },
  pipeline: {
    title: "Speech to Speech Pipeline",
    description: "Transform spoken input into translated speech output using chained AI models.",
  },
  ocr: {
    title: "Optical Character Recognition (OCR)",
    description: "Extract editable text from images and scanned documents.",
  },
  transliteration: {
    title: "Transliteration",
    description: "Convert text from one script to another while preserving pronunciation.",
  },
  "language-detection": {
    title: "Text Language Detection",
    description: "Automatically identify the language and script of any text input.",
  },
  "speaker-diarization": {
    title: "Speaker Diarization",
    description: "Separate audio into segments based on who is speaking.",
  },
  "language-diarization": {
    title: "Language Diarization",
    description: "Detect language switches in real time within spoken audio.",
  },
  "audio-language-detection": {
    title: "Audio Language Detection",
    description: "Identify the spoken language directly from an audio file.",
  },
  ner: {
    title: "Named Entity Recognition (NER)",
    description: "Extract key entities like names, locations, and organizations from text.",
  },
};

export function getServiceTitle(id: ServiceId): string {
  return SERVICE_METADATA[id]?.title ?? id;
}

export function getServiceDescription(id: ServiceId): string {
  return SERVICE_METADATA[id]?.description ?? "";
}
