import type { PiiType, Policy } from "./model";

export interface DetectionHit {
  typeId: string;
  typeName: string;
  handling: PiiType["handling"];
  instances: string[];
  replacements: string[];
}

export interface DetectionResult {
  sanitized: string;
  results: DetectionHit[];
  totalInstances: number;
}

const SAMPLE_LINES: Record<string, (value: string) => string> = {
  "pii-aadhaar": (v) => `Aadhaar on record is ${v}.`,
  "pii-mobile": (v) => `Callback number: ${v}.`,
  "pii-email": (v) => `Reports were emailed to ${v}.`,
  "pii-fullname": (v) => `Patient ${v} contacted the helpdesk today.`,
  "pii-dob": (v) => `Date of birth ${v} was verified.`,
  "pii-pan": (v) => `PAN ${v} submitted for KYC.`,
  "pii-address": (v) => `Residing at ${v}.`,
};

const SAMPLE_VALUES: Record<string, string> = {
  "pii-aadhaar": "1234 5678 9012",
  "pii-mobile": "9876543210",
  "pii-email": "arjun@college.edu",
  "pii-fullname": "Arjun Kumar",
  "pii-dob": "12-08-2004",
  "pii-pan": "ABCDE1234F",
  "pii-address": "24 MG Road Chennai",
  "pii-edu-name": "Meena Raj",
  "pii-edu-id": "EDU20231234",
  "pii-edu-email": "meena@college.edu",
  "pii-edu-phone": "9876543210",
  "pii-edu-dob": "12-08-2004",
  "pii-edu-address": "24 MG Road Chennai",
  "pii-fin-account": "123456789012",
  "pii-fin-card": "4111 1111 1111 1111",
  "pii-fin-ifsc": "SBIN0000456",
  "pii-fin-pan": "ABCDE1234F",
  "pii-fin-txn": "TXN987654321",
  "pii-fin-upi": "arjun@upi",
  "pii-health-name": "Meena Raj",
  "pii-health-mrn": "UHID123456",
  "pii-health-aadhaar": "1234 5678 9012",
  "pii-health-phone": "9876543210",
  "pii-health-insurance": "HIN9876543",
  "pii-health-icd": "E11.9",
};

export function buildSample(policy: Policy, types: PiiType[]): string {
  return policy.typeIds
    .map((id) => {
      const t = types.find((x) => x.id === id);
      if (!t) return null;
      const value = SAMPLE_VALUES[id] ?? t.examples[0];
      if (!value) return null;
      const line = SAMPLE_LINES[id];
      return line ? line(value) : `${t.name}: ${value}.`;
    })
    .filter((line): line is string => Boolean(line))
    .join(" ");
}

function transformValue(value: string, type: PiiType): string {
  if (type.handling === "Redact") return `[${type.name.toUpperCase()} REDACTED]`;
  if (type.handling === "Hash") {
    let h = 0;
    for (let i = 0; i < value.length; i++) h = (h * 31 + value.charCodeAt(i)) >>> 0;
    return `sha256:${h.toString(16).padStart(8, "0")}…`;
  }
  if (type.maskingPattern === "Full") return value.replace(/\S/g, "X");
  if (value.includes("@")) {
    const [local, domain] = value.split("@");
    return `${local.slice(0, 2)}***@${domain}`;
  }
  const visible = 4;
  if (value.length <= visible) return value.replace(/\S/g, "X");
  return value.slice(0, value.length - visible).replace(/\S/g, "X") + value.slice(-visible);
}

function buildRegex(type: PiiType): RegExp | null {
  if (type.detectionMode === "Model") return /\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2}\b/g;
  if (!type.regex) return null;
  try {
    return new RegExp(type.regex, "g");
  } catch {
    return null;
  }
}

export function runDetection(input: string, types: PiiType[]): DetectionResult {
  const matches: { start: number; end: number; value: string; type: PiiType }[] = [];
  types.forEach((type) => {
    const re = buildRegex(type);
    if (!re) return;
    let m: RegExpExecArray | null;
    while ((m = re.exec(input)) !== null) {
      if (m[0].length === 0) {
        re.lastIndex += 1;
        continue;
      }
      const start = m.index;
      const end = m.index + m[0].length;
      if (!matches.some((x) => start < x.end && end > x.start)) {
        matches.push({ start, end, value: m[0], type });
      }
    }
  });
  matches.sort((a, b) => a.start - b.start);
  let sanitized = "";
  let cursor = 0;
  const byType = new Map<string, DetectionHit>();
  matches.forEach((match) => {
    const replacement = transformValue(match.value, match.type);
    sanitized += input.slice(cursor, match.start) + replacement;
    cursor = match.end;
    const existing = byType.get(match.type.id);
    if (existing) {
      existing.instances.push(match.value);
      existing.replacements.push(replacement);
    } else {
      byType.set(match.type.id, {
        typeId: match.type.id,
        typeName: match.type.name,
        handling: match.type.handling,
        instances: [match.value],
        replacements: [replacement],
      });
    }
  });
  sanitized += input.slice(cursor);
  return {
    sanitized,
    results: Array.from(byType.values()),
    totalInstances: matches.length,
  };
}

export function regexCompiles(pattern: string): boolean {
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}
