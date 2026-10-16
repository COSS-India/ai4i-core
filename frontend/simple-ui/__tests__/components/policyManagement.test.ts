import {
  DEFAULT_IS_GLOBAL,
  policyCreatePayload,
  policyUpdatePayload,
} from "../../src/components/policy/pii/apiMap";
import {
  filterPolicies,
  policyEffective,
  policyParentActive,
  subcategoriesForCategory,
  subcategoryAfterCategoryChange,
  type Domain,
  type Policy,
  type PolicyCategory,
  type PolicyInput,
  type PolicySubcategory,
} from "../../src/components/policy/pii/model";

const categories: PolicyCategory[] = [
  { id: "1", name: "Security & Privacy", description: "", status: "Active" },
  { id: "2", name: "Service Routing", description: "", status: "Inactive" },
];

const subcategories: PolicySubcategory[] = [
  { id: "10", categoryId: "1", name: "PII Guardrails", description: "", status: "Active" },
  { id: "11", categoryId: "1", name: "Content Safety", description: "", status: "Inactive" },
  { id: "20", categoryId: "2", name: "Rate Limiting", description: "", status: "Active" },
];

const domains: Domain[] = [
  { id: "dom-education", name: "Education", description: "" },
  { id: "dom-finance", name: "Finance / Banking", description: "" },
];

function policy(id: string, name: string, subcategoryId: string, domainIds: string[] = []): Policy {
  return {
    id,
    policyId: `SPP-${id}`,
    name,
    description: "",
    subcategoryId,
    domainIds,
    languages: [],
    typeIds: [],
    selectedFields: null,
    policyType: "Global",
    scope: "Both",
    status: "Active",
  };
}

const policies: Policy[] = [
  policy("1", "Student Records", "10", ["dom-education"]),
  policy("2", "Card Data", "10", ["dom-finance"]),
  policy("3", "Toxicity", "11"),
  policy("4", "Burst Limit", "20"),
];

const noFilters = { search: "", domainId: "", categoryId: "", subcategoryId: "" };

describe("global policy listing", () => {
  it("lists policies from every category and sub-category when no filter is set", () => {
    expect(filterPolicies(policies, noFilters, subcategories).map((p) => p.id)).toEqual([
      "1",
      "2",
      "3",
      "4",
    ]);
  });

  it("filters by category through each policy's sub-category", () => {
    const rows = filterPolicies(policies, { ...noFilters, categoryId: "1" }, subcategories);
    expect(rows.map((p) => p.id)).toEqual(["1", "2", "3"]);
  });

  it("filters by sub-category", () => {
    const rows = filterPolicies(policies, { ...noFilters, subcategoryId: "11" }, subcategories);
    expect(rows.map((p) => p.id)).toEqual(["3"]);
  });

  it("combines search, domain, category, and sub-category", () => {
    const rows = filterPolicies(
      policies,
      { search: "card", domainId: "dom-finance", categoryId: "1", subcategoryId: "10" },
      subcategories,
    );
    expect(rows.map((p) => p.id)).toEqual(["2"]);
    expect(
      filterPolicies(policies, { ...noFilters, search: "card", categoryId: "2" }, subcategories),
    ).toEqual([]);
  });
});

describe("category and sub-category selection", () => {
  it("offers only the sub-categories under the selected category", () => {
    expect(subcategoriesForCategory(subcategories, "1").map((s) => s.id)).toEqual(["10", "11"]);
    expect(subcategoriesForCategory(subcategories, "2").map((s) => s.id)).toEqual(["20"]);
  });

  it("offers every sub-category when no category is selected", () => {
    expect(subcategoriesForCategory(subcategories, "")).toHaveLength(3);
  });

  it("keeps the sub-category only when it belongs to the new category", () => {
    expect(subcategoryAfterCategoryChange(subcategories, "10", "1")).toBe("10");
    expect(subcategoryAfterCategoryChange(subcategories, "10", "2")).toBe("");
    expect(subcategoryAfterCategoryChange(subcategories, "10", "")).toBe("");
    expect(subcategoryAfterCategoryChange(subcategories, "", "1")).toBe("");
  });
});

