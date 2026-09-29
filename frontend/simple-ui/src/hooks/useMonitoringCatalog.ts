import { useCallback, useEffect, useMemo, useState } from "react";
import { notificationAlertsService } from "../services/notificationAlertsService";
import type {
  MonitoringCatalogItem,
  MonitoringCatalogUpdatePayload,
  MonitoringRecipientRole,
  MonitoringThresholdDraftBand,
} from "../types/notificationAlerts";
import {
  MONITORING_RECIPIENT_ROLES,
  monitoringDraftBandsEqual,
  toMonitoringThresholdDrafts,
  validateMonitoringThresholdDrafts,
} from "../types/notificationAlerts";
import {
  catalogErrorMessage,
  type CatalogSubmitResult,
} from "./useNotificationCatalog";

export interface MonitoringCatalogDraft {
  recipients: Record<MonitoringRecipientRole, boolean>;
  /** Always the complete band set. */
  thresholds: MonitoringThresholdDraftBand[];
}

/** Bands are sorted on load and after each save only — see useNotificationCatalog. */
function toDraft(item: MonitoringCatalogItem): MonitoringCatalogDraft {
  return {
    recipients: { ...item.recipient_roles },
    thresholds: toMonitoringThresholdDrafts(item.monitoring_thresholds),
  };
}

function recipientsEqual(
  a: Record<MonitoringRecipientRole, boolean>,
  b: Record<MonitoringRecipientRole, boolean>,
): boolean {
  return MONITORING_RECIPIENT_ROLES.every((role) => a[role] === b[role]);
}

function thresholdsEqual(
  draft: MonitoringCatalogDraft,
  item: MonitoringCatalogItem,
): boolean {
  return monitoringDraftBandsEqual(
    draft.thresholds,
    toMonitoringThresholdDrafts(item.monitoring_thresholds),
  );
}

function draftsEqual(draft: MonitoringCatalogDraft, item: MonitoringCatalogItem): boolean {
  return (
    recipientsEqual(draft.recipients, item.recipient_roles) &&
    thresholdsEqual(draft, item)
  );
}

/**
 * Adopter Admin editor state for the MONITORING catalog rows. Same shape
 * as useNotificationCatalog minus everything scope-related — monitoring
 * alerts are platform-level, so there's no scope toggle, scope filter or
 * GLOBAL -> INSTITUTION confirmation.
 */
export function useMonitoringCatalog() {
  const [items, setItems] = useState<MonitoringCatalogItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, MonitoringCatalogDraft>>({});
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);
    try {
      const rows = await notificationAlertsService.listMonitoringCatalog(signal);
      if (signal?.aborted) return;
      setItems(rows);
      const nextDrafts: Record<string, MonitoringCatalogDraft> = {};
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
      setError(catalogErrorMessage(e, "Failed to load monitoring alerts."));
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const getDraft = useCallback(
    (item: MonitoringCatalogItem): MonitoringCatalogDraft =>
      drafts[item.name] ?? toDraft(item),
    [drafts],
  );

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.display_name.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q),
    );
  }, [items, search]);

  const updateDraft = useCallback(
    (
      name: string,
      update: (current: MonitoringCatalogDraft) => MonitoringCatalogDraft,
    ) => {
      setDrafts((prev) => {
        const item = items.find((row) => row.name === name);
        if (!item) return prev;
        return { ...prev, [name]: update(prev[name] ?? toDraft(item)) };
      });
    },
    [items],
  );

  const setRecipients = useCallback(
    (name: string, roles: MonitoringRecipientRole[]) => {
      updateDraft(name, (current) => ({
        ...current,
        recipients: {
          ADMIN: roles.includes("ADMIN"),
          MODERATOR: roles.includes("MODERATOR"),
        },
      }));
    },
    [updateDraft],
  );

  /** Replaces a row's whole band set — validated in the editor on Apply and again on Submit. */
  const setThresholds = useCallback(
    (name: string, thresholds: MonitoringThresholdDraftBand[]) => {
      updateDraft(name, (current) => ({
        ...current,
        thresholds: thresholds.map((band) => ({ ...band })),
      }));
    },
    [updateDraft],
  );

  const discard = useCallback(() => {
    const nextDrafts: Record<string, MonitoringCatalogDraft> = {};
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

  const submit = useCallback(async (): Promise<CatalogSubmitResult> => {
    setIsSubmitting(true);
    setError(null);
    const succeeded: string[] = [];
    try {
      for (const item of items) {
        const draft = drafts[item.name];
        if (!draft || draftsEqual(draft, item)) continue;

        // Only the parts that changed — the BE leaves absent fields alone.
        const payload: MonitoringCatalogUpdatePayload = {};
        if (!recipientsEqual(draft.recipients, item.recipient_roles)) {
          payload.recipient_roles = { ...draft.recipients };
        }
        if (!thresholdsEqual(draft, item)) {
          const { bands } = validateMonitoringThresholdDrafts(draft.thresholds);
          if (!bands) {
            const message = `Fix the thresholds on '${item.display_name}' before saving.`;
            setError(message);
            return { succeeded, failed: { name: item.name, message } };
          }
          payload.monitoring_thresholds = bands;
        }

        try {
          const updated = await notificationAlertsService.updateMonitoringCatalog(
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
    setRecipients,
    setThresholds,
    discard,
    dirtyCount,
    submit,
    reload: load,
  };
}
