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
          (wanted.size === 0 ||
            wanted.has(field.domain.toLowerCase()) ||
            field.domain === ""),
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
  return flattened;
}

/** Entity names for a policy's types in its domains, including model-supported rows. */
export function entityNamesForPolicy(policy: Policy, types: PiiType[], domains: Domain[]): string[] {
  const wanted = new Set(
    policy.domainIds.map((id) => apiDomainName(domainLabel(id, domains)).toLowerCase()),
  );
  const names = types
    .filter((type) => policy.typeIds.includes(type.id))
    .flatMap((type) =>
      type.fields
        .filter(
          (field) =>
            field.entityName &&
            (wanted.size === 0 ||
              wanted.has(field.domain.toLowerCase()) ||
              field.domain === ""),
        )
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
