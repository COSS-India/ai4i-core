import {
  definitionFromPolicyType,
  entityNamesForPolicy,
  policyCreatePayload,
  policyFieldsFromDefinition,
  policyFromRecord,
  policyUpdatePayload,
  selectionForField,
} from "../../src/components/policy/pii/apiMap";
import {
  choiceKeys,
  customDraftErrors,
  draftFromField,
  entityAdditionKey,
  fieldLabel,
  otherDetectableEntities,
  ownPolicyFields,
  policyFieldChoices,
  unavailableReason,
  type CustomFieldDraft,
} from "../../src/components/policy/pii/fieldSelection";
import {
  isPolicyOwnedType,
  policyOwnedType,
  policyOwnedTypeName,
  sharedTypes,
} from "../../src/components/policy/pii/policyCustomFields";
import {
  DEFAULT_POLICY_LANGUAGES,
  editableLanguages,
  languageLabel,
  parseSelectedFieldKey,
  selectedFieldKey,
  type Domain,
  type PiiType,
  type PolicyField,
  type PolicyInput,
  type SelectedPolicyField,
} from "../../src/components/policy/pii/model";
import {
  policyRecordSchema,
  type PolicyRecord,
} from "../../src/services/dto/schemas/policyHierarchy";

jest.mock("../../src/services/piiService", () => ({
  piiService: { getSupportedEntities: jest.fn() },
}));

const domains: Domain[] = [
  { id: "dom-education", name: "Education", description: "" },
  { id: "dom-finance", name: "Finance / Banking", description: "" },
];

const custom = (entityName: string, domain = ""): PolicyField => ({
  mode: "custom",
  domain,
  entityName,
  examples: ["a", "b", "c"],
  regex: "\\d+",
  language: "en",
});
const model = (entityName: string, language: string, domain = ""): PolicyField => ({
  mode: "model",
  domain,
  entityName,
  examples: [],
  regex: "",
  language,
});

const piiType: PiiType = definitionFromPolicyType({
  id: 1,
  policy_type: "PII",
  policy_fields: policyFieldsFromDefinition({
    fields: [custom("STUDENT_ID"), model("EMAIL_ADDRESS", "en"), model("IN_PAN", "hi"), model("EMAIL_ADDRESS", "hi")],
  }),
});

const customPick: SelectedPolicyField = { source: "custom_field", typeId: "1", entityName: "STUDENT_ID", language: null };
const emailEn: SelectedPolicyField = { source: "model_supported_field", typeId: "1", entityName: "EMAIL_ADDRESS", language: "en" };
const panHi: SelectedPolicyField = { source: "model_supported_field", typeId: "1", entityName: "IN_PAN", language: "hi" };

const record = (overrides: Partial<PolicyRecord> = {}): PolicyRecord => ({
  id: 5,
  policy_id: "PID-0005",
  name: "Student Records",
  description: null,
  domain: ["Education"],
  guardrail_scope: "both",
  is_global: true,
  sub_category_id: 10,
  is_active: true,
  policy_type_id: [1],
  ...overrides,
});

const input: PolicyInput = {
  name: "Student Records",
  description: "",
  subCategoryId: "10",
  domainIds: ["dom-education"],
  languages: ["en", "hi"],
  typeIds: ["1"],
  selectedFields: [customPick, emailEn, panHi],
  ownFields: [],
  scope: "Both",
};

describe("policy record mapping", () => {
  it("restores saved language codes and selected fields", () => {
    const policy = policyFromRecord(
      record({
        languages: ["en", "hi"],
        selected_policy_fields: [
          { source: "custom_field", policy_type_id: 1, entity_name: "STUDENT_ID", language: null },
          { source: "model_supported_field", policy_type_id: 1, entity_name: "IN_PAN", language: "hi" },
        ],
      }),
      domains,
    );
    expect(policy.languages).toEqual(["en", "hi"]);
    expect(policy.selectedFields).toEqual([customPick, panHi]);
  });

  it("maps a legacy policy (null columns) to no languages and no picks", () => {
    const policy = policyFromRecord(record({ languages: null, selected_policy_fields: null }), domains);
    expect(policy.languages).toEqual([]);
    expect(policy.selectedFields).toBeNull();
  });

  it("treats a response without the new keys like a legacy policy", () => {
    const parsed = policyRecordSchema.parse(record());
    expect(policyFromRecord(parsed, domains).selectedFields).toBeNull();
  });

  it("keeps the new keys through the response schema", () => {
    const parsed = policyRecordSchema.parse(
      record({
        languages: ["ta"],
        selected_policy_fields: [{ source: "custom_field", policy_type_id: 1, entity_name: "STUDENT_ID" }],
      }),
    );
    expect(parsed.languages).toEqual(["ta"]);
    expect(parsed.selected_policy_fields).toHaveLength(1);
  });

  it("rejects a selection with an unknown source", () => {
    expect(() =>
      policyRecordSchema.parse(
        record({ selected_policy_fields: [{ source: "raw_entity", policy_type_id: 1, entity_name: "X" } as never] }),
      ),
    ).toThrow();
  });
});

