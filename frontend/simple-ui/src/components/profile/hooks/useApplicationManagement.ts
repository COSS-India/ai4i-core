import { useCallback, useEffect, useMemo, useState } from "react";
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
import { parseError } from "../../../utils/errorHandler";
import {
  previewKeyCascade,
  resolveApplicationBudget,
  roundMoney,
  roundPct,
  type ApplicationKeyPreview,
} from "../../../utils/applicationBudgetPreview";
import type {
  AllocationUpdate,
  Application,
  ApplicationStatus,
} from "../../../types/application";
import {
  allocationErrorEntityId,
  belowConsumedAmount,
  belowConsumedPct,
  belowConsumedPctRaw,
  BUDGET_TOAST,
  BUDGET_VALIDATION,
  keyWouldDropBelowConsumed,
  mapAllocationError,
  mapBelowConsumedError,
  totalApplicationsOver100,
} from "../../../config/budgetMessages";
import { FIELD_HINTS } from "../../../config/fieldHints";

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

export type BulkBudgetDraft = {
  application_id: string;
  name: string;
  status: ApplicationStatus;
  consumed_percentage: number | null;
  consumed_budget: number | null;
  originalPct: number | null;
  pctInput: string;
  amountInput: string;
  resolvedPct: number | null;
  resolvedAmount: number | null;
  lastEditMode: "percentage" | "amount";
  keysLoading: boolean;
  keysLoaded: boolean;
  keys: ApplicationApiKeyRow[];
  keyPreviews: ApplicationKeyPreview[];
  rowError: string | null;
};

function mapApplicationAllocationError(error: unknown): string {
  return mapAllocationError(error, getApplicationErrorCode);
}

function mapBelowConsumedErrorForApplication(message: string): string {
  return mapBelowConsumedError(message, "application");
}

