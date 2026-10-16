/// <reference types="jest" />

import { validateModelData } from "../../src/components/model-management/modelJsonValidation";

const NAME_PATTERN_MESSAGE =
  'name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). Example: "example-model" or "org/model-name"';

function validModel(overrides: Record<string, unknown> = {}) {
  return {
    name: "example-model",
    version: "1.0",
    description: "A valid model description text.",
    task: { type: "asr" },
    license: "MIT",
    domain: ["general"],
    trainingDataset: { description: "dataset" },
    submitter: { name: "Team" },
    ...overrides,
  };
}

describe("validateModelData", () => {
  it("returns no errors for a minimal valid object", () => {
    expect(validateModelData(validModel())).toEqual([]);
  });

  it("requires a name", () => {
    const { name: _name, ...withoutName } = validModel();
    expect(validateModelData(withoutName)).toContain(
      "name is required and must be a non-empty string",
    );
  });

  it("rejects a name that contains spaces", () => {
    expect(validateModelData(validModel({ name: "bad model" }))).toContain(
      "name must not contain spaces",
    );
  });

  it("rejects a name that fails the character pattern", () => {
    expect(validateModelData(validModel({ name: "model_name" }))).toContain(
      NAME_PATTERN_MESSAGE,
    );
  });

  it("rejects a version outside the length limits", () => {
    expect(validateModelData(validModel({ version: "v".repeat(21) }))).toContain(
      "version must be 1–20 characters",
    );
  });

  it("rejects a description outside the length limits", () => {
    const description = "too short";
    expect(validateModelData(validModel({ description }))).toContain(
      `description must be 25–1000 characters (got ${description.length})`,
    );
  });

  it("rejects languages that are not an array", () => {
    expect(validateModelData(validModel({ languages: "en" }))).toContain(
      "languages must be an array when provided",
    );
  });

  it("requires adapterConfig.inputs to be an array", () => {
    expect(
      validateModelData(validModel({ adapterConfig: { outputs: [] } })),
    ).toContain("adapterConfig.inputs is required and must be an array");
  });

  it("requires adapterConfig.outputs to be an array", () => {
    expect(
      validateModelData(validModel({ adapterConfig: { inputs: [] } })),
    ).toContain("adapterConfig.outputs is required and must be an array");
  });

  it("requires schema.model_name when schema is provided", () => {
    expect(validateModelData(validModel({ schema: {} }))).toContain(
      "schema.model_name is required",
    );
  });

  it("rejects a submitter name outside the length limits", () => {
    expect(
      validateModelData(validModel({ submitter: { name: "Al" } })),
    ).toContain("submitter.name must be 3–50 characters");
  });

  it("rejects a team member name outside the length limits", () => {
    expect(
      validateModelData(
        validModel({ submitter: { name: "Team", team: [{ name: "Bob" }] } }),
      ),
    ).toContain("submitter.team[0].name must be 5–50 characters");
  });
});
