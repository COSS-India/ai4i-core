import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@chakra-ui/react";
import {
  adjustTenantBudget,
  changeTenantTier,
} from "../../../services/tierManagementService";
import { parseError } from "../../../utils/errorHandler";
import {
  budgetWindowToMinDate,
  dateInputToEndOfDayIso,
  dateInputToStartOfDayIso,
  todayDateInputValue,
} from "../../../utils/helpers";
import type { ServiceMappingsStatus } from "../types";
import type { TenantView } from "../../../types/tenant";

/** Mirrors auth-service's MAX_TENANT_BUDGET (NUMERIC(15, 2) -> 10^13 - 0.01). */
const MAX_BUDGET = 9_999_999_999_999.99;

const MESSAGES = {
  tierRequired: "Select a tier.",
  tierMappingsLoading: "Loading service mappings… please try again in a moment.",
  tierMappingsError:
    "Unable to verify service mappings for this Tier. Please refresh and try again.",
  budgetRequired: "Enter a budget.",
  budgetNotPositive: "Budget must be a positive value.",
  budgetTooLarge: `Budget cannot exceed ₹${MAX_BUDGET.toLocaleString("en-IN")}.`,
  budgetUnchanged:
    "This is already the current budget. Enter a different amount — the effective window can only be set alongside a budget change.",
  effectiveFromRequired: "Select a Budget Effective From date.",
  effectiveFromBackdated: "Budget Effective From cannot be in the past.",
  effectiveToRequired: "Select a Budget Effective To date.",
  effectiveToNotFuture: "Budget Effective To must be later than today.",
  effectiveToSameAsFrom:
    "Budget Effective From and Budget Effective To cannot be the same date.",
  effectiveToBeforeFrom:
    "Budget Effective To must be after Budget Effective From.",
} as const;

type FieldKey = "tier" | "budget" | "effectiveFrom" | "effectiveTo";
type FormValues = {
  tierId: string;
  budget: string;
  effectiveFrom: string;
  effectiveTo: string;
};
type FieldErrors = Partial<Record<FieldKey, string>>;

const initialForm = (today: string): FormValues => ({
  tierId: "",
  budget: "",
  effectiveFrom: today,
  effectiveTo: "",
});

/**
 * Keep a budget field to digits with at most one `.` and two decimals, capped
 * at the column's ceiling. Leading zeros are left alone — stripping them
 * mid-typing fights the user.
 */
function sanitizeBudgetInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const [whole = "", ...rest] = cleaned.split(".");
  const next = rest.length ? `${whole}.${rest.join("").slice(0, 2)}` : whole;
  if (next === "" || next === ".") return next;
  return Number(next) > MAX_BUDGET ? String(MAX_BUDGET) : next;
}

/**
 * Turn the absolute budget the admin typed into the delta the budget endpoint
 * actually takes (`current + (±amount)`), so "Budget: 50,000" means the total
 * is 50,000 regardless of what was there before.
 *
 * Returns null when nothing needs to move — which is NOT automatically fine:
 * a tenant re-founding a lapsed window still needs the dates written, and
 * they can only ride along on a revision. Hence `budgetUnchanged`.
 */
function budgetRevisionFor(
  enteredBudget: number,
  currentBudget: number | null | undefined,
): { action: "top-up" | "top-down"; amount: number } | null {
  const current = Number(currentBudget ?? 0);
  const delta = enteredBudget - (Number.isFinite(current) ? current : 0);
  // Float dust from the subtraction is no change at all, and the endpoint
  // would reject it (gt=0) anyway.
  if (Math.abs(delta) < 0.005) return null;
  return {
    action: delta > 0 ? "top-up" : "top-down",
    amount: Math.round(Math.abs(delta) * 100) / 100,
  };
}

type ValidationContext = {
  today: string;
  serviceMappingsStatus: ServiceMappingsStatus;
  tierIdsWithServices: Set<string>;
  noServicesMessage: string;
  currentBudget: number | null | undefined;
  budgetSettled: boolean;
};

