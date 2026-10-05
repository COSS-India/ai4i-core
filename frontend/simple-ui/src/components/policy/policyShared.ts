import { policyService, type PiiTypeOut } from "../../services/policyService";

export const PII_TYPES_QUERY_KEY = ["pii-types-catalog"] as const;
export const EMPTY_PII_TYPES: PiiTypeOut[] = [];

export async function fetchAllPiiTypes(): Promise<PiiTypeOut[]> {
  const acc: PiiTypeOut[] = [];
  let page = 1;
  const limit = 100;
  for (;;) {
    const res = await policyService.listPiiTypes({ page, limit });
    acc.push(...res.data.data);
    if (acc.length >= res.data.meta.total || res.data.data.length === 0) break;
    page += 1;
  }
  return acc;
}

export function getPolicyApiErrorMessage(e: unknown, fallback: string): string {
  const data = (e as {
    response?: {
      data?: {
        detail?: string | { message?: string } | Array<{ msg?: string }>;
        error?: { message?: string };
        message?: string;
      };
    };
    message?: string;
  })?.response?.data;

  const detail = data?.detail;
  if (Array.isArray(detail)) {
    const validationMessage = detail
      .map((item) => item?.msg)
      .filter((msg): msg is string => typeof msg === "string" && msg.trim().length > 0)
      .join("; ");
    if (validationMessage) return validationMessage;
  }

  if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
    const detailMessage = detail.message;
    if (typeof detailMessage === "string" && detailMessage.trim()) return detailMessage;
  }

  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof data?.error?.message === "string" && data.error.message.trim()) return data.error.message;
  if (typeof data?.message === "string" && data.message.trim()) return data.message;

  const topLevelMessage = (e as { message?: string })?.message;
  if (typeof topLevelMessage === "string" && topLevelMessage.trim()) return topLevelMessage;

  return fallback;
}

export function formatDt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function parseDelimitedValues(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}
