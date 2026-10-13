import type {
  GuardrailScope,
  PolicyRecord,
  PolicyTypeItem,
} from "../../../services/dto/schemas/policyHierarchy";
import {
  NER_MODELS,
  domainLabel,
  type DetectionMode,
  type Domain,
  type PiiType,
  type Policy,
  type PolicyField,
  type PolicyScope,
} from "./model";

/** Regex definitions go in custom_field, which the API rejects with fewer than three examples. */
export const MIN_REGEX_EXAMPLES = 3;

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

export interface DomainEntity {
  key: string;
  policyTypeId: string;
  policyTypeName: string;
  domain: string;
  entityName: string;
  mode: PolicyField["mode"];
}

interface FieldBucket {
  custom: { entity_name: string; examples: string[]; regex: string }[];
  model: Map<string, { entity_name: string }[]>;
}

export function policyFieldsFromDefinition(input: DefinitionFields): Record<string, unknown> {
  const grouped = new Map<string, FieldBucket>();
  input.fields.forEach((field) => {
    const domain = apiDomainName(field.domain);
    const entityName = field.entityName.trim();
    if (!domain || !entityName) return;
    const bucket: FieldBucket = grouped.get(domain) ?? { custom: [], model: new Map() };
    if (field.mode === "model") {
      const language = field.language.trim() || "en";
      const entities = bucket.model.get(language) ?? [];
      if (!entities.some((entity) => entity.entity_name === entityName)) {
        entities.push({ entity_name: entityName });
      }
      bucket.model.set(language, entities);
    } else {
      bucket.custom.push({
        entity_name: entityName,
        examples: field.examples.map((example) => example.trim()).filter(Boolean),
        regex: field.regex.trim(),
      });
    }
    grouped.set(domain, bucket);
  });

  const policyFields: Record<string, unknown> = {};
  grouped.forEach((bucket, domain) => {
    const value: Record<string, unknown> = {};
    if (bucket.custom.length > 0) value.custom_field = bucket.custom;
    if (bucket.model.size > 0) {
      const entry: Record<string, { entity_name: string }[]> = {};
      bucket.model.forEach((entities, language) => {
        entry[language] = entities;
      });
      value.model_supported_field = [entry];
    }
    policyFields[domain] = value;
  });
  return policyFields;
}

function fieldsFromPolicyFields(policyFields: Record<string, unknown>): PolicyField[] {
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

function rowsFromBucket(domain: string, bucket: Record<string, unknown>): PolicyField[] {
  const rows: PolicyField[] = [];
  if (Array.isArray(bucket.custom_field)) {
    bucket.custom_field.forEach((entry) => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return;
      const record = entry as Record<string, unknown>;
      const entityName = stringValue(record.entity_name);
      if (!entityName) return;
      rows.push({
        mode: "custom",
        domain,
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
            domain,
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
  const fields = fieldsFromPolicyFields(item.policy_fields);
  const firstCustom = fields.find((field) => field.mode === "custom");
  const firstModel = fields.find((field) => field.mode === "model");
  const detectionMode: DetectionMode = firstCustom ? "Regex" : "Model";
  return {
    id: String(item.id),
    name: item.policy_type,
    domainId: null,
    handling: "Mask",
    maskingPattern: null,
    detectionMode,
    regex: firstCustom?.regex ?? "",
    nerModel: firstModel?.entityName || NER_MODELS[0],
    examples: firstCustom?.examples ?? [],
    isDefault: false,
    fields,
  };
}

/** Entity names inside a domain-filtered policy-type list. */
export function entitiesFromPolicyTypes(items: PolicyTypeItem[], domain?: string): DomainEntity[] {
  const wanted = domain ? apiDomainName(domain).toLowerCase() : "";
  return items.flatMap((item) =>
    fieldsFromPolicyFields(item.policy_fields)
      .filter((field) => field.entityName && (!wanted || field.domain.toLowerCase() === wanted))
      .map((field) => ({
        key: `${item.id}:${field.domain}:${field.entityName}`,
        policyTypeId: String(item.id),
        policyTypeName: item.policy_type,
        domain: field.domain,
        entityName: field.entityName,
        mode: field.mode,
      })),
  );
}

/** Custom regex fields for the selected policy types and domains, for the playground. */
export function detectionTypesForPolicy(policy: Policy, types: PiiType[], domains: Domain[]): PiiType[] {
  const wanted = new Set(
    policy.domainIds.map((id) => apiDomainName(domainLabel(id, domains)).toLowerCase()),
  );
  const linked = types.filter((type) => policy.typeIds.includes(type.id));
  const flattened = linked.flatMap((type) =>
    type.fields
      .filter(
        (field) =>
          field.mode === "custom" &&
          field.regex &&
          (wanted.size === 0 || wanted.has(field.domain.toLowerCase())),
      )
      .map((field) => ({
        ...type,
        id: `${type.id}:${field.domain}:${field.entityName}`,
        name: field.entityName,
        regex: field.regex,
        examples: field.examples,
        detectionMode: "Regex" as const,
        handling: "Redact" as const,
        maskingPattern: null,
        fields: [field],
      })),
  );
  if (flattened.length > 0) return flattened;
  return linked.filter((type) => type.regex);
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
    languages: [],
    typeIds: (item.policy_type_id ?? []).map(String),
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
