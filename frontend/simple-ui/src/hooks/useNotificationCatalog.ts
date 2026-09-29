import { useCallback, useEffect, useMemo, useState } from "react";
import { notificationAlertsService } from "../services/notificationAlertsService";
import type {
  CatalogScopeFilter,
  CatalogUpdatePayload,
  NotificationAlertCatalogItem,
  NotificationAlertType,
  NotificationScope,
  ThresholdDraftBand,
} from "../types/notificationAlerts";
import {
  draftBandsEqual,
  toThresholdDrafts,
  validateThresholdDrafts,
} from "../types/notificationAlerts";
import { replaceTenantCopy } from "../utils/replaceTenantCopy";

export interface CatalogDraft {
  scope: NotificationScope;
  /** recipient_roles.ADMIN — always false while `scope` is INSTITUTION. */
  adminRecipient: boolean;
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
    scope: item.scope,
    adminRecipient: item.recipient_roles.ADMIN,
    thresholds: item.thresholds ? toThresholdDrafts(item.thresholds) : undefined,
  };
}

function draftsEqual(draft: CatalogDraft, item: NotificationAlertCatalogItem): boolean {
  if (draft.scope !== item.scope) return false;
  if (draft.adminRecipient !== item.recipient_roles.ADMIN) return false;
  // No bands at all — nothing to compare (NOTIFICATION rows).
  if (!draft.thresholds) return true;
  return draftBandsEqual(draft.thresholds, toThresholdDrafts(item.thresholds));
}

export function catalogErrorMessage(error: unknown, fallback: string): string {
  let message = fallback;
  if (!error || typeof error !== "object") {
    message = error instanceof Error ? error.message : fallback;
  } else {
    const maybeAxios = error as {
      message?: string;
      response?: {
        data?: {
          detail?: string | { message?: string } | Array<{ msg?: string }>;
          error?: { message?: string };
          message?: string;
        };
      };
    };
    const detail = maybeAxios.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      message = detail;
    } else if (Array.isArray(detail) && detail.length > 0) {
      // Raw pydantic 422 — a list of field errors rather than the app envelope.
      message = detail
        .map((entry) => entry.msg)
        .filter(Boolean)
        .join("; ") || fallback;
    } else if (detail && !Array.isArray(detail) && typeof detail === "object" && detail.message) {
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
  const [scopeFilter, setScopeFilter] = useState<CatalogScopeFilter>("all");
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

  /**
   * Filters on the saved scope, not the draft: filtering on the draft would
   * make a row vanish from under the cursor the moment its toggle is flipped
   * while a scope filter is active.
   */
  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(
      (item) =>
        (scopeFilter === "all" || item.scope === scopeFilter) &&
        (!q ||
          item.display_name.toLowerCase().includes(q) ||
          item.name.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q)),
    );
  }, [items, scopeFilter, search]);

  const updateDraft = useCallback(
    (
      name: string,
      update: (current: CatalogDraft, item: NotificationAlertCatalogItem) => CatalogDraft,
    ) => {
      setDrafts((prev) => {
        const item = items.find((row) => row.name === name);
        if (!item) return prev;
        return { ...prev, [name]: update(prev[name] ?? toDraft(item), item) };
      });
    },
    [items],
  );

  /**
   * INSTITUTION forces the Adopter Admin copy off (the BE does too).
   * GLOBAL turns it on, per design ("defaults to selected") — the BE only
   * defaults a *missing* ADMIN key, and every stored INSTITUTION row already
   * holds ADMIN=false, so a scope-only PATCH would leave it off. Flipping
   * back to the saved scope restores the saved value instead, so an
   * out-and-back toggle leaves the row clean.
   */
  const setScope = useCallback(
    (name: string, scope: NotificationScope) => {
      updateDraft(name, (current, item) => ({
        ...current,
        scope,
        adminRecipient:
          scope === item.scope ? item.recipient_roles.ADMIN : scope === "GLOBAL",
      }));
    },
    [updateDraft],
  );

  const setAdminRecipient = useCallback(
    (name: string, checked: boolean) => {
      updateDraft(name, (current) =>
        current.scope === "INSTITUTION"
          ? current
          : { ...current, adminRecipient: checked },
      );
    },
    [updateDraft],
  );

  /**
   * Replaces a row's whole band set at once — the only threshold mutator.
   * An editable percentage is no stable key to merge a per-band patch
   * against. Bands are validated in the editor on Apply and again on Submit.
   */
  const setThresholds = useCallback(
    (name: string, thresholds: ThresholdDraftBand[]) => {
      updateDraft(name, (current) => ({
        ...current,
        thresholds: thresholds.map((band) => ({ ...band })),
      }));
    },
    [updateDraft],
  );

  const discard = useCallback(() => {
    const nextDrafts: Record<string, CatalogDraft> = {};
    items.forEach((item) => {
      nextDrafts[item.name] = toDraft(item);
    });
    setDrafts(nextDrafts);
    setError(null);
  }, [items]);

  const dirtyCount = useMemo(() => {
    return items.reduce((count, item) => {
      const draft = drafts[item.name];
      if (!draft) return count;
      return draftsEqual(draft, item) ? count : count + 1;
    }, 0);
  }, [items, drafts]);

  /**
   * Rows about to move GLOBAL -> INSTITUTION. The BE resets every
   * institution's subscription to unsubscribed on that flip, so the UI
   * confirms before submitting them.
   */
  const pendingInstitutionFlips = useMemo(
    () =>
      items.filter(
        (item) =>
          item.scope === "GLOBAL" && drafts[item.name]?.scope === "INSTITUTION",
      ),
    [items, drafts],
  );

  const submit = useCallback(async (): Promise<CatalogSubmitResult> => {
    setIsSubmitting(true);
    setError(null);
    const succeeded: string[] = [];
    try {
      for (const item of items) {
        const draft = drafts[item.name];
        if (!draft || draftsEqual(draft, item)) continue;

        // ADMIN is always sent explicitly — see setScope for why the BE's
        // own default can't be relied on after a scope flip.
        const payload: CatalogUpdatePayload = {
          recipient_roles: { ADMIN: draft.adminRecipient },
        };
        if (draft.scope !== item.scope) payload.scope = draft.scope;
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
    scopeFilter,
    setScopeFilter,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setScope,
    setAdminRecipient,
    setThresholds,
    discard,
    dirtyCount,
    pendingInstitutionFlips,
    submit,
    reload: load,
  };
}