/** True once `tierId` is known to have no services mapped to it. */
function tierHasNoServices(
  tierId: string,
  ctx: Pick<ValidationContext, "serviceMappingsStatus" | "tierIdsWithServices">,
): boolean {
  return (
    !!tierId &&
    ctx.serviceMappingsStatus === "ready" &&
    !ctx.tierIdsWithServices.has(String(tierId))
  );
}

function validateTier(tierId: string, ctx: ValidationContext) {
  if (!tierId) return MESSAGES.tierRequired;
  if (ctx.serviceMappingsStatus === "loading") return MESSAGES.tierMappingsLoading;
  if (ctx.serviceMappingsStatus === "error") return MESSAGES.tierMappingsError;
  // A tier with nothing mapped would hand the institution a plan that cannot
  // serve a single request.
  if (!ctx.tierIdsWithServices.has(String(tierId))) return ctx.noServicesMessage;
  return undefined;
}

function validateBudget(
  budget: string,
  currentBudget: number | null | undefined,
  budgetSettled: boolean,
) {
  if (!budget.trim()) return MESSAGES.budgetRequired;
  const value = Number(budget);
  if (!Number.isFinite(value) || value <= 0) return MESSAGES.budgetNotPositive;
  if (value > MAX_BUDGET) return MESSAGES.budgetTooLarge;
  if (!budgetSettled && budgetRevisionFor(value, currentBudget) === null)
    return MESSAGES.budgetUnchanged;
  return undefined;
}

function validateEffectiveFrom(effectiveFrom: string, today: string) {
  if (!effectiveFrom) return MESSAGES.effectiveFromRequired;
  if (effectiveFrom < today) return MESSAGES.effectiveFromBackdated;
  return undefined;
}

function validateEffectiveTo(
  effectiveTo: string,
  effectiveFrom: string,
  today: string,
) {
  if (!effectiveTo) return MESSAGES.effectiveToRequired;
  if (effectiveTo <= today) return MESSAGES.effectiveToNotFuture;
  if (effectiveFrom) {
    if (effectiveTo === effectiveFrom) return MESSAGES.effectiveToSameAsFrom;
    if (effectiveTo < effectiveFrom) return MESSAGES.effectiveToBeforeFrom;
  }
  return undefined;
}

/**
 * All four fields are required together: assigning a tier is one decision —
 * which tier, how much, and for how long — so a partial answer is not a
 * lesser version of it, it is an unusable one.
 *
 * Safe to compare the date strings with `<` / `===`: `<input type="date">`
 * values are fixed-width zero-padded YYYY-MM-DD, so lexical order is
 * chronological order.
 */
function validateForm(values: FormValues, ctx: ValidationContext): FieldErrors {
  const errors: FieldErrors = {};
  const tier = validateTier(values.tierId, ctx);
  if (tier) errors.tier = tier;
  const budget = validateBudget(
    values.budget,
    ctx.currentBudget,
    ctx.budgetSettled,
  );
  if (budget) errors.budget = budget;
  const from = validateEffectiveFrom(values.effectiveFrom, ctx.today);
  if (from) errors.effectiveFrom = from;
  const to = validateEffectiveTo(values.effectiveTo, values.effectiveFrom, ctx.today);
  if (to) errors.effectiveTo = to;
  return errors;
}

export type UseAssignTierOptions = {
  isOpen: boolean;
  tenant: TenantView | null;
  serviceMappingsStatus: ServiceMappingsStatus;
  tierIdsWithServices: Set<string>;
  noServicesMessage: string;
  /** Refresh caches once the assignment has landed. */
  onAssigned: (tenantId: string) => Promise<void> | void;
  onClose: () => void;
};

/**
 * Form state and submit orchestration for the Assign Tier modal.
 */
