/** Service column metadata for the tenant × service heatmap. */
export const METERING_HEATMAP_SERVICES = [
  { key: "nmt", shortLabel: "NMT", displayName: "NMT" },
  { key: "asr", shortLabel: "ASR", displayName: "ASR" },
  { key: "tts", shortLabel: "TTS", displayName: "TTS" },
  { key: "llm", shortLabel: "LLM", displayName: "LLM" },
  { key: "ocr", shortLabel: "OCR", displayName: "OCR" },
  { key: "transliteration", shortLabel: "Translit", displayName: "Transliteration" },
  { key: "pipeline", shortLabel: "Pipeline", displayName: "Pipeline" },
  { key: "ner", shortLabel: "NER", displayName: "NER" },
  { key: "language_detection", shortLabel: "Text LD", displayName: "Language Detection" },
  { key: "audio_language_detection", shortLabel: "Audio LD", displayName: "Audio Language Detection" },
  { key: "speaker_diarization", shortLabel: "Spk. Diar.", displayName: "Speaker Diarization" },
] as const;

export type MeteringHeatmapServiceKey = (typeof METERING_HEATMAP_SERVICES)[number]["key"];

const HEATMAP_PALETTE = [
  "#FFFAF5",
  "#FFF7ED",
  "#FFEDD5",
  "#FED7AA",
  "#FDBA74",
  "#FB923C",
  "#EA580C",
] as const;

/** Orange heatmap background for a normalized intensity 0–1. */
export function heatmapIntensityColor(intensity: number): string {
  if (intensity <= 0) return HEATMAP_PALETTE[0];
  const idx = Math.min(
    HEATMAP_PALETTE.length - 1,
    Math.ceil(intensity * (HEATMAP_PALETTE.length - 1)),
  );
  return HEATMAP_PALETTE[idx];
}

export function heatmapTextColor(intensity: number): string {
  return intensity >= 0.55 ? "white" : "gray.800";
}
