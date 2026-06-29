// Alerting form allowed values and hierarchy maps

export const CATEGORIES = ["application", "infrastructure"] as const;

export const SEVERITIES = ["critical", "warning", "info"] as const;

export const URGENCIES = ["high", "medium", "low"] as const;

export const RBAC_ROLES = ["ADMIN", "MODERATOR", "USER", "GUEST"] as const;

export const DEFAULT_GROUP_BY = ["alertname", "category", "severity", "organization"] as const;

export const EVAL_INTERVALS = ["30s", "1m", "5m"] as const;

export const FOR_DURATIONS = ["1m", "2m", "5m", "10m"] as const;

/** category → allowed subcategories */
export const SUB_CATEGORIES_BY_CATEGORY: Record<string, { value: string; label: string }[]> = {
  application: [
    { value: "performance", label: "Performance" },
    { value: "availability", label: "Availability" },
  ],
  infrastructure: [
    { value: "compute", label: "Compute" },
    { value: "storage", label: "Storage" },
  ],
};

/** sub_category → allowed signals */
export const SIGNALS_BY_SUB_CATEGORY: Record<string, { value: string; label: string }[]> = {
  performance: [{ value: "latency", label: "Latency" }],
  availability: [{ value: "error_rate", label: "Error Rate" }],
  compute: [
    { value: "cpu_utilization", label: "CPU Utilization" },
    { value: "memory_utilization", label: "Memory Utilization" },
  ],
  storage: [{ value: "disk_utilization", label: "Disk Utilization" }],
};

/** signal → allowed signal_metrics */
export const SIGNAL_METRICS_BY_SIGNAL: Record<string, { value: string; label: string }[]> = {
  latency: [
    { value: "latency_p50", label: "Latency P50" },
    { value: "latency_p99", label: "Latency P99" },
  ],
  error_rate: [
    { value: "error_rate_4xx", label: "4xx Error Rate" },
    { value: "error_rate_5xx", label: "5xx Error Rate" },
    { value: "error_rate_timeout", label: "Timeout Error Rate" },
  ],
  cpu_utilization: [{ value: "total_cpu_usage", label: "Total CPU Usage" }],
  memory_utilization: [{ value: "total_memory_usage", label: "Total Memory Usage" }],
  disk_utilization: [{ value: "total_disk_usage", label: "Total Disk Usage" }],
};

/** All 11 application services (not used for infrastructure — always all) */
export const TARGET_SERVICES: { value: string; label: string }[] = [
  { value: "asr", label: "ASR (Automatic Speech Recognition)" },
  { value: "nmt", label: "NMT (Neural Machine Translation)" },
  { value: "tts", label: "TTS (Text-to-Speech)" },
  { value: "llm", label: "LLM (Large Language Model)" },
  { value: "audio-language-detection", label: "Audio Language Detection" },
  { value: "language-detection", label: "Language Detection" },
  { value: "language-diarization", label: "Language Diarization" },
  { value: "speaker-diarization", label: "Speaker Diarization" },
  { value: "ocr", label: "OCR (Optical Character Recognition)" },
  { value: "transliteration", label: "Transliteration" },
  { value: "ner", label: "NER (Named Entity Recognition)" },
];

/** UI checkbox values → platform-core inference task keys (see promql_builder.INFERENCE_TASKS). */
export const UI_VALUE_TO_INFERENCE_TASK: Record<string, string> = {
  asr: "asr",
  nmt: "nmt",
  tts: "tts",
  llm: "llm",
  ocr: "ocr",
  ner: "ner",
  transliteration: "transliteration",
  "language-detection": "language_detection",
  "language-diarization": "language_diarization",
  "speaker-diarization": "speaker_diarization",
  "audio-language-detection": "audio_language_detection",
};

export const INFERENCE_TASK_TO_UI_VALUE: Record<string, string> = Object.fromEntries(
  Object.entries(UI_VALUE_TO_INFERENCE_TASK).map(([ui, task]) => [task, ui])
) as Record<string, string>;

export const CONDITION_OPERATORS: { value: string; label: string }[] = [
  { value: "<", label: "<" },
  { value: "<=", label: "<=" },
  { value: ">", label: ">" },
  { value: ">=", label: ">=" },
];

/** Only for latency signal — user can pick ms or s */
export const LATENCY_THRESHOLD_UNITS: { value: string; label: string }[] = [
  { value: "ms", label: "ms" },
  { value: "s", label: "s" },
];

/** For all non-latency signals — always percentage, no choice */
export const PERCENTAGE_UNIT = "%";

export const THRESHOLD_UNITS: { value: string; label: string }[] = [
  { value: "ms", label: "ms" },
  { value: "s", label: "s" },
  { value: "%", label: "%" },
];
