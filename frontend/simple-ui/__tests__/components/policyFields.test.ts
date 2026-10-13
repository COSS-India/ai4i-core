import {
  apiDomainName,
  definitionFromPolicyType,
  detectionTypesForPolicy,
  entityNamesForPolicy,
  policyFieldsFromDefinition,
} from "../../src/components/policy/pii/apiMap";
import type { Domain, PiiType, Policy, PolicyField } from "../../src/components/policy/pii/model";

const studentId: PolicyField = {
  mode: "custom",
  domain: "",
  entityName: "STUDENT_ID",
  examples: ["EDU20231234", "STU2024567", "SCH12345"],
  regex: "\\b[A-Z]{2,5}\\d{4,10}\\b",
  language: "en",
};

const emailModel: PolicyField = {
  mode: "model",
  domain: "",
  entityName: "EMAIL_ADDRESS",
  examples: [],
  regex: "",
  language: "en",
};

const financePolicy = (typeId: string): Policy => ({
  id: "1",
  policyId: "SPP-1",
  name: "Finance",
  description: "",
  subcategoryId: "1",
  domainIds: ["dom-finance"],
  languages: [],
  typeIds: [typeId],
  entities: [],
  policyType: "Global",
  scope: "Both",
  status: "Active",
});

const domains: Domain[] = [
  { id: "dom-finance", name: "Finance / Banking", description: "", isDefault: true },
];

describe("policy type fields", () => {
  it("writes custom rows and model-supported entities at the top level", () => {
    const fields = policyFieldsFromDefinition({
      fields: [studentId, emailModel, { ...emailModel, language: "hi" }],
    });

    expect(fields).toEqual({
      custom_field: [
        {
          entity_name: "STUDENT_ID",
          examples: ["EDU20231234", "STU2024567", "SCH12345"],
          regex: "\\b[A-Z]{2,5}\\d{4,10}\\b",
        },
      ],
      model_supported_field: [
        { en: [{ entity_name: "EMAIL_ADDRESS" }], hi: [{ entity_name: "EMAIL_ADDRESS" }] },
      ],
    });
  });

  it("reads the flat shape back without a domain", () => {
    const definition = definitionFromPolicyType({
      id: 7,
      policy_type: "PII",
      policy_fields: policyFieldsFromDefinition({ fields: [studentId, emailModel] }),
    });

    expect(definition.name).toBe("PII");
    expect(definition.fields.map((field) => [field.entityName, field.mode, field.domain])).toEqual([
      ["STUDENT_ID", "custom", ""],
      ["EMAIL_ADDRESS", "model", ""],
    ]);
  });

  it("still reads rows keyed by domain", () => {
    const definition = definitionFromPolicyType({
      id: 7,
      policy_type: "PII",
      policy_fields: {
        Education: {
          custom_field: [
            { entity_name: "STUDENT_ID", examples: studentId.examples, regex: studentId.regex },
          ],
        },
        Finance: { model_supported_field: [{ en: [{ entity_name: "EMAIL_ADDRESS" }] }] },
      },
    });

    expect(definition.fields.map((field) => [field.entityName, field.domain])).toEqual([
      ["STUDENT_ID", "Education"],
      ["EMAIL_ADDRESS", "Finance"],
    ]);
    expect(apiDomainName("Finance / Banking")).toBe("Finance");
  });

  it("keeps playground detection inside the policy domain and still lists model entities", () => {
    const type = definitionFromPolicyType({
      id: 7,
      policy_type: "PII",
      policy_fields: {
        Education: {
          custom_field: [
            { entity_name: "STUDENT_ID", examples: studentId.examples, regex: studentId.regex },
          ],
        },
        Finance: { model_supported_field: [{ en: [{ entity_name: "EMAIL_ADDRESS" }] }] },
      },
    });
    const policy = financePolicy(type.id);

    expect(detectionTypesForPolicy(policy, [type as PiiType], domains)).toEqual([]);
    expect(entityNamesForPolicy(policy, [type], domains)).toEqual(["EMAIL_ADDRESS"]);
  });

  it("applies flat fields to every policy domain", () => {
    const type = definitionFromPolicyType({
      id: 8,
      policy_type: "PII",
      policy_fields: policyFieldsFromDefinition({ fields: [studentId, emailModel] }),
    });
    const policy = financePolicy(type.id);

    expect(detectionTypesForPolicy(policy, [type], domains).map((row) => row.name)).toEqual([
      "STUDENT_ID",
    ]);
    expect(entityNamesForPolicy(policy, [type], domains)).toEqual(["STUDENT_ID", "EMAIL_ADDRESS"]);
  });

  it("applies only the picked entities when a policy has picks", () => {
    const type = definitionFromPolicyType({
      id: 8,
      policy_type: "PII",
      policy_fields: policyFieldsFromDefinition({ fields: [studentId, emailModel] }),
    });
    const policy: Policy = {
      ...financePolicy(type.id),
      entities: [{ typeId: type.id, entityName: "EMAIL_ADDRESS" }],
    };

    expect(entityNamesForPolicy(policy, [type], domains)).toEqual(["EMAIL_ADDRESS"]);
    expect(detectionTypesForPolicy(policy, [type], domains)).toEqual([]);
  });
});
