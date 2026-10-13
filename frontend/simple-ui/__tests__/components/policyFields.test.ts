import {
  apiDomainName,
  definitionFromPolicyType,
  detectionTypesForPolicy,
  entitiesFromPolicyTypes,
  entityNamesForPolicy,
  policyFieldsFromDefinition,
} from "../../src/components/policy/pii/apiMap";
import type { Domain, PiiType, Policy, PolicyField } from "../../src/components/policy/pii/model";

const educationCustom: PolicyField = {
  mode: "custom",
  domain: "Education",
  entityName: "STUDENT_ID",
  examples: ["EDU20231234", "STU2024567", "SCH12345"],
  regex: "\\b[A-Z]{2,5}\\d{4,10}\\b",
  language: "en",
};

const financeModel: PolicyField = {
  mode: "model",
  domain: "Finance / Banking",
  entityName: "EMAIL_ADDRESS",
  examples: [],
  regex: "",
  language: "en",
};

describe("policy type fields", () => {
  it("stores custom rows and model-supported entity names under domain keys", () => {
    const fields = policyFieldsFromDefinition({ fields: [educationCustom, financeModel] });

    expect(fields).toEqual({
      Education: {
        custom_field: [
          {
            entity_name: "STUDENT_ID",
            examples: ["EDU20231234", "STU2024567", "SCH12345"],
            regex: "\\b[A-Z]{2,5}\\d{4,10}\\b",
          },
        ],
      },
      Finance: {
        model_supported_field: [{ en: [{ entity_name: "EMAIL_ADDRESS" }] }],
      },
    });
    expect(apiDomainName("Finance / Banking")).toBe("Finance");
  });

  it("reads domain-filtered entity names back from a policy type", () => {
    const item = {
      id: 7,
      policy_type: "PII",
      policy_fields: policyFieldsFromDefinition({ fields: [educationCustom, financeModel] }),
    };

    const definition = definitionFromPolicyType(item);
    expect(definition.name).toBe("PII");
    expect(definition.fields.map((field) => field.entityName)).toEqual(["STUDENT_ID", "EMAIL_ADDRESS"]);

    const education = entitiesFromPolicyTypes([item], "education");
    expect(education.map((entity) => entity.entityName)).toEqual(["STUDENT_ID"]);
    expect(education[0]?.policyTypeId).toBe("7");
  });

  it("keeps playground detection inside the policy domain and still lists model entities", () => {
    const item = {
      id: 7,
      policy_type: "PII",
      policy_fields: policyFieldsFromDefinition({ fields: [educationCustom, financeModel] }),
    };
    const type = definitionFromPolicyType(item);
    const domains: Domain[] = [
      { id: "dom-finance", name: "Finance / Banking", description: "", isDefault: true },
    ];
    const policy: Policy = {
      id: "1",
      policyId: "SPP-1",
      name: "Finance",
      description: "",
      subcategoryId: "1",
      domainIds: ["dom-finance"],
      languages: [],
      typeIds: [type.id],
      policyType: "Global",
      scope: "Both",
      status: "Active",
    };

    expect(detectionTypesForPolicy(policy, [type as PiiType], domains)).toEqual([]);
    expect(entityNamesForPolicy(policy, [type], domains)).toEqual(["EMAIL_ADDRESS"]);
  });

  it("stores a policy field that has no domain without showing a domain name", () => {
    const written = policyFieldsFromDefinition({
      fields: [{ ...educationCustom, domain: "" }],
    });
    const read = definitionFromPolicyType({
      id: 1,
      policy_type: "PII",
      policy_fields: written,
    });
    expect(read.fields[0]?.domain).toBe("");
    expect(read.fields[0]?.entityName).toBe("STUDENT_ID");
  });
});
