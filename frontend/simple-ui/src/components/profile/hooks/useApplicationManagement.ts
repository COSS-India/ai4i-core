import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@chakra-ui/react";
import {
  createApplication,
  getApplicationErrorCode,
  listApplicationDomains,
  listApplications,
  updateApplication,
  updateApplicationAllocations,
} from "../../../services/applicationService";
import { parseError } from "../../../utils/errorHandler";
import type { Application } from "../../../types/application";

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

function parsePct(raw: string): number | null | "invalid" {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return "invalid";
  return n;
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
    setBudgetDraft(app.allocated_percentage == null ? "" : String(app.allocated_percentage));
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
  const budgetValue = budgetParsed == null || budgetParsed === "invalid" ? 0 : budgetParsed;
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

  const handleSaveBudget = async () => {
    if (!selected) return;
    if (budgetFieldError) return;
    const next = budgetParsed == null || budgetParsed === "invalid" ? 0 : budgetParsed;
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
      setBudgetBanner(parseError(error).message);
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
    reload: load,
  };
}
