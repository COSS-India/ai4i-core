// Own-institution details for the read-only Institution Admin view.

import { useQuery } from "@tanstack/react-query";
import * as tenantService from "../../../services/tenantService";
import { fetchTenantUsageById } from "../../../services/usageSpendService";
import { parseError } from "../../../utils/errorHandler";
import { USAGE_SPEND_STALE_MS } from "../../../utils/usageSpendHelpers";
import type { TenantView } from "../../../types/tenant";

const INSTITUTION_STALE_MS = 2 * 60_000;

/** Sentinels the usage endpoint reports when no assignment covers the billing period. */
const UNASSIGNED_TIER_ID = "unassigned";
const UNASSIGNED_TIER_NAME = "unassigned";

export interface UseOwnInstitutionDetailsOptions {
  /** Signed-in user's tenant id. Queries stay idle until it resolves. */
  tenantId?: string | null;
  /** Institution-Admin-only view — pass false on the adopter path. */
  enabled?: boolean;
}

export interface OwnInstitutionDetails {
  institution: TenantView | null;
  tierName: string | null;
  budgetLimit: number | null;
  currency: string;
  isLoading: boolean;
  errorMessage: string | null;
}

/**
 * The Institution Admin's own institution, with its Tier and Budget.
 * PII stays masked. Tier/Budget use `usage-tenant` — `tenant/tier` is ADMIN-only.
 */
export function useOwnInstitutionDetails({
  tenantId,
  enabled = true,
}: UseOwnInstitutionDetailsOptions): OwnInstitutionDetails {
  const id = tenantId?.trim() ?? "";
  const isEnabled = enabled && Boolean(id);

  const institutionQuery = useQuery({
    queryKey: ["own-institution", id],
    queryFn: () => tenantService.getViewTenant(id),
    enabled: isEnabled,
    staleTime: INSTITUTION_STALE_MS,
  });

  const usageQuery = useQuery({
    queryKey: ["own-institution-usage", id],
    queryFn: () => fetchTenantUsageById(id),
    enabled: isEnabled,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const usage = usageQuery.data;
  const tier = usage?.tier?.trim() ?? "";
  const hasTierAssignment =
    Boolean(usage) &&
    usage?.tierId !== UNASSIGNED_TIER_ID &&
    tier.toLowerCase() !== UNASSIGNED_TIER_NAME;

  return {
    institution: institutionQuery.data ?? null,
    // No assignment this period, or a failed usage call → null, rendered as "—".
    tierName: hasTierAssignment ? tier || null : null,
    budgetLimit: hasTierAssignment ? (usage?.budget?.limit ?? null) : null,
    currency: usage?.currency || "INR",
    // Idle queries report "pending" too, hence the isEnabled guard.
    isLoading: isEnabled && (institutionQuery.isPending || usageQuery.isPending),
    errorMessage: institutionQuery.error
      ? parseError(institutionQuery.error).message
      : null,
  };
}
