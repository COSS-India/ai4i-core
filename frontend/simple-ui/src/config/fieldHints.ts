import { INSTITUTION } from "./constants";
import { EMAIL_AVAILABLE_MSG } from "../utils/tenantEmailValidation";

const org = INSTITUTION.toLowerCase();

const NAME_CHARS_HELPER =
  "Letters, spaces, hyphens, and apostrophes only, 2–80 characters";

/** Placeholder + always-visible helper/tooltip copy for field-level guidance. */
export const FIELD_HINTS = {
  tenant: {
    organisation: {
      placeholder: "Enter organisation name",
      helper: "2–100 characters, must be unique",
    },
    contactName: {
      placeholder: "Enter contact's full name",
      helper: NAME_CHARS_HELPER,
    },
    email: {
      placeholder: "Enter official email address",
      helper: "Format: name@domain.com; must be unique",
    },
    phone: {
      placeholder: "Enter phone number",
      helper: "+[country code] [phone number]",
    },
    emailChecking: "Checking if email exists…",
    emailAvailable: EMAIL_AVAILABLE_MSG,
    emailVerifyOnChange:
      "If you change the contact email, the update takes effect only after the new address is verified.",
    emailPendingOnly: `The contact email can only be corrected while the ${org} is pending verification.`,
    planAppliesImmediately: "Tier and Budget changes apply immediately.",
    onboardTier: { helper: "Optional. Tier applies when the institution is activated." },
    onboardBudget: {
      placeholder: "Enter initial budget amount",
      helper: "Optional initial ₹ total. Must be greater than 0 when provided.",
    },
    onboardBudgetEffectiveFrom: {
      helper: "Optional. Defaults to today; cannot be backdated.",
    },
    onboardBudgetEffectiveTo: {
      helper: "Optional. Must be after Effective From.",
    },
  },
  tenantUser: {
    tenant: { helper: `Auto-filled from selected ${org}` },
    fullName: {
      placeholder: "Enter user's full name",
      helper: NAME_CHARS_HELPER,
    },
    email: {
      placeholder: "Enter official email address",
      helper: "Format: name@domain.com, must be unique",
    },
    phone: {
      placeholder: "Enter phone number",
      helper: "+[country code] [phone number]",
    },
    role: { helper: `Sets this user's permission level within the ${org}` },
    username: { helper: "Minimum 3 characters" },
    emailLocked:
      "Email cannot be changed. Suspend or delete the account if the user has left the organisation.",
    rolesLoadFailed: "Roles could not be loaded; role changes are disabled.",
    onlyAdminLocked:
      "You are the only Admin in the default organisation and cannot change your role.",
  },
  assignTier: {
    budget: { placeholder: "Enter budget amount", helper: "Must be greater than 0" },
    effectiveFrom: { helper: "Defaults to today; cannot be backdated" },
    effectiveTo: { helper: "Must be a later date than Effective From" },
  },
  model: {
    jsonUpload: {
      helper:
        ".json files only. Validated before the model is created — refer to the sample JSON for exact field formats.",
    },
  },
  service: {
    taskType: { placeholder: "Select a model task type" },
    modelName: {
      placeholder: "Select model",
      loading: "Loading models...",
      needTaskType: "Select a task type first",
    },
    modelId: { helper: "Auto-filled", empty: "Select a model above" },
    submissionDate: { helper: "Auto-filled" },
    name: {
      placeholder: "Enter service name",
      helper:
        "5–100 characters. Letters, numbers, hyphens, and slashes only. e.g: [model-name]/[GPU]",
    },
    serviceId: {
      placeholder: "Enter service ID",
      helper:
        "5–255 characters. Letters, numbers, hyphens, underscores, and slashes only. e.g: [model-name]/[GPU]",
      llmHelper:
        "Pre-filled with the model prefix. Letters, numbers, hyphens, and slashes only. 5–255 characters. e.g: [model-name]/[GPU]",
    },
    description: {
      placeholder: "Provide a brief description of what this service does",
      helper: (entered: number, min: number, max: number) =>
        `Required. ${min}–${max} characters — ${entered}/${max} entered.`,
    },
    endpoint: {
      placeholder: "Enter full endpoint URL",
      helper: "e.g. http://localhost:8088/v1/completions. Must include http:// or https://",
      llmHelper: "Enter the model host URL (host:port only).",
      llmPlaceholder: "e.g. http://host:port",
    },
    hardware: {
      placeholder: "e.g. Auto-scalable deployment, using T4 GPUs",
      helper: (min: number, max: number) =>
        `${min}–${max} characters. Describes the infrastructure this service runs on.`,
    },
    unitType: { helper: "Auto-set based on the task type", needTaskType: "Select a task type first" },
    unitSize: { placeholder: "Select unit size", helper: "Defines the unit size for pricing" },
    price: { placeholder: "Enter price", helper: "e.g., 600. Must be 0 or greater" },
    tier: { placeholder: "Select applicable tier(s)", helper: "Select at least one" },
    tierSearch: { placeholder: "Search tiers..." },
  },
  logs: {
    search: { placeholder: "Search by trace ID, URL, task type, or status" },
    startTime: { helper: "Filter logs from this date & time" },
    endTime: { helper: "Filter logs up to this date & time; must be after Start Time" },
    tenant: { helper: `Filter logs by ${org}.` },
    autoRefresh: { helper: "Automatically refresh this list at regular intervals." },
  },
  profile: {
    fullName: {
      placeholder: "Enter your full name",
      helper: NAME_CHARS_HELPER,
    },
    timezone: { helper: "Used to display dates and times across the portal" },
    currentPassword: { placeholder: "Enter current password", helper: "Required" },
    newPassword: { placeholder: "Enter new password" },
    confirmPassword: {
      placeholder: "Re-enter new password",
      helper: "Must match New Password",
    },
    roleUser: { helper: "Choose a user to change their current role" },
    usernameLocked: "Username cannot be changed",
    emailLocked: "Email cannot be changed",
    phone: {
      placeholder: "+91XXXXXXXXXX or XXXXXXXXXX",
      helper: "Enter a valid Indian mobile number (10 digits starting with 6-9)",
    },
  },
  tier: {
    name: { placeholder: "Enter tier name", helper: "e.g. Enterprise, Standard, Basic" },
    description: {
      placeholder: "Enter tier description",
      helper: "e.g. Enterprise tier for high usage.",
    },
    quotaUnit: { helper: "Auto-filled based on Model Task Type (e.g., tokens for LLM)" },
    quotaLimit: { placeholder: "Enter quota limit", helper: "e.g. 10000. Must be greater than 0" },
  },
  apiKey: {
    expiry: {
      placeholder: "Enter number of days",
      helper: "e.g. 30. Must be between 1 and 365",
    },
    permissions: { helper: "Select at least one permission" },
    application: {
      helper: "Required. Keys are scoped to one Application.",
    },
    budget: {
      placeholder: "0",
      helper: "Optional. Percentage of the parent Application's Budget.",
    },
    search: {
      placeholder: "Search by key name",
      helper: "Matches API key name.",
    },
    tooltips: {
      budgetAllocation:
        "Share of the parent Application's Budget reserved for this key. Active keys cannot exceed 100% combined per Application.",
    },
  },
  application: {
    name: {
      placeholder: "e.g. Citizen Services Portal",
      helper:
        "Required. Must be unique within this Institution (case-insensitive).",
    },
    description: {
      placeholder: "What this Application is used for",
      helper: "Optional plain text. Shown on the Application details view.",
    },
    domain: {
      placeholder: "e.g. citizen-services.gov.in",
      helper: "Optional. Used to search and filter this Application later.",
    },
    budget: {
      placeholder: "0",
      helper:
        "Optional. Percentage of the Institution's Budget. Leave blank for no ceiling.",
    },
    budgetEdit: {
      helper:
        "Percentage of this Institution's total Budget. Cannot be reduced below already-consumed usage.",
    },
    institutionBudgetNotSet:
      "This Institution does not have a Budget (₹) assigned yet. Assign a Tier and Budget from Institution Management before saving Application budget allocations.",
    amountRequiresInstitutionBudget:
      "Assign an Institution Budget (₹) before entering amounts.",
    search: {
      placeholder: "Search by name or domain",
      helper: "Matches Application name or domain.",
    },
    domainFilter: {
      helper: "Exact-match filter on Application domain.",
    },
    tooltips: {
      totalApplications:
        "Count of Applications onboarded under this Institution.",
      allocatedBudget:
        "Sum of Budget % assigned across all Applications, as a share of the Institution's total Budget.",
      availableToAllocate:
        "Institution Budget % not yet assigned to any Application. This share may stay unallocated.",
      institutionBudgetAllocated:
        "Total Budget % assigned across all Applications after this change.",
      minimumAllowed:
        "Lowest % allowed for this Application — already-consumed usage cannot be reduced.",
      availableAtInstitution:
        "Maximum % you can assign without exceeding 100% across all Applications.",
    },
  },
  application: {
    name: {
      placeholder: "e.g. Citizen Services Portal",
      helper:
        "Required. Must be unique within this Institution (case-insensitive).",
    },
    description: {
      placeholder: "What this Application is used for",
      helper: "Optional plain text. Shown on the Application details view.",
    },
    domain: {
      placeholder: "e.g. citizen-services.gov.in",
      helper: "Optional. Used to search and filter this Application later.",
    },
    budget: {
      placeholder: "0",
      helper:
        "Optional. Percentage of the Institution's Budget. Leave blank for no ceiling.",
    },
    budgetEdit: {
      helper:
        "Percentage of this Institution's total Budget. Cannot be reduced below already-consumed usage.",
    },
    search: {
      placeholder: "Search by name or domain",
      helper: "Matches Application name or domain.",
    },
    domainFilter: {
      helper: "Exact-match filter on Application domain.",
    },
    tooltips: {
      totalApplications:
        "Count of Applications onboarded under this Institution.",
      allocatedBudget:
        "Sum of Budget % assigned across all Applications, as a share of the Institution's total Budget.",
      availableToAllocate:
        "Institution Budget % not yet assigned to any Application. This share may stay unallocated.",
      institutionBudgetAllocated:
        "Total Budget % assigned across all Applications after this change.",
      minimumAllowed:
        "Lowest % allowed for this Application — already-consumed usage cannot be reduced.",
      availableAtInstitution:
        "Maximum % you can assign without exceeding 100% across all Applications.",
    },
  },
  register: {
    emailChecking: "Checking if email exists…",
  },
  policy: {
    tenantIdsManual: `Enter one or more ${org} IDs.`,
    tenantIdsSelect: `Select one or more active ${org} assignments for this policy.`,
  },
} as const;
