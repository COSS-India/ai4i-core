import type {
  GuardrailScope,
  PolicyRecord,
  PolicyTypeItem,
  SelectedPolicyFieldRecord,
} from "../../../services/dto/schemas/policyHierarchy";
import type {
  PolicyPatch,
  PolicyWrite,
  SimulationPolicyType,
} from "../../../services/policyHierarchyService";
import {
  domainLabel,
  type Domain,
  type PiiType,
  type Policy,
  type PolicyField,
  type PolicyInput,
  type PolicyScope,
  type SelectedPolicyField,
} from "./model";

/** Regex definitions go in custom_field, which the API rejects with fewer than three examples. */
export const MIN_REGEX_EXAMPLES = 3;

/**
 * The API still requires is_global on create. The form no longer asks for it, so new policies
 * are Global, the previous form default.
 */
export const DEFAULT_IS_GLOBAL = true;

const SCOPE_TO_API: Record<PolicyScope, GuardrailScope> = {
  "Input requests": "input",
  "Output requests": "output",
  Both: "both",
};

const SCOPE_FROM_API: Record<GuardrailScope, PolicyScope> = {
  input: "Input requests",
  output: "Output requests",
  both: "Both",
};

export interface DefinitionFields {
  fields: PolicyField[];
}

/** Catalog labels such as "Finance / Banking" are stored as the API domain key "Finance". */
export function apiDomainName(name: string): string {
  const trimmed = name.trim();
  if (/^finance\b/i.test(trimmed)) return "Finance";
  return trimmed;
}

/** Writes the flat shape: top-level custom_field and model_supported_field. */
export function policyFieldsFromDefinition(input: DefinitionFields): Record<string, unknown> {
  const custom: { entity_name: string; examples: string[]; regex: string }[] = [];
  const model = new Map<string, { entity_name: string }[]>();
  input.fields.forEach((field) => {
    const entityName = field.entityName.trim();
    if (!entityName) return;
    if (field.mode === "model") {
      const language = field.language.trim() || "en";
      const entities = model.get(language) ?? [];
      if (!entities.some((entity) => entity.entity_name === entityName)) {
        entities.push({ entity_name: entityName });
      }
      model.set(language, entities);
    } else {
      custom.push({
        entity_name: entityName,
        examples: field.examples.map((example) => example.trim()).filter(Boolean),
        regex: field.regex.trim(),
      });
    }
  });

  const policyFields: Record<string, unknown> = {};
  if (custom.length > 0) policyFields.custom_field = custom;
  if (model.size > 0) {
    const entry: Record<string, { entity_name: string }[]> = {};
    model.forEach((entities, language) => {
      entry[language] = entities;
    });
    policyFields.model_supported_field = [entry];
  }
  return policyFields;
}

/** Reads the flat shape, and also rows still keyed by domain from before the flatten migration. */
function fieldsFromPolicyFields(policyFields: Record<string, unknown>): PolicyField[] {
  if (isDomainBucket(policyFields)) return rowsFromBucket("", policyFields);
  const entries = Object.entries(policyFields);
  const domainBuckets = entries.filter((entry): entry is [string, Record<string, unknown>] =>
    isDomainBucket(entry[1]),
  );
  if (domainBuckets.length > 0) {
    return domainBuckets.flatMap(([domain, bucket]) => rowsFromBucket(domain, bucket));
  }
  return rowsFromBucket("", policyFields);
}

function isDomainBucket(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return "custom_field" in record || "model_supported_field" in record;
}

function rowsFromBucket(storedDomain: string, bucket: Record<string, unknown>): PolicyField[] {
  const rows: PolicyField[] = [];
  if (Array.isArray(bucket.custom_field)) {
    bucket.custom_field.forEach((entry) => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return;
      const record = entry as Record<string, unknown>;
      const entityName = stringValue(record.entity_name);
      if (!entityName) return;
      rows.push({
        mode: "custom",
        domain: storedDomain,
        entityName,
        examples: stringList(record.examples),
        regex: stringValue(record.regex),
        language: "en",
      });
    });
  }
  if (Array.isArray(bucket.model_supported_field)) {
    bucket.model_supported_field.forEach((entry) => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return;
      Object.entries(entry as Record<string, unknown>).forEach(([language, entities]) => {
        if (!Array.isArray(entities)) return;
        entities.forEach((entity) => {
          if (!entity || typeof entity !== "object" || Array.isArray(entity)) return;
          const entityName = stringValue((entity as Record<string, unknown>).entity_name);
          if (!entityName) return;
          rows.push({
            mode: "model",
            domain: storedDomain,
            entityName,
            examples: [],
            regex: "",
            language: language || "en",
          });
        });
      });
    });
  }
  return rows;
}