export function useAssignTier({
  isOpen,
  tenant,
  serviceMappingsStatus,
  tierIdsWithServices,
  noServicesMessage,
  onAssigned,
  onClose,
}: UseAssignTierOptions) {
  const toast = useToast();

  // Pinned for the lifetime of one open modal so a session left open across
  // midnight cannot have the floor shift under a date already chosen.
  const today = useMemo(
    () => todayDateInputValue(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isOpen],
  );

  const [values, setValues] = useState<FormValues>(() => initialForm(today));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isAssigning, setIsAssigning] = useState(false);
  const [committedBudget, setCommittedBudget] = useState<number | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setValues(initialForm(today));
    setErrors({});
    setSubmitError(null);
    setCommittedBudget(null);
  }, [isOpen, today]);

  const currentBudget = committedBudget ?? tenant?.allocated_budget ?? null;
  const budgetSettled = committedBudget !== null;

  const validationContext = useMemo(
    () => ({
      today,
      serviceMappingsStatus,
      tierIdsWithServices,
      noServicesMessage,
      currentBudget,
      budgetSettled,
    }),
    [
      today,
      serviceMappingsStatus,
      tierIdsWithServices,
      noServicesMessage,
      currentBudget,
      budgetSettled,
    ],
  );

  const setTierId = useCallback((tierId: string) => {
    setValues((prev) => ({ ...prev, tierId }));
    setErrors((prev) => ({ ...prev, tier: undefined }));
  }, []);

  const setBudget = useCallback((raw: string) => {
    setValues((prev) => ({ ...prev, budget: sanitizeBudgetInput(raw) }));
    setErrors((prev) => ({ ...prev, budget: undefined }));
  }, []);

  const setEffectiveFrom = useCallback((effectiveFrom: string) => {
    setValues((prev) => ({
      ...prev,
      effectiveFrom,
      // An Effective To the new Effective From has put out of range would
      // otherwise sit there looking valid until submit.
      effectiveTo:
        effectiveFrom && prev.effectiveTo && prev.effectiveTo <= effectiveFrom
          ? ""
          : prev.effectiveTo,
    }));
    setErrors((prev) => ({ ...prev, effectiveFrom: undefined, effectiveTo: undefined }));
  }, []);

  const setEffectiveTo = useCallback((effectiveTo: string) => {
    setValues((prev) => ({ ...prev, effectiveTo }));
    setErrors((prev) => ({ ...prev, effectiveTo: undefined }));
  }, []);

  const close = useCallback(() => {
    if (isAssigning) return;
    onClose();
  }, [isAssigning, onClose]);

  const submit = useCallback(async () => {
    if (!tenant) return;

    const found = validateForm(values, validationContext);
    setErrors(found);
    setSubmitError(null);
    if (Object.keys(found).length > 0) return;

    const tenantId = String(tenant.tenant_id);
    const enteredBudget = Number(values.budget);
    const revision = budgetRevisionFor(enteredBudget, currentBudget);

    setIsAssigning(true);
    try {
      if (revision) {
        const res = await adjustTenantBudget({
          tenant_id: tenantId,
          action: revision.action,
          amount: revision.amount,
          budget_effective_from: dateInputToStartOfDayIso(values.effectiveFrom),
          budget_effective_to: dateInputToEndOfDayIso(values.effectiveTo),
        });
        const committed = Number(res.allocated_budget);
        setCommittedBudget(Number.isFinite(committed) ? committed : enteredBudget);
      }

      if (String(tenant.tier_id ?? "") !== values.tierId) {
        await changeTenantTier(tenantId, values.tierId);
      }

      toast({
        title: "Tier assigned",
        description: `Tier assigned to "${tenant.organisation}" successfully.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      await onAssigned(tenantId);
      onClose();
    } catch (err: unknown) {
      // parseError already applies the institution-copy substitution.
      setSubmitError(parseError(err).message);
    } finally {
      setIsAssigning(false);
    }
  }, [
    tenant,
    values,
    validationContext,
    currentBudget,
    toast,
    onAssigned,
    onClose,
  ]);

  return {
    values,
    errors,
    submitError,
    isAssigning,
    today,
    effectiveToMin: budgetWindowToMinDate(values.effectiveFrom, today),
    showTierNoServices: tierHasNoServices(values.tierId, validationContext),
    setTierId,
    setBudget,
    setEffectiveFrom,
    setEffectiveTo,
    submit,
    close,
  };
}
