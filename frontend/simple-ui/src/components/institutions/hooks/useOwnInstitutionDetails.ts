// Own-institution details for the read-only Institution Admin view.

import { useQuery } from "@tanstack/react-query";
import * as tenantService from "../../../services/tenantService";
import { parseError } from "../../../utils/errorHandler";
import type { TenantView } from "../../../types/tenant";

const INSTITUTION_STALE_MS = 2 * 60_000;

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
  /** Tier/Budget could not be read — distinct from nothing being assigned. */
  tierBudgetErrorMessage: string | null;
}

function parseBudget(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Institution Admin's own institution with Tier and Budget from GET /tenants/{id}.
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

  const institution = institutionQuery.data ?? null;
  const tierName = institution?.tier_name?.trim() || null;
  const budgetLimit = parseBudget(institution?.allocated_budget);

  return {
    institution,
    tierName: institution?.tier_id ? tierName : null,
    budgetLimit: institution?.tier_id || budgetLimit != null ? budgetLimit : null,
    currency: "INR",
    isLoading: isEnabled && institutionQuery.isPending,
    errorMessage: institutionQuery.error
      ? parseError(institutionQuery.error).message
      : null,
    tierBudgetErrorMessage: null,
  };
}
