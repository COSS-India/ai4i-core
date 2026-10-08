import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useToast } from "@chakra-ui/react";
import {
  createApplication,
  getApplicationErrorCode,
  listAllApplicationsForBudget,
  listApplications,
  updateApplication,
  updateApplicationAllocations,
  type ApplicationApiKeyRow,
} from "../../../services/applicationService";
import {
  fetchApplicationUsageDetail,
  fetchApplicationUsageList,
} from "../../../services/applicationUsageService";
import { countActiveApiKeysForApplications } from "../../../services/apiKeyService";
import { parseError } from "../../../utils/errorHandler";
import {
  allocatedKeyFloorAmount,
  allocatedKeyHolders,
  previewKeyCascade,
  roundMoney,
  roundPct,
  type KeyAllocationHolder,
} from "../../../utils/applicationBudgetPreview";
import type { AllocationUpdate, Application } from "../../../types/application";
import {
  allocationErrorEntityId,
  belowConsumedAmount,
  BUDGET_TOAST,
  BUDGET_VALIDATION,
  mapAllocationError,
  mapBelowConsumedError,
  percentageBoundMessage,
  totalApplicationsOver100,
} from "../../../config/budgetMessages";
import { FIELD_HINTS } from "../../../config/fieldHints";
import type { PercentageBound } from "../../common/PercentageStepper";
import {
  allocationDriftTolerance,
  applyResolved,
  belowKeyAllocationError,
  buildDraftFromApplication,
  evaluateRowError,
  isApplicationBudgetEditable,
  rowHasBudgetChange,
  toInstitutionConsumedPct,
  type BulkBudgetDraft,
} from "../applicationBudgetDraft";

export type { BulkBudgetDraft };

const PAGE_SIZE = 25;

export type ApplicationForm = {
  name: string;
  description: string;
  domain: string;
  allocated_percentage: string;
};

const EMPTY_FORM: ApplicationForm = {
  name: "",
  description: "",
  domain: "",
  allocated_percentage: "",
};

function mapApplicationAllocationError(error: unknown): string {
  return mapAllocationError(error, getApplicationErrorCode, "application");
}

function mapBelowConsumedErrorForApplication(message: string): string {
  return mapBelowConsumedError(message, "application");
}

function usageDetailToKeyRows(
  apiKeys: Awaited<ReturnType<typeof fetchApplicationUsageDetail>>["apiKeys"],
  appAllocatedAmount: number,
): ApplicationApiKeyRow[] {
  return apiKeys
    .filter((key) => key.isActive)
    .map((key) => ({
      id: key.keyId,
      key_name: key.keyName,
      allocated_percentage:
        appAllocatedAmount > 0 && key.allocatedBudget.amount > 0
          ? roundPct((key.allocatedBudget.amount / appAllocatedAmount) * 100)
          : key.allocatedBudget.percentage,
      allocated_budget: key.allocatedBudget.amount,
      consumed_budget: key.spendBudget.amount,
      is_active: key.isActive,
    }));
}

function parsePct(raw: string): number | null | "invalid" {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return "invalid";
  return n;
}

function sumAllocatedPercentage(apps: Application[]): number {
  return apps.reduce((sum, app) => sum + (app.allocated_percentage ?? 0), 0);
}


function buildAllocationUpdate(row: BulkBudgetDraft): AllocationUpdate | null {
  if (row.resolvedPct == null) return null;
  return {
    application_id: row.application_id,
    allocation: { type: "PERCENTAGE", value: row.resolvedPct },
  };
}

/** Keep inactive Applications at their current share so a sibling save does not re-fit them. */
function buildFrozenAllocationUpdate(row: BulkBudgetDraft): AllocationUpdate | null {
  if (row.originalPct != null) {
    return {
      application_id: row.application_id,
      allocation: { type: "PERCENTAGE", value: row.originalPct },
    };
  }
  if (row.resolvedAmount != null) {
    return {
      application_id: row.application_id,
      allocation: { type: "FIXED", value: row.resolvedAmount },
    };
  }
  if (row.resolvedPct != null) {
    return {
      application_id: row.application_id,
      allocation: { type: "PERCENTAGE", value: row.resolvedPct },
    };
  }
  return null;
}

