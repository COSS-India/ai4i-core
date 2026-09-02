import { useCallback, useMemo, useRef, useState } from "react";
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
import type { AllocationValue } from "../../../services/allocationService";

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

function mapBelowConsumedError(message: string): string {
  if (/api[_-]?key/i.test(message)) {
    return message;
  }
  return `An API key would drop below its consumed amount. ${message}`;
}

function allocationErrorApiKeyId(error: unknown): number | null {
  const message = parseError(error).message;
  const match =
    message.match(/api_key_id[=:\s]+(\d+)/i) ?? message.match(/\bid=(\d+)/);
  return match ? Number(match[1]) : null;
}

function mapAllocationError(error: unknown): string {
  const code = getAllocationErrorCode(error);
  const message = parseError(error).message;
  if (code === "APPLICATION_BUDGET_NOT_SET") {
    return "This Application has no Budget allocation yet — assign one from Application Management first.";
  }
  if (code === "APPLICATION_ALLOCATION_MISMATCH") {
    return "Application budget changed elsewhere — close this dialog, refresh, and try again.";
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
    return mapBelowConsumedError(message);
  }
  return message;
}

function buildKeyAllocation(row: KeyBudgetDraft): AllocationValue {
  if (rowHasBudgetChange(row)) {
    if (row.lastEditMode === "amount" && row.resolvedAmount != null) {
      return { type: "FIXED", value: row.resolvedAmount };
    }
    return { type: "PERCENTAGE", value: row.resolvedPct ?? 0 };
  }
  return { type: "FIXED", value: row.resolvedAmount ?? 0 };
}

function resolveApplicationEcho(app: Application | null): AllocationValue | null {
  if (app?.allocated_percentage != null) {
    return { type: "PERCENTAGE", value: app.allocated_percentage };
  }
  if (app?.allocated_budget != null) {
    return { type: "FIXED", value: app.allocated_budget };
  }
  return null;
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
  const [applicationEchoAllocation, setApplicationEchoAllocation] =
    useState<AllocationValue | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [rows, setRows] = useState<KeyBudgetDraft[]>([]);
  const pendingLoadApplicationIdRef = useRef<string | null>(null);

  const applicationBudgetUnset = applicationBudget <= 0;

  const liveTotalPct = useMemo(
    () => rows.reduce((sum, row) => sum + (row.resolvedPct ?? 0), 0),
    [rows],
  );

  const canSave = useMemo(() => {
    if (!selectedApplicationId || isLoading || isSaving) return false;
    if (!applicationEchoAllocation) return false;
    if (rows.length === 0) return false;
    if (liveTotalPct > 100 + 1e-6) return false;
    if (rows.some((row) => row.rowError)) return false;
    const changed = rows.filter(rowHasBudgetChange);
    if (changed.length === 0) return false;
    return true;
  }, [
    selectedApplicationId,
    applicationEchoAllocation,
    isLoading,
    isSaving,
    rows,
    liveTotalPct,
  ]);

  const loadKeysForApplication = useCallback(
    async (applicationId: string) => {
      const tid = tenantId?.trim();
      if (!tid || !applicationId) return;
      pendingLoadApplicationIdRef.current = applicationId;
      setIsLoading(true);
      setBanner(null);
      setRows([]);
      try {
        const app =
          applications.find((a) => a.application_id === applicationId) ?? null;
        const detail = await fetchApplicationUsageDetail(tid, Number(applicationId));
        if (pendingLoadApplicationIdRef.current !== applicationId) return;
        const appAmount = detail.allocatedBudget.amount;
        const echo = resolveApplicationEcho(app);
        setApplicationName(detail.applicationName || app?.name || applicationId);
        setApplicationBudget(appAmount);
        setApplicationAllocatedPct(
          app?.allocated_percentage ?? detail.allocatedBudget.percentage ?? null,
        );
        setApplicationEchoAllocation(echo);
        const activeKeys = detail.apiKeys.filter((k) => k.isActive);
        const drafts = activeKeys.map((key) => buildDraftFromUsageKey(key, appAmount));
        setRows(drafts);
        if (activeKeys.length === 0) {
          setBanner("No active API keys under this Application.");
        }
      } catch (error) {
        if (pendingLoadApplicationIdRef.current !== applicationId) return;
        setBanner(parseError(error).message);
        setRows([]);
      } finally {
        if (pendingLoadApplicationIdRef.current === applicationId) {
          setIsLoading(false);
        }
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
      setApplicationEchoAllocation(null);
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
        setApplicationEchoAllocation(null);
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
    if (!canSave || !selectedApplicationId || !applicationEchoAllocation) return;
    const changes = rows.filter(rowHasBudgetChange);
    setIsSaving(true);
    setBanner(null);
    try {
      await updateApiKeyAllocations(
        Number(selectedApplicationId),
        applicationEchoAllocation,
        rows.map((row) => ({
          api_key_id: row.api_key_id,
          allocation: buildKeyAllocation(row),
        })),
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
      const code = getAllocationErrorCode(error);
      if (code === "ALLOCATION_BELOW_CONSUMED") {
        const keyId = allocationErrorApiKeyId(error);
        const rowMessage = mapBelowConsumedError(parseError(error).message);
        if (keyId != null) {
          let matched = false;
          setRows((prev) => {
            if (!prev.some((row) => row.api_key_id === keyId)) return prev;
            matched = true;
            return prev.map((row) =>
              row.api_key_id === keyId ? { ...row, rowError: rowMessage } : row,
            );
          });
          if (!matched) setBanner(rowMessage);
        } else {
          setBanner(rowMessage);
        }
      } else {
        setBanner(mapAllocationError(error));
      }
    } finally {
      setIsSaving(false);
    }
  }, [canSave, selectedApplicationId, applicationEchoAllocation, rows, toast, close, onSaved]);

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
