export type BudgetInputMode = "percentage" | "amount";

export interface ApplicationKeyPreviewInput {
  id: number;
  key_name: string;
  allocated_percentage: number;
  allocated_budget: number | null;
  consumed_budget?: number | null;
}

export interface ApplicationKeyPreview {
  id: number;
  key_name: string;
  allocated_percentage: number;
  allocated_budget: number;
  floorViolation: boolean;
}

export function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

export function roundPct(value: number): number {
  return Math.round(value * 100) / 100;
}

export interface ResolvedApplicationBudget {
  pct: number;
  /** Null when the Institution has no ₹ budget — % can still be edited in the UI. */
  amount: number | null;
}

export function resolveApplicationBudget(
  mode: BudgetInputMode,
  rawValue: number,
  tenantBudget: number,
): ResolvedApplicationBudget | null {
  if (!Number.isFinite(rawValue)) return null;
  if (mode === "percentage") {
    const pct = roundPct(rawValue);
    if (tenantBudget <= 0) {
      return { pct, amount: null };
    }
    const amount = roundMoney((tenantBudget * pct) / 100);
    return { pct, amount };
  }
  if (tenantBudget <= 0) return null;
  const pct = roundPct((rawValue / tenantBudget) * 100);
  const amount = roundMoney((tenantBudget * pct) / 100);
  return { pct, amount };
}

export function previewKeyCascade(
  applicationAmount: number,
  keys: ApplicationKeyPreviewInput[],
): ApplicationKeyPreview[] {
  return keys.map((key) => {
    // A Key's own ₹ (allocated_budget) never moves just because its parent
    // Application is resized — the server only ever recomputes
    // allocated_percentage for an un-listed Key (the same ₹ is now a
    // different share of the Application's new total); see
    // AllocationService._recompute_unlisted_percentages /
    // ._cascade_into_keys. Recomputing a hypothetical moved-₹ figure here
    // (applicationAmount * storedPercentage / 100) and floor-checking
    // *that* against consumed_budget could flag — and block Save on — a
    // "floor violation" the server itself would never produce, since the
    // server's own floor check only ever applies to an amount that's
    // actually moving. Use the Key's real, current allocated_budget for
    // both the returned preview value and the floor check instead.
    const allocated_budget = key.allocated_budget ?? 0;
    // Same "only recompute when allocated_budget is a positive amount"
    // rule the server applies: a never-funded Key (no ₹ yet) keeps its
    // stored percentage exactly, rather than previewing it as 0.
    const allocated_percentage =
      allocated_budget > 0 && applicationAmount > 0
        ? roundPct((allocated_budget / applicationAmount) * 100)
        : key.allocated_percentage ?? 0;
    const consumed = key.consumed_budget ?? 0;
    return {
      id: key.id,
      key_name: key.key_name,
      allocated_percentage,
      allocated_budget,
      floorViolation: allocated_budget < consumed - 1e-6,
    };
  });
}
