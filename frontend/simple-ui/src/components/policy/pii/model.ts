/**
 * Policies catalog. Categories, sub-categories, PII definitions, and policies
 * come from the platform-core policy APIs. Domain rows and the playground
 * sample text stay local.
 */

export type Handling = "Mask" | "Redact" | "Hash";
export type MaskingPattern = "Full" | "Partial";
export type DetectionMode = "Regex" | "Model";
export type PolicyType = "Global" | "Institution level";
export type PolicyScope = "Input requests" | "Output requests" | "Both";
export type RecordStatus = "Active" | "Inactive";
export type PortalRole = "adopter" | "institution";

export interface Domain {
  id: string;
  name: string;
  description: string;
  isDefault: boolean;
}

/** A row on a policy type: a Presidio entity, or a custom regex entity. */
export interface PolicyField {
  mode: "model" | "custom";
  /** Domain key stored on policy_fields, such as Education or Finance. */
  domain: string;
  entityName: string;
  examples: string[];
  regex: string;
  /** Language key inside model_supported_field. Custom rows keep "en". */
  language: string;
}

/** Language codes stored on model_supported_field. */
export const MODEL_FIELD_LANGUAGES = ["en", "hi", "ta", "te", "kn", "mr", "bn"] as const;

export interface PiiType {
  id: string;
  name: string;
  domainId: string | null;
  handling: Handling;
  maskingPattern: MaskingPattern | null;
  detectionMode: DetectionMode;
  regex: string;
  nerModel: string;
  examples: string[];
  isDefault: boolean;
  fields: PolicyField[];
}

export interface Policy {
  id: string;
  policyId: string;
  name: string;
  description: string;
  /** Parent sub-category. Policies are listed under this id. */
  subcategoryId: string;
  domainIds: string[];
  languages: string[];
  typeIds: string[];
  policyType: PolicyType;
  scope: PolicyScope;
  status: RecordStatus;
}

export interface PolicyCategory {
  id: string;
  name: string;
  description: string;
  status: RecordStatus;
}

export interface PolicySubcategory {
  id: string;
  categoryId: string;
  name: string;
  description: string;
  status: RecordStatus;
}

export interface Institution {
  id: string;
  name: string;
}

export const NER_MODELS = [
  "spaCy en_core_web_lg (Person / Org / Location)",
  "Presidio Analyzer (Multi-entity)",
  "BERT-NER (Fine-tuned, multilingual)",
  "Custom Fine-tuned Transformer",
] as const;

export const LANGUAGES = [
  "English",
  "Hindi",
  "Tamil",
  "Telugu",
  "Kannada",
  "Marathi",
  "Bengali",
] as const;

export const HANDLING_OPTIONS: Handling[] = ["Mask", "Redact", "Hash"];
export const SCOPE_OPTIONS: PolicyScope[] = [
  "Input requests",
  "Output requests",
  "Both",
];

export const INSTITUTIONS: Institution[] = [
  { id: "inst-springfield", name: "Springfield University" },
  { id: "inst-northbank", name: "Northbank Financial" },
  { id: "inst-carewell", name: "CareWell Hospitals" },
  { id: "inst-metro", name: "Metro Public Services" },
];

/** The deployed PII sub-category. Matched by name because the id is assigned by the API. */
export function isPiiGuardrailsSubcategory(sub: { name: string }): boolean {
  return sub.name.trim().toLowerCase().replace(/\s+/g, " ") === "pii guardrails";
}

const DOMAINS: Domain[] = [
  {
    id: "dom-education",
    name: "Education",
    description: "K-12 and higher-education institutions",
    isDefault: true,
  },
  {
    id: "dom-finance",
    name: "Finance / Banking",
    description: "Banks, NBFCs, and payment platforms",
    isDefault: true,
  },
  {
    id: "dom-healthcare",
    name: "Healthcare",
    description: "Hospitals, clinics, and health insurers",
    isDefault: true,
  },
];