describe("reload persistence", () => {
  it("returns what was saved after a create and a reload", () => {
    const payload = policyCreatePayload(input, domains);
    expect(payload).not.toBeNull();
    // What platform-core stores and returns: the same selections, custom fields with a null language.
    const saved = record({
      languages: payload?.languages ?? null,
      selected_policy_fields: (payload?.selected_policy_fields ?? []).map((field) => ({
        language: null,
        ...field,
      })),
    });
    const reloaded = policyFromRecord(policyRecordSchema.parse(JSON.parse(JSON.stringify(saved))), domains);
    expect(reloaded.languages).toEqual(input.languages);
    expect(reloaded.selectedFields).toEqual(input.selectedFields);
  });
});

describe("selection payloads", () => {
  it("sends custom fields without a language and model fields with one", () => {
    expect(policyCreatePayload(input, domains)?.selected_policy_fields).toEqual([
      { source: "custom_field", policy_type_id: 1, entity_name: "STUDENT_ID" },
      { source: "model_supported_field", policy_type_id: 1, language: "en", entity_name: "EMAIL_ADDRESS" },
      { source: "model_supported_field", policy_type_id: 1, language: "hi", entity_name: "IN_PAN" },
    ]);
  });

  it("leaves selected_policy_fields out of an update that keeps a legacy policy's picks", () => {
    const payload = policyUpdatePayload({ ...input, selectedFields: null }, domains);
    expect(payload).not.toHaveProperty("selected_policy_fields");
    expect(payload?.languages).toEqual(["en", "hi"]);
  });

  it("leaves languages out when none are chosen", () => {
    expect(policyUpdatePayload({ ...input, languages: [] }, domains)).not.toHaveProperty("languages");
  });

  it("refuses picks with an invalid type id or a model field without a language", () => {
    expect(policyCreatePayload({ ...input, selectedFields: [{ ...customPick, typeId: "pii-local" }] }, domains)).toBeNull();
    expect(policyUpdatePayload({ ...input, selectedFields: [{ ...emailEn, language: null }] }, domains)).toBeNull();
  });
});

describe("creating a policy from GET /pii/entities picks", () => {
  const fields = ownPolicyFields([], [
    { language: "en", entityName: "EMAIL_ADDRESS" },
    { language: "en", entityName: "PERSON" },
  ]);

  it("writes the picks as English model_supported_field entries of the new policy type", () => {
    expect(policyFieldsFromDefinition({ fields })).toEqual({
      model_supported_field: [{ en: [{ entity_name: "EMAIL_ADDRESS" }, { entity_name: "PERSON" }] }],
    });
  });

  it("links only the returned policy type id and selects the same entities", () => {
    const payload = policyCreatePayload(
      {
        ...input,
        typeIds: ["42"],
        selectedFields: fields.map((field) => selectionForField("42", field)),
        ownFields: fields,
      },
      domains,
    );
    expect(payload?.policy_type_id).toEqual([42]);
    expect(payload?.selected_policy_fields).toEqual([
      { source: "model_supported_field", policy_type_id: 42, language: "en", entity_name: "EMAIL_ADDRESS" },
      { source: "model_supported_field", policy_type_id: 42, language: "en", entity_name: "PERSON" },
    ]);
  });
});