describe("policy payloads", () => {
  const input: PolicyInput = {
    name: "Card Data",
    description: "  Masks card numbers.  ",
    subCategoryId: "11",
    domainIds: ["dom-finance"],
    languages: ["en"],
    typeIds: ["3", "7"],
    selectedFields: [
      { source: "custom_field", typeId: "3", entityName: "CREDIT_CARD", language: null },
      { source: "model_supported_field", typeId: "7", entityName: "EMAIL_ADDRESS", language: "en" },
    ],
    ownFields: [],
    scope: "Input requests",
  };

  it("creates in the selected sub-category with the default is_global", () => {
    expect(policyCreatePayload(input, domains)).toEqual({
      name: "Card Data",
      description: "Masks card numbers.",
      domain: ["Finance / Banking"],
      guardrail_scope: "input",
      is_global: DEFAULT_IS_GLOBAL,
      sub_category_id: 11,
      policy_type_id: [3, 7],
      languages: ["en"],
      selected_policy_fields: [
        { source: "custom_field", policy_type_id: 3, entity_name: "CREDIT_CARD" },
        { source: "model_supported_field", policy_type_id: 7, language: "en", entity_name: "EMAIL_ADDRESS" },
      ],
    });
    expect(DEFAULT_IS_GLOBAL).toBe(true);
  });

  it("sends a blank description as null", () => {
    expect(policyCreatePayload({ ...input, description: "   " }, domains)?.description).toBeNull();
  });

  it("updates the sub-category from the form and leaves is_global and name untouched", () => {
    const payload = policyUpdatePayload({ ...input, subCategoryId: "20", scope: "Both" }, domains);
    expect(payload).toEqual({
      description: "Masks card numbers.",
      domain: ["Finance / Banking"],
      guardrail_scope: "both",
      sub_category_id: 20,
      policy_type_id: [3, 7],
      languages: ["en"],
      selected_policy_fields: [
        { source: "custom_field", policy_type_id: 3, entity_name: "CREDIT_CARD" },
        { source: "model_supported_field", policy_type_id: 7, language: "en", entity_name: "EMAIL_ADDRESS" },
      ],
    });
    expect(payload).not.toHaveProperty("is_global");
    expect(payload).not.toHaveProperty("name");
  });

  it("rejects a missing or invalid sub-category or PII type id", () => {
    expect(policyCreatePayload({ ...input, subCategoryId: "" }, domains)).toBeNull();
    expect(policyCreatePayload({ ...input, subCategoryId: "abc" }, domains)).toBeNull();
    expect(policyUpdatePayload({ ...input, subCategoryId: "0" }, domains)).toBeNull();
    expect(policyCreatePayload({ ...input, typeIds: ["3", "pii-local"] }, domains)).toBeNull();
  });
});

describe("parent status", () => {
  it("is active only when the sub-category and its category are active", () => {
    expect(policyParentActive({ subcategoryId: "10" }, subcategories, categories)).toBe(true);
  });

  it("is inactive when the sub-category is inactive", () => {
    expect(policyParentActive({ subcategoryId: "11" }, subcategories, categories)).toBe(false);
  });

  it("is inactive when the category is inactive, even if the sub-category is active", () => {
    expect(policyParentActive({ subcategoryId: "20" }, subcategories, categories)).toBe(false);
  });

  it("is inactive when the sub-category is unknown", () => {
    expect(policyParentActive({ subcategoryId: "99" }, subcategories, categories)).toBe(false);
  });

  it("makes an active policy effectively inactive under an inactive parent", () => {
    const rows = policies.map((p) => policyEffective(p, policyParentActive(p, subcategories, categories)));
    expect(rows).toEqual(["Active", "Active", "Inactive", "Inactive"]);
  });
});