/** Spend as a share of the Institution budget (not the Application's own allocation). */
function toInstitutionConsumedPct(
  consumedAmount: number,
  tenantBudget: number,
): number | null {
  if (tenantBudget <= 0) return null;
  return roundPct((consumedAmount / tenantBudget) * 100);
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
        appAllocatedAmount > 0
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

function pctString(value: number | null): string {
  if (value == null) return "";
  return String(value);
}

function amountString(value: number | null): string {
  if (value == null) return "";
  return String(value);
}

function sumAllocatedPercentage(apps: Application[]): number {
  return apps.reduce((sum, app) => sum + (app.allocated_percentage ?? 0), 0);
}


function buildAllocationUpdate(row: BulkBudgetDraft): AllocationUpdate | null {
  if (row.resolvedPct == null) return null;
  if (row.lastEditMode === "amount" && row.resolvedAmount != null) {
    return {
      application_id: row.application_id,
      allocation: { type: "FIXED", value: row.resolvedAmount },
    };
  }
  return {
    application_id: row.application_id,
    allocation: { type: "PERCENTAGE", value: row.resolvedPct },
  };
}

function rowHasBudgetChange(row: BulkBudgetDraft): boolean {
  const orig = row.originalPct;
  const next = row.resolvedPct;
  if (orig == null && next == null) return false;
  if (orig == null || next == null) return true;
  return Math.abs(orig - next) > 1e-6;
}

function isApplicationBudgetEditable(status: ApplicationStatus): boolean {
  return status === "ACTIVE";
}

function buildDraftFromApplication(app: Application): BulkBudgetDraft {
  const pct = app.allocated_percentage;
  const amount = app.allocated_budget;
  return {
    application_id: app.application_id,
    name: app.name,
    status: app.status,
    consumed_percentage: app.consumed_percentage ?? null,
    consumed_budget: app.consumed_budget ?? null,
    originalPct: pct,
    pctInput: pctString(pct),
    amountInput: amountString(amount),
    resolvedPct: pct,
    resolvedAmount: amount,
    lastEditMode: "percentage",
    keysLoading: false,
    keysLoaded: false,
    keys: [],
    keyPreviews: [],
    rowError: null,
  };
}

function evaluateRowError(
  row: BulkBudgetDraft,
  tenantBudget: number,
): string | null {
  if (row.resolvedPct == null) return null;
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

function applyResolved(
  row: BulkBudgetDraft,
  tenantBudget: number,
  mode: "percentage" | "amount",
  raw: string,
): BulkBudgetDraft {
  const trimmed = raw.trim();
  if (trimmed === "") {
    const next = {
      ...row,
      pctInput: "",
      amountInput: "",
      resolvedPct: null,
      resolvedAmount: null,
      keyPreviews: [],
      rowError: null,
    };
    return { ...next, rowError: evaluateRowError(next, tenantBudget) };
  }
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) {
    return { ...row, rowError: BUDGET_VALIDATION.enterValidNumber };
  }
  const resolved = resolveApplicationBudget(mode, numeric, tenantBudget);
  if (!resolved) {
    if (mode === "amount") {
      return {
        ...row,
        amountInput: trimmed,
        rowError: FIELD_HINTS.application.amountRequiresInstitutionBudget,
      };
    }
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
    amountInput: resolved.amount != null ? String(resolved.amount) : "",
    resolvedPct: resolved.pct,
    resolvedAmount: resolved.amount,
    keyPreviews,
    rowError: null,
  };
  return { ...next, rowError: evaluateRowError(next, tenantBudget) };
}

export function useApplicationManagement(tenantId: string, institutionBudget: number | null) {
  const toast = useToast();
  const [applications, setApplications] = useState<Application[]>([]);
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
  const [budgetFloor, setBudgetFloor] = useState(0);
  const [budgetBanner, setBudgetBanner] = useState<string | null>(null);
  const [budgetStepperHint, setBudgetStepperHint] = useState<string | null>(null);

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

  const loadAllocationSummary = useCallback(async () => {
    if (!tenantId) return;
    try {
      const all = await listAllApplicationsForBudget(tenantId);
      setTotalAllocatedPct(sumAllocatedPercentage(all.applications));
    } catch {
      // Keep the previous summary if the full fetch fails.
    }
  }, [tenantId]);

  const loadTable = useCallback(async () => {
    if (!tenantId) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const list = await listApplications(tenantId, {
        search: search || undefined,
        page,
        size: pageSize,
      });
      setApplications(list.applications);
      setTotal(list.pagination.total);
    } catch (error) {
      setLoadError(parseError(error).message);
    } finally {
      setIsLoading(false);
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
          return { ...next, rowError: evaluateRowError(next, tenantBudget) };
        }),
      );
    } catch (error) {
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
  }, [tenantBudget, tenantId]);

  const openBulkBudget = useCallback(async () => {
    if (!tenantId) return;
    setBulkBudgetOpen(true);
    setBulkBanner(null);
    setBulkLoading(true);
    setBulkRows([]);
    try {
      const list = await listAllApplicationsForBudget(tenantId);
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
      const usageByAppId = new Map(
        usageRows.map((row) => [String(row.applicationId), row]),
      );
      const effectiveBudget = institutionBudget ?? 0;
      setTenantBudget(effectiveBudget);
      const drafts = list.applications.map((app) => {
        const draft = buildDraftFromApplication(app);
        const usageRow = usageByAppId.get(app.application_id);
        if (usageRow) {
          draft.consumed_percentage = toInstitutionConsumedPct(
            usageRow.spendBudget.amount,
            effectiveBudget,
          );
          draft.consumed_budget = usageRow.spendBudget.amount;
        }
        if (
          draft.resolvedPct != null &&
          draft.resolvedAmount == null &&
          effectiveBudget > 0
        ) {
          draft.resolvedAmount = roundMoney((effectiveBudget * draft.resolvedPct) / 100);
          draft.amountInput = String(draft.resolvedAmount);
        }
        return draft;
      });
      setBulkRows(drafts);
      if (usageWarning) setBulkBanner(usageWarning);
    } catch (error) {
      setBulkBanner(mapApplicationAllocationError(error));
    } finally {
      setBulkLoading(false);
    }
  }, [tenantId, institutionBudget]);

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
          const next = { ...applyResolved(row, tenantBudget, "percentage", value), lastEditMode: "percentage" as const };
          if (row.keysLoaded && next.resolvedAmount != null) {
            next.keyPreviews = previewKeyCascade(next.resolvedAmount, row.keys);
            next.rowError = evaluateRowError(next, tenantBudget);
          }
          return next;
        }),
      );
      onBulkRowFocus(applicationId);
    },
    [tenantBudget, onBulkRowFocus],
  );

  const onBulkAmountChange = useCallback(
    (applicationId: string, value: string) => {
      setBulkRows((prev) =>
        prev.map((row) => {
          if (row.application_id !== applicationId) return row;
          if (!isApplicationBudgetEditable(row.status)) return row;
          const next = { ...applyResolved(row, tenantBudget, "amount", value), lastEditMode: "amount" as const };
          if (row.keysLoaded && next.resolvedAmount != null) {
            next.keyPreviews = previewKeyCascade(next.resolvedAmount, row.keys);
            next.rowError = evaluateRowError(next, tenantBudget);
          }
          return next;
        }),
      );
      onBulkRowFocus(applicationId);
    },
    [tenantBudget, onBulkRowFocus],
  );

  const handleSaveBulkBudget = async () => {
    if (!bulkCanSave) return;
    const changes = bulkRows
      .filter((row) => isApplicationBudgetEditable(row.status))
      .filter(rowHasBudgetChange)
      .map(buildAllocationUpdate)
      .filter((row): row is AllocationUpdate => row != null);
    if (changes.length === 0) {
      setBulkBudgetOpen(false);
      return;
    }
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
    setBudgetFloor(0);
    setBudgetBanner(null);
    setBudgetStepperHint(null);
    setBudgetOpen(true);
    void fetchApplicationUsageDetail(tenantId, Number(app.application_id))
      .then((detail) => {
        const budget = institutionBudget ?? tenantBudget;
        const floor = toInstitutionConsumedPct(detail.spendBudget.amount, budget);
        setBudgetFloor(floor ?? 0);
      })
      .catch(() => setBudgetFloor(0));
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
    if (budgetParsed === "invalid") return BUDGET_VALIDATION.enterValidPercentage;
    if (budgetParsed != null && budgetParsed < 0) return BUDGET_VALIDATION.budgetCannotBeNegative;
    if (budgetParsed != null && budgetFloor > 0 && budgetParsed < budgetFloor - 1e-6) {
      return belowConsumedPctRaw(budgetFloor);
    }
    if (budgetLiveTotal > 100 + 1e-6) {
      return totalApplicationsOver100(budgetLiveTotal);
    }
    return null;
  }, [budgetParsed, budgetFloor, budgetLiveTotal]);

  const validateCreate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!form.name.trim()) errors.name = "Application name is required.";
    const pct = parsePct(form.allocated_percentage);
    if (pct === "invalid") errors.allocated_percentage = BUDGET_VALIDATION.enterValidPercentage;
    else if (pct != null && pct < 0) errors.allocated_percentage = BUDGET_VALIDATION.budgetCannotBeNegative;
    else if (pct != null && pct > remainingPct + 1e-6) {
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
    onBudgetBoundHit: (bound: "min" | "max") => {
      if (bound === "min" && budgetFloor > 0) {
        setBudgetStepperHint(belowConsumedPctRaw(budgetFloor));
        return;
      }
      const wouldBe = budgetOthersAllocated + budgetAvailable + 1;
      setBudgetStepperHint(totalApplicationsOver100(wouldBe));
    },
    budgetStepperHint,
    budgetLiveTotal,
    budgetFieldError,
    budgetFloor,
    budgetAvailable,
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
    onBulkAmountChange,
    handleSaveBulkBudget,
    statusBusyId,
    handleToggleStatus,
    reload,
  };
}