describe("language-dependent field choices", () => {
  const all = new Set<string>();
  const detectable = { en: ["EMAIL_ADDRESS", "PERSON"], hi: ["IN_PAN", "EMAIL_ADDRESS"] };

  it("lists custom fields always and model fields only for the chosen languages, in their order", () => {
    const [choice] = policyFieldChoices([piiType], all, ["hi"], detectable);
    expect(choice.custom).toEqual([customPick]);
    expect(choice.model).toEqual([
      ["hi", [panHi, { ...emailEn, language: "hi" }]],
    ]);
    const both = policyFieldChoices([piiType], all, ["hi", "en"], detectable);
    expect(both[0].model.map(([language]) => language)).toEqual(["hi", "en"]);
  });

  it("lists a model field only when /pii/entities returns it for that language", () => {
    const [choice] = policyFieldChoices([piiType], all, ["en", "hi"], { en: ["PERSON"], hi: ["IN_PAN"] });
    expect(choice.model).toEqual([["hi", [panHi]]]);
    expect(choice.custom).toEqual([customPick]);
  });

  it("lists no model field for a language whose entities have not loaded", () => {
    const [choice] = policyFieldChoices([piiType], all, ["en", "hi"], { hi: ["IN_PAN", "EMAIL_ADDRESS"] });
    expect(choice.model.map(([language]) => language)).toEqual(["hi"]);
  });

  it("changes the model fields as the language selection changes", () => {
    const entities = (languages: string[]) =>
      choiceKeys(policyFieldChoices([piiType], all, languages, detectable))
        .map(parseSelectedFieldKey)
        .filter((field) => field.language)
        .map(fieldLabel);
    expect(entities(["en"])).toEqual(["EMAIL_ADDRESS (English)"]);
    expect(entities(["hi"])).toEqual(["IN_PAN (Hindi)", "EMAIL_ADDRESS (Hindi)"]);
    expect(entities(["ta"])).toEqual([]);
  });

  it("offers only custom fields before a language is chosen", () => {
    expect(choiceKeys(policyFieldChoices([piiType], all, [], detectable))).toEqual([selectedFieldKey(customPick)]);
  });

  it("drops a type with no field for the chosen languages", () => {
    const modelOnly = definitionFromPolicyType({
      id: 2,
      policy_type: "Model only",
      policy_fields: policyFieldsFromDefinition({ fields: [model("PERSON", "en")] }),
    });
    expect(policyFieldChoices([modelOnly], all, ["hi"], detectable)).toEqual([]);
  });

  it("shows fields stored under a domain only when that domain is chosen", () => {
    const keyed = { ...piiType, id: "3", fields: [custom("ACCOUNT_NO", "Finance"), custom("STUDENT_ID", "Education")] };
    const keys = choiceKeys(policyFieldChoices([keyed], new Set(["education"]), ["en"], detectable));
    expect(keys.map((key) => parseSelectedFieldKey(key).entityName)).toEqual(["STUDENT_ID"]);
  });

  it("lists a field defined twice once", () => {
    const repeated = { ...piiType, fields: [custom("STUDENT_ID"), custom("STUDENT_ID")] };
    expect(choiceKeys(policyFieldChoices([repeated], all, ["en"], detectable))).toHaveLength(1);
  });

  it("never offers anything that is not a field of a linked type", () => {
    const keys = choiceKeys(policyFieldChoices([piiType], all, ["en", "hi"], { en: ["CREDIT_CARD", "EMAIL_ADDRESS"], hi: ["IN_PAN"] }));
    keys.forEach((key) => {
      const field = parseSelectedFieldKey(key);
      expect(field.typeId).toBe("1");
      expect(piiType.fields.some((f) => f.entityName === field.entityName)).toBe(true);
    });
  });
});

describe("unavailable saved selections", () => {
  const detectable = { en: ["EMAIL_ADDRESS"], hi: ["IN_PAN"], ta: [] };

  it("marks a field the type no longer defines", () => {
    expect(unavailableReason({ ...customPick, entityName: "AADHAAR" }, [piiType], ["en"], detectable)).toBe("No longer defined");
    expect(unavailableReason({ ...customPick, typeId: "99" }, [piiType], ["en"], detectable)).toBe("No longer defined");
    expect(unavailableReason({ ...panHi, language: "ta" }, [piiType], ["ta"], detectable)).toBe("No longer defined");
  });

  it("explains a model field whose language was removed", () => {
    expect(unavailableReason(panHi, [piiType], ["en"], detectable)).toBe("Hindi is not a supported language");
  });

  it("explains a model field /pii/entities does not return for its language", () => {
    expect(unavailableReason(panHi, [piiType], ["hi"], { hi: ["PERSON"] })).toBe("Not detectable in Hindi");
  });

  it("explains a field outside the chosen domains", () => {
    const keyed = { ...piiType, fields: [custom("ACCOUNT_NO", "Finance")] };
    const pick = { ...customPick, entityName: "ACCOUNT_NO" };
    expect(unavailableReason(pick, [keyed], ["en"], detectable)).toBe("Not in the selected domains");
  });

  it("labels model fields with their language", () => {
    expect(fieldLabel(panHi)).toBe("IN_PAN (Hindi)");
    expect(fieldLabel(customPick)).toBe("STUDENT_ID");
  });
});

