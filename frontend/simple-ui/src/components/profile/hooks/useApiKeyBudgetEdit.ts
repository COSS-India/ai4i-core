import { useCallback, useMemo, useState } from "react";
import { useToast } from "@chakra-ui/react";
import {
  getAllocationErrorCode,
  updateApiKeyAllocations,
} from "../../../services/allocationService";
import { fetchApplicationUsageDetail } from "../../../services/applicationUsageService";
import { parseError } from "../../../utils/errorHandler";
import {
  resolveApplicationBudget,
  roundMoney,
  roundPct,
} from "../../../utils/applicationBudgetPreview";
import type { Application } from "../../../types/application";
import { FIELD_HINTS } from "../../../config/fieldHints";

export type KeyBudgetDraft = {
  api_key_id: number;
  key_name: string;
  consumed_percentage: number | null;
  consumed_budget: number | null;
  originalPct: number | null;
  pctInput: string;
  amountInput: string;
  resolvedPct: number | null;
  resolvedAmount: number | null;
  lastEditMode: "percentage" | "amount";
  rowError: string | null;
};

function pctString(value: number | null): string {
  if (value == null) return "";
  return String(value);
}

function amountString(value: number | null): string {
  if (value == null) return "";
  return String(value);
}

function parsePct(raw: string): number | null | "invalid" {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return "invalid";
  return n;
}

function rowHasBudgetChange(row: KeyBudgetDraft): boolean {
  const orig = row.originalPct;
  const next = row.resolvedPct;
  if (orig == null && next == null) return false;
  if (orig == null || next == null) return true;
  return Math.abs(orig - next) > 1e-6;
}

function evaluateKeyRowError(
  row: KeyBudgetDraft,
  applicationBudget: number,
): string | null {
  if (row.pctInput.trim() === "" && row.originalPct != null) {
    return "Enter a budget allocation percentage.";
  }
  if (row.resolvedPct == null) return null;
  if (row.resolvedPct < 0) return "Budget cannot be negative.";
  if (
    row.consumed_percentage != null &&
    row.resolvedPct < row.consumed_percentage - 1e-6
  ) {
    return `Cannot go below ${roundPct(row.consumed_percentage)}% already consumed.`;
  }
  if (
    row.consumed_budget != null &&
    row.resolvedAmount != null &&
    row.resolvedAmount < row.consumed_budget - 1e-6
  ) {
    return `Cannot go below ${roundMoney(row.consumed_budget)} already consumed.`;
  }
  if (applicationBudget <= 0 && row.resolvedAmount != null && row.resolvedAmount > 0) {
    return "This Application has no Budget (₹) assigned yet.";
  }
  return null;
}

function applyResolved(
  row: KeyBudgetDraft,
  applicationBudget: number,
  mode: "percentage" | "amount",
  raw: string,
): KeyBudgetDraft {
  const trimmed = raw.trim();
  if (trimmed === "") {
    const next = {
      ...row,
      pctInput: "",
      amountInput: "",
      resolvedPct: null,
      resolvedAmount: null,
      rowError: null,
    };
    return { ...next, rowError: evaluateKeyRowError(next, applicationBudget) };
  }
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) {
    return { ...row, rowError: "Enter a valid number." };
  }
  const resolved = resolveApplicationBudget(mode, numeric, applicationBudget);
  if (!resolved) {
    if (mode === "amount") {
      return {
        ...row,
        amountInput: trimmed,
        rowError: "Enter a Budget amount after this Application has a Budget (₹) assigned.",
      };
    }
    return { ...row, rowError: "Enter a valid number." };
  }
  const next: KeyBudgetDraft = {
    ...row,
    pctInput: String(resolved.pct),
    amountInput: resolved.amount != null ? String(resolved.amount) : "",
    resolvedPct: resolved.pct,
    resolvedAmount: resolved.amount,
    rowError: null,
  };
  return { ...next, rowError: evaluateKeyRowError(next, applicationBudget) };
}

function buildDraftFromUsageKey(
  key: {
    keyId: number;
    keyName: string;
    allocatedBudget: { amount: number; percentage: number };
    spendBudget: { amount: number; percentage: number };
  },
  applicationBudget: number,
): KeyBudgetDraft {
  const pct =
    applicationBudget > 0
      ? roundPct((key.allocatedBudget.amount / applicationBudget) * 100)
      : key.allocatedBudget.percentage;
  const consumedPct =
    applicationBudget > 0
      ? roundPct((key.spendBudget.amount / applicationBudget) * 100)
      : key.spendBudget.percentage;
  return {
    api_key_id: key.keyId,
    key_name: key.keyName,
    consumed_percentage: consumedPct,
    consumed_budget: key.spendBudget.amount,
    originalPct: pct,
    pctInput: pctString(pct),
    amountInput: amountString(key.allocatedBudget.amount),
    resolvedPct: pct,
    resolvedAmount: key.allocatedBudget.amount,
    lastEditMode: "percentage",
    rowError: null,
  };
}

function mapAllocationError(error: unknown): string {
  const code = getAllocationErrorCode(error);
  if (code === "APPLICATION_BUDGET_NOT_SET") {
    return "This Application has no Budget allocation yet — assign one from Application Management first.";
  }
  if (code === "TENANT_BUDGET_NOT_SET") {
    return FIELD_HINTS.application.institutionBudgetNotSet;
  }
  return parseError(error).message;
}

export interface UseApiKeyBudgetEditOptions {
  tenantId: string | null | undefined;
  applications: Application[];
  /** Pre-select when the manage tab already filters to one Application. */
  initialApplicationId?: string;
  onSaved?: () => Promise<void>;
}

