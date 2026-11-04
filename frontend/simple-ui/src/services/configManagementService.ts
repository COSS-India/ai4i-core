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

/** The platform's standard domain list, in the order the `domains` config stores it. */
export async function getDomainOptions(): Promise<DomainOption[]> {
  const items = await listConfigs("domains");
  const config = items.find((item) => item.type === "domains");
  if (!config) return [];
  const codes = domainsConfigDataSchema.parse(config.data).allowed;
  return Array.from(new Set(codes.map((code) => code.trim()).filter(Boolean))).map((code) => ({
    code,
    label: domainCodeLabel(code),
  }));
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
