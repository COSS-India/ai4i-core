import { useEffect, useState } from "react";

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
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
