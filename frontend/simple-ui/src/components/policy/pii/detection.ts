import { detectionTypesForPolicy, entityNamesForPolicy } from "./apiMap";
import type { Domain, PiiType, Policy } from "./model";

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
    ...detectionTypesForPolicy(policy, types, domains).flatMap((t) =>
      t.examples[0] ? [`${t.name}: ${t.examples[0]}.`] : [],
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
