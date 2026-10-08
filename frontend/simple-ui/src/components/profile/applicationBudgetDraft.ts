import {
  allocatedKeyHolders,
  previewKeyCascade,
  resolveApplicationBudget,
  roundMoney,
  roundPct,
  type ApplicationKeyPreview,
  type KeyAllocationHolder,
} from "../../utils/applicationBudgetPreview";
import type { Application, ApplicationStatus } from "../../types/application";
import type { ApplicationApiKeyRow } from "../../services/applicationService";
import {
  belowAllocatedToKeys,
  belowConsumedAmount,
  belowConsumedPct,
  BUDGET_VALIDATION,
  keyWouldDropBelowConsumed,
} from "../../config/budgetMessages";

/** Application-level amounts from the usage list. Null means that list did not supply them. */
export type BulkBudgetDraft = {
  application_id: string;
  name: string;
  status: ApplicationStatus;
  allocated_amount: number | null;
  consumed_percentage: number | null;
  consumed_budget: number | null;
  remaining_budget: number | null;
  originalPct: number | null;
  pctInput: string;
  resolvedPct: number | null;
  resolvedAmount: number | null;
  keysLoading: boolean;
  keysLoaded: boolean;
  keys: ApplicationApiKeyRow[];
  keyPreviews: ApplicationKeyPreview[];
  rowError: string | null;
  /** Rejected stepper attempt. Does not change the draft or block save. */
  inputNotice: string | null;
};

/** Spend as a share of the Institution budget (not the Application's own allocation). */
export function toInstitutionConsumedPct(
  consumedAmount: number,
  tenantBudget: number,
): number | null {
  if (tenantBudget <= 0) return null;
  return roundPct((consumedAmount / tenantBudget) * 100);
}

function pctString(value: number | null): string {
  if (value == null) return "";
  return String(value);
}

export function rowHasBudgetChange(row: BulkBudgetDraft): boolean {
  const orig = row.originalPct;
  const next = row.resolvedPct;
  if (orig == null && next == null) return false;
  if (orig == null || next == null) return true;
  return Math.abs(orig - next) > 1e-6;
}

export function isApplicationBudgetEditable(status: ApplicationStatus): boolean {
  return status === "ACTIVE";
}

export function buildDraftFromApplication(app: Application): BulkBudgetDraft {
  const pct = app.allocated_percentage;
  const amount = app.allocated_budget;
  return {
    application_id: app.application_id,
    name: app.name,
    status: app.status,
    allocated_amount: null,
    consumed_percentage: app.consumed_percentage ?? null,
    consumed_budget: app.consumed_budget ?? null,
    remaining_budget: null,
    originalPct: pct,
    pctInput: pctString(pct),
    resolvedPct: pct,
    resolvedAmount: amount,
    keysLoading: false,
    keysLoaded: false,
    keys: [],
    keyPreviews: [],
    rowError: null,
    inputNotice: null,
  };
}

export function evaluateRowError(
  row: BulkBudgetDraft,
  tenantBudget: number,
  currency = "INR",
): string | null {
  if (row.pctInput.trim() === "" && row.originalPct != null) {
    return BUDGET_VALIDATION.enterValidAllocationPercentage;
  }
  if (row.resolvedPct == null) return null;
  if (row.resolvedPct < 0 || row.resolvedPct > 100) {
    return BUDGET_VALIDATION.percentageMustBeBetween0And100;
  }
  const keyFloorError = belowKeyAllocationError(
    row.name,
    row.resolvedAmount,
    allocatedKeyHolders(row.keys),
    row.consumed_budget,
    tenantBudget,
    currency,
  );
  if (keyFloorError) return keyFloorError;
  if (
    row.consumed_percentage != null &&
    row.resolvedPct < row.consumed_percentage - 1e-6
  ) {
    return belowConsumedPct(row.consumed_percentage);
  }
  if (
    row.consumed_budget != null &&
    row.resolvedAmount != null &&
    row.resolvedAmount < row.consumed_budget - 1e-6
  ) {
    return belowConsumedAmount(row.consumed_budget);
  }
  const keyViolation = row.keyPreviews.find((k) => k.floorViolation);
  if (keyViolation) {
    return keyWouldDropBelowConsumed(keyViolation.key_name);
  }
  if (tenantBudget <= 0 && row.resolvedAmount != null && row.resolvedAmount > 0) {
    return BUDGET_VALIDATION.institutionBudgetNotSet;
  }
  return null;
}

/** Server allows a cent of legacy drift per key before rejecting a reduction. */
export function allocationDriftTolerance(keyCount: number): number {
  return 0.01 * Math.max(keyCount, 1);
}

export function belowKeyAllocationError(
  applicationName: string,
  resolvedAmount: number | null,
  holders: KeyAllocationHolder[],
  consumedAmount: number | null,
  tenantBudget: number,
  currency: string,
): string | null {
  const keyFloor = roundMoney(holders.reduce((sum, key) => sum + key.amount, 0));
  const consumed = consumedAmount ?? 0;
  if (
    holders.length === 0 ||
    resolvedAmount == null ||
    keyFloor <= consumed + 1e-6 ||
    resolvedAmount >= keyFloor - allocationDriftTolerance(holders.length)
  ) {
    return null;
  }
  return belowAllocatedToKeys(
    applicationName.trim() || "This Application",
    keyFloor,
    toInstitutionConsumedPct(keyFloor, tenantBudget),
    holders,
    currency,
  );
}

export function applyResolved(
  row: BulkBudgetDraft,
  tenantBudget: number,
  raw: string,
  currency = "INR",
): BulkBudgetDraft {
  const trimmed = raw.trim();
  if (trimmed === "") {
    const next = {
      ...row,
      pctInput: "",
      resolvedPct: null,
      resolvedAmount: null,
      keyPreviews: [],
      rowError: null,
      inputNotice: null,
    };
    return { ...next, rowError: evaluateRowError(next, tenantBudget, currency) };
  }
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) {
    return { ...row, inputNotice: null, rowError: BUDGET_VALIDATION.enterValidAllocationPercentage };
  }
  const resolved = resolveApplicationBudget("percentage", numeric, tenantBudget);
  if (!resolved) {
    return { ...row, rowError: BUDGET_VALIDATION.enterValidNumber };
  }
  const keys = row.keys.filter((k) => k.is_active);
  const keyPreviews =
    resolved.amount != null && keys.length > 0
      ? previewKeyCascade(resolved.amount, keys)
      : [];
  const next: BulkBudgetDraft = {
    ...row,
    pctInput: String(resolved.pct),
    resolvedPct: resolved.pct,
    resolvedAmount: resolved.amount,
    keyPreviews,
    rowError: null,
    inputNotice: null,
  };
  return { ...next, rowError: evaluateRowError(next, tenantBudget, currency) };
}
