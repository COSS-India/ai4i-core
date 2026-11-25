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
      FALLBACK_REQUESTS: "fallback_requests",
      FALLBACK_SUCCESSFUL: "fallback_successful",
      FALLBACK_FAILED: "fallback_failed",
      AVG_RPS: "avg_rps",
    },
    LABELS: {
      total_requests: "Total Requests",
      successful: "Successful Requests",
      failed: "Failed Requests",
      fallback_requests: "Fallback Requests",
      avg_rps: "Average Requests per Second",
    },
    HELPERS: {
      total_requests: `Across all ${INSTITUTIONS}`,
      successful: "Of all requests",
      failed: "Of all requests",
    },
    TOOLTIPS: {
      total_requests:
        `Total AI Model requests across all models and ${INSTITUTIONS.toLowerCase()} in the selected window.`,
      successful:
        "Total AI Model requests that completed without error in the selected window.",
      failed: "Total AI Model requests that returned an error in the selected window.",
      fallback_requests:
        "Count of requests served by a fallback Service instead of the primary Service during the selected period. This is also included in Total Requests.",
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
    { key: "last_7_days", label: "Last 7 Days" },
  ] as const satisfies ReadonlyArray<{ key: MeteringPresetPeriodKey; label: string }>,
  /** Quick button that applies a 30-day custom range. */
  LAST_30_DAYS_LABEL: "Last 30 Days",
  /** Preset period in running text, e.g. "Consumption across all Models – today". */
  PERIOD_LABELS: {
    today: "today",
    yesterday: "yesterday",
    last_7_days: "last 7 days",
  } as const satisfies Record<MeteringPresetPeriodKey, string>,
  /** Custom date ranges are calendar days in IST, whatever the browser zone. */
  IST_TIME_ZONE: "Asia/Kolkata",
  CUSTOM_RANGE: {
    TITLE: "Custom Date Range",
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
    CUSTOM_RANGE: "Custom Range",
    LAST_REFRESHED_PREFIX: "Last refreshed:",
    REFRESH: "Refresh",
  },
  TENANT_VIEW: {
    TITLE: "My Usage",
  },
  USAGE_SPEND: {
    BUDGET_SUMMARY: "Budget Summary",
    BUDGET: "Budget",
    QUOTA_SUMMARY: "Quota Summary",
    USAGE_BY_TASK_TYPE: "Usage by Task Type",
    /** Followed by the billing month, e.g. "Usage vs. Quota (Oct 2026)". */
    USAGE_VS_QUOTA: "Usage vs. Quota",
    THIS_MONTH: "This Month",
    NO_QUOTA_THIS_MONTH: "No quota this month",
    USAGE_IN_PERIOD: "Usage in Period",
    PERIOD_SPEND: "Spend in Period",
    TABLE_PERIOD_SPEND: "Spend in Period",
    TIER_FILTER_ALL: "Filter by Tier · All Tiers",
    TABLE_TIER: "Tier",
    TABLE_ALLOCATED_BUDGET: "Allocated Budget (INR)",
    TABLE_BUDGET: "Budget",
    /** Expandable LLM rows: input / cached input / output tokens and their cost. */
    TOGGLE_COST_BREAKDOWN: "Toggle cost breakdown for",
    COST_SHARE_SUFFIX: "% of cost",
    BREAKDOWN_TOTAL: "Total",
    TABLE_NOTE:
      "Spend and usage are for the selected period. Budget is all-time and quota is for the current month — open an institution for the full breakdown.",
    MULTI_TIER_NOTE: `Grouped by tier since this ${INSTITUTION.toLowerCase()} changed tier during the period.`,
    /** @deprecated Use USAGE_BY_TASK_TYPE */
    SPEND_BY_TASK_TYPE: "Usage by Task Type",
    TENANT_DETAIL_TITLE: `${INSTITUTION} Usage Details`,
    BUDGET_TOTALS_NOTE:
      "Allocated and Remaining Budget reflect overall totals and are not affected by the selected date range.",
    TIER_BREAKDOWN_NOTE:
      "Usage in the selected period; quota is for the current billing month.",
    TOTAL_ALLOCATED: "Total Allocated",
    TOTAL_USED: "Total Used",
    TOTAL_REMAINING: "Total Remaining",
    TOOLTIPS: {
      TOTAL_ALLOCATED: "Total budget allocated to institutions.",
      TOTAL_USED: "Total budget used by institutions.",
      TOTAL_REMAINING: "Total budget remaining across institutions.",
      ALLOCATED_BUDGET: "Monetary budget assigned to this institution.",
      BUDGET: "All-time: how much of the allocated budget has been spent versus what remains. Not affected by the selected period.",
      ALLOCATED_TOKENS: "Token allowance assigned to this institution.",
      USAGE: "This month's quota used versus remaining for this task type.",
      PERIOD_USAGE: "Units used and their cost in the selected period.",
      PERIOD_SPEND: `Spend by this ${INSTITUTION.toLowerCase()} in the selected period.`,
      TASK_TYPES: `Number of task types this ${INSTITUTION.toLowerCase()} has consumed.`,
    },
    TABLE_TASK_TYPES: "Task Types",
  },
  APPLICATION_USAGE: {
    TENANT_SUBTITLE: "Application usage and spend",
    LIFETIME_NOTE:
      "Spend in period follows the selected period. Allocated, spend and remaining budget are lifetime totals.",
    SUMMARY: {
      TOTAL_APPLICATIONS: "Total Applications",
      ALLOCATED: "Allocated Budget",
      SPENT: "Spend Budget",
      REMAINING: "Remaining Budget",
      SCOPE_ONBOARDED: "Onboarded under this Institution",
      SCOPE_ACROSS_APPS: "Across all Applications",
      PCT_OF_INSTITUTION: "of Institution Budget",
      PERIOD_SPEND: "Spend in Period",
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
      APPLICATION: "Application",
      DOMAIN: "Domain",
      ALLOCATED: "Allocated Budget",
      SPEND: "Spend Budget",
      REMAINING: "Remaining Budget",
      API_KEY: "API Key",
      ALLOCATED_SHORT: "Allocated",
      SPEND_SHORT: "Spend",
      REMAINING_SHORT: "Remaining",
      NO_BUDGET: "No Budget allocated",
      REMAINING_OF_ALLOCATION: "of App allocation",
      REMAINING_OF_KEY_ALLOCATION: "remaining",
      PERIOD_SPEND: "Spend in Period",
      PERIOD_SPEND_SHORT: "In Period",
      PERIOD_OF_ALLOCATION: "of allocation",
    },
    DRAWER_TITLE: "Application Spend Details",
    DRAWER_SPEND_BY_API_KEY: "Spend by API Key",
    DRAWER_PERIOD_SPEND: "Spend in Period",
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
      TITLE: "Usage Concentration",
      SUBTITLE: `${INSTITUTIONS} by request volume – reflects the selected time window`,
      DONUT_SECONDARY: INSTITUTIONS,
    },
    /** Adopter Admin: Institution and Model summary cards under one heading. */
    PLATFORM_OVERVIEW: {
      TITLE: "Platform Overview",
      SUBTITLE: "Platform-wide institution and model indicators",
      INSTITUTION_CARDS: [
        {
          key: "total_tenants",
          label: `Total ${INSTITUTIONS}`,
          tooltip: `Count of ${INSTITUTIONS.toLowerCase()} registered on the platform.`,
        },
        {
          key: "active_30d",
          label: `Active ${INSTITUTIONS}`,
          helper: "In the last 30 days",
          tooltip: `${INSTITUTIONS} with at least one AI Model request in the last 30 days.`,
        },
        {
          key: "new_tenants_15d",
          label: `New ${INSTITUTIONS}`,
          helper: "In the last 15 days",
          tooltip: `Count of ${INSTITUTIONS.toLowerCase()} onboarded in the last 15 days.`,
        },
        {
          key: "tenants_budget_exhausted",
          label: `Budget-Exhausted ${INSTITUTIONS}`,
          helper: INSTITUTIONS,
          tooltip: `Count of ${INSTITUTIONS.toLowerCase()} whose all-time spend has reached their allocated budget.`,
        },
      ] as const,
      MODEL_CARDS: [
        {
          key: "total_models",
          label: "Total Models",
          tooltip: "Total number of models registered on the platform.",
        },
        {
          key: "active_models_30d",
          label: "Active Models",
          helper: "In the last 30 days",
          tooltip:
            "Total number of models that have received at least one request in the last 30 days.",
        },
        {
          key: "model_usage_growth_pct",
          label: "Model Usage Growth",
          helper: "Last 30 days vs Previous 30",
          tooltip:
            "Percentage change in overall model usage over the last 30 days compared to the 30 days before that.",
        },
      ] as const,
    },
    TENANT_RANKING: {
      TITLE: `${INSTITUTION} Ranking`,
      SUBTITLE_PREFIX: "By request volume ·",
      TABLE_RANK: "Rank",
      TABLE_INSTITUTION: INSTITUTION,
      TABLE_REQUESTS: "Requests",
      TABLE_SHARE: "Share",
      AVG_REQUESTS_LABEL: `Average Requests per Active ${INSTITUTION}`,
      TOOLTIPS: {
        AVG_REQUESTS:
          `Total requests divided by the number of active ${INSTITUTIONS.toLowerCase()} in the selected window.`,
        REQUESTS: "AI Model request count for this institution in the selected time window.",
        SHARE:
          `Each ${INSTITUTION.toLowerCase()}'s share of total requests among the ${INSTITUTIONS.toLowerCase()} shown (Top 10 or Top 25, per the toggle).`,
      },
    },
    REQUEST_VOLUME: {
      TITLE: "Request Volume & Health",
      SUBTITLE: "Request volume over the selected time window",
      TOTAL: "Total Requests",
      SUCCESSFUL: "Successful",
      FAILED: "Failed",
      Y_AXIS_REQUESTS: "Requests",
    },
    // Model Consumption tab — model-level KPIs + per-service drill-down
    MODEL: {
      TITLE: "Model Consumption",
      SUBTITLE:
        "Model request distribution – reflects the selected time window",
      BREAKDOWN_TITLE: "Model Consumption Drill Down",
      BREAKDOWN_SUBTITLE_PREFIX: "Consumption across all Models –",
      DONUT_PRIMARY: "All",
      DONUT_SECONDARY: "Models",
      TOTAL_MODELS: "Total Models",
      ACTIVE_MODELS: "Active Models",
      MOST_USED: "Most Used Model",
      // Values carry their own "%" sign, so the label does not repeat it.
      OVERALL_SUCCESS: "Overall Success Rate",
      SUCCESS_RATE_SUFFIX: "Across all models",
      REQUESTS_SUFFIX: "requests",
      REQUESTS_ACROSS_INSTITUTIONS: `requests across all ${INSTITUTIONS}`,
      REQUESTS_ACROSS_INSTITUTION: `requests across this ${INSTITUTION}`,
      TABLE_TASK_TYPE: "Task Type",
      TABLE_MODEL: "Model Name",
      TABLE_SERVICE: "Service Name",
      TABLE_TOTAL_REQUESTS: "Total Requests",
      TABLE_NATIVE: "Total Native Units",
      TABLE_SUCCESS: "Successful",
      TABLE_FAILURE: "Failed",
      FILTER_TASK_TYPES: "Task Type",
      FILTER_SELECT_ALL: "Select all",
      FILTER_CLEAR_ALL: "Clear all",
      /** Expandable LLM rows: input / cached input / output tokens. */
      TOGGLE_TOKEN_BREAKDOWN: "Toggle token breakdown for",
      TOKEN_SHARE_SUFFIX: "% of tokens",
      TOOLTIPS: {
        TASK_TYPE:
          "The kind of work this model does, such as translation or speech to text, as recorded in the Model Registry.",
        MODEL_NAME: "The name of the model that handled the requests.",
        SERVICE_NAME:
          "The service through which requests reach this model.",
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
      HEADER_TOTAL_REQUESTS: "Total Requests",
      HEADER_RIGHT: "% of Total",
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