export function useApplicationManagement(
  tenantId: string,
  institutionBudget: number | null,
  currency = "INR",
) {
  const toast = useToast();
  const [applications, setApplications] = useState<Application[]>([]);
  /** Count from the full budget list, so search does not change the overview. */
  const [institutionApplicationCount, setInstitutionApplicationCount] = useState<number | null>(
    null,
  );
  const [totalAllocatedPct, setTotalAllocatedPct] = useState(0);
  const [tenantBudget, setTenantBudget] = useState(institutionBudget ?? 0);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [selected, setSelected] = useState<Application | null>(null);
  const [form, setForm] = useState<ApplicationForm>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [formBanner, setFormBanner] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [budgetDraft, setBudgetDraft] = useState("");
  const [budgetBanner, setBudgetBanner] = useState<string | null>(null);
  const [budgetStepperHint, setBudgetStepperHint] = useState<string | null>(null);
  /** Null unless usage detail succeeded. Never treat a failed load as ₹0. */
  const [budgetUsage, setBudgetUsage] = useState<{
    allocated: number;
    consumed: number;
    remaining: number;
    keyFloorAmount: number;
    keyHolders: KeyAllocationHolder[];
  } | null>(null);
  const [budgetUsageState, setBudgetUsageState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const budgetUsageRequestRef = useRef<string | null>(null);
  const tableRequestRef = useRef(0);

  const [bulkBudgetOpen, setBulkBudgetOpen] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkRows, setBulkRows] = useState<BulkBudgetDraft[]>([]);
  const [bulkBanner, setBulkBanner] = useState<string | null>(null);
  const [statusBusyId, setStatusBusyId] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    setTenantBudget(institutionBudget ?? 0);
  }, [institutionBudget]);

  const budgetApplicationsRef = useRef<{
    tenantId: string;
    applications: Application[];
  } | null>(null);
  /** Drops in-flight key loads when the bulk dialog is opened again. */
  const bulkLoadGenerationRef = useRef(0);

  const loadAllocationSummary = useCallback(async () => {
    if (!tenantId) return;
    try {
      const all = await listAllApplicationsForBudget(tenantId);
      budgetApplicationsRef.current = {
        tenantId,
        applications: all.applications,
      };
      setTotalAllocatedPct(sumAllocatedPercentage(all.applications));
      setInstitutionApplicationCount(all.applications.length);
    } catch {
      // Keep the previous summary if the full fetch fails.
    }
  }, [tenantId]);

  const loadTable = useCallback(async () => {
    if (!tenantId) return;
    const requestId = ++tableRequestRef.current;
    setIsLoading(true);
    setLoadError(null);
    try {
      const list = await listApplications(tenantId, {
        search: search || undefined,
        page,
        size: pageSize,
      });
      if (requestId !== tableRequestRef.current) return;
      setApplications(list.applications);
      setTotal(list.pagination.total);
      setIsLoading(false);
      const counts = await countActiveApiKeysForApplications(
        list.applications.map((app) => app.application_id),
      );
      if (requestId !== tableRequestRef.current) return;
      setApplications((prev) =>
        prev.map((app) => {
          const count = counts.get(app.application_id);
          return count === undefined ? app : { ...app, api_key_count: count };
        }),
      );
    } catch (error) {
      if (requestId !== tableRequestRef.current) return;
      setLoadError(parseError(error).message);
    } finally {
      if (requestId === tableRequestRef.current) setIsLoading(false);
    }
  }, [tenantId, search, page, pageSize]);

  useEffect(() => {
    void loadTable();
  }, [loadTable]);

  useEffect(() => {
    void loadAllocationSummary();
  }, [loadAllocationSummary]);

  const reload = useCallback(async () => {
    await Promise.all([loadTable(), loadAllocationSummary()]);
  }, [loadTable, loadAllocationSummary]);

  const remainingPct = Math.max(0, 100 - totalAllocatedPct);
  const institutionBudgetUnset = tenantBudget <= 0;

  const bulkLiveTotalPct = useMemo(() => {
    return bulkRows.reduce((sum, row) => sum + (row.resolvedPct ?? 0), 0);
  }, [bulkRows]);

  const bulkCanSave = useMemo(() => {
    if (institutionBudgetUnset) return false;
    if (bulkLoading || bulkRows.length === 0) return false;
    if (bulkLiveTotalPct > 100 + 1e-6) return false;
    if (bulkRows.some((row) => row.rowError)) return false;
    const changedRows = bulkRows.filter(
      (row) => isApplicationBudgetEditable(row.status) && rowHasBudgetChange(row),
    );
    if (changedRows.length === 0) return false;
    if (changedRows.some((row) => !row.keysLoaded)) return false;
    return true;
  }, [institutionBudgetUnset, bulkLoading, bulkRows, bulkLiveTotalPct]);

  const loadKeysForRow = useCallback(async (applicationId: string) => {
    if (!tenantId) return;
    const generation = bulkLoadGenerationRef.current;
    setBulkRows((prev) =>
      prev.map((row) =>
        row.application_id === applicationId
          ? { ...row, keysLoading: true, rowError: null }
          : row,
      ),
    );
    try {
      const detail = await fetchApplicationUsageDetail(
        tenantId,
        Number(applicationId),
      );
      if (bulkLoadGenerationRef.current !== generation) return;
      const activeKeys = usageDetailToKeyRows(
        detail.apiKeys,
        detail.allocatedBudget.amount,
      );
      setBulkRows((prev) =>
        prev.map((row) => {
          if (row.application_id !== applicationId) return row;
          const keyPreviews =
            row.resolvedAmount != null
              ? previewKeyCascade(row.resolvedAmount, activeKeys)
              : [];
          const next = {
            ...row,
            keysLoading: false,
            keysLoaded: true,
            keys: activeKeys,
            keyPreviews,
            consumed_percentage: toInstitutionConsumedPct(
              detail.spendBudget.amount,
              tenantBudget,
            ),
            consumed_budget: detail.spendBudget.amount,
          };
          return { ...next, rowError: evaluateRowError(next, tenantBudget, currency) };
        }),
      );
    } catch (error) {
      if (bulkLoadGenerationRef.current !== generation) return;
      const message = parseError(error).message;
      setBulkRows((prev) =>
        prev.map((row) =>
          row.application_id === applicationId
            ? {
                ...row,
                keysLoading: false,
                keysLoaded: false,
                rowError: `Could not load API keys for this Application: ${message}`,
              }
            : row,
        ),
      );
    }
  }, [currency, tenantBudget, tenantId]);

  const openBulkBudget = useCallback(async () => {
    if (!tenantId) return;
    const generation = bulkLoadGenerationRef.current + 1;
    bulkLoadGenerationRef.current = generation;
    setBulkBudgetOpen(true);
    setBulkBanner(null);
    setBulkLoading(true);
    setBulkRows([]);
    try {
      const cached = budgetApplicationsRef.current;
      const list =
        cached?.tenantId === tenantId
          ? { applications: cached.applications }
          : await listAllApplicationsForBudget(tenantId);
      if (cached?.tenantId !== tenantId) {
        budgetApplicationsRef.current = {
          tenantId,
          applications: list.applications,
        };
      }
      let usageWarning: string | null = null;
      let usageRows: Awaited<
        ReturnType<typeof fetchApplicationUsageList>
      >["data"] = [];
      try {
        const usage = await fetchApplicationUsageList({ tenantId, limit: 500 });
        usageRows = usage.data;
      } catch (usageError) {
        usageWarning = `Could not load consumption data: ${parseError(usageError).message}`;
      }
      if (bulkLoadGenerationRef.current !== generation) return;
      const usageByAppId = new Map(
        usageRows.map((row) => [String(row.applicationId), row]),
      );
      const effectiveBudget = institutionBudget ?? 0;
      setTenantBudget(effectiveBudget);
      const drafts = list.applications.map((app) => {
        const draft = buildDraftFromApplication(app);
        const usageRow = usageByAppId.get(app.application_id);
        if (usageRow) {
          draft.allocated_amount = usageRow.allocatedBudget.amount;
          draft.consumed_percentage = toInstitutionConsumedPct(
            usageRow.spendBudget.amount,
            effectiveBudget,
          );
          draft.consumed_budget = usageRow.spendBudget.amount;
          draft.remaining_budget = usageRow.remainingBudget.amount;
        }
        if (
          draft.resolvedPct != null &&
          draft.resolvedAmount == null &&
          effectiveBudget > 0
        ) {
          draft.resolvedAmount = roundMoney((effectiveBudget * draft.resolvedPct) / 100);
        }
        if (isApplicationBudgetEditable(draft.status)) {
          draft.keysLoading = true;
        }
        return draft;
      });
      setBulkRows(drafts);
      if (usageWarning) setBulkBanner(usageWarning);
      for (const draft of drafts) {
        if (isApplicationBudgetEditable(draft.status)) {
          void loadKeysForRow(draft.application_id);
        }
      }
    } catch (error) {
      if (bulkLoadGenerationRef.current !== generation) return;
      setBulkBanner(mapApplicationAllocationError(error));
    } finally {
      if (bulkLoadGenerationRef.current === generation) {
        setBulkLoading(false);
      }
    }
  }, [tenantId, institutionBudget, loadKeysForRow]);

  const onBulkRowFocus = useCallback(
    (applicationId: string) => {
      const row = bulkRows.find((r) => r.application_id === applicationId);
      if (!row || row.keysLoaded || row.keysLoading) return;
      void loadKeysForRow(applicationId);
    },
    [bulkRows, loadKeysForRow],
  );

  const onBulkPctChange = useCallback(
    (applicationId: string, value: string) => {
      setBulkRows((prev) =>
        prev.map((row) => {
          if (row.application_id !== applicationId) return row;
          if (!isApplicationBudgetEditable(row.status)) return row;
          const next = applyResolved(row, tenantBudget, value, currency);
          if (row.keysLoaded && next.resolvedAmount != null) {
            next.keyPreviews = previewKeyCascade(next.resolvedAmount, row.keys);
            next.rowError = evaluateRowError(next, tenantBudget, currency);
          }
          return next;
        }),
      );
      onBulkRowFocus(applicationId);
    },
    [currency, tenantBudget, onBulkRowFocus],
  );

  const onBulkPctBoundHit = useCallback((applicationId: string, bound: PercentageBound) => {
    setBulkRows((prev) =>
      prev.map((row) =>
        row.application_id === applicationId && isApplicationBudgetEditable(row.status)
          ? { ...row, inputNotice: percentageBoundMessage(bound) }
          : row,
      ),
    );
  }, []);

  const handleSaveBulkBudget = async () => {
    if (!bulkCanSave) return;
    const activeChanges = bulkRows
      .filter((row) => isApplicationBudgetEditable(row.status))
      .filter(rowHasBudgetChange)
      .map(buildAllocationUpdate)
      .filter((row): row is AllocationUpdate => row != null);
    if (activeChanges.length === 0) {
      setBulkBudgetOpen(false);
      return;
    }
    // Pin inactive rows at their current allocation so the API's unlisted
    // re-fit does not rewrite them when active siblings change.
    const inactivePins = bulkRows
      .filter((row) => !isApplicationBudgetEditable(row.status))
      .map(buildFrozenAllocationUpdate)
      .filter((row): row is AllocationUpdate => row != null);
    const changes = [...activeChanges, ...inactivePins];
    setIsSaving(true);
    setBulkBanner(null);
    try {
      await updateApplicationAllocations(tenantId, changes);
      toast({
        title: BUDGET_TOAST.applicationBudgetsUpdated,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setBulkBudgetOpen(false);
      await reload();
    } catch (error) {
      const code = getApplicationErrorCode(error);
      const message = parseError(error).message;
      if (code === "ALLOCATION_BELOW_CONSUMED") {
        const appId = allocationErrorEntityId(error, "application");
        const rowMessage = mapBelowConsumedErrorForApplication(message);
        if (appId) {
          let matched = false;
          setBulkRows((prev) => {
            if (!prev.some((row) => row.application_id === appId)) {
              return prev;
            }
            matched = true;
            return prev.map((row) =>
              row.application_id === appId ? { ...row, rowError: rowMessage } : row,
            );
          });
          if (!matched) setBulkBanner(rowMessage);
        } else {
          setBulkBanner(rowMessage);
        }
      } else {
        setBulkBanner(mapApplicationAllocationError(error));
      }
    } finally {
      setIsSaving(false);
    }
  };

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setFormErrors({});
    setFormBanner(null);
    setCreateOpen(true);
  };

  const openEdit = (app: Application) => {
    setSelected(app);
    setForm({
      name: app.name,
      description: app.description,
      domain: app.domain,
      allocated_percentage: "",
    });
    setFormErrors({});
    setFormBanner(null);
    setEditOpen(true);
  };

  const openView = (app: Application) => {
    setSelected(app);
    setViewOpen(true);
  };

  const openBudget = (app: Application) => {
    if (!isApplicationBudgetEditable(app.status)) return;
    setSelected(app);
    setBudgetDraft(
      app.allocated_percentage == null ? "" : String(app.allocated_percentage),
    );
    setBudgetBanner(null);
    setBudgetStepperHint(null);
    setBudgetUsage(null);
    setBudgetUsageState("loading");
    setBudgetOpen(true);
    const requestId = app.application_id;
    budgetUsageRequestRef.current = requestId;
    void fetchApplicationUsageDetail(tenantId, Number(app.application_id))
      .then((detail) => {
        if (budgetUsageRequestRef.current !== requestId) return;
        const activeKeys = usageDetailToKeyRows(
          detail.apiKeys,
          detail.allocatedBudget.amount,
        );
        const keyHolders = allocatedKeyHolders(activeKeys);
        const keyFloorAmount = allocatedKeyFloorAmount(activeKeys);
        setBudgetUsage({
          allocated: detail.allocatedBudget.amount,
          consumed: detail.spendBudget.amount,
          remaining: detail.remainingBudget.amount,
          keyFloorAmount,
          keyHolders,
        });
        setBudgetUsageState("ready");
      })
      .catch(() => {
        if (budgetUsageRequestRef.current !== requestId) return;
        setBudgetUsage(null);
        setBudgetUsageState("error");
      });
  };

  const budgetOthersAllocated = useMemo(() => {
    if (!selected) return totalAllocatedPct;
    return totalAllocatedPct - (selected.allocated_percentage ?? 0);
  }, [selected, totalAllocatedPct]);

  const budgetParsed = parsePct(budgetDraft);
  const budgetValue =
    budgetParsed == null || budgetParsed === "invalid" ? 0 : budgetParsed;
  const budgetLiveTotal = budgetOthersAllocated + budgetValue;
  const budgetAvailable = Math.max(0, 100 - budgetOthersAllocated);

  const budgetFieldError = useMemo(() => {
    if (budgetDraft.trim() === "" || budgetParsed === "invalid") {
      return BUDGET_VALIDATION.enterValidAllocationPercentage;
    }
    if (budgetParsed != null && budgetParsed < 0) return BUDGET_VALIDATION.budgetCannotBeNegative;
    if (budgetParsed != null && budgetParsed > 100) {
      return BUDGET_VALIDATION.percentageMustBeBetween0And100;
    }
    if (budgetParsed != null && tenantBudget > 0 && budgetUsage) {
      const enteredAmount = roundMoney((tenantBudget * budgetParsed) / 100);
      const keyFloorError = belowKeyAllocationError(
        selected?.name ?? "This Application",
        enteredAmount,
        budgetUsage.keyHolders,
        budgetUsage.consumed,
        tenantBudget,
        currency,
      );
      if (keyFloorError) return keyFloorError;
      const tolerance = allocationDriftTolerance(Math.max(budgetUsage.keyHolders.length, 1));
      if (budgetUsage.consumed > 0 && enteredAmount < budgetUsage.consumed - tolerance) {
        return belowConsumedAmount(budgetUsage.consumed);
      }
    }
    if (budgetLiveTotal > 100 + 1e-6) {
      return totalApplicationsOver100(budgetLiveTotal);
    }
    return null;
  }, [budgetDraft, budgetParsed, budgetLiveTotal, budgetUsage, currency, selected, tenantBudget]);

  const validateCreate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!form.name.trim()) errors.name = "Application name is required.";
    const pct = parsePct(form.allocated_percentage);
    if (pct === "invalid") errors.allocated_percentage = BUDGET_VALIDATION.enterValidPercentage;
    else if (pct != null && pct < 0) errors.allocated_percentage = BUDGET_VALIDATION.budgetCannotBeNegative;
    else if (pct != null && pct > 100) {
      errors.allocated_percentage = BUDGET_VALIDATION.percentageMustBeBetween0And100;
    } else if (pct != null && pct > remainingPct + 1e-6) {
      errors.allocated_percentage = `Cannot exceed ${remainingPct.toFixed(2)}% still available.`;
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreate = async () => {
    if (!validateCreate()) return;
    setIsSaving(true);
    setFormBanner(null);
    const pct = parsePct(form.allocated_percentage);
    try {
      await createApplication(tenantId, {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        domain: form.domain.trim() || undefined,
        allocated_percentage: pct == null || pct === "invalid" ? undefined : pct,
      });
      toast({ title: "Application created.", status: "success", duration: 3000, isClosable: true });
      setCreateOpen(false);
      setPage(1);
      await reload();
    } catch (error) {
      const code = getApplicationErrorCode(error);
      const message = parseError(error).message;
      if (code === "APPLICATION_NAME_ALREADY_EXISTS") {
        setFormErrors((prev) => ({ ...prev, name: message }));
      } else if (code === "ALLOCATION_TOTAL_EXCEEDED") {
        setFormBanner(message);
      } else {
        setFormBanner(message);
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveBudget = async () => {
    if (!selected) return;
    if (!isApplicationBudgetEditable(selected.status)) return;
    if (budgetFieldError) return;
    const next =
      budgetParsed == null || budgetParsed === "invalid" ? 0 : budgetParsed;
    if (
      selected.allocated_percentage != null &&
      Math.abs(next - selected.allocated_percentage) < 1e-6
    ) {
      setBudgetOpen(false);
      return;
    }
    if (selected.allocated_percentage == null && budgetDraft.trim() === "") {
      setBudgetOpen(false);
      return;
    }
    setIsSaving(true);
    setBudgetBanner(null);
    try {
      await updateApplicationAllocations(tenantId, [
        {
          application_id: selected.application_id,
          allocation: { type: "PERCENTAGE", value: next },
        },
      ]);
      toast({
        title: `Budget for "${selected.name}" updated to ${next}%.`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setBudgetOpen(false);
      await reload();
    } catch (error) {
      setBudgetBanner(mapApplicationAllocationError(error));
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggleStatus = async (app: Application) => {
    const nextStatus = app.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
    setStatusBusyId(app.application_id);
    try {
      await updateApplication(tenantId, app.application_id, { status: nextStatus });
      toast({
        title: nextStatus === "ACTIVE" ? "Application activated." : "Application deactivated.",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      await reload();
    } catch (error) {
      toast({
        title: parseError(error).message,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setStatusBusyId(null);
    }
  };

  const handleEdit = async () => {
    if (!selected) return;
    const errors: Record<string, string> = {};
    if (!form.name.trim()) errors.name = "Application name is required.";
    setFormErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setIsSaving(true);
    setFormBanner(null);
    try {
      await updateApplication(tenantId, selected.application_id, {
        name: form.name.trim(),
        description: form.description.trim(),
        domain: form.domain.trim(),
      });
      toast({ title: "Application updated.", status: "success", duration: 3000, isClosable: true });
      setEditOpen(false);
      setViewOpen(false);
      await reload();
    } catch (error) {
      const code = getApplicationErrorCode(error);
      const message = parseError(error).message;
      if (code === "APPLICATION_NAME_ALREADY_EXISTS") {
        setFormErrors((prev) => ({ ...prev, name: message }));
      } else {
        setFormBanner(message);
      }
    } finally {
      setIsSaving(false);
    }
  };

  return {
    applications,
    total,
    page,
    pageSize,
    setPage,
    setPageSize: (size: number) => {
      setPageSize(size);
      setPage(1);
    },
    searchInput,
    setSearchInput: (value: string) => {
      setSearchInput(value);
      setPage(1);
    },
    isLoading,
    loadError,
    remainingPct,
    totalAllocatedPct,
    institutionApplicationCount,
    tenantBudget,
    institutionBudgetUnset,
    createOpen,
    setCreateOpen,
    editOpen,
    setEditOpen,
    viewOpen,
    setViewOpen,
    budgetOpen,
    setBudgetOpen,
    selected,
    form,
    setForm,
    formErrors,
    formBanner,
    isSaving,
    openCreate,
    openEdit,
    openView,
    openBudget,
    handleCreate,
    handleEdit,
    handleSaveBudget,
    budgetDraft,
    setBudgetDraft: (next: string) => {
      setBudgetDraft(next);
      setBudgetStepperHint(null);
    },
    onBudgetBoundHit: (bound: PercentageBound) => {
      setBudgetStepperHint(percentageBoundMessage(bound));
    },
    budgetStepperHint,
    budgetLiveTotal,
    budgetFieldError,
    budgetAvailable,
    budgetUsage,
    budgetUsageState,
    budgetBanner,
    bulkBudgetOpen,
    setBulkBudgetOpen,
    bulkLoading,
    bulkRows,
    bulkBanner,
    bulkLiveTotalPct,
    bulkCanSave,
    openBulkBudget,
    onBulkRowFocus,
    onBulkPctChange,
    onBulkPctBoundHit,
    handleSaveBulkBudget,
    statusBusyId,
    handleToggleStatus,
    reload,
  };
}
