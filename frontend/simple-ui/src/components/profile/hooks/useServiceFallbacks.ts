import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { updateApplication } from "../../../services/applicationService";
import { fetchAllServicesMatchingFilters } from "../../../services/servicesManagementService";
import { getViewTenant } from "../../../services/tenantService";
import { parseError } from "../../../utils/errorHandler";
import { SERVICE_FALLBACK_COPY } from "../../../config/serviceFallbackMessages";
import type { Application } from "../../../types/application";
import {
  buildFallbackCatalogue,
  countFallbackChanges,
  emptyFallbackRow,
  fallbackMapFromRows,
  isRowComplete,
  isRowStale,
  markRowsSaved,
  rowsFromFallbackMap,
  withFallback,
  withPrimary,
  type FallbackCatalogue,
  type FallbackRow,
} from "../serviceFallbackDraft";

const COPY = SERVICE_FALLBACK_COPY.editor;

export type FallbackCatalogueStatus = "idle" | "loading" | "error" | "no-tier" | "ready";

export interface FallbackCatalogueState {
  status: FallbackCatalogueStatus;
  tierName: string | null;
  catalogue: FallbackCatalogue;
  retry: () => void;
}

/** The Institution's Tier and the published services mapped to it. */
export function useFallbackCatalogue(tenantId: string, enabled: boolean): FallbackCatalogueState {
  const tenantQuery = useQuery({
    queryKey: ["application-fallback-tenant", tenantId],
    queryFn: () => getViewTenant(tenantId),
    enabled: enabled && Boolean(tenantId),
  });
  const tierId = tenantQuery.data?.tier_id?.trim() || null;
  const servicesQuery = useQuery({
    queryKey: ["application-fallback-services", tierId],
    // Every task type: the fallback options are narrowed to the primary's task type.
    queryFn: () => fetchAllServicesMatchingFilters({ isPublished: true, tierIds: tierId ?? undefined }),
    enabled: enabled && Boolean(tierId),
  });

  const services = servicesQuery.data?.items;
  const catalogue = useMemo(() => buildFallbackCatalogue(services ?? []), [services]);

  let status: FallbackCatalogueStatus = "ready";
  if (!enabled && !tenantQuery.data) status = "idle";
  else if (tenantQuery.isError || servicesQuery.isError) status = "error";
  else if (tenantQuery.isPending) status = "loading";
  else if (!tierId) status = "no-tier";
  else if (servicesQuery.isPending) status = "loading";

  const { refetch: refetchTenant } = tenantQuery;
  const { refetch: refetchServices } = servicesQuery;
  const tenantFailed = tenantQuery.isError;
  const retry = useCallback(() => {
    if (tenantFailed) void refetchTenant();
    else void refetchServices();
  }, [tenantFailed, refetchTenant, refetchServices]);

  return {
    status,
    tierName: tierId ? tenantQuery.data?.tier_name?.trim() || null : null,
    catalogue,
    retry,
  };
}

/**
 * Draft state for the Service fallbacks modal. Saving sends only
 * `service_fallbacks`, which replaces the Application's whole map, and keeps
 * the modal open so the fallbacks stay editable.
 */
export function useServiceFallbackEditor({
  tenantId,
  catalogue,
  catalogueReady,
  onSaved,
  onClose,
}: {
  tenantId: string;
  catalogue: FallbackCatalogue;
  catalogueReady: boolean;
  onSaved: (application: Application) => void;
  /** With the Application as it now stands, including any save made while open. */
  onClose: (application: Application) => void;
}) {
  const toast = useToast();
  const [application, setApplication] = useState<Application | null>(null);
  const [rows, setRows] = useState<FallbackRow[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Rows need the catalogue to know each saved primary's task type.
  useEffect(() => {
    if (!application || seeded || !catalogueReady) return;
    setRows(rowsFromFallbackMap(application.service_fallbacks, catalogue));
    setSeeded(true);
  }, [application, seeded, catalogueReady, catalogue]);

  const open = useCallback((app: Application) => {
    setApplication(app);
    setRows([]);
    setSeeded(false);
    setBanner(null);
  }, []);

  /** Close, or Cancel when there are unsaved changes: either way they are discarded. */
  const close = () => {
    if (!application || isSaving) return;
    setApplication(null);
    onClose(application);
  };

  const updateRow = (key: string, change: (row: FallbackRow) => FallbackRow) => {
    setRows((prev) => prev.map((row) => (row.key === key ? change(row) : row)));
  };

  const saved = application?.service_fallbacks ?? {};
  const hasIncomplete = rows.some((row) => !isRowComplete(row));
  const hasStale = rows.some((row) => isRowStale(row, catalogue));
  const changeCount = countFallbackChanges(saved, rows);
  const isDirty = changeCount > 0;
  const canSave = seeded && isDirty && !hasIncomplete && !hasStale && !isSaving;

  let statusText: string = COPY.statusClean;
  if (isDirty) {
    if (hasStale) statusText = COPY.statusStale;
    else if (hasIncomplete) statusText = COPY.statusIncomplete;
    else statusText = COPY.statusChanges(changeCount);
  }

  const save = async () => {
    if (!application || !canSave) return;
    setIsSaving(true);
    setBanner(null);
    try {
      const updated = await updateApplication(tenantId, application.application_id, {
        service_fallbacks: fallbackMapFromRows(rows),
      });
      toast({ title: COPY.saved, status: "success", duration: 3000, isClosable: true });
      const next = { ...application, service_fallbacks: updated.service_fallbacks };
      setApplication(next);
      setRows(markRowsSaved);
      onSaved(next);
    } catch (error) {
      setBanner(parseError(error).message);
    } finally {
      setIsSaving(false);
    }
  };

  return {
    application,
    isOpen: Boolean(application),
    rows,
    seeded,
    banner,
    isSaving,
    hasStale,
    isDirty,
    canSave,
    statusText,
    open,
    close,
    save,
    addRow: () => setRows((prev) => [...prev, emptyFallbackRow()]),
    removeRow: (key: string) => setRows((prev) => prev.filter((row) => row.key !== key)),
    removeStaleRows: () => setRows((prev) => prev.filter((row) => !isRowStale(row, catalogue))),
    setPrimary: (key: string, value: string) => updateRow(key, (row) => withPrimary(row, value, catalogue)),
    setFallback: (key: string, value: string) => updateRow(key, (row) => withFallback(row, value)),
  };
}

export type ServiceFallbackEditor = ReturnType<typeof useServiceFallbackEditor>;
