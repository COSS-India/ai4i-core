import { TARGET_SERVICES } from "../../../types/alerting";
import { FOR_DURATION_BY_EVAL_INTERVAL } from "./constants";

export function getAllowedForDurations(evalInterval: string | null | undefined): string[] {
  const key = evalInterval ?? "30s";
  return [...(FOR_DURATION_BY_EVAL_INTERVAL[key] ?? FOR_DURATION_BY_EVAL_INTERVAL["30s"])];
}

export function expandServices(raw: string[]): string[] {
  return raw.includes("all") ? TARGET_SERVICES.map((t) => t.value) : raw;
}

export function normalizeServiceValue(raw: string): string {
  const v0 = String(raw ?? "").trim().toLowerCase();
  if (!v0) return v0;
  let v = v0.replace(/_+/g, "-").replace(/\/+/g, "-");
  if (v.endsWith("-service")) v = v.slice(0, -"-service".length);
  if (v === "audio-lang-detection") v = "audio-language-detection";
  return v;
}

export function extractServicesFromPromql(expr: string | null | undefined): string[] {
  const text = String(expr ?? "");
  if (!text) return [];
  const out: string[] = [];
  const re = /service\s*=\s*"([^"]+)"/g;
  let match: RegExpExecArray | null = re.exec(text);
  while (match) {
    if (match[1]) out.push(match[1]);
    match = re.exec(text);
  }
  return out;
}