export function definitionFromPolicyType(item: PolicyTypeItem): PiiType {
  return {
    id: String(item.id),
    name: item.policy_type,
    fields: fieldsFromPolicyFields(item.policy_fields),
  };
}

/** platform-core stores policy_fields flat; /pii/simulate reads them as domain sections. */
export function simulationPolicyType(item: PolicyTypeItem): SimulationPolicyType {
  const fields = item.policy_fields;
  return {
    id: item.id,
    policy_type: item.policy_type,
    policy_fields: {
      default: {
        custom_field: Array.isArray(fields.custom_field) ? fields.custom_field : [],
        model_supported_field: Array.isArray(fields.model_supported_field)
          ? fields.model_supported_field
          : [],
      },
    },
  };
}

/** The selection a type's field is saved as. Model-supported fields are picked per language. */
export function selectionForField(typeId: string, field: PolicyField): SelectedPolicyField {
  return field.mode === "model"
    ? { source: "model_supported_field", typeId, entityName: field.entityName, language: field.language || "en" }
    : { source: "custom_field", typeId, entityName: field.entityName, language: null };
}

function sameSelection(a: SelectedPolicyField, b: SelectedPolicyField): boolean {
  return (
    a.source === b.source &&
    a.typeId === b.typeId &&
    a.entityName === b.entityName &&
    (a.language ?? null) === (b.language ?? null)
  );
}

/** Whether the policy applies this field: in one of its domains and, when it has picks, picked. */
function policyAppliesField(
  policy: Policy,
  typeId: string,
  field: PolicyField,
  wantedDomains: Set<string>,
): boolean {
  if (!field.entityName) return false;
  const inDomain =
    wantedDomains.size === 0 || field.domain === "" || wantedDomains.has(field.domain.toLowerCase());
  if (!inDomain) return false;
  if (policy.selectedFields == null) return true;
  const selection = selectionForField(typeId, field);
  return policy.selectedFields.some((picked) => sameSelection(picked, selection));
}

function policyDomainKeys(policy: Policy, domains: Domain[]): Set<string> {
  return new Set(policy.domainIds.map((id) => apiDomainName(domainLabel(id, domains)).toLowerCase()));
}

/** Custom regex fields the policy applies, for the playground. */
export function regexFieldsForPolicy(policy: Policy, types: PiiType[], domains: Domain[]): PolicyField[] {
  const wanted = policyDomainKeys(policy, domains);
  return types
    .filter((type) => policy.typeIds.includes(type.id))
    .flatMap((type) =>
      type.fields.filter(
        (field) =>
          field.mode === "custom" && field.regex && policyAppliesField(policy, type.id, field, wanted),
      ),
    );
}

/** Entity names the policy applies, including model-supported rows. */
export function entityNamesForPolicy(policy: Policy, types: PiiType[], domains: Domain[]): string[] {
  const wanted = policyDomainKeys(policy, domains);
  const names = types
    .filter((type) => policy.typeIds.includes(type.id))
    .flatMap((type) =>
      type.fields
        .filter((field) => policyAppliesField(policy, type.id, field, wanted))
        .map((field) => field.entityName),
    );
  return Array.from(new Set(names));
}

export function guardrailToApi(scope: PolicyScope): GuardrailScope {
  return SCOPE_TO_API[scope];
}

export function domainNames(ids: string[], domains: Domain[]): string[] {
  return ids
    .map((id) => domains.find((domain) => domain.id === id)?.name ?? id)
    .map((name) => name.trim())
    .filter(Boolean);
}

