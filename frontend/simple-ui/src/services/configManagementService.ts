import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  configListResponseSchema,
  domainsConfigDataSchema,
  statusReasonsConfigDataSchema,
  type ConfigItem,
} from "./dto/schemas/configManagement";

export type { ConfigItem } from "./dto/schemas/configManagement";

export interface DomainOption {
  code: string;
  label: string;
}

export async function listConfigs(type?: string): Promise<ConfigItem[]> {
  const response = await apiService.get(apiEndpoints.platform.configs, {
    params: type ? { type } : undefined,
    responseSchema: configListResponseSchema,
    suppressErrorAlert: true,
  });
  return response.data.data.items;
}

/** The platform's standard domain list, in the order the `domain` config stores it. */
export async function getDomainOptions(): Promise<DomainOption[]> {
  const items = await listConfigs("domain");
  const config = items.find((item) => item.type === "domain");
  if (!config) return [];
  const options = new Map<string, DomainOption>();
  for (const { key, label } of domainsConfigDataSchema.parse(config.data)) {
    const code = key.trim();
    if (!code || options.has(code)) continue;
    options.set(code, { code, label: label?.trim() || domainCodeLabel(code) });
  }
  return Array.from(options.values());
}

export type StatusReasonConfigType = "suspend-reasons" | "deactivate-reasons";

export interface StatusReasonOption {
  code: string;
  label: string;
  /** The admin must add remarks when picking this reason (e.g. Other). */
  remarksRequired: boolean;
}

/** Matches an "Other" reason by key or label: "OTHER", "other_reason", "Other (remarks mandatory)". */
const OTHER_REASON_PATTERN = /^other\b/i;

/** Predefined reasons for suspending or deactivating an institution, in config order. */
export async function getStatusReasonOptions(
  type: StatusReasonConfigType,
): Promise<StatusReasonOption[]> {
  const items = await listConfigs(type);
  const config = items.find((item) => item.type === type);
  if (!config) return [];
  const options = new Map<string, StatusReasonOption>();
  for (const { key, label, remarks_required } of statusReasonsConfigDataSchema.parse(config.data)) {
    const code = key.trim();
    if (!code || options.has(code)) continue;
    const text = label?.trim() || code;
    options.set(code, {
      code,
      label: text,
      // "Other" always needs remarks, even if the config omits the flag.
      remarksRequired:
        remarks_required === true || OTHER_REASON_PATTERN.test(code) || OTHER_REASON_PATTERN.test(text),
    });
  }
  return Array.from(options.values());
}

/** "art-and-culture" → "Art and Culture". */
export function domainCodeLabel(code: string): string {
  return code
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((word, index) =>
      index > 0 && word.toLowerCase() === "and" ? "and" : word.charAt(0).toUpperCase() + word.slice(1),
    )
    .join(" ");
}
