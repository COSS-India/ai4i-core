import {
  formatTenantStatusLabel,
  formatTenantUserStatusLabel,
} from "../../../config/constants";

export function dash(v?: string | null): string {
  return v && v.trim() ? v : "—";
}

export function fmtDate(v?: string | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}

export function formatStatusConfirmLabel(
  targetType: "tenant" | "user" | undefined,
  status: string
): string {
  if (targetType === "user") {
    return formatTenantUserStatusLabel(status);
  }
  return formatTenantStatusLabel(status);
}
