import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  configListResponseSchema,
  domainsConfigDataSchema,
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