function type(partial: Omit<PiiType, "nerModel" | "detectionMode" | "maskingPattern" | "fields"> & {
  nerModel?: string;
  detectionMode?: DetectionMode;
  maskingPattern?: MaskingPattern | null;
  fields?: PolicyField[];
}): PiiType {
  return {
    nerModel: NER_MODELS[0],
    detectionMode: "Regex",
    fields: [],
    ...partial,
    maskingPattern: partial.handling === "Mask" ? partial.maskingPattern ?? "Partial" : null,
  };
}

const PII_TYPES: PiiType[] = [
  type({
    id: "pii-aadhaar",
    name: "Aadhaar Number",
    domainId: null,
    handling: "Hash",
    regex: "\\b\\d{4}\\s?\\d{4}\\s?\\d{4}\\b",
    examples: ["1234 5678 9012"],
    isDefault: true,
  }),
  type({
    id: "pii-mobile",
    name: "Mobile Number",
    domainId: null,
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b(?:\\+91[-\\s]?)?[6-9]\\d{9}\\b",
    examples: ["9876543210"],
    isDefault: true,
  }),
  type({
    id: "pii-email",
    name: "Email Address",
    domainId: null,
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
    examples: ["arjun@college.edu"],
    isDefault: true,
  }),
  type({
    id: "pii-fullname",
    name: "Full Name",
    domainId: null,
    handling: "Mask",
    maskingPattern: "Full",
    regex: "\\b[A-Z][a-z]+(?:\\s[A-Z][a-z]+){1,2}\\b",
    examples: ["Arjun Kumar"],
    isDefault: true,
  }),
  type({
    id: "pii-dob",
    name: "Date of Birth",
    domainId: null,
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b(0[1-9]|[12]\\d|3[01])[-/](0[1-9]|1[0-2])[-/]\\d{4}\\b",
    examples: ["12-08-2004"],
    isDefault: true,
  }),
  type({
    id: "pii-pan",
    name: "PAN Card",
    domainId: null,
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Z]{5}\\d{4}[A-Z]\\b",
    examples: ["ABCDE1234F"],
    isDefault: true,
  }),
  type({
    id: "pii-address",
    name: "Postal Address",
    domainId: null,
    handling: "Redact",
    regex: "\\b\\d+\\s[A-Za-z0-9\\s,.-]{6,60}\\b",
    examples: ["24 MG Road Chennai"],
    isDefault: true,
  }),
  type({
    id: "pii-edu-name",
    name: "Student Name",
    domainId: "dom-education",
    handling: "Mask",
    maskingPattern: "Full",
    regex: "\\b[A-Z][a-z]+(?:\\s[A-Z][a-z]+){1,3}\\b",
    examples: ["Meena Raj"],
    isDefault: true,
  }),
  type({
    id: "pii-edu-id",
    name: "Student ID",
    domainId: "dom-education",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Z]{2,5}\\d{4,10}\\b",
    examples: ["EDU20231234"],
    isDefault: true,
  }),
  type({
    id: "pii-edu-email",
    name: "Email",
    domainId: "dom-education",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
    examples: ["meena@college.edu"],
    isDefault: true,
  }),
  type({
    id: "pii-edu-phone",
    name: "Phone Number",
    domainId: "dom-education",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b(?:\\+?\\d{1,3}[-\\s]?)?\\d{10}\\b",
    examples: ["9876543210"],
    isDefault: true,
  }),
  type({
    id: "pii-edu-dob",
    name: "Date of Birth",
    domainId: "dom-education",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b(0[1-9]|[12]\\d|3[01])[-/](0[1-9]|1[0-2])[-/]\\d{4}\\b",
    examples: ["12-08-2004"],
    isDefault: true,
  }),
  type({
    id: "pii-edu-address",
    name: "Address",
    domainId: "dom-education",
    handling: "Redact",
    regex: "\\d+[\\w\\s,.-]+",
    examples: ["24 MG Road Chennai"],
    isDefault: true,
  }),
  type({
    id: "pii-fin-account",
    name: "Bank Account Number",
    domainId: "dom-finance",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b\\d{9,18}\\b",
    examples: ["123456789012"],
    isDefault: true,
  }),
  type({
    id: "pii-fin-card",
    name: "Credit / Debit Card",
    domainId: "dom-finance",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b(?:\\d[ -]*?){13,16}\\b",
    examples: ["4111 1111 1111 1111"],
    isDefault: true,
  }),
  type({
    id: "pii-fin-ifsc",
    name: "IFSC Code (India)",
    domainId: "dom-finance",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Z]{4}0[A-Z0-9]{6}\\b",
    examples: ["SBIN0000456"],
    isDefault: true,
  }),
  type({
    id: "pii-fin-pan",
    name: "PAN Number (India)",
    domainId: "dom-finance",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Z]{5}\\d{4}[A-Z]\\b",
    examples: ["ABCDE1234F"],
    isDefault: true,
  }),
  type({
    id: "pii-fin-txn",
    name: "Transaction ID",
    domainId: "dom-finance",
    handling: "Redact",
    regex: "\\b[A-Z0-9]{8,20}\\b",
    examples: ["TXN987654321"],
    isDefault: true,
  }),
  type({
    id: "pii-fin-upi",
    name: "UPI ID",
    domainId: "dom-finance",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[\\w.-]+@[\\w.-]+\\b",
    examples: ["arjun@upi"],
    isDefault: true,
  }),
  type({
    id: "pii-health-name",
    name: "Patient Name",
    domainId: "dom-healthcare",
    handling: "Mask",
    maskingPattern: "Full",
    regex: "\\b[A-Z][a-z]+(?:\\s[A-Z][a-z]+){1,3}\\b",
    examples: ["Meena Raj"],
    isDefault: true,
  }),
  type({
    id: "pii-health-mrn",
    name: "Medical Record Number",
    domainId: "dom-healthcare",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Z]{2,5}\\d{4,10}\\b",
    examples: ["UHID123456"],
    isDefault: true,
  }),
  type({
    id: "pii-health-aadhaar",
    name: "Aadhaar Number (India)",
    domainId: "dom-healthcare",
    handling: "Hash",
    regex: "\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b",
    examples: ["1234 5678 9012"],
    isDefault: true,
  }),
  type({
    id: "pii-health-phone",
    name: "Phone Number",
    domainId: "dom-healthcare",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b(?:\\+?\\d{1,3}[-\\s]?)?\\d{10}\\b",
    examples: ["9876543210"],
    isDefault: true,
  }),
  type({
    id: "pii-health-insurance",
    name: "Health Insurance ID",
    domainId: "dom-healthcare",
    handling: "Mask",
    maskingPattern: "Partial",
    regex: "\\b[A-Z0-9]{6,20}\\b",
    examples: ["HIN9876543"],
    isDefault: true,
  }),
  type({
    id: "pii-health-icd",
    name: "Diagnosis Code (ICD-10)",
    domainId: "dom-healthcare",
    handling: "Redact",
    regex: "\\b[A-TV-Z][0-9]{2}(\\.[0-9A-TV-Z]{1,4})?\\b",
    examples: ["E11.9"],
    isDefault: true,
  }),
];

