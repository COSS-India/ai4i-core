import { useCallback, useEffect, useMemo, useState } from "react";
import { notificationAlertsService } from "../services/notificationAlertsService";
import type {
  NotificationAlertType,
  NotificationSubscriptionItem,
  SubscriptionStatusFilter,
} from "../types/notificationAlerts";
import { catalogErrorMessage, type CatalogSubmitResult } from "./useNotificationCatalog";

export interface SubscriptionDraft {
  /** Ignored (always true) on locked rows. */
  subscribed: boolean;
  recipients: string[];
}

function toDraft(item: NotificationSubscriptionItem): SubscriptionDraft {
  return { subscribed: item.subscribed, recipients: [...item.recipients] };
}

/** Order-insensitive — the picker doesn't preserve the saved order. */
function sameRecipients(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((id) => set.has(id));
}

function subscribedChanged(draft: SubscriptionDraft, item: NotificationSubscriptionItem): boolean {
  return !item.locked && draft.subscribed !== item.subscribed;
}

function draftsEqual(draft: SubscriptionDraft, item: NotificationSubscriptionItem): boolean {
  return !subscribedChanged(draft, item) && sameRecipients(draft.recipients, item.recipients);
}

function matchesStatus(item: NotificationSubscriptionItem, status: SubscriptionStatusFilter): boolean {
  switch (status) {
    case "mandatory":
      return item.locked;
    case "subscribed":
      return !item.locked && item.subscribed;
    case "unsubscribed":
      return !item.subscribed;
    default:
      return true;
  }
}

function isAbort(e: unknown): boolean {
  const err = e as { code?: string; name?: string } | undefined;
  return (
    err?.code === "ERR_CANCELED" ||
    err?.name === "CanceledError" ||
    err?.name === "AbortError"
  );
}

/**
 * Institution Admin's subscriptions for one catalog type. Same draft-then-
 * Submit model as useNotificationCatalog: toggles and recipient picks stay
 * local until Submit, which sends one PATCH (subscribe state) and/or one PUT
 * (recipients) per changed row, in order, stopping at the first failure.
 */
export function useNotificationSubscriptions(
  type: NotificationAlertType,
  tenantId: string | null,
) {
  const [items, setItems] = useState<NotificationSubscriptionItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, SubscriptionDraft>>({});
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<SubscriptionStatusFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!tenantId) {
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const rows = await notificationAlertsService.listSubscriptions(tenantId, type, signal);
        if (signal?.aborted) return;
        setItems(rows);
        const nextDrafts: Record<string, SubscriptionDraft> = {};
        rows.forEach((row) => {
          nextDrafts[row.name] = toDraft(row);
        });
        setDrafts(nextDrafts);
      } catch (e) {
        if (signal?.aborted || isAbort(e)) return;
        setError(catalogErrorMessage(e, "Failed to load subscriptions."));
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [tenantId, type],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const getDraft = useCallback(
    (item: NotificationSubscriptionItem): SubscriptionDraft =>
      drafts[item.name] ?? toDraft(item),
    [drafts],
  );

  /** Filters on the saved state, so a row doesn't vanish mid-edit. */
  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(
      (item) =>
        matchesStatus(item, statusFilter) &&
        (!q ||
          item.display_name.toLowerCase().includes(q) ||
          item.name.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q)),
    );
  }, [items, search, statusFilter]);

  const updateDraft = useCallback(
    (name: string, update: (current: SubscriptionDraft) => SubscriptionDraft) => {
      setDrafts((prev) => {
        const item = items.find((row) => row.name === name);
        if (!item) return prev;
        return { ...prev, [name]: update(prev[name] ?? toDraft(item)) };
      });
    },
    [items],
  );

  const setSubscribed = useCallback(
    (name: string, subscribed: boolean) => {
      const item = items.find((row) => row.name === name);
      if (!item || item.locked) return;
      updateDraft(name, (current) => ({ ...current, subscribed }));
    },
    [items, updateDraft],
  );

  /** Recipients are kept (not cleared) on unsubscribe — the BE keeps them too. */
  const setRecipients = useCallback(
    (name: string, recipients: string[]) => {
      updateDraft(name, (current) => ({ ...current, recipients: [...recipients] }));
    },
    [updateDraft],
  );

  const discard = useCallback(() => {
    const nextDrafts: Record<string, SubscriptionDraft> = {};
    items.forEach((item) => {
      nextDrafts[item.name] = toDraft(item);
    });
    setDrafts(nextDrafts);
    setError(null);
  }, [items]);

  const dirtyCount = useMemo(
    () =>
      items.reduce((count, item) => {
        const draft = drafts[item.name];
        return draft && !draftsEqual(draft, item) ? count + 1 : count;
      }, 0),
    [items, drafts],
  );

  /**
   * `inactiveIds`: recipients deactivated since they were saved. They stay
   * in the draft (shown greyed, still counted) but are left out of the PUT
   * — the API rejects an inactive id, and the send path skips them anyway.
   */
  const submit = useCallback(async (
    inactiveIds: ReadonlySet<string> = new Set(),
  ): Promise<CatalogSubmitResult> => {
    const succeeded: string[] = [];
    if (!tenantId) return { succeeded };
    setIsSubmitting(true);
    setError(null);
    try {
      for (const item of items) {
        const draft = drafts[item.name];
        if (!draft || draftsEqual(draft, item)) continue;

        const replaceItem = (updated: NotificationSubscriptionItem) =>
          setItems((prev) =>
            prev.map((row) => (row.name === updated.name ? updated : row)),
          );

        try {
          let updated = item;
          if (subscribedChanged(draft, item)) {
            updated = await notificationAlertsService.updateSubscriptionState(
              tenantId,
              item.notification_id,
              draft.subscribed,
            );
            // Applied now, not after the PUT: if the PUT then fails, the
            // row stays dirty for its recipients only.
            replaceItem(updated);
          }
          if (!sameRecipients(draft.recipients, item.recipients)) {
            updated = await notificationAlertsService.updateSubscriptionRecipients(
              tenantId,
              item.notification_id,
              draft.recipients.filter((id) => !inactiveIds.has(id)),
            );
            replaceItem(updated);
          }
          succeeded.push(updated.display_name);
          setDrafts((prev) => ({ ...prev, [updated.name]: toDraft(updated) }));
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
          return { succeeded, failed: { name: item.display_name, message } };
        }
      }
      return { succeeded };
    } finally {
      setIsSubmitting(false);
    }
  }, [drafts, items, tenantId]);

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
    setSubscribed,
    setRecipients,
    discard,
    dirtyCount,
    submit,
    reload: load,
  };
}
