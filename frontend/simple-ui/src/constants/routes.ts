// Sidebar navigation tab ids (route segments)

/** Sidebar nav item ids (kebab-case segments; `home` uses path `/` not `/home`). */
export const TABS = {
  home: "home",
  modelManagement: "model-management",
  servicesManagement: "services-management",
  tenantManagement: "tenant-management",
  apiKeyManagement: "api-key-management",
  logs: "logs",
  usageDashboard: "usage-dashboard",
  traces: "traces",
  alertsManagement: "alerts-management",
  piiManagement: "pii-management",
  tierManagement: "tier-management",
  policyManagement: "policy-management",
  nmt: "nmt",
  asr: "asr",
  tts: "tts",
  llm: "llm",
  pipeline: "pipeline",
  ocr: "ocr",
  transliteration: "transliteration",
  languageDetection: "language-detection",
  speakerDiarization: "speaker-diarization",
  languageDiarization: "language-diarization",
  audioLanguageDetection: "audio-language-detection",
  ner: "ner",
} as const;

/** Route path segments keyed by sidebar tab id. */
export const ROUTES = TABS;