const POLICIES: Policy[] = [
  {
    id: "policy-core",
    policyId: "SPP-1001",
    subcategoryId: "",
    name: "Core PII Protection",
    description: "Baseline protection applied platform-wide.",
    domainIds: ["dom-education", "dom-finance", "dom-healthcare"],
    languages: ["English", "Hindi"],
    typeIds: ["pii-aadhaar", "pii-mobile", "pii-email", "pii-fullname", "pii-pan"],
    policyType: "Global",
    scope: "Both",
    status: "Active",
  },
  {
    id: "policy-edu",
    policyId: "SPP-1002",
    subcategoryId: "",
    name: "Education Data Safeguard",
    description: "Student-record protection for education-sector institutions.",
    domainIds: ["dom-education"],
    languages: ["English"],
    typeIds: ["pii-edu-name", "pii-edu-id", "pii-edu-email", "pii-edu-phone", "pii-edu-dob"],
    policyType: "Institution level",
    scope: "Input requests",
    status: "Active",
  },
  {
    id: "policy-fin",
    policyId: "SPP-1003",
    subcategoryId: "",
    name: "Financial Services Compliance",
    description: "RBI-aligned protection for banking and payments data.",
    domainIds: ["dom-finance"],
    languages: ["English", "Hindi", "Tamil"],
    typeIds: [
      "pii-fin-account",
      "pii-fin-card",
      "pii-fin-ifsc",
      "pii-fin-pan",
      "pii-fin-txn",
      "pii-fin-upi",
    ],
    policyType: "Institution level",
    scope: "Both",
    status: "Active",
  },
  {
    id: "policy-health",
    policyId: "SPP-1004",
    subcategoryId: "",
    name: "Healthcare Privacy Shield",
    description: "Patient-data protection for healthcare-sector institutions.",
    domainIds: ["dom-healthcare"],
    languages: ["English"],
    typeIds: [
      "pii-health-name",
      "pii-health-mrn",
      "pii-health-aadhaar",
      "pii-health-phone",
      "pii-health-insurance",
      "pii-health-icd",
    ],
    policyType: "Institution level",
    scope: "Output requests",
    status: "Inactive",
  },
];

