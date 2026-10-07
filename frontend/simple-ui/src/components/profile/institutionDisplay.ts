import type { TenantTierAssignment } from "../../services/tierManagementService";
import type { TenantView } from "../../types/tenant";

const AVATAR_COLORS = [
  "blue.500",
  "green.500",
  "purple.500",
  "teal.500",
  "orange.500",
  "pink.500",
];

export function getTenantInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export function getTenantAvatarBg(name: string): string {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.codePointAt(i) ?? 0;
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

export type TierOption = { id: string; name: string };

export function tenantBudgetNumber(t: TenantView): number | null {
  if (t.allocated_budget == null) return null;
  const n = Number(t.allocated_budget);
  return Number.isFinite(n) ? n : null;
}

export function resolveTierLabel(
  tierId: string | null | undefined,
  tierOptions: TierOption[],
  fallbackName?: string | null,
): string {
  if (fallbackName?.trim()) return fallbackName.trim();
  if (!tierId) return "—";
  const match = tierOptions.find((tier) => String(tier.id) === String(tierId));
  return match?.name ?? tierId;
}

/**
 * Keyed off `tenant.tier_id` alone, the same field the Tier filter matches on,
 * so a row cannot show a tier yet filter as "No tier assigned". The name falls
 * back to the assignment list, which covers a tier newer than the cached catalog.
 */
export function resolveTenantTierName(
  tenant: TenantView,
  tierOptions: TierOption[],
  assignmentsByTenantId: Map<string, TenantTierAssignment>,
): string | null {
  const tierId = tenant.tier_id;
  if (!tierId) return null;
  const match = tierOptions.find((tier) => String(tier.id) === String(tierId));
  if (match?.name?.trim()) return match.name.trim();
  const assignment = assignmentsByTenantId.get(String(tenant.tenant_id));
  return assignment?.tier_name?.trim() || tenant.tier_name?.trim() || null;
}

export function formatRupees(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return `₹${amount.toLocaleString("en-IN")}`;
}
