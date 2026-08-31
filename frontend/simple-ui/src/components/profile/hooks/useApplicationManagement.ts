import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@chakra-ui/react";
import {
  createApplication,
  getApplicationErrorCode,
  listAllApplicationsForBudget,
  listApplicationApiKeys,
  listApplicationDomains,
  listApplications,
  updateApplication,
  updateApplicationAllocations,
  type ApplicationApiKeyRow,
} from "../../../services/applicationService";
import { parseError } from "../../../utils/errorHandler";
import {
  previewKeyCascade,
  resolveApplicationBudget,
  roundMoney,
  roundPct,
  type ApplicationKeyPreview,
} from "../../../utils/applicationBudgetPreview";
import type { Application } from "../../../types/application";
import { FIELD_HINTS } from "../../../config/fieldHints";

const PAGE_SIZE = 20;

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
  consumed_percentage: number;
  consumed_budget: number;
  originalPct: number | null;
  pctInput: string;
  amountInput: string;
  resolvedPct: number | null;
  resolvedAmount: number | null;
  keysLoading: boolean;
  keysLoaded: boolean;
  keys: ApplicationApiKeyRow[];
  keyPreviews: ApplicationKeyPreview[];
  rowError: string | null;
};

function mapAllocationError(error: unknown): string {
  const code = getApplicationErrorCode(error);
  if (code === "TENANT_BUDGET_NOT_SET") {
    return FIELD_HINTS.application.institutionBudgetNotSet;
  }
  return parseError(error).message;
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

function buildDraftFromApplication(app: Application): BulkBudgetDraft {
  const pct = app.allocated_percentage;
  const amount = app.allocated_budget;
  return {
    application_id: app.application_id,
    name: app.name,
    consumed_percentage: app.consumed_percentage,
    consumed_budget: app.consumed_budget,
    originalPct: pct,
    pctInput: pctString(pct),
    amountInput: amountString(amount),
    resolvedPct: pct,
    resolvedAmount: amount,
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
  if (row.resolvedPct < row.consumed_percentage - 1e-6) {
    return `Cannot go below ${roundPct(row.consumed_percentage)}% already consumed.`;
  }
  if (row.resolvedAmount != null && row.resolvedAmount < row.consumed_budget - 1e-6) {
    return `Cannot go below ${roundMoney(row.consumed_budget)} already consumed.`;
  }
  const keyViolation = row.keyPreviews.find((k) => k.floorViolation);
  if (keyViolation) {
    return `Key "${keyViolation.key_name}" would drop below its consumed amount.`;
  }
  if (tenantBudget <= 0 && row.resolvedAmount != null && row.resolvedAmount > 0) {
    return "Institution budget is not set.";
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
    return { ...row, rowError: "Enter a valid number." };
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
    return { ...row, rowError: "Enter a valid number." };
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
  const [domains, setDomains] = useState<string[]>([]);
  const [totalAllocatedPct, setTotalAllocatedPct] = useState(0);
  const [tenantBudget, setTenantBudget] = useState(institutionBudget ?? 0);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
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

  const [bulkBudgetOpen, setBulkBudgetOpen] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkRows, setBulkRows] = useState<BulkBudgetDraft[]>([]);
  const [bulkBanner, setBulkBanner] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const load = useCallback(async () => {
    if (!tenantId) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const [list, domainList] = await Promise.all([
        listApplications(tenantId, {
          search: search || undefined,
          domain: domainFilter === "all" ? undefined : domainFilter,
          page,
          size: pageSize,
        }),
        listApplicationDomains(tenantId),
      ]);
      setApplications(list.applications);
      setTotal(list.pagination.total);
      setTotalAllocatedPct(list.total_allocated_percentage);
      setTenantBudget(institutionBudget ?? list.tenant_allocated_budget);
      setDomains(domainList);
    } catch (error) {
      setLoadError(parseError(error).message);
    } finally {
      setIsLoading(false);
    }
  }, [tenantId, search, domainFilter, page, pageSize, institutionBudget]);

  useEffect(() => {
    void load();
  }, [load]);

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
    const hasChange = bulkRows.some((row) => {
      const orig = row.originalPct;
      const next = row.resolvedPct;
      if (orig == null && next == null) return false;
      if (orig == null || next == null) return true;
      return Math.abs(orig - next) > 1e-6;
    });
    return hasChange;
  }, [institutionBudgetUnset, bulkLoading, bulkRows, bulkLiveTotalPct]);

  const loadKeysForRow = useCallback(async (applicationId: string) => {
    setBulkRows((prev) =>
      prev.map((row) =>
        row.application_id === applicationId
          ? { ...row, keysLoading: true }
          : row,
      ),
    );
    try {
      const keys = await listApplicationApiKeys(applicationId);
      setBulkRows((prev) =>
        prev.map((row) => {
          if (row.application_id !== applicationId) return row;
          const activeKeys = keys.filter((k) => k.is_active);
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
          };
          return { ...next, rowError: evaluateRowError(next, tenantBudget) };
        }),
      );
    } catch {
      setBulkRows((prev) =>
        prev.map((row) =>
          row.application_id === applicationId
            ? { ...row, keysLoading: false, keysLoaded: true }
            : row,
        ),
      );
    }
  }, [tenantBudget]);

  const openBulkBudget = useCallback(async () => {
    if (!tenantId) return;
    setBulkBudgetOpen(true);
    setBulkBanner(null);
    setBulkLoading(true);
    setBulkRows([]);
    try {
      const list = await listAllApplicationsForBudget(tenantId);
      const effectiveBudget = institutionBudget ?? list.tenant_allocated_budget;
      setTenantBudget(effectiveBudget);
      const drafts = list.applications.map((app) => {
        const draft = buildDraftFromApplication(app);
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
    } catch (error) {
      setBulkBanner(mapAllocationError(error));
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
          const next = applyResolved(row, tenantBudget, "percentage", value);
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
          const next = applyResolved(row, tenantBudget, "amount", value);
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
      .filter((row) => {
        const orig = row.originalPct;
        const next = row.resolvedPct;
        if (orig == null && next == null) return false;
        if (orig == null || next == null) return true;
        return Math.abs(orig - next) > 1e-6;
      })
      .filter((row) => row.resolvedPct != null)
      .map((row) => ({
        application_id: row.application_id,
        allocated_percentage: row.resolvedPct as number,
      }));
    if (changes.length === 0) {
      setBulkBudgetOpen(false);
      return;
    }
    setIsSaving(true);
    setBulkBanner(null);
    try {
      await updateApplicationAllocations(tenantId, changes);
      toast({
        title: "Application budgets updated.",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setBulkBudgetOpen(false);
      await load();
    } catch (error) {
      setBulkBanner(mapAllocationError(error));
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
    setSelected(app);
    setBudgetDraft(
      app.allocated_percentage == null ? "" : String(app.allocated_percentage),
    );
    setBudgetBanner(null);
    setBudgetStepperHint(null);
    setBudgetOpen(true);
  };

  const budgetOthersAllocated = useMemo(() => {
    if (!selected) return totalAllocatedPct;
    return totalAllocatedPct - (selected.allocated_percentage ?? 0);
  }, [selected, totalAllocatedPct]);

  const budgetFloor = selected?.consumed_percentage ?? 0;

  const budgetParsed = parsePct(budgetDraft);
  const budgetValue =
    budgetParsed == null || budgetParsed === "invalid" ? 0 : budgetParsed;
  const budgetLiveTotal = budgetOthersAllocated + budgetValue;
  const budgetAvailable = Math.max(0, 100 - budgetOthersAllocated);

  const budgetFieldError = useMemo(() => {
    if (budgetParsed === "invalid") return "Enter a valid percentage.";
    if (budgetParsed != null && budgetParsed < 0) return "Budget cannot be negative.";
    if (budgetParsed != null && budgetParsed < budgetFloor - 1e-6) {
      return `Cannot go below ${budgetFloor}% already consumed.`;
    }
    if (budgetLiveTotal > 100 + 1e-6) {
      return `Total across Applications would be ${budgetLiveTotal.toFixed(2)}% — over 100%.`;
    }
    return null;
  }, [budgetParsed, budgetFloor, budgetLiveTotal]);

  const validateCreate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!form.name.trim()) errors.name = "Application name is required.";
    const pct = parsePct(form.allocated_percentage);
    if (pct === "invalid") errors.allocated_percentage = "Enter a valid percentage.";
    else if (pct != null && pct < 0) errors.allocated_percentage = "Budget cannot be negative.";
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
      await load();
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
        { application_id: selected.application_id, allocated_percentage: next },
      ]);
      toast({
        title: `Budget for "${selected.name}" updated to ${next}%.`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setBudgetOpen(false);
      await load();
    } catch (error) {
      setBudgetBanner(mapAllocationError(error));
    } finally {
      setIsSaving(false);
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
      await load();
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
    domains,
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
    domainFilter,
    setDomainFilter: (value: string) => {
      setDomainFilter(value);
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
      if (bound === "min") {
        setBudgetStepperHint(`Cannot go below ${budgetFloor}% already consumed.`);
        return;
      }
      const wouldBe = budgetOthersAllocated + budgetAvailable + 1;
      setBudgetStepperHint(
        `Total across Applications would be ${wouldBe.toFixed(2)}% — over 100%.`,
      );
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
    reload: load,
  };
}
