import { FIELD_HINTS } from "./fieldHints";
import { parseError } from "../utils/errorHandler";
import { roundMoney, roundPct } from "../utils/applicationBudgetPreview";

/** Shared validation copy for budget percentage / amount fields. */
export const BUDGET_VALIDATION = {
  enterBudgetAllocationPercentage: "Enter a budget allocation percentage.",
  budgetCannotBeNegative: "Budget cannot be negative.",
  enterValidNumber: "Enter a valid number.",
  enterValidPercentage: "Enter a valid percentage.",
  applicationBudgetNotAssigned: "This Application has no Budget (₹) assigned yet.",
  amountRequiresApplicationBudget:
    "Enter a Budget amount after this Application has a Budget (₹) assigned.",
  institutionBudgetNotSet: "Institution budget is not set.",
} as const;

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
  return `Cannot go below ${roundPct(pct)}% already consumed.`;
}

export function belowConsumedAmount(amount: number): string {
  return `Cannot go below ${roundMoney(amount)} already consumed.`;
}

export function belowConsumedPctRaw(floor: number): string {
  return `Cannot go below ${floor}% already consumed.`;
}

export function keyWouldDropBelowConsumed(keyName: string): string {
  return `Key "${keyName}" would drop below its consumed amount.`;
}

export function totalApplicationsOver100(totalPct: number): string {
  return `Total across Applications would be ${totalPct.toFixed(2)}% — over 100%.`;
}

export function totalApplicationsExceeds100(totalPct: number): string {
  return `Total across Applications is ${totalPct.toFixed(2)}% — cannot exceed 100%.`;
}

export function totalApiKeysExceeds100(totalPct: number): string {
  return `Total across active keys is ${totalPct.toFixed(2)}% — cannot exceed 100% of this Application's Budget.`;
}

export function editKeyBudgetTitle(applicationName?: string): string {
  return applicationName ? `Edit Key Budget — ${applicationName}` : "Edit Key Budget";
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
