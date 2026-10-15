/// <reference types="node" />
import { readFileSync } from "fs";
import { join } from "path";
import {
  PLAYGROUND_SIMULATION_HELP,
  simulationRows,
} from "../../src/components/policy/pii/detection";

const detected = [
  {
    entityType: "EMAIL_ADDRESS",
    policyTypes: ["PII"],
    instances: 2,
    replacements: [
      { original: "arjun@example.com", output: "<EMAIL_ADDRESS_1>" },
      { original: "meena@example.com", output: "<EMAIL_ADDRESS_2>" },
    ],
  },
  {
    entityType: "PAN_NUMBER",
    policyTypes: ["PII", "Finance"],
    instances: 1,
    replacements: [{ original: "ABCDE1234F", output: "<PAN_NUMBER_1>" }],
  },
];

describe("playground simulation results", () => {
  it("shows each detection with what was found and the simulator's token output", () => {
    expect(simulationRows(detected)).toEqual([
      {
        entityType: "EMAIL_ADDRESS",
        found: ["arjun@example.com", "meena@example.com"],
        outputs: ["<EMAIL_ADDRESS_1>", "<EMAIL_ADDRESS_2>"],
        instances: 2,
      },
      {
        entityType: "PAN_NUMBER",
        found: ["ABCDE1234F"],
        outputs: ["<PAN_NUMBER_1>"],
        instances: 1,
      },
    ]);
  });

  it("does not attach a handling action to any detection", () => {
    simulationRows(detected).forEach((row) => {
      expect(Object.keys(row).sort()).toEqual(["entityType", "found", "instances", "outputs"]);
    });
  });

  it("returns no rows when nothing was detected", () => {
    expect(simulationRows([])).toEqual([]);
  });
});

describe("playground helper text", () => {
  it("describes numbered token replacement", () => {
    expect(PLAYGROUND_SIMULATION_HELP).toMatch(/numbered placeholder token/);
    expect(PLAYGROUND_SIMULATION_HELP).toContain("<EMAIL_ADDRESS_1>");
  });

  it("does not claim Mask, Redact, or Hash is applied", () => {
    expect(PLAYGROUND_SIMULATION_HELP).not.toMatch(/\b(mask|redact|hash)(ed|ing)?\b/i);
    expect(PLAYGROUND_SIMULATION_HELP).toMatch(/handling modes are not applied/i);
  });
});

describe("playground panel", () => {
  const source = readFileSync(
    join(__dirname, "../../src/components/policy/pii/panels.tsx"),
    "utf8",
  );
  const start = source.indexOf("export function PlaygroundPanel()");
  const end = source.indexOf("function SimplePolicySummary(");
  const playground = source.slice(start, end);

  it("is found in panels.tsx", () => {
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
  });

  it("renders no Action column or handling badge for detections", () => {
    expect(playground).not.toMatch(/header:\s*"Action"/);
    expect(playground).not.toMatch(/handlingBadgeColor|\.handling\b|handlings/);
    expect(playground).not.toMatch(/Mask, Redact, or Hash/);
  });

  it("keeps the PII Definition, Found, Instances, and Output columns", () => {
    ["PII Definition", "Found", "Instances", "Output"].forEach((header) => {
      expect(playground).toContain(`header: "${header}"`);
    });
  });
});
