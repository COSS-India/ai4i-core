import type { MeteringTopN, MeteringWindow } from "../types/metering";
import { INSTITUTION, INSTITUTIONS } from "./constants";

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
      MODEL: "model",
    },
    SCROLL_ROOT_MARGIN: "100px",
  },
  DEFAULTS: {
    TIME_WINDOW: "24h" satisfies MeteringWindow,
    TOP_N: 10 satisfies MeteringTopN,
    SUB_TAB: "overview" as const,
    /** Tenant Admin lands on Overview (same as Adopter Admin). */
    TENANT_SUB_TAB: "overview" as const,
    ASYNC_STATE_HEIGHT: "300px",
    LOADING_MIN_HEIGHT: "400px",
  },
  SUB_TAB: {
    OVERVIEW: "overview",
    TENANT: "tenant",
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
    LABELS: {
      total_requests: "Total LLM Requests",
      avg_rps: "Average RPS",
    },
    HELPERS: {
      total_requests: `Across all ${INSTITUTIONS}`,
      successful: "of all requests",
      failed: "of all requests",
      avg_rps: "requests per second",
    },
    TOOLTIPS: {
      total_requests:
        `Total requests across all models and ${INSTITUTIONS.toLowerCase()} in the selected window.`,
      successful: "Total requests that completed without error in the selected window.",
      failed: "Total requests that returned an error in the selected window.",
      avg_rps: "Average requests per second over the selected window.",
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
  /** Model Usage tab — Top 5 / Top 10 ranking toggle (API `limit`). */
  MODEL_TOP_N_SEGMENT_OPTIONS: [
    { id: "5", label: "Top 5" },
    { id: "10", label: "Top 10" },
  ] as const,
  MODEL_TOP_N_DEFAULT: 10 as const,
  SUB_TABS: [
    { id: "overview", label: "Overview" },
    { id: "tenant", label: `${INSTITUTION} Consumption` },
    // Extra tab — per-service LLM via /model-consumption
    { id: "model", label: "Model Usage" },
    { id: "usage-spend", label: "Budget and usage" },
  ] as const,
  TENANT_SUB_TABS: [
    { id: "overview", label: "Overview" },
    { id: "model", label: "Model Usage" },
    { id: "usage-spend", label: "Budget and usage" },
  ] as const,
  ROLE_VIEWS: {
    adopter: "Adopter Admin",
    tenant: `${INSTITUTION} Admin`,
  } as const,
  CONTROLS: {
    ALL_TENANTS: `All ${INSTITUTIONS}`,
    TOP_N_PREFIX: "Top",
    LAST_REFRESHED_PREFIX: "Last refreshed:",
    REFRESH: "Refresh",
  },
  TENANT_VIEW: {
    TITLE: "My Usage",
  },
  USAGE_SPEND: {
    BILLING_PERIOD: "BILLING PERIOD",
    CURRENT_MONTH: "Current month",
    LAST_MONTH: "Last month",
    BUDGET_SUMMARY: "BUDGET SUMMARY",
    QUOTA_SUMMARY: "QUOTA SUMMARY",
    SPEND_BY_TASK_TYPE: "SPEND BY MODEL TASK TYPE",
    TOTAL_ALLOCATED: "TOTAL ALLOCATED",
    TOTAL_USED: "TOTAL USED",
    TOTAL_REMAINING: "TOTAL REMAINING",
    TOOLTIPS: {
      TOTAL_ALLOCATED:
        "Sum of budget and token allowances assigned to institutions for this billing period.",
      TOTAL_USED: "Sum of budget spent and tokens consumed in this billing period.",
      TOTAL_REMAINING:
        "Budget and tokens still available (allocated minus used) for this billing period.",
      ALLOCATED_BUDGET: "Monetary budget assigned to this institution for the billing period.",
      BUDGET:
        "How much of the allocated budget has been spent versus what remains in this period.",
      ALLOCATED_TOKENS: "Token allowance assigned to this institution for the billing period.",
      TOKEN_USAGE:
        "Tokens consumed versus remaining allowance in this billing period. Multi-task institutions expand for a per-type breakdown.",
      USAGE: "Quota consumed versus remaining for this model task type.",
      SPEND: "Monetary spend for this model task type in the selected billing period.",
      SHARE: "This row's spend as a percentage of the institution's total spend in the period.",
      ACTIVE_TENANTS: `${INSTITUTIONS} with spend recorded in the selected billing period.`,
      BUDGET_EXCEEDED: `Number of ${INSTITUTIONS.toLowerCase()} whose spend has exceeded their allocated budget for this period.`,
      VS_LAST_MONTH:
        "Percentage change in total spend compared with the previous billing period.",
      USAGE_BREAKDOWN: `Number of tiers or task types this ${INSTITUTION.toLowerCase()} consumed under in the selected period — expand to see the breakdown.`,
    },
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
  },
  EMPTY: {
    DEFAULT: "No data available.",
    TENANT_CONSUMPTION: `No ${INSTITUTION.toLowerCase()} consumption data available.`,
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
      TITLE: "Usage concentration",
      SUBTITLE:
        "Top 5 Institutions by request volume · reflects selected time window",
      DONUT_PRIMARY: "Top 5",
      DONUT_SECONDARY: INSTITUTIONS.toLowerCase(),
    },
    PLATFORM_ADOPTION: {
      TITLE: "Platform adoption",
      SUBTITLE: `${INSTITUTION} overview`,
      CARDS: [
        {
          key: "total_tenants",
          label: `Total ${INSTITUTIONS.toLowerCase()}`,
          helper: "registered on platform",
          tooltip: `${INSTITUTIONS} registered on the platform, regardless of status.`,
        },
        {
          key: "active_24h",
          label: `Active ${INSTITUTIONS.toLowerCase()}`,
          helper: "last 24 hours",
          tooltip: `${INSTITUTIONS} with at least one request in the last 24 hours.`,
        },
        {
          key: "active_7d",
          label: `Active ${INSTITUTIONS.toLowerCase()}`,
          helper: "last 7 days",
          tooltip: `${INSTITUTIONS} with at least one request in the last 7 days.`,
        },
        {
          key: "active_30d",
          label: `Active ${INSTITUTIONS.toLowerCase()}`,
          helper: "last 30 days",
          tooltip: `${INSTITUTIONS} with at least one request in the last 30 days.`,
        },
        {
          key: "new_tenants_7d",
          label: `New ${INSTITUTIONS.toLowerCase()}`,
          helper: "onboarded in last 7 days",
          tooltip: `${INSTITUTIONS} onboarded to the platform in the last 7 days.`,
        },
      ] as const,
    },
    TENANT_RANKING: {
      TITLE: `${INSTITUTION} ranking`,
      SUBTITLE_PREFIX: "By request volume ·",
      TABLE_RANK: "Rank",
      TABLE_INSTITUTION: INSTITUTION,
      TABLE_REQUESTS: "Requests",
      TABLE_SHARE: "Share",
      AVG_REQUESTS_LABEL: `Average Requests Per Active ${INSTITUTION}`,
      TOOLTIPS: {
        AVG_REQUESTS:
          `Total requests divided by the number of active ${INSTITUTIONS.toLowerCase()} in the selected window.`,
        REQUESTS: "LLM request count for this institution in the selected time window.",
        SHARE:
          `Each ${INSTITUTION.toLowerCase()}'s share of total requests among the ${INSTITUTIONS.toLowerCase()} shown (Top 10 or Top 25, per the toggle).`,
      },
    },
    REQUEST_VOLUME: {
      TITLE: "Request volume & health",
      SUBTITLE: "Request volume over the selected time window",
      SUCCESSFUL: "Successful",
      FAILED: "Failed",
      FAILURE_RATE_SUFFIX: "failure rate",
      Y_AXIS_REQUESTS: "REQUESTS",
    },
    // Model Consumption tab — model-level KPIs + per-service drill-down
    MODEL: {
      TITLE: "Model consumption",
      SUBTITLE:
        "Model request distribution · reflects selected time window",
      BREAKDOWN_TITLE: "Model consumption Drill down",
      BREAKDOWN_SUBTITLE_PREFIX: "Consumption across LLM services ·",
      DONUT_PRIMARY: "All",
      DONUT_SECONDARY: "Models",
      TOTAL_MODELS: "Total models",
      ACTIVE_MODELS: "Active models",
      MOST_USED: "Most used model",
      OVERALL_SUCCESS: "Overall success rate %",
      SUCCESS_RATE_SUFFIX: "across all models",
      REQUESTS_SUFFIX: "requests",
      REQUESTS_ACROSS_INSTITUTIONS: `requests across all ${INSTITUTIONS}`,
      REQUESTS_ACROSS_INSTITUTION: `requests across this ${INSTITUTION}`,
      TABLE_MODEL: "Model Name",
      TABLE_SERVICE: "Service Name",
      TABLE_TOTAL_REQUESTS: "Total requests",
      TABLE_NATIVE: "Token consumption",
      TABLE_SUCCESS: "Success rate %",
      TABLE_FAILURE: "Failure rate %",
      TOOLTIPS: {
        TOTAL_MODELS:
          "Registered LLM model versions in the Registry (active and deprecated).",
        ACTIVE_MODELS:
          "LLM model versions with traffic in the selected time window.",
        OVERALL_SUCCESS:
          "Success rate across all models combined in the selected window — the request count here covers every model, not just the one shown as Most Used.",
        MOST_USED: "Model with the highest number of requests in the selected window.",
        TOTAL_REQUESTS: "LLM request count for this service in the selected time window.",
        CONSUMPTION_PCT:
          "This model's share of requests among services with a resolved Registry model name.",
        TOKEN_CONSUMPTION:
          "Consumption measured in the model's own billing unit — for example, tokens, characters, or seconds.",
        SUCCESS_RATE: "Share of successful requests for this service.",
        FAILURE_RATE: "Share of failed requests for this service (100 − success rate).",
      },
    },
    RANKED_SHARE: {
      HEADER_LEFT: INSTITUTION,
      HEADER_TOTAL_REQUESTS: "Total requests",
      HEADER_RIGHT: "% of total",
      TOOLTIPS: {
        TOTAL_REQUESTS: "Request count for this row in the selected time window.",
        PCT_OF_TOTAL: "This row's share of the total requests shown in the list.",
      },
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

export type MeteringSubTab = (typeof METERING.SUB_TABS)[number]["id"];
