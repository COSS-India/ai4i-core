import { useCallback, useEffect, useMemo, useState } from "react";
import { notificationAlertsService } from "../services/notificationAlertsService";
import type {
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
  RecipientRoleKey,
  ThresholdDraftBand,
} from "../types/notificationAlerts";
import {
  DEFAULT_ENABLE_ROLE,
  draftBandsEqual,
  isCatalogItemEnabled,
  toThresholdDrafts,
  validateThresholdDrafts,
} from "../types/notificationAlerts";
import { replaceTenantCopy } from "../utils/replaceTenantCopy";

export interface CatalogDraft {
  recipient_roles: Record<RecipientRoleKey, boolean>;
  /** ALERT rows only. Always the complete band set once present. */
  thresholds?: ThresholdDraftBand[];
}

export interface CatalogSubmitResult {
  succeeded: string[];
  failed?: { name: string; message: string };
}

/**
 * Bands are sorted here — on load and after each save — and never again
 * while the user is editing. Re-sorting a live draft would make a row jump
 * under the cursor the moment someone typed a digit that reordered it.
 */
function toDraft(item: NotificationAlertCatalogItem): CatalogDraft {
  return {
    recipient_roles: { ...item.recipient_roles },
    thresholds: item.thresholds ? toThresholdDrafts(item.thresholds) : undefined,
  };
}

function draftEnabled(draft: CatalogDraft): boolean {
  return isCatalogItemEnabled(draft.recipient_roles);
}

function draftsEqual(draft: CatalogDraft, item: NotificationAlertCatalogItem): boolean {
  if (draft.recipient_roles["TENANT ADMIN"] !== item.recipient_roles["TENANT ADMIN"]) {
    return false;
  }
  if (draft.recipient_roles.ADMIN !== item.recipient_roles.ADMIN) return false;
  // No bands at all — nothing to compare (NOTIFICATION rows).
  if (!draft.thresholds) return true;
  return draftBandsEqual(draft.thresholds, toThresholdDrafts(item.thresholds));
}

function catalogErrorMessage(error: unknown, fallback: string): string {
  let message = fallback;
  if (!error || typeof error !== "object") {
    message = error instanceof Error ? error.message : fallback;
  } else {
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
    if (typeof detail === "string" && detail.trim()) {
      message = detail;
    } else if (detail && typeof detail === "object" && detail.message) {
      message = detail.message;
    } else if (maybeAxios.response?.data?.error?.message) {
      message = maybeAxios.response.data.error.message;
    } else if (maybeAxios.response?.data?.message) {
      message = maybeAxios.response.data.message;
    } else if (maybeAxios.message) {
      message = maybeAxios.message;
    }
  }
  return replaceTenantCopy(message);
}

