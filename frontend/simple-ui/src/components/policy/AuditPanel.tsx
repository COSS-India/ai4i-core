import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Textarea,
  useDisclosure,
} from "@chakra-ui/react";
import { showToast } from "../../utils/toast";
import StandardModal from "../common/StandardModal";
import DataTableActions from "../common/DataTableActions";
import DataTable, {
  useAdminTableSurface,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import { policyService, type AuditLogOut } from "../../services/policyService";
import { INSTITUTION } from "../../config/constants";
import { formatDt, getPolicyApiErrorMessage } from "./policyShared";

const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export function AuditPanel() {
  const [items, setItems] = useState<AuditLogOut[]>([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tenantFilter, setTenantFilter] = useState("");
  const [policyIdFilter, setPolicyIdFilter] = useState("");
  const [traceIdFilter, setTraceIdFilter] = useState("");
  const [minPii, setMinPii] = useState("");
  const auditSortAccessors = useMemo(
    () => ({
      context: (row: AuditLogOut) => row.target_context ?? "",
      piiCount: (row: AuditLogOut) => row.pii_count ?? 0,
      ms: (row: AuditLogOut) => row.processing_ms ?? 0,
      created: (row: AuditLogOut) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
    }),
    [],
  );
  const auditSort = useDeferredColumnSort("created", auditSortAccessors);
  const detailModal = useDisclosure();
  const [detailJson, setDetailJson] = useState<string>("");

  const filterSnapshot = useMemo(
    () => ({
      tenant: tenantFilter.trim(),
      policy: policyIdFilter.trim(),
      trace: traceIdFilter.trim(),
      minPii: minPii.trim(),
    }),
    [tenantFilter, policyIdFilter, traceIdFilter, minPii]
  );
  const debouncedFilters = useDebouncedValue(filterSnapshot, 350);
  const debouncedKey = useMemo(
    () =>
      `${debouncedFilters.tenant}|${debouncedFilters.policy}|${debouncedFilters.trace}|${debouncedFilters.minPii}`,
    [debouncedFilters]
  );
  const prevDebouncedKeyRef = useRef<string | null>(null);

  const { cardBg } = useAdminTableSurface();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const filtersChanged =
        prevDebouncedKeyRef.current !== null && prevDebouncedKeyRef.current !== debouncedKey;
      const pageForRequest = filtersChanged ? 1 : meta.page;
      prevDebouncedKeyRef.current = debouncedKey;

      const params: Parameters<typeof policyService.listAuditLogs>[0] = {
        page: pageForRequest,
        limit: meta.limit,
      };
      if (debouncedFilters.tenant) params.tenant_id = debouncedFilters.tenant;
      if (debouncedFilters.policy) params.policy_id = debouncedFilters.policy;
      if (debouncedFilters.trace) params.trace_id = debouncedFilters.trace;
      if (debouncedFilters.minPii !== "" && !Number.isNaN(Number(debouncedFilters.minPii))) {
        params.min_pii_count = Number(debouncedFilters.minPii);
      }
      const res = await policyService.listAuditLogs(params);
      setItems(res.data.data);
      setMeta(res.data.meta);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load audit logs"));
    } finally {
      setLoading(false);
    }
  }, [meta.page, meta.limit, debouncedKey, debouncedFilters]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActiveFilters =
    debouncedFilters.tenant !== "" ||
    debouncedFilters.policy !== "" ||
    debouncedFilters.trace !== "" ||
    debouncedFilters.minPii !== "";

  const clearAllFilters = () => {
    setTenantFilter("");
    setPolicyIdFilter("");
    setTraceIdFilter("");
    setMinPii("");
    setMeta((m) => ({ ...m, page: 1 }));
  };

  const displayItems = useMemo(
    () => auditSort.apply(items),
    [items, auditSort],
  );

  const openDetail = async (id: string) => {
    try {
      const res = await policyService.getAuditLog(id);
      setDetailJson(JSON.stringify(res.data.trace_json ?? res.data, null, 2));
      detailModal.onOpen();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Could not load log detail"),
      });
    }
  };

  const auditColumns = useMemo((): DataTableColumn<AuditLogOut>[] => [
    {
      id: "tenant",
      header: INSTITUTION,
      cell: (row) => row.tenant_id || "—",
    },
    {
      id: "policy",
      header: "Policy",
      tdProps: { fontFamily: "mono", fontSize: "xs" },
      cell: (row) => row.policy_id || "—",
    },
    {
      id: "trace",
      header: "Trace",
      tdProps: { fontFamily: "mono", fontSize: "xs", maxW: "120px", isTruncated: true },
      cell: (row) => (
        <Box as="span" title={row.trace_id || ""} display="block" isTruncated maxW="120px">
          {row.trace_id || "—"}
        </Box>
      ),
    },
    {
      id: "context",
      header: "Context",
      tdProps: { maxW: "200px", isTruncated: true },
      sortable: true,
      sortAccessor: (row) => row.target_context ?? "",
      cell: (row) => (
        <Box as="span" title={row.target_context || ""} display="block" isTruncated maxW="200px">
          {row.target_context || "—"}
        </Box>
      ),
    },
    {
      id: "piiCount",
      header: "PII #",
      thProps: { isNumeric: true },
      tdProps: { isNumeric: true },
      sortable: true,
      sortAccessor: (row) => row.pii_count ?? 0,
      cell: (row) => row.pii_count ?? "—",
    },
    {
      id: "ms",
      header: "ms",
      thProps: { isNumeric: true },
      tdProps: { isNumeric: true },
      sortable: true,
      sortAccessor: (row) => row.processing_ms ?? 0,
      cell: (row) => row.processing_ms ?? "—",
    },
    {
      id: "created",
      header: "Created",
      sortable: true,
      sortAccessor: (row) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
      tdProps: { whiteSpace: "nowrap" },
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "detail",
      header: "Detail",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <DataTableActions
          actions={[
            {
              id: "view",
              label: "View JSON detail",
              "aria-label": "View audit log JSON",
              onClick: () => void openDetail(row.pii_audit_id),
            },
          ]}
        />
      ),
    },
  ], [openDetail]);

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <DataTable<AuditLogOut>
        layout="admin"
        items={displayItems}
        columns={auditColumns}
          sort={auditSort.sort}
          onSortChange={auditSort.onSortChange}
        getRowKey={(row) => row.pii_audit_id}
        filterDefs={[
          {
            id: "tenantId",
            label: `${INSTITUTION} ID`,
            type: "text",
            param: "tenant_id",
            value: tenantFilter,
            onChange: setTenantFilter,
            placeholder: "Filter…",
            width: { base: "full", sm: "200px" },
          },
          {
            id: "policyId",
            label: "Policy ID",
            type: "text",
            param: "policy_id",
            value: policyIdFilter,
            onChange: setPolicyIdFilter,
            placeholder: "UUID…",
            width: { base: "full", sm: "200px" },
          },
          {
            id: "traceId",
            label: "Trace ID",
            type: "text",
            param: "trace_id",
            value: traceIdFilter,
            onChange: setTraceIdFilter,
            placeholder: "Filter…",
            width: { base: "full", sm: "200px" },
          },
          {
            id: "minPii",
            label: "Min PII count",
            type: "text",
            param: "min_pii",
            value: minPii,
            onChange: setMinPii,
            inputType: "number",
          },
        ]}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearAllFilters}
        isLoading={loading}
        loadingMessage="Loading audit logs…"
        emptyMessage="No audit entries yet."
        noResultsMessage="No results found. Try adjusting your filters or pagination."
        onRowClick={(row) => void openDetail(row.pii_audit_id)}
        paginate="server"
        paginationPosition="bottom"
        initialPageSize={50}
        pageSizeOptions={AUDIT_PAGE_SIZE_OPTIONS}
        serverPagination={{
          page: meta.page,
          pageSize: meta.limit,
          totalItems: meta.total,
          onPageChange: (page) => setMeta((m) => ({ ...m, page })),
          onPageSizeChange: (limit) => setMeta((m) => ({ ...m, limit, page: 1 })),
          pageSizeOptions: AUDIT_PAGE_SIZE_OPTIONS,
        }}
        tableContainerProps={{ overflowX: "auto" }}
      />

      <StandardModal
        isOpen={detailModal.isOpen}
        onClose={detailModal.onClose}
        title="Audit log by ID (detail)"
        size="xl"
      >
        <Textarea value={detailJson} readOnly fontFamily="mono" fontSize="sm" rows={18} />
      </StandardModal>
    </Box>
  );
}
