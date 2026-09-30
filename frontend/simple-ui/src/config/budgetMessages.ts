import { FIELD_HINTS } from "./fieldHints";
import { parseError } from "../utils/errorHandler";
import { roundMoney, roundPct } from "../utils/applicationBudgetPreview";

/** Labels and status copy shared by Application and API key budget dialogs. */
export const BUDGET_COPY = {
  loading: "Loading…",
  currentBudget: "Current budget",
  newAllocation: "New allocation",
  atThisPercentage: "at this percentage",
  previousValueKept: "The previous value was kept.",
  editBudget: "Edit Budget",
  saveChanges: "Save Changes",
  saveAllChanges: "Save All Changes",
  saving: "Saving...",
  bulkUpdateBudgets: "Bulk Update Budgets",
  remaining: "Remaining",
  leftForThisKey: "Left for this key",
  applicationPrefix: "Application:",
  apiKeyFallback: "API key",
  inactiveKeyNotEditable: "This API key is not active, so its allocation cannot be edited.",
  keyHasNoApplication: "This key has no application",
} as const;

export function editBudgetTitle(name?: string | null): string {
  const trimmed = name?.trim();
  return trimmed ? `Edit Budget — ${trimmed}` : BUDGET_COPY.editBudget;
}

export function editBudgetForKey(name?: string | null): string {
  const trimmed = name?.trim() || BUDGET_COPY.apiKeyFallback;
  return `Edit budget for ${trimmed}`;
}

/** Shared validation copy for budget percentage / amount fields. */
export const BUDGET_VALIDATION = {
  enterBudgetAllocationPercentage: "Enter a budget allocation percentage.",
  budgetCannotBeNegative: "Budget cannot be negative.",
  budgetMustBeGreaterThanZero:
    "Budget must be greater than 0% — a 0% allocation is a Key that can never be used.",
  percentageMustBeBetween0And100: "Enter a percentage between 0 and 100.",
  enterValidNumber: "Enter a valid number.",
  enterValidPercentage: "Enter a valid percentage.",
  enterValidAllocationPercentage: "Enter a valid allocation percentage.",
  applicationBudgetUnavailable:
    "Application budget is unavailable. Allocation cannot be calculated.",
  applicationBudgetNotAssigned: "This Application has no Budget (₹) assigned yet.",
  amountRequiresApplicationBudget:
    "Enter a Budget amount after this Application has a Budget (₹) assigned.",
  institutionBudgetNotSet: "Institution budget is not set.",
} as const;

/** Message for hard 0–100 rejects from PercentageStepper. */
export function percentageBoundMessage(bound: "min" | "max"): string {
  return bound === "min"
    ? BUDGET_VALIDATION.budgetCannotBeNegative
    : BUDGET_VALIDATION.percentageMustBeBetween0And100;
}

/** API allocation error codes mapped to user-facing messages. */
export const ALLOCATION_ERROR_MESSAGES = {
  applicationBudgetNotSet:
    "This Application has no Budget allocation yet — assign one from Application Management first.",
  applicationAllocationMismatch:
    "Application budget changed elsewhere — close this dialog, refresh, and try again.",
} as const;

export const BUDGET_TOAST = {
  applicationBudgetsUpdated: "Application budgets updated.",
  keyBudgetUpdated: (count: number) => `Budget updated for ${count} key(s).`,
} as const;

export function belowConsumedPct(pct: number): string {
  return `Allocation cannot be lower than ${roundPct(pct)}% already consumed.`;
}

export function belowConsumedAmount(amount: number): string {
  return `Allocation cannot be lower than ${roundMoney(amount)} already consumed.`;
}

export function belowConsumedPctRaw(floor: number): string {
  return `Allocation cannot be lower than ${floor}% already consumed.`;
}

export function keyWouldDropBelowConsumed(keyName: string): string {
  return `Key "${keyName}" would drop below its consumed amount.`;
}

export function totalApplicationsOver100(totalPct: number): string {
  return `Allocation exceeds the available institution budget (${totalPct.toFixed(2)}%).`;
}

export function totalApiKeysExceeds100(totalPct: number): string {
  return `Total API key allocation cannot exceed 100% of this application's budget (${totalPct.toFixed(2)}%).`;
}

export type BelowConsumedContext = "application" | "apiKey";

export function mapBelowConsumedError(
  message: string,
  context: BelowConsumedContext,
): string {
  if (/api[_-]?key/i.test(message)) {
    if (context === "application") {
      return `A Key under this Application would drop below its consumed amount. ${message}`;
    }
    return message;
  }
  if (context === "apiKey") {
    return `An API key would drop below its consumed amount. ${message}`;
  }
  return message;
}

export function mapAllocationError(
  error: unknown,
  getCode: (error: unknown) => string | null,
  context: BelowConsumedContext = "apiKey",
): string {
  const code = getCode(error);
  const message = parseError(error).message;
  if (code === "APPLICATION_BUDGET_NOT_SET") {
    return ALLOCATION_ERROR_MESSAGES.applicationBudgetNotSet;
  }
  if (code === "APPLICATION_ALLOCATION_MISMATCH") {
    return ALLOCATION_ERROR_MESSAGES.applicationAllocationMismatch;
  }
  if (code === "TENANT_BUDGET_NOT_SET") {
    return FIELD_HINTS.application.institutionBudgetNotSet;
  }
  if (code === "API_KEY_REVOKED") {
    return message;
  }
  if (code === "ALLOCATION_TOTAL_EXCEEDED") {
    return message;
  }
  if (code === "ALLOCATION_BELOW_CONSUMED") {
    return mapBelowConsumedError(message, context);
  }
  return message;
}

export function allocationErrorEntityId(
  error: unknown,
  entity: "api_key" | "application",
): number | string | null {
  const message = parseError(error).message;
  if (entity === "api_key") {
    const match =
      message.match(/api_key_id[=:\s]+(\d+)/i) ?? message.match(/\bid=(\d+)/);
    return match ? Number(match[1]) : null;
  }
  const match =
    message.match(/application_id[=:\s]+(\d+)/i) ?? message.match(/\bid=(\d+)/);
  return match?.[1] ?? null;
}