export function useNotificationCatalog(type: NotificationAlertType) {
  const [items, setItems] = useState<NotificationAlertCatalogItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, CatalogDraft>>({});
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
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
    },
    [type],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const getDraft = useCallback(
    (item: NotificationAlertCatalogItem): CatalogDraft =>
      drafts[item.name] ?? toDraft(item),
    [drafts],
  );

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(
      (item) =>
        !q ||
        item.display_name.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q),
    );
  }, [items, search]);

  const updateDraft = useCallback(
    (
      name: string,
      patch: {
        recipient_roles?: Partial<Record<RecipientRoleKey, boolean>>;
        thresholds?: ThresholdDraftBand[];
      },
    ) => {
      setDrafts((prev) => {
        const current =
          prev[name] ?? toDraft(items.find((item) => item.name === name)!);
        return {
          ...prev,
          [name]: {
            ...current,
            recipient_roles: patch.recipient_roles
              ? { ...current.recipient_roles, ...patch.recipient_roles }
              : current.recipient_roles,
            thresholds: patch.thresholds
              ? patch.thresholds.map((band) => ({ ...band }))
              : current.thresholds,
          },
        };
      });
    },
    [items],
  );

  /** Enable/disable maps to recipient_roles only (no wire `enabled` field). */
  const setEnabled = useCallback(
    (name: string, enabled: boolean) => {
      setDrafts((prev) => {
        const item = items.find((row) => row.name === name);
        if (!item) return prev;
        const current = prev[name] ?? toDraft(item);
        if (!enabled) {
          return {
            ...prev,
            [name]: {
              ...current,
              recipient_roles: { "TENANT ADMIN": false, ADMIN: false },
            },
          };
        }
        const hasRole = isCatalogItemEnabled(current.recipient_roles);
        return {
          ...prev,
          [name]: {
            ...current,
            recipient_roles: hasRole
              ? current.recipient_roles
              : {
                  "TENANT ADMIN": DEFAULT_ENABLE_ROLE === "TENANT ADMIN",
                  ADMIN: DEFAULT_ENABLE_ROLE === "ADMIN",
                },
          },
        };
      });
    },
    [items],
  );

  const setAllEnabled = useCallback(
    (enabled: boolean) => {
      setDrafts((prev) => {
        const next = { ...prev };
        filteredItems.forEach((item) => {
          const current = next[item.name] ?? toDraft(item);
          if (!enabled) {
            next[item.name] = {
              ...current,
              recipient_roles: { "TENANT ADMIN": false, ADMIN: false },
            };
            return;
          }
          const hasRole = isCatalogItemEnabled(current.recipient_roles);
          next[item.name] = {
            ...current,
            recipient_roles: hasRole
              ? current.recipient_roles
              : {
                  "TENANT ADMIN": DEFAULT_ENABLE_ROLE === "TENANT ADMIN",
                  ADMIN: DEFAULT_ENABLE_ROLE === "ADMIN",
                },
          };
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
      });
    },
    [updateDraft],
  );

  /**
   * Replaces a row's whole band set at once — the only threshold mutator.
   * Never a per-band patch the way recipient_roles does it: an editable
   * percentage is no stable key to merge against. The modal validates before
   * applying, so bands arrive complete and valid — what the API takes too.
   */
  const setThresholds = useCallback(
    (name: string, thresholds: ThresholdDraftBand[]) => {
      updateDraft(name, { thresholds });
    },
    [updateDraft],
  );

  const allFilteredEnabled =
    filteredItems.length > 0 &&
    filteredItems.every((item) => draftEnabled(getDraft(item)));

  const dirtyCount = useMemo(() => {
    return items.reduce((count, item) => {
      const draft = drafts[item.name];
      if (!draft) return count;
      return draftsEqual(draft, item) ? count : count + 1;
    }, 0);
  }, [items, drafts]);

  const submit = useCallback(async (): Promise<CatalogSubmitResult> => {
    setIsSubmitting(true);
    setError(null);
    const succeeded: string[] = [];
    try {
      for (const item of items) {
        const draft = drafts[item.name];
        if (!draft || draftsEqual(draft, item)) continue;

        const payload: CatalogUpdatePayload = {
          recipient_roles: draft.recipient_roles,
        };
        if (item.type === "ALERT" && draft.thresholds) {
          const original = toThresholdDrafts(item.thresholds);
          if (!draftBandsEqual(draft.thresholds, original)) {
            const { bands } = validateThresholdDrafts(draft.thresholds);
            if (!bands) {
              const message = `Fix the thresholds on '${item.display_name}' before saving.`;
              setError(message);
              return { succeeded, failed: { name: item.name, message } };
            }
            payload.thresholds = bands;
          }
        }

        try {
          const updated = await notificationAlertsService.updateCatalog(
            item.name,
            payload,
          );
          succeeded.push(updated.name);
          setItems((prev) =>
            prev.map((row) => (row.name === updated.name ? updated : row)),
          );
          setDrafts((prev) => ({
            ...prev,
            [updated.name]: toDraft(updated),
          }));
        } catch (e) {
          const message = catalogErrorMessage(
            e,
            `Failed to save '${item.display_name}'.`,
          );
          setError(
            succeeded.length > 0
              ? `Saved ${succeeded.length} row(s), then failed on '${item.display_name}': ${message}`
              : message,
          );
          return { succeeded, failed: { name: item.name, message } };
        }
      }
      return { succeeded };
    } finally {
      setIsSubmitting(false);
    }
  }, [drafts, items]);

  return {
    items,
    filteredItems,
    search,
    setSearch,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    draftEnabled,
    setEnabled,
    setAllEnabled,
    setRecipientRole,
    setThresholds,
    allFilteredEnabled,
    dirtyCount,
    submit,
    reload: load,
  };
}
