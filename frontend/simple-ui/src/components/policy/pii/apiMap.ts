import type {
  GuardrailScope,
  PolicyRecord,
  PolicyTypeItem,
} from "../../../services/dto/schemas/policyHierarchy";
import {
  NER_MODELS,
  type DetectionMode,
  type Domain,
  type Handling,
  type MaskingPattern,
  type PiiType,
  type Policy,
  type PolicyScope,
  type PolicyType,
} from "./model";

/** Regex definitions go in custom_field, which the API rejects with fewer than three examples. */
export const MIN_REGEX_EXAMPLES = 3;

const HANDLING_TO_API: Record<Handling, string> = {
  Mask: "mask",
  Hash: "hash",
  Redact: "redact",
};

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
  name: string;
  examples: string[];
  handling: Handling;
  maskingPattern: MaskingPattern | null;
  detectionMode: DetectionMode;
  regex: string;
  nerModel: string;
}

export function policyFieldsFromDefinition(input: DefinitionFields): Record<string, unknown> {
  const handling = HANDLING_TO_API[input.handling];
  const fields: Record<string, unknown> = {
    handling,
    implementation_method: input.detectionMode === "Model" ? "model" : "regex",
    examples: input.examples,
  };
  if (input.handling === "Mask" && input.maskingPattern) {
    fields.masking_pattern = input.maskingPattern.toLowerCase();
  }
  if (input.detectionMode === "Model") {
    fields.ner_model = input.nerModel;
    fields.model_supported_field = [{ en: [{ entity_name: input.name }] }];
    return fields;
  }
  fields.custom_field = [
    {
      entity_name: input.name,
      examples: input.examples,
      regex: input.regex,
      mode: handling,
    },
  ];
  return fields;
}

export function definitionFromPolicyType(item: PolicyTypeItem): PiiType {
  const fields = item.policy_fields;
  const custom = firstRecord(fields.custom_field);
  const regex = stringValue(custom?.regex) || stringValue(fields.regex);
  const nerModel = stringValue(fields.ner_model);
  const method = stringValue(fields.implementation_method).toLowerCase();
  const detectionMode: DetectionMode =
    method === "model" || (!regex && (Boolean(nerModel) || fields.model_supported_field != null))
      ? "Model"
      : "Regex";
  const handling = handlingFromApi(fields.handling ?? custom?.mode);
  const examples = stringList(fields.examples);
  return {
    id: String(item.id),
    name: item.policy_type,
    domainId: null,
    handling,
    maskingPattern: handling === "Mask" ? maskingFromApi(fields.masking_pattern) : null,
    detectionMode,
    regex,
    nerModel: nerModel || NER_MODELS[0],
    examples: examples.length > 0 ? examples : stringList(custom?.examples),
    isDefault: false,
  };
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
      const match = domains.find((domain) => domain.name.toLowerCase() === name.toLowerCase());
      return match?.id ?? name;
    }),
    languages: [],
    typeIds: (item.policy_type_id ?? []).map(String),
    policyType: item.is_global ? "Global" : "Institution level",
    scope: SCOPE_FROM_API[item.guardrail_scope],
    status: item.is_active ? "Active" : "Inactive",
  };
}

function handlingFromApi(value: unknown): Handling {
  const text = stringValue(value).toLowerCase();
  if (text === "hash") return "Hash";
  if (text === "redact") return "Redact";
  return "Mask";
}

function maskingFromApi(value: unknown): MaskingPattern {
  return stringValue(value).toLowerCase() === "full" ? "Full" : "Partial";
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

function firstRecord(value: unknown): Record<string, unknown> | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const entry = value[0];
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
  return entry as Record<string, unknown>;
}
