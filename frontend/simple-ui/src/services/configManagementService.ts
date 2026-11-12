import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  configListResponseSchema,
  domainsConfigDataSchema,
  modelColumnsConfigDataSchema,
  statusReasonsConfigDataSchema,
  type ConfigItem,
} from "./dto/schemas/configManagement";

export type { ConfigItem } from "./dto/schemas/configManagement";

export interface DomainOption {
  code: string;
  label: string;
}

/**
 * `sortOrder` with a `type` makes the backend sort that config's data items by
 * label (case-insensitive); without a `type` it orders the config rows by id.
 */
export async function listConfigs(
  type?: string,
  sortOrder?: "asc" | "desc",
): Promise<ConfigItem[]> {
  const params: Record<string, string> = {};
  if (type) params.type = type;
  if (sortOrder) params.sort_order = sortOrder;
  const response = await apiService.get(apiEndpoints.platform.configs, {
    params: Object.keys(params).length ? params : undefined,
    responseSchema: configListResponseSchema,
    suppressErrorAlert: true,
  });
  return response.data.data.items;
}

/** The platform's standard domain list, sorted A→Z by label by the backend. */
export async function getDomainOptions(): Promise<DomainOption[]> {
  const items = await listConfigs("domain", "asc");
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

export interface ModelColumnConfigEntry {
  key: string;
  label: string;
  required: boolean;
  /** Omitted when the config does not say; the built-in default applies. */
  defaultVisible?: boolean;
}

/** Model List columns from the `model-column` config, in display order. */
export async function getModelColumnConfig(): Promise<ModelColumnConfigEntry[]> {
  const items = await listConfigs("model-column");
  const config = items.find((item) => item.type === "model-column");
  if (!config) return [];
  const entries = new Map<string, ModelColumnConfigEntry>();
  for (const { key, label, required, defaultVisible } of modelColumnsConfigDataSchema.parse(
    config.data,
  )) {
    const id = key.trim();
    if (!id || entries.has(id)) continue;
    entries.set(id, {
      key: id,
      label: label?.trim() || id,
      required: required === true,
      ...(typeof defaultVisible === "boolean" ? { defaultVisible } : {}),
    });
  }
  return Array.from(entries.values());
}

export type StatusReasonConfigType = "suspend-reasons" | "deactivate-reasons";

export interface StatusReasonOption {
  code: string;
  label: string;
  /** The admin must add remarks when picking this reason (only Other). */
  remarksRequired: boolean;
}

/**
 * The "Other" reason: the only reason whose remarks are mandatory. Matched by key,
 * which must be `other` or start with `other-` / `other_` (any case), e.g.
 * `other-remarks-mandatory`. The config's own `required` flag is not used.
 */
const OTHER_REASON_KEY_PATTERN = /^other(?![a-z0-9])/i;

/** Predefined reasons for suspending or deactivating an institution, in config order. */
export async function getStatusReasonOptions(
  type: StatusReasonConfigType,
): Promise<StatusReasonOption[]> {
  const items = await listConfigs(type);
  const config = items.find((item) => item.type === type);
  if (!config) return [];
  const options = new Map<string, StatusReasonOption>();
  for (const { key, label } of statusReasonsConfigDataSchema.parse(config.data)) {
    const code = key.trim();
    if (!code || options.has(code)) continue;
    options.set(code, {
      code,
      label: label?.trim() || code,
      remarksRequired: OTHER_REASON_KEY_PATTERN.test(code),
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