export function useApiKeyBudgetEdit({
  tenantId,
  applications,
  initialApplicationId,
  onSaved,
}: UseApiKeyBudgetEditOptions) {
  const toast = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [selectedApplicationId, setSelectedApplicationId] = useState("");
  const [applicationName, setApplicationName] = useState("");
  const [applicationBudget, setApplicationBudget] = useState(0);
  const [applicationAllocatedPct, setApplicationAllocatedPct] = useState<number | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [rows, setRows] = useState<KeyBudgetDraft[]>([]);

  const applicationBudgetUnset = applicationBudget <= 0;

  const liveTotalPct = useMemo(
    () => rows.reduce((sum, row) => sum + (row.resolvedPct ?? 0), 0),
    [rows],
  );

  const canSave = useMemo(() => {
    if (!selectedApplicationId || isLoading || isSaving) return false;
    if (rows.length === 0) return false;
    if (liveTotalPct > 100 + 1e-6) return false;
    if (rows.some((row) => row.rowError)) return false;
    const changed = rows.filter(rowHasBudgetChange);
    if (changed.length === 0) return false;
    return true;
  }, [selectedApplicationId, isLoading, isSaving, rows, liveTotalPct]);

  const loadKeysForApplication = useCallback(
    async (applicationId: string) => {
      const tid = tenantId?.trim();
      if (!tid || !applicationId) return;
      setIsLoading(true);
      setBanner(null);
      setRows([]);
      try {
        const app =
          applications.find((a) => a.application_id === applicationId) ?? null;
        const detail = await fetchApplicationUsageDetail(tid, Number(applicationId));
        const appAmount = detail.allocatedBudget.amount;
        setApplicationName(detail.applicationName || app?.name || applicationId);
        setApplicationBudget(appAmount);
        setApplicationAllocatedPct(
          app?.allocated_percentage ?? detail.allocatedBudget.percentage ?? null,
        );
        const activeKeys = detail.apiKeys.filter((k) => k.isActive);
        const drafts = activeKeys.map((key) => buildDraftFromUsageKey(key, appAmount));
        setRows(drafts);
        if (activeKeys.length === 0) {
          setBanner("No active API keys under this Application.");
        }
      } catch (error) {
        setBanner(parseError(error).message);
        setRows([]);
      } finally {
        setIsLoading(false);
      }
    },
    [applications, tenantId],
  );

  const open = useCallback(
    (applicationId?: string) => {
      const nextId = applicationId?.trim() || initialApplicationId?.trim() || "";
      setSelectedApplicationId(nextId);
      setApplicationName("");
      setApplicationBudget(0);
      setApplicationAllocatedPct(null);
      setBanner(null);
      setRows([]);
      setIsOpen(true);
      if (nextId) {
        void loadKeysForApplication(nextId);
      }
    },
    [initialApplicationId, loadKeysForApplication],
  );

  const close = useCallback(() => {
    setIsOpen(false);
    setBanner(null);
    setRows([]);
  }, []);

  const onApplicationChange = useCallback(
    (applicationId: string) => {
      setSelectedApplicationId(applicationId);
      if (applicationId) {
        void loadKeysForApplication(applicationId);
      } else {
        setRows([]);
        setApplicationName("");
        setApplicationBudget(0);
        setApplicationAllocatedPct(null);
      }
    },
    [loadKeysForApplication],
  );

  const onPctChange = useCallback(
    (apiKeyId: number, value: string) => {
      setRows((prev) =>
        prev.map((row) => {
          if (row.api_key_id !== apiKeyId) return row;
          const next = {
            ...applyResolved(row, applicationBudget, "percentage", value),
            lastEditMode: "percentage" as const,
          };
          return next;
        }),
      );
    },
    [applicationBudget],
  );

  const onAmountChange = useCallback(
    (apiKeyId: number, value: string) => {
      setRows((prev) =>
        prev.map((row) => {
          if (row.api_key_id !== apiKeyId) return row;
          const next = {
            ...applyResolved(row, applicationBudget, "amount", value),
            lastEditMode: "amount" as const,
          };
          return next;
        }),
      );
    },
    [applicationBudget],
  );

  const save = useCallback(async () => {
    if (!canSave || !selectedApplicationId) return;
    const changes = rows.filter(rowHasBudgetChange);
    setIsSaving(true);
    setBanner(null);
    try {
      await updateApiKeyAllocations(
        Number(selectedApplicationId),
        changes.map((row) => {
          if (row.lastEditMode === "amount" && row.resolvedAmount != null) {
            return { api_key_id: row.api_key_id, allocated_budget: row.resolvedAmount };
          }
          return {
            api_key_id: row.api_key_id,
            allocated_percentage: row.resolvedPct ?? 0,
          };
        }),
      );
      toast({
        title: `Budget updated for ${changes.length} key(s).`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      close();
      await onSaved?.();
    } catch (error) {
      setBanner(mapAllocationError(error));
    } finally {
      setIsSaving(false);
    }
  }, [canSave, selectedApplicationId, rows, toast, close, onSaved]);

  return {
    isOpen,
    open,
    close,
    selectedApplicationId,
    onApplicationChange,
    applicationName,
    applicationBudget,
    applicationAllocatedPct,
    applicationBudgetUnset,
    applications,
    isLoading,
    isSaving,
    banner,
    rows,
    liveTotalPct,
    canSave,
    onPctChange,
    onAmountChange,
    save,
  };
}