describe("custom fields added from the policy form", () => {
  const draft = (overrides: Partial<CustomFieldDraft> = {}): CustomFieldDraft => ({
    key: "custom-1",
    entityName: "ROLL_NO",
    examples: ["R-1", "R-2", "R-3"],
    regex: "R-\\d+",
    ...overrides,
  });

  it("accepts a complete draft", () => {
    expect(customDraftErrors([draft()])).toEqual({});
  });

  it("requires an entity name, three examples and a valid regex", () => {
    expect(customDraftErrors([draft({ entityName: " ", examples: ["a", " "], regex: "(" })])).toEqual({
      "custom-1-entity": "Entity name is required.",
      "custom-1-examples": "Add at least 3 examples.",
      "custom-1-regex": "Enter a valid regular expression.",
    });
    expect(customDraftErrors([draft({ regex: "  " })])["custom-1-regex"]).toBe("A regex pattern is required.");
  });

  it("rejects a custom field another draft of the policy already adds", () => {
    expect(customDraftErrors([draft(), draft({ key: "custom-2", entityName: " roll_no " })])).toEqual({
      "custom-2-entity": "This policy already has this custom field.",
    });
  });

  it("allows a custom field named like a field of a shared type", () => {
    expect(customDraftErrors([draft({ entityName: "STUDENT_ID" })])).toEqual({});
  });

  it("turns drafts and checked entities into the policy's own fields, trimmed", () => {
    expect(
      ownPolicyFields(
        [draft({ entityName: " ROLL_NO ", examples: [" R-1", "R-2", "R-3", " "] })],
        [{ language: "hi", entityName: "URL" }],
      ),
    ).toEqual([
      { mode: "custom", domain: "", entityName: "ROLL_NO", examples: ["R-1", "R-2", "R-3"], regex: "R-\\d+", language: "en" },
      { mode: "model", domain: "", entityName: "URL", examples: [], regex: "", language: "hi" },
    ]);
  });

  it("round-trips a saved custom field back into a draft", () => {
    const [field] = ownPolicyFields([draft()], []);
    expect(draftFromField("custom-9", field)).toEqual({ ...draft(), key: "custom-9" });
  });
});

describe("types owned by a policy", () => {
  const owned: PiiType = { ...piiType, id: "9", name: policyOwnedTypeName("Student Records") };

  it("names the type after the policy, ignoring case", () => {
    expect(policyOwnedTypeName(" Student Records ")).toBe(policyOwnedTypeName("student records"));
    expect(isPolicyOwnedType(owned)).toBe(true);
    expect(isPolicyOwnedType(piiType)).toBe(false);
  });

  it("keeps long names within the 100-character type name limit and apart", () => {
    const a = policyOwnedTypeName(`${"x".repeat(100)}a`);
    const b = policyOwnedTypeName(`${"x".repeat(100)}b`);
    expect(a.length).toBeLessThanOrEqual(100);
    expect(isPolicyOwnedType({ name: a })).toBe(true);
    expect(a).not.toBe(b);
  });

  it("leaves owned types out of the shared list and finds the policy's own", () => {
    expect(sharedTypes([piiType, owned])).toEqual([piiType]);
    expect(policyOwnedType({ typeIds: ["1", "9"] }, [piiType, owned])).toBe(owned);
    expect(policyOwnedType({ typeIds: ["1"] }, [piiType, owned])).toBeUndefined();
  });

  it("does not offer another policy's own fields as choices", () => {
    const choices = policyFieldChoices(sharedTypes([piiType, owned]), new Set(), ["en"], { en: ["EMAIL_ADDRESS"] });
    expect(choices.map((choice) => choice.id)).toEqual(["1"]);
  });
});

describe("detectable entities no type offers", () => {
  const detectable = { en: ["PERSON", "EMAIL_ADDRESS", "URL"], hi: ["IN_PAN", "URL"], ta: [] };

  it("lists, per language, the returned entities not already offered under a type", () => {
    const choices = policyFieldChoices([piiType], new Set(), ["en", "hi", "ta"], detectable);
    expect(otherDetectableEntities(choices, ["en", "hi", "ta"], detectable)).toEqual([
      ["en", ["PERSON", "URL"]],
      ["hi", ["URL"]],
    ]);
  });

  it("follows the language selection and skips languages not loaded", () => {
    const choices = policyFieldChoices([piiType], new Set(), ["hi", "te"], detectable);
    expect(otherDetectableEntities(choices, ["hi", "te"], detectable)).toEqual([["hi", ["URL"]]]);
  });

  it("keys an entity by language", () => {
    expect(entityAdditionKey({ language: "en", entityName: "URL" })).not.toBe(
      entityAdditionKey({ language: "hi", entityName: "URL" }),
    );
  });
});

