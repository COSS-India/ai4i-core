export type BudgetInputMode = "percentage" | "amount";

export interface ApplicationKeyPreviewInput {
  id: number;
  key_name: string;
  allocated_percentage: number;
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
    const pct = key.allocated_percentage ?? 0;
    const allocated_budget = roundMoney((applicationAmount * pct) / 100);
    const consumed = key.consumed_budget ?? 0;
    return {
      id: key.id,
      key_name: key.key_name,
      allocated_percentage: pct,
      allocated_budget,
      floorViolation: allocated_budget < consumed - 1e-6,
    };
  });
}
