import type { MeteringPeriod, MeteringPeriodKey, MeteringTopN } from "../types/metering";
import { INSTITUTION, INSTITUTIONS } from "./constants";

type MeteringPresetPeriodKey = Exclude<MeteringPeriodKey, "custom">;

/** Earliest year the custom range picker offers. */
const CUSTOM_RANGE_MIN_YEAR = 2000;

/** Metering & usage dashboard — copy, defaults, and configuration. */
export const METERING = {
  ERRORS: {
    LOAD_FAILED: "Failed to load metering data.",
    UNAVAILABLE_503:
      "Metering data is temporarily unavailable. Prometheus may not be configured.",
    FORBIDDEN_403: "You do not have permission to view this metering data.",
    /** `detail.code` of a 422 for a period the API rejects. */
    INVALID_PERIOD_CODE: "INVALID_PERIOD",
    INVALID_PERIOD_RESET: "That date range can't be shown, so the dashboard is back on Today.",
    BAD_REQUEST_400: "Invalid metering request parameters.",
  },
  BANNERS: {
    DEGRADED:
      "Some metrics could not be loaded completely. Showing partial data from the metering API.",
    DATA_STATE: {
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
      MODEL: "model",
    },
    SCROLL_ROOT_MARGIN: "100px",
  },
  DEFAULTS: {
    PERIOD: { key: "today" } satisfies MeteringPeriod,
    TOP_N: 10 satisfies MeteringTopN,
    SUB_TAB: "overview" as const,
    ASYNC_STATE_HEIGHT: "300px",
    LOADING_MIN_HEIGHT: "400px",
  },
  SUB_TAB: {
    OVERVIEW: "overview",
    MODEL: "model",
    USAGE_SPEND: "usage-spend",
    APPLICATIONS: "applications",
  } as const,
  KPI: {
    KEYS: {
      TOTAL_REQUESTS: "total_requests",
      SUCCESSFUL: "successful",
      FAILED: "failed",
      AVG_RPS: "avg_rps",
    },
    LABELS: {
      total_requests: "Total Requests",
      avg_rps: "Average RPS",
    },
    HELPERS: {
      total_requests: `Across all ${INSTITUTIONS}`,
      successful: "Of all requests",
      failed: "Of all requests",
      avg_rps: "Requests per second",
    },
    TOOLTIPS: {
      total_requests:
        `Total AI Model requests across all models and ${INSTITUTIONS.toLowerCase()} in the selected window.`,
      successful:
        "Total AI Model requests that completed without error in the selected window.",
      failed: "Total AI Model requests that returned an error in the selected window.",
      avg_rps: "Average AI Model requests per second over the selected window.",
    },
  },
  GRAPH: {
    SERIES_KEYS: {
      SUCCESSFUL: "successful",
      FAILED: "failed",
    },
    EMPTY_VALUE: "—",
  },
  /** Preset period buttons; a custom range comes from the date picker. */
  PERIODS: [
    { key: "today", label: "Today" },
    { key: "yesterday", label: "Yesterday" },
    { key: "last_7_days", label: "Last 7 days" },
  ] as const satisfies ReadonlyArray<{ key: MeteringPresetPeriodKey; label: string }>,
  /** Preset period in running text, e.g. "Consumption across all Models – today". */
  PERIOD_LABELS: {
    today: "today",
    yesterday: "yesterday",
    last_7_days: "last 7 days",
  } as const satisfies Record<MeteringPresetPeriodKey, string>,
  /** Custom date ranges are calendar days in IST, whatever the browser zone. */
  IST_TIME_ZONE: "Asia/Kolkata",
  CUSTOM_RANGE: {
    TITLE: "Custom date range",
    SUBTITLE: "Select a start date and an end date (any day up to today)",
    APPLY: "Apply",
    CANCEL: "Cancel",
    CLEAR: "Clear custom range",
    PREVIOUS_MONTH: "Previous month",
    NEXT_MONTH: "Next month",
    /** Title hint: clicking the month title opens the year / month picker. */
    CHOOSE_MONTH_YEAR: "Choose month and year",
    MIN_YEAR: CUSTOM_RANGE_MIN_YEAR,
    /** Earliest pickable day: 1 Jan of MIN_YEAR. */
    EARLIEST_DAY: `${CUSTOM_RANGE_MIN_YEAR}-01-01`,
    WEEKDAYS: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
  },
  TOP_N_OPTIONS: [10, 25] as const satisfies readonly MeteringTopN[],
  TOP_N_SEGMENT_OPTIONS: [
    { id: "10", label: "Top 10" },
    { id: "25", label: "Top 25" },
  ] as const,
  /** Max institutions fetched for usage concentration; UI slices to the selected Top N. */
  USAGE_CONCENTRATION_FETCH_LIMIT: 25 as const,
  /** Model Usage tab — Top 5 / Top 10 ranking toggle (API `limit`). */
  MODEL_TOP_N_SEGMENT_OPTIONS: [
    { id: "5", label: "Top 5" },
    { id: "10", label: "Top 10" },
  ] as const,
  MODEL_TOP_N_DEFAULT: 10 as const,
  SUB_TABS: [
    { id: "overview", label: INSTITUTION },
    { id: "model", label: "Model" },
    { id: "usage-spend", label: "Budget" },
    { id: "applications", label: "Applications" },
  ] as const,
  ROLE_VIEWS: {
    adopter: "Adopter Admin",
    tenant: `${INSTITUTION} Admin`,
  } as const,
  CONTROLS: {
    ALL_TENANTS: `All ${INSTITUTIONS}`,
    TOP_N_PREFIX: "Top",
    CUSTOM_RANGE: "Custom range",
    LAST_REFRESHED_PREFIX: "Last refreshed:",
    REFRESH: "Refresh",
  },
  TENANT_VIEW: {
    TITLE: "My Usage",
  },
  USAGE_SPEND: {
    BUDGET_SUMMARY: "BUDGET SUMMARY",
    BUDGET: "BUDGET",
    QUOTA_SUMMARY: "QUOTA SUMMARY",
    USAGE_BY_TASK_TYPE: "USAGE BY MODEL TASK TYPE",
    /** Followed by the billing month, e.g. "USAGE VS. QUOTA (OCT 2026)". */
    USAGE_VS_QUOTA: "USAGE VS. QUOTA",
    THIS_MONTH: "THIS MONTH",
    NO_QUOTA_THIS_MONTH: "No quota this month",
    USAGE_IN_PERIOD: "USAGE IN PERIOD",
    PERIOD_SPEND: "SPEND IN PERIOD",
    TABLE_PERIOD_SPEND: "Spend in period",
    /** Expandable LLM rows: input / cached input / output tokens and their cost. */
    TOGGLE_COST_BREAKDOWN: "Toggle cost breakdown for",
    COST_SHARE_SUFFIX: "% of cost",
    BREAKDOWN_TOTAL: "Total",
    TABLE_NOTE:
      "Spend and usage are for the selected period. Budget is all-time and quota is for the current month — open an institution for the full breakdown.",
    MULTI_TIER_NOTE: `Grouped by tier since this ${INSTITUTION.toLowerCase()} changed tier during the period.`,
    /** @deprecated Use USAGE_BY_TASK_TYPE */
    SPEND_BY_TASK_TYPE: "USAGE BY MODEL TASK TYPE",
    TENANT_DETAIL_TITLE: "Institution Usage Details",
    BUDGET_TOTALS_NOTE:
      "Allocated and Remaining Budget reflect overall totals and are not affected by the selected date range.",
    TIER_BREAKDOWN_NOTE:
      "Usage in the selected period; quota is for the current billing month.",
    TOTAL_ALLOCATED: "TOTAL ALLOCATED",
    TOTAL_USED: "TOTAL USED",
    TOTAL_REMAINING: "TOTAL REMAINING",
    TOOLTIPS: {
      TOTAL_ALLOCATED: "Total budget allocated to institutions.",
      TOTAL_USED: "Total budget used by institutions.",
      TOTAL_REMAINING: "Total budget remaining across institutions.",
      ALLOCATED_BUDGET: "Monetary budget assigned to this institution.",
      BUDGET: "All-time: how much of the allocated budget has been spent versus what remains. Not affected by the selected period.",
      ALLOCATED_TOKENS: "Token allowance assigned to this institution.",
      USAGE: "This month's quota used versus remaining for this model task type.",
      PERIOD_USAGE: "Units used and their cost in the selected period.",
      PERIOD_SPEND: `Spend by this ${INSTITUTION.toLowerCase()} in the selected period.`,
      TASK_TYPES: `Number of model task types this ${INSTITUTION.toLowerCase()} has consumed.`,
    },
    TABLE_TASK_TYPES: "Task Types",
  },
  APPLICATION_USAGE: {
    TENANT_SUBTITLE: "Application usage and spend",
    LIFETIME_NOTE:
      "Spend in period follows the selected period. Allocated, spend and remaining budget are lifetime totals.",
    SUMMARY: {
      TOTAL_APPLICATIONS: "TOTAL APPLICATIONS",
      ALLOCATED: "ALLOCATED BUDGET",
      SPENT: "SPEND BUDGET",
      REMAINING: "REMAINING BUDGET",
      SCOPE_ONBOARDED: "Onboarded under this Institution",
      SCOPE_ACROSS_APPS: "Across all Applications",
      PCT_OF_INSTITUTION: "of Institution Budget",
      PERIOD_SPEND: "SPEND IN PERIOD",
    },
    TOOLTIPS: {
      TOTAL_APPLICATIONS: "Count of all Applications onboarded under the Institution.",
      ALLOCATED:
        "Sum of Budget allocated across all Applications. Equals 100% of the Institution's Budget when fully allocated.",
      SPENT: "Lifetime sum of Budget consumed across all Applications.",
      PERIOD_SPEND:
        "Spend across all Applications in the selected period, as % of the Institution's Budget.",
      PERIOD_SPEND_COL:
        "This Application's spend in the selected period, as % of its own allocation.",
      API_KEY_PERIOD_SPEND: "This Key's spend in the selected period, as % of its own allocation.",
      REMAINING:
        "Allocated Budget minus Spend Budget, summed across all Applications.",
      ALLOCATED_COL:
        "% of the Institution's total Budget assigned to this Application, and its ₹ equivalent.",
      SPEND_COL:
        "% of this Application's own Allocated Budget consumed, and its ₹ equivalent.",
      REMAINING_COL:
        "This Application's Allocated Budget minus its Spend, as % of its own allocation and ₹.",
      API_KEY_ALLOCATED:
        "% of the Application's total Budget assigned to this Key.",
      API_KEY_SPEND: "% of this Key's own Allocated amount consumed.",
      API_KEY_REMAINING:
        "This Key's Allocated amount minus its Spend, as % of its own allocation.",
    },
    TABLE: {
      APPLICATION: "APPLICATION",
      DOMAIN: "DOMAIN",
      ALLOCATED: "ALLOCATED BUDGET",
      SPEND: "SPEND BUDGET",
      REMAINING: "REMAINING BUDGET",
      API_KEY: "API KEY",
      ALLOCATED_SHORT: "ALLOCATED",
      SPEND_SHORT: "SPEND",
      REMAINING_SHORT: "REMAINING",
      NO_BUDGET: "No Budget allocated",
      REMAINING_OF_ALLOCATION: "of App allocation",
      REMAINING_OF_KEY_ALLOCATION: "remaining",
      PERIOD_SPEND: "SPEND IN PERIOD",
      PERIOD_SPEND_SHORT: "IN PERIOD",
      PERIOD_OF_ALLOCATION: "of allocation",
    },
    DRAWER_TITLE: "Application Spend Details",
    DRAWER_SPEND_BY_API_KEY: "Spend by API Key",
    DRAWER_PERIOD_SPEND: "SPEND IN PERIOD",
    DRAWER_NO_BUDGET: "No Budget has been allocated to this Application yet.",
    DRAWER_NO_KEYS: "No API keys have been issued against this Application yet.",
    SELECT_INSTITUTION: "Select an institution from the filter above to view application usage.",
    EMPTY: "No application usage data available for this institution.",
    FOOTER:
      "Table columns are sortable. Spend and remaining percentages are relative to each application's own allocation unless noted otherwise.",
  },
  COLORS: {
    RANK: ["#DD6B20", "#3182CE", "#38A169", "#805AD5", "#00B5D8"] as const,
    /** Ranked-list / donut colours — one per Top-N row (up to USAGE_CONCENTRATION_FETCH_LIMIT). */
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
      "#9F7AEA",
      "#ED64A6",
      "#48BB78",
      "#4299E1",
      "#ECC94B",
      "#F56565",
      "#667EEA",
      "#38B2AC",
      "#ED8936",
      "#A0AEC0",
      "#FC8181",
      "#68D391",
      "#63B3ED",
      "#B794F4",
      "#F6AD55",
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
    /** Every tab's empty state when the selected period has no usage (AI4IDS-3341/3342). */
    PERIOD: "No usage for the selected date range.",
    /** The period has usage, but the task-type filter hides every row. */
    FILTERED: "No usage matches the selected task types.",
  },
  REFRESH: {
    JUST_NOW: "just now",
    SECONDS_AGO_SUFFIX: " sec ago",
    MINUTES_AGO_SUFFIX: "m ago",
  },
  SECTIONS: {
    CONSUMPTION_OVERVIEW: {
      TITLE: "Usage concentration",
      SUBTITLE: `${INSTITUTIONS} by request volume – reflects the selected time window`,
      DONUT_SECONDARY: INSTITUTIONS.toLowerCase(),
    },
    KEY_METRICS: {
      TITLE: "Key metrics",
      SUBTITLE: "Platform-wide institution and model indicators",
      INSTITUTION_ROW_TITLE: `${INSTITUTIONS} metrics`,
      MODEL_ROW_TITLE: "Model metrics",
      INSTITUTION_CARDS: [
        {
          key: "total_tenants",
          label: `Total ${INSTITUTIONS.toLowerCase()}`,
          helper: "Registered on platform",
          tooltip: `Count of ${INSTITUTIONS.toLowerCase()} registered on the platform.`,
        },
        {
          key: "active_30d",
          label: `Active ${INSTITUTIONS.toLowerCase()}`,
          helper: "In the last 30 days",
          tooltip: `${INSTITUTIONS} with at least one AI Model request in the last 30 days.`,
        },
        {
          key: "new_tenants_15d",
          label: `New ${INSTITUTIONS.toLowerCase()}`,
          helper: "In the last 15 days",
          tooltip: `Count of ${INSTITUTIONS.toLowerCase()} onboarded in the last 15 days.`,
        },
        {
          key: "tenants_budget_exhausted",
          label: "Budget exhausted",
          helper: INSTITUTIONS,
          tooltip: `Count of ${INSTITUTIONS.toLowerCase()} whose all-time spend has reached their allocated budget.`,
        },
      ] as const,
      MODEL_CARDS: [
        {
          key: "total_models",
          label: "Total models",
          helper: "On platform",
          tooltip: "Total number of models registered on the platform.",
        },
        {
          key: "active_models_30d",
          label: "Active models",
          helper: "In the last 30 days",
          tooltip:
            "Total number of models that have received at least one request in the last 30 days.",
        },
        {
          key: "model_usage_growth_pct",
          label: "Model usage growth",
          helper: "Last 30 days vs Previous 30",
          tooltip:
            "Percentage change in overall model usage over the last 30 days compared to the 30 days before that.",
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
        REQUESTS: "AI Model request count for this institution in the selected time window.",
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
        "Model request distribution – reflects the selected time window",
      BREAKDOWN_TITLE: "Model consumption Drill down",
      BREAKDOWN_SUBTITLE_PREFIX: "Consumption across all Models –",
      DONUT_PRIMARY: "All",
      DONUT_SECONDARY: "Models",
      TOTAL_MODELS: "Total models",
      ACTIVE_MODELS: "Active models",
      MOST_USED: "Most used model",
      OVERALL_SUCCESS: "Overall success rate %",
      SUCCESS_RATE_SUFFIX: "Across all models",
      REQUESTS_SUFFIX: "requests",
      REQUESTS_ACROSS_INSTITUTIONS: `requests across all ${INSTITUTIONS}`,
      REQUESTS_ACROSS_INSTITUTION: `requests across this ${INSTITUTION}`,
      TABLE_TASK_TYPE: "Model Task Type",
      TABLE_MODEL: "Model Name",
      TABLE_SERVICE: "Service Name",
      TABLE_TOTAL_REQUESTS: "Total requests",
      TABLE_NATIVE: "Native Consumption",
      TABLE_SUCCESS: "Success rate %",
      TABLE_FAILURE: "Failure rate %",
      FILTER_TASK_TYPES: "Model Task Type",
      /** Expandable LLM rows: input / cached input / output tokens. */
      TOGGLE_TOKEN_BREAKDOWN: "Toggle token breakdown for",
      TOKEN_SHARE_SUFFIX: "% of tokens",
      BREAKDOWN_TOTAL: "Total",
      TOOLTIPS: {
        TASK_TYPE:
          "The task type this model performs, as registered in the Model Registry.",
        TOTAL_MODELS:
          "Registered model versions for enabled task types in the Registry (active and deprecated).",
        ACTIVE_MODELS:
          "Model versions with traffic in the selected time window (enabled task types only).",
        OVERALL_SUCCESS:
          "Success rate across all models combined in the selected window — the request count here covers every model, not just the one shown as Most Used.",
        MOST_USED: "Model with the highest number of requests in the selected window.",
        TOTAL_REQUESTS: "Request count for this service in the selected time window.",
        CONSUMPTION_PCT:
          "This model's share of requests among services with a resolved Registry model name.",
        TOKEN_CONSUMPTION:
          "Consumption measured in the model's own billing unit (Native units).",
        SUCCESS_RATE: "Share of successful requests for this service.",
        FAILURE_RATE: "Share of failed requests for this service (100 − success rate).",
      },
    },
    RANKED_SHARE: {
      HEADER_LEFT: INSTITUTION,
      HEADER_TOTAL_REQUESTS: "Total requests",
      HEADER_RIGHT: "% of total",
      TOOLTIPS: {
        TOTAL_REQUESTS: "Request count for this institution in the selected time window.",
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
