/**
 * Per-service defaults for the reusable service page components.
 * Extend when adding a new AI service try-it page.
 */

import type { ServiceInputType } from "../types/servicePage";
import type { ServiceId } from "./serviceMetadata";

export interface ServicePageDefaults {
  inputType: ServiceInputType;
  submitLabel: string;
  submitLoadingLabel: string;
  helperText?: string;
  textPlaceholder?: string;
  maxTextLength?: number;
  showExport?: boolean;
}

export const SERVICE_PAGE_DEFAULTS: Partial<Record<ServiceId, ServicePageDefaults>> = {
  nmt: {
    inputType: "text",
    submitLabel: "Translate",
    submitLoadingLabel: "Translating...",
    helperText:
      'Select an NMT service and languages above, enter text, then click "Translate".',
    textPlaceholder: "Type your text here to translate...",
    maxTextLength: 512,
  },
  asr: {
    inputType: "audio",
    submitLabel: "Transcribe",
    submitLoadingLabel: "Transcribing...",
    helperText: "Record or upload audio above, then click Transcribe to generate the transcript.",
  },
  tts: {
    inputType: "text",
    submitLabel: "Generate Audio",
    submitLoadingLabel: "Generating...",
    textPlaceholder: "Enter text to synthesize...",
  },
  llm: {
    inputType: "text",
    submitLabel: "Process",
    submitLoadingLabel: "Processing...",
    textPlaceholder: "Enter text to process...",
    maxTextLength: 512,
  },
  ocr: {
    inputType: "image",
    submitLabel: "Extract Text",
    submitLoadingLabel: "Extracting...",
    showExport: true,
  },
  transliteration: {
    inputType: "text",
    submitLabel: "Transliterate",
    submitLoadingLabel: "Transliterating...",
  },
  ner: {
    inputType: "text",
    submitLabel: "Analyze",
    submitLoadingLabel: "Analyzing...",
  },
  "language-detection": {
    inputType: "text",
    submitLabel: "Detect Language",
    submitLoadingLabel: "Detecting...",
  },
};

export function getServicePageDefaults(serviceId: ServiceId): ServicePageDefaults {
  return (
    SERVICE_PAGE_DEFAULTS[serviceId] ?? {
      inputType: "text",
      submitLabel: "Submit",
      submitLoadingLabel: "Processing...",
    }
  );
}