export const INITIAL_SUBSCRIPTIONS: Record<string, string[]> = {
  "SPP-1002": ["inst-springfield"],
  "SPP-1003": ["inst-northbank"],
};

export interface PiiCatalog {
  domains: Domain[];
  types: PiiType[];
  policies: Policy[];
  subscriptions: Record<string, string[]>;
}

export function createInitialCatalog(): PiiCatalog {
  return {
    domains: DOMAINS.map((d) => ({ ...d })),
    types: PII_TYPES.map((t) => ({ ...t, examples: [...t.examples] })),
    policies: POLICIES.map((p) => ({
      ...p,
      domainIds: [...p.domainIds],
      languages: [...p.languages],
      typeIds: [...p.typeIds],
    })),
    subscriptions: Object.fromEntries(
      Object.entries(INITIAL_SUBSCRIPTIONS).map(([k, v]) => [k, [...v]]),
    ),
  };
}

export function categoryEffective(cat: PolicyCategory): RecordStatus {
  return cat.status;
}

export function subcategoryEffective(
  sub: PolicySubcategory,
  categories: PolicyCategory[],
): RecordStatus {
  const cat = categories.find((c) => c.id === sub.categoryId);
  return sub.status === "Active" && cat && categoryEffective(cat) === "Active"
    ? "Active"
    : "Inactive";
}

export function policyEffective(
  policy: Policy,
  parentActive: boolean,
): RecordStatus {
  return policy.status === "Active" && parentActive ? "Active" : "Inactive";
}

export function nextPolicyCode(policies: Policy[]): string {
  const nums = policies
    .map((p) => parseInt(p.policyId.split("-")[1] ?? "", 10))
    .filter((n) => !Number.isNaN(n));
  const next = Math.max(1000, ...nums) + 1;
  return `SPP-${next}`;
}

export function domainLabel(id: string, domains: { id: string; name: string }[]): string {
  return domains.find((domain) => domain.id === id)?.name ?? id;
}

export function parseExampleValues(raw: string): string[] {
  return raw
    .split(/\n|,/)
    .map((v) => v.trim())
    .filter(Boolean);
}

export function previewFor(handling: Handling, maskingPattern: MaskingPattern | null): string {
  if (handling === "Hash") return "sha256:…";
  if (handling === "Redact") return "[REDACTED]";
  return maskingPattern === "Full" ? "XXXX XXXX" : "XXXX*****";
}
