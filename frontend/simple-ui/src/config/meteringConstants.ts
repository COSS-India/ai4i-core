import type { MeteringTopN, MeteringWindow } from "../types/metering";

/** Metering & usage dashboard — copy, defaults, and configuration. */
export const METERING = {
  ERRORS: {
    LOAD_FAILED: "Failed to load metering data.",
    UNAVAILABLE_503:
      "Metering data is temporarily unavailable. Prometheus may not be configured.",
    FORBIDDEN_403: "You do not have permission to view this metering data.",
    BAD_REQUEST_400: "Invalid metering request parameters.",
  },
  BANNERS: {
    DEGRADED:
      "Some metrics could not be loaded completely. Showing partial data from the metering API.",
    DATA_STATE: {
      EMPTY: "No data for selected time window",
      NO_HISTORY:
        "No consumption data found. Usage metrics will appear once API requests are recorded.",
      ERROR_PREFIX: "Unable to refresh data. Last successful refresh at",
    },
  },
  QUERY: {
    STALE_TIME_MS: 60_000,
    TENANT_DIRECTORY_STALE_MS: 5 * 60_000,
    SCOPES: {
      TENANT_DIRECTORY: "tenant-directory",
      OVERVIEW: "overview",
      TENANT: "tenant",
      SERVICE: "service",
      MODEL: "model",
    },
    HEATMAP_SERVICES_ALL: "all",
    SCROLL_ROOT_MARGIN: "100px",
  },
  DEFAULTS: {
    TIME_WINDOW: "24h" satisfies MeteringWindow,
    TOP_N: 10 satisfies MeteringTopN,
    SUB_TAB: "overview" as const,
    /** Tenant Admin lands on Usage and Spend (not legacy My Usage overview). */
    TENANT_SUB_TAB: "usage-spend" as const,
    ASYNC_STATE_HEIGHT: "300px",
    LOADING_MIN_HEIGHT: "400px",
  },
  SUB_TAB: {
    OVERVIEW: "overview",
    TENANT: "tenant",
    SERVICE: "service",
    MODEL: "model",
    USAGE_SPEND: "usage-spend",
  } as const,
  KPI: {
    KEYS: {
      TOTAL_REQUESTS: "total_requests",
      SUCCESSFUL: "successful",
      FAILED: "failed",
      AVG_RPS: "avg_rps",
    },
    HELPERS: {
      total_requests: "across all services and tenants",
      successful: "of all requests",
      failed: "of all requests",
      avg_rps: "requests per second",
    },
  },
  GRAPH: {
    SERIES_KEYS: {
      SUCCESSFUL: "successful",
      FAILED: "failed",
    },
    EMPTY_VALUE: "—",
  },
  TIME_WINDOWS: [
    { value: "1h", label: "Last 1 hour" },
    { value: "24h", label: "Last 24 hours" },
    { value: "7d", label: "Last 7 days" },
    { value: "30d", label: "Last 30 days" },
  ] as const satisfies ReadonlyArray<{ value: MeteringWindow; label: string }>,
  TIME_WINDOW_LABELS: {
    "1h": "last 1 hour",
    "24h": "last 24 hours",
    "7d": "last 7 days",
    "30d": "last 30 days",
  } as const satisfies Record<MeteringWindow, string>,
  TOP_N_OPTIONS: [10, 25] as const satisfies readonly MeteringTopN[],
  TOP_N_SEGMENT_OPTIONS: [
    { id: "10", label: "Top 10" },
    { id: "25", label: "Top 25" },
  ] as const,
  SUB_TABS: [
    { id: "overview", label: "Overview" },
    { id: "tenant", label: "Tenant Consumption" },
    { id: "service", label: "Service Usage" },
    // AI4IDS-2588: extra tab — per-service LLM via /model-consumption
    { id: "model", label: "Model Usage" },
    { id: "usage-spend", label: "Cost and Budget" },
  ] as const,
  TENANT_SUB_TABS: [
    { id: "overview", label: "Overview" },
    { id: "service", label: "Service Usage" },
    { id: "model", label: "Model Usage" },
    { id: "usage-spend", label: "Cost and Budget" },
  ] as const,
  ROLE_VIEWS: {
    adopter: "Adopter Admin",
    tenant: "Tenant Admin",
  } as const,
  CONTROLS: {
    ALL_TENANTS: "All Tenants",
    TOP_N_PREFIX: "Top",
    LAST_REFRESHED_PREFIX: "Last refreshed:",
    REFRESH: "Refresh",
  },
  TENANT_VIEW: {
    TITLE: "My Usage",
  },
  USAGE_SPEND: {
    TITLE: "Usage and Spend",
    ADOPTER_SUBTITLE:
      "Monitor model task type consumption and spend across all tenants",
    TENANT_SUBTITLE_SUFFIX:
      "consumption and spend for the selected billing period",
    BILLING_PERIOD: "BILLING PERIOD",
    CURRENT_MONTH: "Current month",
    LAST_MONTH: "Last month",
    BUDGET_SUMMARY: "BUDGET SUMMARY",
    QUOTA_SUMMARY: "QUOTA SUMMARY",
    SPEND_BY_TASK_TYPE: "SPEND BY MODEL TASK TYPE",
  },
  COLORS: {
    RANK: ["#DD6B20", "#3182CE", "#38A169", "#805AD5", "#00B5D8"] as const,
    PALETTE: [
      "#DD6B20",
      "#3182CE",
      "#38A169",
      "#805AD5",
      "#D69E2E",
      "#319795",
      "#E53E3E",
      "#718096",
      "#B7791F",
      "#4FD1C5",
    ] as const,
    HEATMAP: [
      "#FFFAF5",
      "#FFF7ED",
      "#FFEDD5",
      "#FED7AA",
      "#FDBA74",
      "#FB923C",
      "#EA580C",
    ] as const,
    SERVICE: {
      nmt: "#38A169",
      asr: "#FF7A61",
      tts: "#3182CE",
      llm: "#F061C8",
      ocr: "#319795",
      transliteration: "#99F45A",
      pipeline: "#805AD5",
      ner: "#9D72FF",
      "language-detection": "#DD6B20",
      "audio-language-detection": "#F5C554",
      "speaker-diarization": "#718096",
      "language-diarization": "#4FD1C5",
    } as const,
    /** Fixed per-task-type color, keyed by the raw `inference_types[].name` values from the metering API. */
    TASK_TYPE: {
      llm: "#F061C8",
      asr: "#9B2C2C",
      nmt: "#38A169",
      tts: "#855a69",
      ner: "#060fb4",
      ocr: "#319795",
      transliteration: "#99F45A",
      "language-detection": "#F5C554",
      "language-diarization": "#00B5D8",
      "speaker-diarization": "#718096",
      "audio-lang-detection": "#DD6B20",
      pipeline: "#805AD5",
    } as const,
    CHART: {
      GRID: "#E2E8F0",
      GRID_DARK: "#4A5568",
      AXIS: "#A0AEC0",
      PRIMARY_STROKE: "#3182CE",
      PRIMARY_FILL: "#BEE3F8",
      SUCCESS_FILL: "#4ADE80",
      FAILURE_STROKE: "#F87171",
      TOOLTIP_BORDER: "#E2E8F0",
      DONUT_STROKE: "#FFFFFF",
    } as const,
    HEATMAP_TEXT_HIGH: "#FFFFFF",
  },
  HEATMAP: {
    SERVICES: [
      { key: "nmt", shortLabel: "NMT", displayName: "NMT" },
      { key: "asr", shortLabel: "ASR", displayName: "ASR" },
      { key: "tts", shortLabel: "TTS", displayName: "TTS" },
      { key: "llm", shortLabel: "LLM", displayName: "LLM" },
      { key: "ocr", shortLabel: "OCR", displayName: "OCR" },
      {
        key: "transliteration",
        shortLabel: "Translit",
        displayName: "Transliteration",
      },
      { key: "pipeline", shortLabel: "Pipeline", displayName: "Pipeline" },
      { key: "ner", shortLabel: "NER", displayName: "NER" },
      {
        key: "language_detection",
        shortLabel: "Text LD",
        displayName: "Language Detection",
      },
      {
        key: "audio_language_detection",
        shortLabel: "Audio LD",
        displayName: "Audio Language Detection",
      },
      {
        key: "speaker_diarization",
        shortLabel: "Spk. Diar.",
        displayName: "Speaker Diarization",
      },
    ] as const,
    LEGEND_INDICES: [0, 2, 3, 4, 5, 6] as const,
    INTENSITY_TEXT_THRESHOLD: 0.55,
    TITLE: "Usage by tenant & service",
    SUBTITLE_PREFIX: "Heatmap of request volume per tenant per service ·",
    EMPTY: "No tenant × service data for the selected window.",
    TABLE_TENANT: "Tenant",
    TABLE_TOTAL: "Total",
    FOOTER_PRIMARY:
      "Showing Top {topN} tenants by total request volume. Adjust using the selector above.",
    FOOTER_SECONDARY: "Colour intensity = request volume",
    LEGEND_LOW: "Low",
    LEGEND_HIGH: "High",
  },
  EMPTY: {
    DEFAULT: "No data available.",
    TENANT_CONSUMPTION: "No tenant consumption data available.",
    SERVICE_CONSUMPTION: "No service consumption data available.",
    MODEL_CONSUMPTION: "No model consumption data available.",
    CHART: "No data available for the selected time window.",
  },
  REFRESH: {
    JUST_NOW: "just now",
    SECONDS_AGO_SUFFIX: " sec ago",
    MINUTES_AGO_SUFFIX: "m ago",
  },
  SECTIONS: {
    CONSUMPTION_OVERVIEW: {
      TITLE: "Consumption overview",
      SUBTITLE_SUFFIX: "reflects selected time window ·",
      CONCENTRATION_TITLE: "Usage concentration",
      CONCENTRATION_SUBTITLE:
        "Top 5 by request volume · reflects selected time window",
      DONUT_PRIMARY: "Top 5",
      DONUT_SECONDARY: "tenants",
    },
    PLATFORM_ADOPTION: {
      TITLE: "Platform adoption",
      SUBTITLE: "Tenant overview",
      CARDS: [
        {
          key: "total_tenants",
          label: "Total tenants",
          helper: "registered on platform",
        },
        { key: "active_24h", label: "Active tenants", helper: "last 24 hours" },
        { key: "active_7d", label: "Active tenants", helper: "last 7 days" },
        { key: "active_30d", label: "Active tenants", helper: "last 30 days" },
        {
          key: "new_tenants_7d",
          label: "New — Last 7 days",
          helper: "onboarded in last 7 days",
        },
      ] as const,
    },
    TENANT_RANKING: {
      TITLE: "Tenant ranking",
      SUBTITLE_PREFIX: "By request volume ·",
    },
    REQUEST_VOLUME: {
      TITLE: "Request volume & health",
      SUBTITLE: "Request volume over the selected time window",
      SUCCESSFUL: "Successful",
      FAILED: "Failed",
      FAILURE_RATE_SUFFIX: "failure rate",
      Y_AXIS_REQUESTS: "REQUESTS",
    },
    // AI4IDS-2588: Model Consumption tab — per-service LLM usage from /model-consumption
    MODEL: {
      TITLE: "Model consumption",
      SUBTITLE:
        "Per-service LLM request distribution · reflects selected time window",
      BREAKDOWN_TITLE: "Model breakdown",
      BREAKDOWN_SUBTITLE_PREFIX: "Consumption across LLM services ·",
      DONUT_PRIMARY: "All",
      DONUT_SECONDARY: "Models",
      MOST_USED: "Most used model",
      HIGHEST_FAILURE: "Highest failure rate",
      REQUESTS_SUFFIX: "requests",
      TABLE_SERVICE: "Service",
      TABLE_MODEL: "Model",
      TABLE_TOTAL_REQUESTS: "Total requests",
      TABLE_NATIVE: "Native consumption",
      TABLE_SUCCESS: "Success rate %",
      TABLE_FAILURE: "Failure rate %",
    },
    SERVICE: {
      TITLE: "Service consumption",
      SUBTITLE:
        "Platform-wide request distribution · reflects selected time window",
      BREAKDOWN_TITLE: "Service breakdown",
      BREAKDOWN_SUBTITLE_PREFIX: "Consumption across model task types ·",
      DONUT_PRIMARY: "All",
      DONUT_SECONDARY: "Services",
      MOST_USED: "Most used service",
      HIGHEST_FAILURE: "Highest failure rate",
      REQUESTS_SUFFIX: "requests",
      TABLE_SERVICE: "Service",
      TABLE_TOTAL_REQUESTS: "Total requests",
      TABLE_NATIVE: "Native consumption",
      TABLE_SUCCESS: "Success rate %",
      TABLE_FAILURE: "Failure rate %",
    },
    RANKED_SHARE: {
      HEADER_LEFT: "Request volume & share",
      HEADER_RIGHT: "% of total",
    },
  },
  SERVICE_CSS_KEYS: {
    NMT: "nmt",
    ASR: "asr",
    TTS: "tts",
    LLM: "llm",
    OCR: "ocr",
    Transliteration: "transliteration",
    Pipeline: "pipeline",
    NER: "ner",
    "Language Detection": "language-detection",
    "Audio Language Detection": "audio-language-detection",
    "Speaker Diarization": "speaker-diarization",
    "Language Diarization": "language-diarization",
  } as const,
} as const;

export type MeteringHeatmapServiceKey =
  (typeof METERING.HEATMAP.SERVICES)[number]["key"];

export type MeteringSubTab = (typeof METERING.SUB_TABS)[number]["id"];
