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
  },
  QUERY: {
    STALE_TIME_MS: 60_000,
    TENANT_DIRECTORY_STALE_MS: 5 * 60_000,
    SCOPES: {
      TENANT_DIRECTORY: "tenant-directory",
      OVERVIEW: "overview",
      TENANT: "tenant",
      SERVICE: "service",
    },
    HEATMAP_SERVICES_ALL: "all",
    SCROLL_ROOT_MARGIN: "100px",
  },
  DEFAULTS: {
    TIME_WINDOW: "24h" satisfies MeteringWindow,
    TOP_N: 10 satisfies MeteringTopN,
    SUB_TAB: "overview" as const,
    ASYNC_STATE_HEIGHT: "300px",
    LOADING_MIN_HEIGHT: "400px",
  },
  SUB_TAB: {
    OVERVIEW: "overview",
    TENANT: "tenant",
    SERVICE: "service",
  } as const,
  KPI: {
    KEYS: {
      TOTAL_REQUESTS: "total_requests",
      SUCCESS_RATE: "success_rate",
      AVG_RPS: "avg_rps",
      AVG_REQUESTS_PER_TENANT: "avg_requests_per_tenant",
    },
    HELPERS: {
      total_requests: "across selected window",
      success_rate: "of all requests",
      avg_rps: "requests per second",
      avg_requests_per_tenant: "across active tenants",
    },
  },
  GRAPH: {
    SERIES_KEYS: {
      SUCCESSFUL: "successful",
      FAILED: "failed",
    },
    // Backend bucket sizes per window (see WINDOW_STEP in metering_promql_builder.py).
    // Label formatting keys off the step's duration, not these exact strings.
    STEP: {
      TEN_MINUTES: "10m",
      FOUR_HOURS: "4h",
      SIX_HOURS: "6h",
      ONE_DAY: "1d",
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
  TOP_N_OPTIONS: [5, 10, 25] as const satisfies readonly MeteringTopN[],
  TOP_N_SEGMENT_OPTIONS: [
    { id: "5", label: "Top 5" },
    { id: "10", label: "Top 10" },
    { id: "25", label: "Top 25" },
  ] as const,
  SUB_TABS: [
    { id: "overview", label: "Overview" },
    { id: "tenant", label: "Tenant Consumption" },
    { id: "service", label: "Service Consumption" },
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
  COLORS: {
    RANK: [
      "#DD6B20",
      "#3182CE",
      "#38A169",
      "#805AD5",
      "#00B5D8",
    ] as const,
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
    CHART: {
      GRID: "#E2E8F0",
      GRID_DARK: "#4A5568",
      AXIS: "#A0AEC0",
      PRIMARY_STROKE: "#3182CE",
      PRIMARY_FILL: "#BEE3F8",
      FAILURE_STROKE: "#E53E3E",
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
      { key: "transliteration", shortLabel: "Translit", displayName: "Transliteration" },
      { key: "pipeline", shortLabel: "Pipeline", displayName: "Pipeline" },
      { key: "ner", shortLabel: "NER", displayName: "NER" },
      { key: "language_detection", shortLabel: "Text LD", displayName: "Language Detection" },
      { key: "audio_language_detection", shortLabel: "Audio LD", displayName: "Audio Language Detection" },
      { key: "speaker_diarization", shortLabel: "Spk. Diar.", displayName: "Speaker Diarization" },
    ] as const,
    LEGEND_INDICES: [0, 2, 3, 4, 5, 6] as const,
    INTENSITY_TEXT_THRESHOLD: 0.55,
    TITLE: "Usage by tenant & service",
    SUBTITLE_PREFIX: "Heatmap of request volume per tenant per service ·",
    EMPTY: "No tenant × service data for the selected window.",
    TABLE_TENANT: "Tenant",
    TABLE_TOTAL: "Total",
    FOOTER_PRIMARY: "Showing Top {topN} tenants by total request volume. Adjust using the selector above.",
    FOOTER_SECONDARY: "Colour intensity = request volume",
    LEGEND_LOW: "Low",
    LEGEND_HIGH: "High",
  },
  EMPTY: {
    DEFAULT: "No data available.",
    TENANT_CONSUMPTION: "No tenant consumption data available.",
    SERVICE_CONSUMPTION: "No service consumption data available.",
    CHART: "No chart data available for the selected window.",
  },
  REFRESH: {
    JUST_NOW: "just now",
    MINUTES_AGO_SUFFIX: "m ago",
  },
  SECTIONS: {
    CONSUMPTION_OVERVIEW: {
      TITLE: "Consumption overview",
      SUBTITLE_SUFFIX: "reflects selected time window ·",
      CONCENTRATION_TITLE: "Usage concentration",
      CONCENTRATION_SUBTITLE: "Top 5 by request volume · reflects selected time window",
      DONUT_PRIMARY: "Top 5",
      DONUT_SECONDARY: "tenants",
    },
    PLATFORM_ADOPTION: {
      TITLE: "Platform adoption",
      SUBTITLE: "Tenant overview",
      CARDS: [
        { key: "total_tenants", label: "Total tenants", helper: "registered on platform" },
        { key: "active_24h", label: "Active tenants", helper: "last 24 hours" },
        { key: "active_7d", label: "Active tenants", helper: "last 7 days" },
        { key: "active_30d", label: "Active tenants", helper: "last 30 days" },
        { key: "new_tenants_7d", label: "New — Last 7 days", helper: "onboarded in last 7 days" },
      ] as const,
    },
    TENANT_RANKING: {
      TITLE: "Tenant ranking",
      SUBTITLE_PREFIX: "By request volume ·",
    },
    REQUEST_VOLUME: {
      TITLE: "Request volume",
      SUBTITLE: "Successful and failed requests per interval over the selected period",
      FAILURE_RATE_SUFFIX: "failure rate",
      Y_AXIS_REQUESTS: "REQUESTS",
      SERIES_SUCCESSFUL: "Successful",
      SERIES_FAILED: "Failed",
    },
    SERVICE: {
      BREAKDOWN_TITLE: "Service breakdown",
      BREAKDOWN_SUBTITLE_PREFIX: "Consumption across all services ·",
      MOST_USED: "Most used service",
      HIGHEST_FAILURE: "Highest failure rate",
      REQUESTS_SUFFIX: "requests",
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
