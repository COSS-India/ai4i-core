import { useCallback, useEffect, useMemo, useState } from "react";
import { notificationAlertsService } from "../services/notificationAlertsService";
import type {
  CatalogStatusFilter,
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
  RecipientRoleKey,
} from "../types/notificationAlerts";

export interface CatalogDraft {
  enabled: boolean;
  recipient_roles: Record<RecipientRoleKey, boolean>;
  thresholds?: Record<string, boolean>;
}

function toDraft(item: NotificationAlertCatalogItem): CatalogDraft {
  return {
    enabled: item.enabled,
    recipient_roles: { ...item.recipient_roles },
    thresholds: item.thresholds ? { ...item.thresholds } : undefined,
  };
}

function draftsEqual(a: CatalogDraft, b: CatalogDraft): boolean {
  if (a.enabled !== b.enabled) return false;
  if (a.recipient_roles["TENANT ADMIN"] !== b.recipient_roles["TENANT ADMIN"]) return false;
  if (a.recipient_roles.ADMIN !== b.recipient_roles.ADMIN) return false;
  const aKeys = Object.keys(a.thresholds ?? {});
  const bKeys = Object.keys(b.thresholds ?? {});
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((key) => (a.thresholds?.[key] ?? false) === (b.thresholds?.[key] ?? false));
}

function catalogErrorMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== "object") {
    return error instanceof Error ? error.message : fallback;
  }
  const maybeAxios = error as {
    message?: string;
    response?: {
      data?: {
        detail?: string | { message?: string };
        error?: { message?: string };
        message?: string;
      };
    };
  };
  const detail = maybeAxios.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  if (maybeAxios.response?.data?.error?.message) {
    return maybeAxios.response.data.error.message;
  }
  if (maybeAxios.response?.data?.message) return maybeAxios.response.data.message;
  if (maybeAxios.message) return maybeAxios.message;
  return fallback;
}

export function useNotificationCatalog(type: NotificationAlertType) {
  const [items, setItems] = useState<NotificationAlertCatalogItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, CatalogDraft>>({});
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<CatalogStatusFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);
    try {
      const rows = await notificationAlertsService.listCatalog(type, signal);
      if (signal?.aborted) return;
      setItems(rows);
      const nextDrafts: Record<string, CatalogDraft> = {};
      rows.forEach((row) => {
        nextDrafts[row.name] = toDraft(row);
      });
      setDrafts(nextDrafts);
    } catch (e) {
      if (signal?.aborted) return;
      // Axios cancel / AbortError — ignore (Strict Mode remount).
      if (
        (e as { code?: string; name?: string })?.code === "ERR_CANCELED" ||
        (e as { name?: string })?.name === "CanceledError" ||
        (e as { name?: string })?.name === "AbortError"
      ) {
        return;
      }
      setError(catalogErrorMessage(e, "Failed to load catalog."));
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, [type]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      const draft = drafts[item.name] ?? toDraft(item);
      const matchesName =
        !q ||
        item.display_name.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q);
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "enabled" && draft.enabled) ||
        (statusFilter === "disabled" && !draft.enabled);
      return matchesName && matchesStatus;
    });
  }, [items, drafts, search, statusFilter]);

  const getDraft = useCallback(
    (item: NotificationAlertCatalogItem): CatalogDraft =>
      drafts[item.name] ?? toDraft(item),
    [drafts],
  );

  const updateDraft = useCallback(
    (
      name: string,
      patch: {
        enabled?: boolean;
        recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
        thresholds?: Record<string, boolean>;
      },
    ) => {
      setDrafts((prev) => {
        const current =
          prev[name] ??
          toDraft(items.find((item) => item.name === name)!);
        return {
          ...prev,
          [name]: {
            ...current,
            enabled: patch.enabled ?? current.enabled,
            recipient_roles: patch.recipient_roles
              ? { ...current.recipient_roles, ...patch.recipient_roles }
              : current.recipient_roles,
            thresholds: patch.thresholds
              ? { ...patch.thresholds }
              : current.thresholds,
          },
        };
      });
    },
    [items],
  );

  const setEnabled = useCallback(
    (name: string, enabled: boolean) => {
      updateDraft(name, { enabled });
    },
    [updateDraft],
  );

  const setAllEnabled = useCallback(
    (enabled: boolean) => {
      setDrafts((prev) => {
        const next = { ...prev };
        filteredItems.forEach((item) => {
          const current = next[item.name] ?? toDraft(item);
          next[item.name] = { ...current, enabled };
        });
        return next;
      });
    },
    [filteredItems],
  );

  const setRecipientRole = useCallback(
    (name: string, role: RecipientRoleKey, checked: boolean) => {
      updateDraft(name, {
        recipient_roles: { [role]: checked },
        ...(checked ? { enabled: true } : {}),
      });
    },
    [updateDraft],
  );

  const setThreshold = useCallback(
    (name: string, threshold: string, checked: boolean) => {
      const item = items.find((row) => row.name === name);
      const current =
        drafts[name]?.thresholds ??
        item?.thresholds ??
        {};
      updateDraft(name, {
        thresholds: { ...current, [threshold]: checked },
      });
    },
    [drafts, items, updateDraft],
  );

  const allFilteredEnabled =
    filteredItems.length > 0 &&
    filteredItems.every((item) => getDraft(item).enabled);

  const dirtyCount = useMemo(() => {
    return items.reduce((count, item) => {
      const draft = drafts[item.name];
      if (!draft) return count;
      return draftsEqual(draft, toDraft(item)) ? count : count + 1;
    }, 0);
  }, [items, drafts]);

  const submit = useCallback(async (): Promise<number> => {
    setIsSubmitting(true);
    setError(null);
    try {
      let changed = 0;
      for (const item of items) {
        const draft = drafts[item.name];
        if (!draft || draftsEqual(draft, toDraft(item))) continue;

        const payload: CatalogUpdatePayload = {
          enabled: draft.enabled,
          recipient_roles: draft.recipient_roles,
        };
        if (item.type === "ALERT" && draft.thresholds) {
          payload.thresholds = draft.thresholds;
        }

        const updated = await notificationAlertsService.updateCatalog(
          item.name,
          payload,
        );
        changed += 1;
        setItems((prev) =>
          prev.map((row) => (row.name === updated.name ? updated : row)),
        );
        setDrafts((prev) => ({
          ...prev,
          [updated.name]: toDraft(updated),
        }));
      }
      return changed;
    } catch (e) {
      const message = catalogErrorMessage(e, "Failed to save catalog changes.");
      setError(message);
      throw new Error(message);
    } finally {
      setIsSubmitting(false);
    }
  }, [drafts, items]);

  return {
    items,
    filteredItems,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setEnabled,
    setAllEnabled,
    setRecipientRole,
    setThreshold,
    allFilteredEnabled,
    dirtyCount,
    submit,
    reload: load,
  };
}
