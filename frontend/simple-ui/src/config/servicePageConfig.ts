/**
 * Per-service defaults for the reusable service page components.
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
    helperText:
      'Enter text and click "Generate Audio" to create speech synthesis. Adjust voice settings in the configuration panel.',
    textPlaceholder: "Enter text to synthesize...",
    maxTextLength: 512,
  },
  llm: {
    inputType: "text",
    submitLabel: "Translate",
    submitLoadingLabel: "Translating...",
    helperText: 'Enter text and click "Translate" to process.',
    textPlaceholder: "Enter text to process...",
    maxTextLength: 512,
  },
  ocr: {
    inputType: "image",
    submitLabel: "Extract Text",
    submitLoadingLabel: "Extracting...",
    showExport: true,
    helperText:
      "Upload an image or provide an image URL above, then click Extract Text to run OCR.",
  },
  transliteration: {
    inputType: "text",
    submitLabel: "Transliterate",
    submitLoadingLabel: "Processing...",
    helperText:
      "Select a transliteration and languages above, enter source text, then click Transliterate to convert the script.",
    textPlaceholder: "Enter text to transliterate...",
  },
  ner: {
    inputType: "text",
    submitLabel: "Detect Entities",
    submitLoadingLabel: "Processing...",
    helperText:
      'Enter text and select language above, then click "Detect Entities" to extract entities.',
    textPlaceholder: "Enter text to identify entities...",
  },
  "language-detection": {
    inputType: "text",
    submitLabel: "Detect Language",
    submitLoadingLabel: "Detecting...",
    helperText:
      'Enter text and select a service, then click "Detect Language" to identify the language and script.',
  },
  "audio-language-detection": {
    inputType: "audio",
    submitLabel: "Submit for Detection",
    submitLoadingLabel: "Processing...",
    helperText:
      'Record audio or upload a file above, then click "Submit for Detection" to identify the spoken language.',
  },
  "speaker-diarization": {
    inputType: "audio",
    submitLabel: "Submit for Diarization",
    submitLoadingLabel: "Processing...",
    helperText:
      'Record audio or upload a file above, then click "Submit for Diarization" to separate the conversation by speaker.',
  },
  "language-diarization": {
    inputType: "audio",
    submitLabel: "Submit for Diarization",
    submitLoadingLabel: "Processing...",
    helperText:
      'Record audio or upload a file above, then click "Submit for Diarization" to detect language switches in the audio.',
  },
  pipeline: {
    inputType: "custom",
    submitLabel: "Run Pipeline",
    submitLoadingLabel: "Running...",
    helperText:
      "After recording or uploading audio, click Run Pipeline to generate the transcribed text, translated text, and synthesized speech.",
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
