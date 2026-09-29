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

/** Parenthetical acronym already present in the service title, when one exists. */
export function getServiceShortCode(id: ServiceId): string | undefined {
  const match = getServiceTitle(id).match(/\(([A-Z]{2,6})\)$/);
  return match?.[1];
}

/** Pastel identity palette for Explore cards. Not a global action colour. */
export type ServiceAccentShade = 50 | 300 | 400 | 600;

export const SERVICE_ACCENT: Record<
  ServiceId,
  Record<ServiceAccentShade, string>
> = {
  asr: { 50: "#FFE9E2", 300: "#FFB8A4", 400: "#FF9C86", 600: "#FF7A61" },
  tts: { 50: "#EAF0FF", 300: "#B3C7FF", 400: "#8CAEFF", 600: "#668FFF" },
  nmt: { 50: "#E7FAF1", 300: "#B3EFD4", 400: "#90E6C0", 600: "#6AD2A7" },
  llm: { 50: "#FFE6FA", 300: "#FFB3EB", 400: "#FF8CDE", 600: "#F061C8" },
  pipeline: { 50: "#F8F0FA", 300: "#E4C9EE", 400: "#D8AFE8", 600: "#C08BD8" },
  ocr: { 50: "#E5F7F7", 300: "#B5E8E8", 400: "#90DDDD", 600: "#6BC7C7" },
  transliteration: { 50: "#E8FCFA", 300: "#B5F3EC", 400: "#8DEBDD", 600: "#6BD2C1" },
  "language-detection": { 50: "#FFE9EE", 300: "#FFBBC8", 400: "#FF9EAF", 600: "#FF7A8F" },
  "speaker-diarization": { 50: "#FFF9E6", 300: "#FEE5A8", 400: "#FFDA7A", 600: "#F5C554" },
  "language-diarization": { 50: "#F3FFE8", 300: "#D4FFAA", 400: "#C0FF85", 600: "#99F45A" },
  "audio-language-detection": { 50: "#E7F7FF", 300: "#B3E4FF", 400: "#89D6FF", 600: "#63C5FF" },
  ner: { 50: "#F1E8FF", 300: "#D0BBFF", 400: "#BA9AFF", 600: "#9D72FF" },
};

export function getServiceAccent(
  id: ServiceId,
  shade: ServiceAccentShade,
): string {
  return SERVICE_ACCENT[id][shade];
}

/** Shared Explore card chrome. `available` is false for anonymous-blocked services. */
export function getExploreServiceCardVisuals(id: ServiceId, available: boolean) {
  const accent = SERVICE_ACCENT[id];
  if (available) {
    return {
      iconBg: accent[50],
      iconColor: accent[600],
      iconHoverBg: accent[300],
      accentBorder: accent[400],
      badgeBg: accent[50],
      badgeColor: accent[600],
      ctaBg: accent[50],
      ctaBorder: accent[50],
      ctaHoverBg: accent[300],
      ctaColor: "ink.800",
    };
  }
  return {
    iconBg: accent[50],
    iconColor: accent[300],
    iconHoverBg: accent[50],
    accentBorder: accent[300],
    badgeBg: accent[50],
    badgeColor: accent[300],
    ctaBg: "transparent",
    ctaBorder: undefined,
    ctaHoverBg: undefined,
    ctaColor: undefined,
  };
}

/** Try-it page path. Always `/${serviceId}`. `pipeline-builder` is not a ServiceId. */
export function servicePath(id: ServiceId): `/${ServiceId}` {
  return `/${id}`;
}

/** Path → ServiceId for the 12 Try-it pages. */
export const PATH_TO_SERVICE_ID: Record<string, ServiceId> = Object.fromEntries(
  (Object.keys(SERVICE_METADATA) as ServiceId[]).map((id) => [
    servicePath(id),
    id,
  ]),
) as Record<string, ServiceId>;