describe("selection identity", () => {
  it("round-trips through its key, including entity names with the separator", () => {
    const odd: SelectedPolicyField = { ...emailEn, entityName: "A::B" };
    expect(parseSelectedFieldKey(selectedFieldKey(odd))).toEqual(odd);
    expect(parseSelectedFieldKey(selectedFieldKey(customPick))).toEqual(customPick);
  });

  it("keeps the same entity in two languages apart", () => {
    expect(selectedFieldKey(emailEn)).not.toBe(selectedFieldKey({ ...emailEn, language: "hi" }));
  });

  it("shows unknown language codes as-is", () => {
    expect(languageLabel("hi")).toBe("Hindi");
    expect(languageLabel("brx")).toBe("brx");
  });
});

describe("entity names a policy applies", () => {
  const policy = {
    ...policyFromRecord(record(), domains),
    languages: ["hi"],
  };

  it("applies every field of the linked types for a legacy policy", () => {
    expect(entityNamesForPolicy(policy, [piiType], domains)).toEqual(["STUDENT_ID", "EMAIL_ADDRESS", "IN_PAN"]);
  });

  it("applies a model pick only in its language", () => {
    const picked = { ...policy, selectedFields: [{ ...emailEn, language: "hi" }] };
    expect(entityNamesForPolicy(picked, [piiType], domains)).toEqual(["EMAIL_ADDRESS"]);
    const otherLanguage = { ...policy, selectedFields: [panHi] };
    expect(entityNamesForPolicy(otherLanguage, [piiType], domains)).toEqual(["IN_PAN"]);
  });
});

describe("editing a policy the API returns without languages", () => {
  it("keeps saved languages as they are", () => {
    expect(editableLanguages({ languages: ["hi", "ta"] })).toEqual({ languages: ["hi", "ta"], prefilled: false });
  });

  it("starts on the default languages and flags them as prefilled", () => {
    const result = editableLanguages({ languages: [] });
    expect(result).toEqual({ languages: ["en"], prefilled: true });
    result.languages.push("hi");
    expect(DEFAULT_POLICY_LANGUAGES).toEqual(["en"]);
  });

  it("can be saved without picking languages again, keeping its linked types and every-field behavior", () => {
    const policy = policyFromRecord(policyRecordSchema.parse(record()), domains);
    const { languages } = editableLanguages(policy);
    const payload = policyUpdatePayload(
      { ...input, languages, typeIds: policy.typeIds, selectedFields: policy.selectedFields },
      domains,
    );
    expect(payload).toMatchObject({ languages: ["en"], policy_type_id: [1] });
    expect(payload).not.toHaveProperty("selected_policy_fields");
  });
});

describe("GET /pii/entities cache", () => {
  function load() {
    let loadModelEntities!: typeof import("../../src/components/policy/pii/modelEntities").loadModelEntities;
    let getSupportedEntities!: jest.Mock;
    jest.isolateModules(() => {
      ({ loadModelEntities } = jest.requireActual("../../src/components/policy/pii/modelEntities"));
      ({ getSupportedEntities } = jest.requireMock("../../src/services/piiService").piiService);
    });
    getSupportedEntities.mockReset();
    return { loadModelEntities, getSupportedEntities };
  }

  it("requests each language code once", async () => {
    const { loadModelEntities, getSupportedEntities } = load();
    getSupportedEntities.mockImplementation((language: string) => Promise.resolve([`${language}-ENTITY`]));
    await expect(loadModelEntities("hi")).resolves.toEqual(["hi-ENTITY"]);
    await expect(loadModelEntities("hi")).resolves.toEqual(["hi-ENTITY"]);
    await expect(loadModelEntities("ta")).resolves.toEqual(["ta-ENTITY"]);
    expect(getSupportedEntities.mock.calls).toEqual([["hi"], ["ta"]]);
  });

  it("retries a language whose request failed", async () => {
    const { loadModelEntities, getSupportedEntities } = load();
    getSupportedEntities.mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce(["IN_PAN"]);
    await expect(loadModelEntities("hi")).rejects.toThrow("down");
    await expect(loadModelEntities("hi")).resolves.toEqual(["IN_PAN"]);
    expect(getSupportedEntities).toHaveBeenCalledTimes(2);
  });
});