/** POST /policies body, or null when an id is not a positive integer. */
export function policyCreatePayload(input: PolicyInput, domains: Domain[]): PolicyWrite | null {
  const subCategoryId = positiveInt(input.subCategoryId);
  const typeIds = positiveInts(input.typeIds);
  const selections = selectionPayload(input);
  if (subCategoryId == null || typeIds == null || selections === null) return null;
  return {
    name: input.name,
    description: blankToNull(input.description),
    domain: domainNames(input.domainIds, domains),
    guardrail_scope: guardrailToApi(input.scope),
    is_global: DEFAULT_IS_GLOBAL,
    sub_category_id: subCategoryId,
    policy_type_id: typeIds,
    ...selections,
  };
}

/**
 * PUT /policies body without id. Leaves is_global as stored; the name cannot change.
 * Without picks (selectedFields null) selected_policy_fields is omitted, so the stored value stays.
 */
export function policyUpdatePayload(input: PolicyInput, domains: Domain[]): PolicyPatch | null {
  const subCategoryId = positiveInt(input.subCategoryId);
  const typeIds = positiveInts(input.typeIds);
  const selections = selectionPayload(input);
  if (subCategoryId == null || typeIds == null || selections === null) return null;
  return {
    description: blankToNull(input.description),
    domain: domainNames(input.domainIds, domains),
    guardrail_scope: guardrailToApi(input.scope),
    sub_category_id: subCategoryId,
    policy_type_id: typeIds,
    ...selections,
  };
}

/** languages and selected_policy_fields for a write, or null when a pick has an invalid id. */
function selectionPayload(
  input: PolicyInput,
): { languages?: string[]; selected_policy_fields?: SelectedPolicyFieldRecord[] } | null {
  const payload: { languages?: string[]; selected_policy_fields?: SelectedPolicyFieldRecord[] } = {};
  if (input.languages.length > 0) payload.languages = [...input.languages];
  if (input.selectedFields == null) return payload;
  const records: SelectedPolicyFieldRecord[] = [];
  for (const field of input.selectedFields) {
    const typeId = positiveInt(field.typeId);
    if (typeId == null) return null;
    if (field.source === "model_supported_field") {
      if (!field.language) return null;
      records.push({ source: field.source, policy_type_id: typeId, language: field.language, entity_name: field.entityName });
    } else {
      records.push({ source: field.source, policy_type_id: typeId, entity_name: field.entityName });
    }
  }
  payload.selected_policy_fields = records;
  return payload;
}

function selectedFieldFromRecord(record: SelectedPolicyFieldRecord): SelectedPolicyField {
  return {
    source: record.source,
    typeId: String(record.policy_type_id),
    entityName: record.entity_name,
    language: record.source === "model_supported_field" ? (record.language ?? null) : null,
  };
}

function positiveInt(id: string): number | null {
  const value = Number(id);
  return id.trim() !== "" && Number.isInteger(value) && value > 0 ? value : null;
}

function positiveInts(ids: string[]): number[] | null {
  const values = ids.map(positiveInt);
  return values.every((value): value is number => value != null) ? values : null;
}

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function policyFromRecord(item: PolicyRecord, domains: Domain[]): Policy {
  return {
    id: String(item.id),
    policyId: item.policy_id,
    name: item.name,
    description: item.description?.trim() ?? "",
    subcategoryId: String(item.sub_category_id),
    domainIds: item.domain.map((name) => {
      const match =
        domains.find((domain) => domain.name.toLowerCase() === name.toLowerCase()) ??
        domains.find(
          (domain) => apiDomainName(domain.name).toLowerCase() === apiDomainName(name).toLowerCase(),
        );
      return match?.id ?? name;
    }),
    languages: item.languages ?? [],
    typeIds: (item.policy_type_id ?? []).map(String),
    selectedFields: item.selected_policy_fields?.map(selectedFieldFromRecord) ?? null,
    policyType: item.is_global ? "Global" : "Institution level",
    scope: SCOPE_FROM_API[item.guardrail_scope],
    status: item.is_active ? "Active" : "Inactive",
  };
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}
