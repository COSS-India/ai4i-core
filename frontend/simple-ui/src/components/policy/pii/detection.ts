import type { PolicySimulation } from "../../../services/dto/schemas/policyHierarchy";
import { entityNamesForPolicy, regexFieldsForPolicy } from "./apiMap";
import type { Domain, PiiType, Policy } from "./model";

/** /pii/simulate replaces each detection with a numbered token; it applies no handling mode. */
export const PLAYGROUND_SIMULATION_HELP =
  "Each detected value is replaced with a numbered " +
  "placeholder token, such as <EMAIL_ADDRESS_1>. Configured handling modes are not applied here.";

/** One row of the Playground results table. */
export interface SimulationRow {
  entityType: string;
  found: string[];
  outputs: string[];
  instances: number;
}

export function simulationRows(detected: PolicySimulation["detected"]): SimulationRow[] {
  return detected.map((d) => ({
    entityType: d.entityType,
    found: d.replacements.map((r) => r.original),
    outputs: d.replacements.map((r) => r.output),
    instances: d.instances,
  }));
}

const MODEL_ENTITY_SAMPLES: Record<string, string> = {
  PERSON: "Patient Arjun Kumar contacted the helpdesk today.",
  EMAIL_ADDRESS: "Reports were emailed to arjun.kumar@example.com.",
  PHONE_NUMBER: "Callback number: +91 98765 43210.",
  LOCATION: "He lives in Chennai, Tamil Nadu.",
  DATE_TIME: "The appointment is on 12 August 2026.",
  CREDIT_CARD: "Card 4111 1111 1111 1111 was charged.",
  IP_ADDRESS: "The request came from 192.168.10.24.",
  URL: "Details are at https://example.com/records/42.",
  ORGANIZATION: "He works at Infosys.",
};

const FALLBACK_SAMPLE =
  "Patient Arjun Kumar (arjun.kumar@example.com, +91 98765 43210) visited on 12 August 2026. " +
  "Aadhaar 1234 5678 9012, PAN ABCDE1234F.";

/** Example text containing a value for each field the policy applies. */
export function buildSample(policy: Policy, types: PiiType[], domains: Domain[]): string {
  const lines = [
    ...regexFieldsForPolicy(policy, types, domains).flatMap((field) =>
      field.examples[0] ? [`${field.entityName}: ${field.examples[0]}.`] : [],
    ),
    ...entityNamesForPolicy(policy, types, domains).flatMap((name) => {
      const line = MODEL_ENTITY_SAMPLES[name.toUpperCase()];
      return line ? [line] : [];
    }),
  ];
  return lines.length > 0 ? Array.from(new Set(lines)).join(" ") : FALLBACK_SAMPLE;
}

export function regexCompiles(pattern: string): boolean {
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}
