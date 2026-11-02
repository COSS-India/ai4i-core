import { INSTITUTION, INSTITUTIONS } from "./constants";
import { EMAIL_AVAILABLE_MSG } from "../utils/tenantEmailValidation";
import { PRICE_PER_UNIT_MAX_LABEL } from "../components/services-management/serviceFormValidation";
import { QUOTA_LIMIT_MAX_LABEL } from "../components/tier-management/tierFormValidation";
import { SELF_REGISTERED_ROLE_LOCKED_MESSAGE } from "../utils/registrationMethod";

const org = INSTITUTION.toLowerCase();

/**
 * Form copy (PM):
 * - `placeholder` — example value only
 * - `tip` — info-icon: what this field is for (purpose). One short sentence.
 * - `helper` — under field: only hard constraints (length, uniqueness, counters)
 * - Never restates the label. Never “optional” as the only copy.
 * - Validation errors own invalid input; tips/helpers do not.
 */
const NAME_CHARS_HELPER =
  "2–80 characters · letters, spaces, hyphens, apostrophes";

/** Placeholder + tip / helper copy for field-level guidance. */
export const FIELD_HINTS = {
  tenant: {
    organisation: {
      placeholder: "e.g. Acme Public Sector",
      tip: `Official name of this ${org}.`,
      helper: "2–100 characters · unique",
    },
    contactName: {
      placeholder: "e.g. Priya Sharma",
      tip: "Person who receives notices and verification mail.",
      helper: NAME_CHARS_HELPER,
    },
    email: {
      placeholder: "name@domain.com",
      tip: "Address for login invites and institution notices.",
      helper: "Must be unique",
    },
    phone: {
      placeholder: "+91 98765 43210",
      tip: "Number for the primary contact.",
    },
    emailChecking: "Checking if email exists…",
    emailAvailable: EMAIL_AVAILABLE_MSG,
    emailPendingOnly: `Editable only while Pending — not for the Default Organisation.`,
    emailEdit: "Correct email",
    emailEditHint:
      "Opens a typed correction. A new activation link is sent to the new address.",
    emailVerifyOnChange:
      "A new activation link is sent to the corrected address.",
    emailVerificationPending: "Verification pending",
    contactChange: "Change contact",
    contactChangeLoading: "Loading Institution Admins…",
    contactChangeHint:
      "Only another active Institution Admin. The change applies immediately.",
    contactChangeNone: "Add an Institution Admin before changing the contact.",
    contactChangePending:
      "The contact can't be changed until the institution is active. Correct the contact email instead.",
    contactChangeSuspended:
      "The contact cannot be changed while the institution is suspended.",
    contactChangeDeactivated:
      "The contact cannot be changed while the institution is deactivated.",
    contactChangeUnavailable:
      "The contact cannot be changed for this institution.",
    contactChangeDefaultOrg:
      "The Default Organisation's contact cannot be changed.",
    contactChangeLoadFailed: "Institution Admins could not be loaded.",
    contactChangeSelect: "Select an Institution Admin",
    planAppliesImmediately: "Tier and budget apply immediately.",
  },
  tenantUser: {
    tenant: { tip: `${INSTITUTION} this user belongs to.` },
    fullName: {
      placeholder: "e.g. Priya Sharma",
      tip: "Name shown for this user in the portal.",
      helper: NAME_CHARS_HELPER,
    },
    email: {
      placeholder: "name@domain.com",
      tip: "Login and invite address for this user.",
      helper: "Must be unique",
    },
    phone: {
      placeholder: "+91 98765 43210",
      tip: "Contact number for this user.",
    },
    role: {
      tip: `Access level inside this ${org}.`,
    },
    username: {
      tip: "Login ID for this user.",
      helper: "3–100 characters",
    },
    emailLocked:
      "Email cannot be changed. Suspend or delete the account if the user has left.",
    rolesLoadFailed: "Roles could not be loaded; role changes are disabled.",
    onlyAdminLocked:
      "You are the only Admin in the default organisation and cannot change your role.",
    selfRegisteredRoleLocked: SELF_REGISTERED_ROLE_LOCKED_MESSAGE,
  },
  assignTier: {
    tier: {
      tip: "Usage plan for this institution’s services and quotas.",
    },
    budget: {
      placeholder: "e.g. 500000",
      tip: "Spend ceiling for this institution on the selected tier.",
      helper: "Greater than 0",
    },
    effectiveFrom: {
      tip: "First day this budget is active.",
    },
    effectiveTo: {
      tip: "Last day this budget is active.",
    },
    currentBudget: {
      tip: "Active spend ceiling for the current window.",
    },
  },
  model: {
    jsonUpload: {
      tip: "Model definition file used to register this model.",
      helper: "JSON only · validated on create",
      requirements: {
        required:
          "name (5–100 chars, no spaces), version, description (25–1000 chars), task.type, license, domain, trainingDataset.description, submitter.name",
        byKind: [
          {
            label: "NLP models",
            text: "classInstance must match task.type (e.g. NMTTaskService for nmt)",
          },
          {
            label: "LLM models",
            text: "adapterConfig.model_name must match your AI server’s model name",
          },
        ],
      },
      specReferences: [
        {
          id: "ulca",
          badge: "NLP",
          shortLabel: "ULCA spec",
          text: "NLP model details must follow the ULCA Model specification.",
          linkLabel: "View ULCA Model specification",
          sampleKind: "nlp",
          sampleLabel: "Download NLP sample JSON",
        },
        {
          id: "openai",
          badge: "LLM",
          shortLabel: "OpenAI spec",
          text: "LLM model details must follow the OpenAI specification.",
          linkLabel: "View OpenAI specification",
          sampleKind: "llm",
          sampleLabel: "Download LLM sample JSON",
        },
      ],
    },
    columns: { tip: "Columns shown in the model list." },
    col: {
      status: "Active models can back new services; deprecated cannot.",
      services: "Published services using this model.",
      task: "Capability family of this model.",
      provider: "Organisation or submitter that registered this model.",
    },
  },
  service: {
    taskType: {
      placeholder: "Select a task type",
      tip: "Capability this service exposes (ASR, NMT, LLM, …).",
    },
    modelName: {
      placeholder: "Select model",
      loading: "Loading models...",
      needTaskType: "Select a task type first",
      tip: "Registered model this service runs.",
    },
    modelId: { empty: "Select a model above" },
    name: {
      placeholder: "e.g. indic-nmt-v1/T4",
      tip: "Display name in the service registry.",
      helper: "5–100 characters · letters, numbers, - /",
    },
    serviceId: {
      placeholder: "model-name/service-01",
      tip: "Stable ID used in APIs and logs. 5–255 characters; prefilled from the model.",
      helper: "5–255 characters · prefilled from model",
      llmHelper: "5–255 characters · prefilled from model",
      llmTip:
        "Stable ID used in APIs and logs (no underscores). 5–255 characters; prefilled from the model.",
    },
    description: {
      placeholder: "What this service does for callers",
      tip: "Short summary shown on the service details view.",
      helper: (entered: number, min: number, max: number) =>
        `${min}–${max} characters · ${entered}/${max}`,
    },
    endpoint: {
      placeholder: "https://host.example/v1/completions",
      tip: "URL the platform calls for this service.",
      llmHelper: "Host:port only",
      llmTip: "Host where the model server listens.",
      llmPlaceholder: "host:port",
    },
    authToken: {
      placeholder: "Bearer token",
      tip: "Credential sent to the endpoint when it requires auth.",
      editHelper: "Leave blank to keep the saved token",
      editTip: "Replace the stored token, or leave blank to keep it.",
      editEmptyTip: "Leave blank if the endpoint needs no auth.",
    },
    hardware: {
      placeholder: "e.g. Auto-scalable T4 GPUs",
      tip: "Where this service runs (GPU, region, scale).",
      helper: (min: number, max: number) => `${min}–${max} characters`,
    },
    unitType: {
      tip: "Metering unit from the selected task type.",
      needTaskType: "Select a task type first",
    },
    unitSize: {
      placeholder: "Select unit size",
      tip: "How many units one price covers.",
      llmTip: "Token count each listed price applies to.",
    },
    price: {
      placeholder: "e.g. 600",
      tip: `Charge per unit size for this service (0–${PRICE_PER_UNIT_MAX_LABEL}).`,
      helper: `0–${PRICE_PER_UNIT_MAX_LABEL}`,
    },
    llmInputPrice: {
      placeholder: "e.g. 600",
      tip: `Price for uncached input tokens per unit size (0–${PRICE_PER_UNIT_MAX_LABEL}).`,
      helper: `0–${PRICE_PER_UNIT_MAX_LABEL}`,
    },
    llmCachedInputPrice: {
      placeholder: "e.g. 150",
      tip: `Price for prefix-cache input tokens per unit size (0–${PRICE_PER_UNIT_MAX_LABEL}).`,
      helper: `0–${PRICE_PER_UNIT_MAX_LABEL}`,
    },
    llmOutputPrice: {
      placeholder: "e.g. 900",
      tip: `Price for generated output tokens per unit size (0–${PRICE_PER_UNIT_MAX_LABEL}).`,
      helper: `0–${PRICE_PER_UNIT_MAX_LABEL}`,
    },
    tier: {
      placeholder: "Select applicable tier(s)",
      tip: "Usage plans that may call this service.",
    },
    tierSearch: { placeholder: "Search tiers..." },
    columns: { tip: "Columns shown in the service list." },
    col: {
      status: "Published if live for callers; otherwise draft.",
      tier: "Usage plans linked to this service.",
      inputPrice: "Charge per unit for input.",
      outputPrice: "Charge per unit for output.",
      cachedInputPrice: "Charge per unit for cached input (LLM).",
      publishedOn: "When this service was last published.",
    },
  },
  logs: {
    search: {
      placeholder: "Keyword search",
      tip: "Find traces by text in log fields.",
      tooLong: "Keyword must be at most 256 characters",
    },
    startTime: { tip: "Earliest time included in results." },
    endTime: { tip: "Latest time included in results." },
    tenant: { tip: `${INSTITUTION} whose requests to include.` },
    autoRefresh: {
      tip: "Keep loading new traces while End Time is now.",
    },
    narrowDateRange:
      "Too many results. Narrow the date range or refine your search.",
    columns: { tip: "Columns shown in the logs table." },
  },
  profile: {
    fullName: {
      placeholder: "e.g. Priya Sharma",
      tip: "Your display name in the portal.",
      helper: NAME_CHARS_HELPER,
    },
    timezone: {
      tip: "Time zone for dates and times in the portal.",
    },
    currentPassword: { placeholder: "Current password" },
    newPassword: { placeholder: "New password" },
    confirmPassword: {
      placeholder: "Re-enter new password",
      tip: "Repeat the new password to confirm.",
      helper: "Must match new password",
    },
    roleUser: {
      tip: "User whose role you will change.",
    },
    usernameLocked: "Username cannot be changed",
    emailLocked: "Email cannot be changed",
    phone: {
      placeholder: "+91XXXXXXXXXX or XXXXXXXXXX",
      tip: "Your contact mobile number.",
      helper: "10 digits starting 6–9 · +91 allowed",
    },
  },
  tier: {
    name: {
      placeholder: "e.g. Enterprise",
      tip: "Label for this usage plan.",
      helper: "2–100 characters",
    },
    description: {
      placeholder: "Who this tier is for",
      tip: "Short summary of this tier’s audience.",
    },
    quotaUnit: {
      tip: "Unit for quotas (from task type).",
    },
    rateLimit: {
      placeholder: "e.g. 60",
      tip: "Max inference requests per minute. Blank = platform default.",
    },
    quotaLimit: {
      placeholder: "e.g. 10000",
      tip: "Max usage for this task type in the quota unit.",
      helper: `Whole number · 1–${QUOTA_LIMIT_MAX_LABEL}`,
    },
  },
  apiKey: {
    keyName: {
      placeholder: "e.g. Production mobile app",
      tip: "Label to identify this key.",
      helper: "Up to 100 characters",
    },
    expiry: {
      placeholder: "e.g. 30",
      tip: "Days until this key stops working.",
      helper: "1–365 days",
    },
    permissions: {
      tip: "API actions this key is allowed to call.",
    },
    application: {
      tip: "Application this key can call APIs for.",
    },
    budget: {
      placeholder: "e.g. 25",
      tip: "% of the Application budget reserved for this key.",
      helper: "Greater than 0%",
    },
    gracePeriod: {
      tip: "Days the old key still works after rotation.",
    },
    search: {
      placeholder: "Search by key name",
    },
    tooltips: {
      budgetAllocation:
        "% of the Application budget for this key. Active keys under one Application cannot exceed 100% combined.",
    },
    col: {
      allocation: "% of Application budget reserved for this key.",
      status: "Whether this key can call APIs right now.",
      permissions: "API actions this key is allowed to call.",
      expiry: "When this key stops working.",
    },
    bulkBudgetEdit: {
      intro:
        "Change Budget % for active keys under one Application. Only edited rows are saved.",
      selectApplicationPlaceholder: "Select Application",
      selectApplicationPrompt: "Select an Application to edit key budgets.",
      loading: "Loading API keys…",
      empty: "No active API keys under this Application.",
      modalTitle: "Edit Key Budget",
      allocatedToKeysLabel: "Application budget allocated to keys",
      applicationBudgetUnset:
        "This Application has no Budget (₹) yet. Assign one in Application Management first.",
      applicationAllocationPrefix: "Application allocation:",
    },
  },
  application: {
    name: {
      placeholder: "e.g. Citizen Services Portal",
      tip: "Name shown for this application in the portal.",
      helper: "Unique within this Institution",
    },
    description: {
      placeholder: "What this application is used for",
      tip: "Short summary of this application’s purpose.",
    },
    domain: {
      placeholder: "e.g. citizen-services.gov.in",
      tip: "Domain used to find this application.",
    },
    budget: {
      placeholder: "0",
      tip: "% of Institution budget for this app. Blank = no limit.",
    },
    budgetEdit: {
      helper: "Cannot go below budget already given to API keys",
      belowConsumed:
        "% of Institution budget. Cannot go below already-consumed usage.",
    },
    institutionBudgetNotSet:
      "This Institution has no Budget (₹) yet. Assign a Tier and Budget in Institution Management first.",
    inactiveBudgetNotEditable:
      "Inactive applications cannot change budget. Reactivate to edit.",
    bulkBudgetEdit: {
      intro:
        "Change Budget % across Applications. Only edited rows are saved. Inactive rows are view-only.",
      institutionBudgetAllocatedLabel: "Institution Budget allocated",
      institutionTotalPrefix: "Institution total:",
    },
    search: {
      placeholder: "Search by name or domain",
    },
    domainFilter: {
      tip: "Exact domain match.",
    },
    status: {
      activate: "Activate this Application",
      deactivate: "Deactivate this Application",
    },
    col: {
      budget: "% of Institution budget assigned to this app.",
      keys: "Active API keys under this application.",
      status: "Whether this app can use the platform.",
      domain: "Domain used to find this application.",
    },
    tooltips: {
      totalApplications: "Applications under this Institution.",
      allocatedBudget: "Budget % assigned to Applications vs Institution total.",
      availableToAllocate: "Institution budget % not yet assigned to any Application.",
      institutionBudgetAllocated: "Budget % assigned to Applications after this change.",
      minimumAllowed: "Floor for this app — cannot go below consumed usage.",
      availableAtInstitution: "Max % you can set without exceeding 100% across apps.",
    },
  },
  register: {
    emailChecking: "Checking if email exists…",
  },
  policy: {
    name: { tip: "Label for this PII detection policy." },
    description: { tip: "Short summary of what this policy covers." },
    global: {
      tip: `On = all ${INSTITUTIONS.toLowerCase()}; off = only selected ones.`,
    },
    institutions: {
      tip: `${INSTITUTIONS} this policy applies to.`,
    },
    languages: {
      tip: "Languages this policy scans for PII.",
    },
    piiTypes: {
      tip: "Entity types this policy detects.",
    },
    tenantIdsManual: `${INSTITUTION} IDs this policy applies to (comma or newline).`,
    tenantIdsSelect: `${INSTITUTIONS} this policy applies to.`,
    playground: {
      policy: { tip: "Policy used to scan the sample text." },
      input: { tip: "Sample text to run detection against." },
      scope: { tip: "Whether the run used a global or scoped policy." },
      entities: { tip: "PII entities found in the sample." },
    },
    col: {
      scope: `Global vs selected ${INSTITUTIONS.toLowerCase()}.`,
      status: "Whether this policy is active for detection.",
      piiTypes: "Entity types configured on this policy.",
      languages: "Languages this policy covers.",
    },
  },
  piiType: {
    label: { tip: "Display name for this PII entity type." },
    regex: { tip: "Pattern used to detect this entity." },
    examples: { tip: "Sample values used to validate the pattern." },
    mask: { tip: "How matched values are redacted in output." },
    col: {
      mask: "How matches are redacted.",
      regex: "Detection pattern for this type.",
    },
  },
  tenantCol: {
    status: `Lifecycle state of this ${org}.`,
    tier: "Usage plan and budget linked to this institution.",
    onboarded: "When this institution was created.",
  },
  alerting: {
    severity: { tip: "How urgent this alert is when it fires." },
    category: { tip: "Area of the platform this alert watches." },
    signal: { tip: "Metric that can trigger this alert." },
    threshold: { tip: "Value that must be crossed to fire." },
    evalInterval: { tip: "How often the condition is checked." },
    forDuration: { tip: "How long the condition must stay true." },
  },
} as const;
