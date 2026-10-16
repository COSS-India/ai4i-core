import { MIN_REGEX_EXAMPLES, selectionForField } from "./apiMap";
import { regexCompiles } from "./detection";
import {
  languageLabel,
  selectedFieldKey,
  type PiiType,
  type PolicyField,
  type SelectedPolicyField,
} from "./model";

export interface TypeChoice {
  id: string;
  name: string;
  custom: SelectedPolicyField[];
  /** Model-supported fields by language code, for the policy's languages only, in their order. */
  model: [string, SelectedPolicyField[]][];
}

/** Entity names GET /pii/entities returned, by language code. A language not loaded yet is absent. */
export type DetectableEntities = Record<string, readonly string[]>;

/**
 * Fields a policy can pick: each type's custom fields, and its model-supported fields listed under
 * one of the policy's languages whose detectable entities include them. Fields stored under a domain
 * show only when that domain is chosen.
 */
export function policyFieldChoices(
  types: PiiType[],
  domainKeys: Set<string>,
  languages: string[],
  detectable: DetectableEntities,
): TypeChoice[] {
  return types
    .map((type) => {
      const seen = new Set<string>();
      const custom: SelectedPolicyField[] = [];
      const model = new Map<string, SelectedPolicyField[]>();
      type.fields.forEach((field) => {
        if (!field.entityName) return;
        if (field.domain && !domainKeys.has(field.domain.toLowerCase())) return;
        const selection = selectionForField(type.id, field);
        if (selection.language && !languages.includes(selection.language)) return;
        if (selection.language && !detectable[selection.language]?.includes(selection.entityName)) return;
        const key = selectedFieldKey(selection);
        if (seen.has(key)) return;
        seen.add(key);
        if (selection.language) {
          model.set(selection.language, [...(model.get(selection.language) ?? []), selection]);
        } else {
          custom.push(selection);
        }
      });
      const byLanguage = languages
        .filter((language) => model.has(language))
        .map((language): [string, SelectedPolicyField[]] => [language, model.get(language) ?? []]);
      return { id: type.id, name: type.name, custom, model: byLanguage };
    })
    .filter((choice) => choice.custom.length > 0 || choice.model.length > 0);
}

export function choiceKeys(choices: TypeChoice[]): string[] {
  return choices.flatMap((choice) =>
    [...choice.custom, ...choice.model.flatMap(([, fields]) => fields)].map(selectedFieldKey),
  );
}

/** Whether the type still defines this field (same source, entity and, for model fields, language). */
export function fieldDefined(field: SelectedPolicyField, types: PiiType[]): boolean {
  const type = types.find((t) => t.id === field.typeId);
  const key = selectedFieldKey(field);
  return Boolean(
    type?.fields.some((f) => f.entityName && selectedFieldKey(selectionForField(type.id, f)) === key),
  );
}

/** Why a saved pick is not among the fields the form can offer. */
export function unavailableReason(
  field: SelectedPolicyField,
  types: PiiType[],
  languages: string[],
  detectable: DetectableEntities,
): string {
  if (!fieldDefined(field, types)) return "No longer defined";
  if (field.language && !languages.includes(field.language)) {
    return `${languageLabel(field.language)} is not a supported language`;
  }
  if (field.language && !detectable[field.language]?.includes(field.entityName)) {
    return `Not detectable in ${languageLabel(field.language)}`;
  }
  return "Not in the selected domains";
}

export function fieldLabel(field: SelectedPolicyField): string {
  return field.language ? `${field.entityName} (${languageLabel(field.language)})` : field.entityName;
}

/** A custom field of the policy being edited; it belongs to that policy only. */
export interface CustomFieldDraft {
  key: string;
  entityName: string;
  examples: string[];
  regex: string;
}

export function draftFromField(key: string, field: PolicyField): CustomFieldDraft {
  return { key, entityName: field.entityName, examples: [...field.examples], regex: field.regex };
}

/** Errors keyed `${draft.key}-entity`, `-examples` and `-regex`. */
export function customDraftErrors(drafts: CustomFieldDraft[]): Record<string, string> {
  const errors: Record<string, string> = {};
  const seen = new Set<string>();
  drafts.forEach((draft) => {
    const entityName = draft.entityName.trim();
    if (!entityName) {
      errors[`${draft.key}-entity`] = "Entity name is required.";
    } else {
      const name = entityName.toLowerCase();
      if (seen.has(name)) errors[`${draft.key}-entity`] = "This policy already has this custom field.";
      seen.add(name);
    }
    if (draft.examples.filter((example) => example.trim()).length < MIN_REGEX_EXAMPLES) {
      errors[`${draft.key}-examples`] = `Add at least ${MIN_REGEX_EXAMPLES} examples.`;
    }
    if (!draft.regex.trim()) errors[`${draft.key}-regex`] = "A regex pattern is required.";
    else if (!regexCompiles(draft.regex.trim())) errors[`${draft.key}-regex`] = "Enter a valid regular expression.";
  });
  return errors;
}

/** A detectable entity the policy form adds to the policy as a model-supported field. */
export interface EntityAddition {
  language: string;
  entityName: string;
}

export function entityAdditionKey(addition: EntityAddition): string {
  return JSON.stringify([addition.language, addition.entityName]);
}

/**
 * Per policy language, in order: the entities GET /pii/entities returned that no offered type field
 * covers, in response order. Languages whose entities have not loaded are left out.
 */
export function otherDetectableEntities(
  choices: TypeChoice[],
  languages: string[],
  detectable: DetectableEntities,
): [string, string[]][] {
  return languages
    .map((language): [string, string[]] => {
      const offered = new Set(
        choices.flatMap((choice) =>
          choice.model.filter(([code]) => code === language).flatMap(([, fields]) => fields.map((f) => f.entityName)),
        ),
      );
      return [language, (detectable[language] ?? []).filter((entity) => !offered.has(entity))];
    })
    .filter(([, entities]) => entities.length > 0);
}

/** The policy's own fields: the drafts as custom fields and the entities as model-supported fields. */
export function ownPolicyFields(drafts: CustomFieldDraft[], entities: EntityAddition[]): PolicyField[] {
  return [
    ...drafts.map(
      (draft): PolicyField => ({
        mode: "custom",
        domain: "",
        entityName: draft.entityName.trim(),
        examples: draft.examples.map((example) => example.trim()).filter(Boolean),
        regex: draft.regex.trim(),
        language: "en",
      }),
    ),
    ...entities.map(
      (entity): PolicyField => ({
        mode: "model",
        domain: "",
        entityName: entity.entityName,
        examples: [],
        regex: "",
        language: entity.language,
      }),
    ),
  ];
}
