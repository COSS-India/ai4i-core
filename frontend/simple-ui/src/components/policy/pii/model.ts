/**
 * Policy catalog types. Categories, sub-categories, PII definitions, policies,
 * and domains come from the platform APIs. The playground builds its sample
 * text from the policy's own fields.
 */

export type PolicyType = "Global" | "Institution level";
export type PolicyScope = "Input requests" | "Output requests" | "Both";
export type RecordStatus = "Active" | "Inactive";
export type PortalRole = "adopter" | "institution";

export interface Domain {
  id: string;
  name: string;
  description: string;
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

/**
 * Configuration lists and edits custom fields only while this is off. Saved
 * model-supported fields are kept as they are when a type is edited.
 */
export const SHOW_MODEL_SUPPORTED_FIELDS = false;

export function isFieldShown(field: PolicyField): boolean {
  return SHOW_MODEL_SUPPORTED_FIELDS || field.mode === "custom";
}

/** Language codes stored on model_supported_field. */
export const MODEL_FIELD_LANGUAGES = ["en", "hi", "ta", "te", "kn", "mr", "bn"] as const;

export interface PiiType {
  id: string;
  name: string;
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
  /** Language codes such as "en". Empty when the API returns none for the policy. */
  languages: string[];
  typeIds: string[];
  /** Fields picked from the linked types. null: the API returns no picks, so every field applies. */
  selectedFields: SelectedPolicyField[] | null;
  policyType: PolicyType;
  scope: PolicyScope;
  status: RecordStatus;
}

export type PolicyFieldSource = "custom_field" | "model_supported_field";

/** A field of a linked type: custom by type and entity, model-supported also by language. */
export interface SelectedPolicyField {
  source: PolicyFieldSource;
  typeId: string;
  entityName: string;
  /** Set for model_supported_field only. */
  language: string | null;
}

/** What the policy form submits. The sub-category comes from the form, not the open page. */
export interface PolicyInput {
  name: string;
  description: string;
  subCategoryId: string;
  domainIds: string[];
  languages: string[];
  typeIds: string[];
  /** null keeps a policy saved without picks on "every field applies". */
  selectedFields: SelectedPolicyField[] | null;
  /** Fields that belong to this policy only, not to a shared PII type. Excluded from typeIds/selectedFields. */
  ownFields: PolicyField[];
  scope: PolicyScope;
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

/** Languages a policy can support, stored by code. */
export const POLICY_LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu" },
  { code: "kn", label: "Kannada" },
  { code: "mr", label: "Marathi" },
  { code: "bn", label: "Bengali" },
];

/** Languages a new policy starts with. */
export const DEFAULT_POLICY_LANGUAGES: readonly string[] = ["en"];

/**
 * Languages shown in lists and view drawers. Empty storage falls back to the release default (English).
 */
export function displayLanguages(policy: Pick<Policy, "languages">): string[] {
  return policy.languages.length > 0 ? [...policy.languages] : [...DEFAULT_POLICY_LANGUAGES];
}

/**
 * Languages the edit form starts with. A policy without saved languages starts on the defaults,
 * flagged as prefilled so the form can ask the admin to check them.
 */
export function editableLanguages(policy: Pick<Policy, "languages">): { languages: string[]; prefilled: boolean } {
  return policy.languages.length > 0
    ? { languages: [...policy.languages], prefilled: false }
    : { languages: [...DEFAULT_POLICY_LANGUAGES], prefilled: true };
}

/** Display name for a language code; codes outside POLICY_LANGUAGES show as-is. */
export function languageLabel(code: string): string {
  return POLICY_LANGUAGES.find((language) => language.code === code)?.label ?? code;
}

/** Stable identity of a selected field, matching the API's (source, type, language, entity). */
export function selectedFieldKey(field: SelectedPolicyField): string {
  return [field.source, field.typeId, field.language ?? "", field.entityName].join("::");
}

export function parseSelectedFieldKey(key: string): SelectedPolicyField {
  const [source, typeId, language, ...entity] = key.split("::");
  return {
    source: source as PolicyFieldSource,
    typeId,
    language: language || null,
    entityName: entity.join("::"),
  };
}

export const SCOPE_OPTIONS: PolicyScope[] = [
  "Input requests",
  "Output requests",
  "Both",
];

/** The deployed PII sub-category. Matched by name because the id is assigned by the API. */
export function isPiiGuardrailsSubcategory(sub: { name: string }): boolean {
  return sub.name.trim().toLowerCase().replace(/\s+/g, " ") === "pii guardrails";
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

/** Whether the policy's sub-category and its category are both active. An unknown parent is not. */
export function policyParentActive(
  policy: Pick<Policy, "subcategoryId">,
  subcategories: PolicySubcategory[],
  categories: PolicyCategory[],
): boolean {
  const sub = subcategories.find((s) => s.id === policy.subcategoryId);
  return sub ? subcategoryEffective(sub, categories) === "Active" : false;
}

/** Sub-categories under the category, or every sub-category when none is selected. */
export function subcategoriesForCategory(
  subcategories: PolicySubcategory[],
  categoryId: string,
): PolicySubcategory[] {
  return categoryId ? subcategories.filter((s) => s.categoryId === categoryId) : subcategories;
}

/** The sub-category to keep after the category changes: kept only when it is under the new category. */
export function subcategoryAfterCategoryChange(
  subcategories: PolicySubcategory[],
  subcategoryId: string,
  categoryId: string,
): string {
  const sub = subcategories.find((s) => s.id === subcategoryId);
  return sub && sub.categoryId === categoryId ? subcategoryId : "";
}

export interface PolicyFilters {
  search: string;
  domainId: string;
  categoryId: string;
  subcategoryId: string;
}

/** Policies across every category, narrowed by the list's search and filters. */
export function filterPolicies(
  policies: Policy[],
  filters: PolicyFilters,
  subcategories: PolicySubcategory[],
): Policy[] {
  const query = filters.search.toLowerCase();
  const categoryOf = new Map(subcategories.map((s) => [s.id, s.categoryId]));
  return policies.filter((p) => {
    if (query && !p.name.toLowerCase().includes(query)) return false;
    if (filters.domainId && !p.domainIds.includes(filters.domainId)) return false;
    if (filters.subcategoryId && p.subcategoryId !== filters.subcategoryId) return false;
    if (filters.categoryId && categoryOf.get(p.subcategoryId) !== filters.categoryId) return false;
    return true;
  });
}

export function domainLabel(id: string, domains: { id: string; name: string }[]): string {
  return domains.find((domain) => domain.id === id)?.name ?? id;
}
