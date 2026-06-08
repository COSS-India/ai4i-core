import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  Checkbox,
  CheckboxGroup,
  Flex,
  FormControl,
  FormHelperText,
  FormLabel,
  Heading,
  HStack,
  IconButton,
  Input,
  Select,
  Spinner,
  Stack,
  Switch,
  Text,
  Textarea,
  Tooltip,
  useDisclosure,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import StandardModal from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import { useAdminTableSurface } from "../common/TableControls";
import {
  policyService,
  type AuditLogOut,
  type MaskFormat,
  type PiiTypeOut,
  type PolicyOut,
} from "../../services/policyService";
import { isTenantStatus, TENANT } from "../../config/constants";
import { listTenants } from "../../services/tenantService";
import type { TenantView } from "../../types/tenant";
import { AUDIT_PAGE_SIZE_OPTIONS, LANGUAGE_OPTIONS, MASK_OPTIONS } from "./constants";
import { formatDt, getPolicyApiErrorMessage, parseDelimitedValues, useDebouncedValue } from "./utils";

export default function AuditPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const [items, setItems] = useState<AuditLogOut[]>([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tenantFilter, setTenantFilter] = useState("");
  const [policyIdFilter, setPolicyIdFilter] = useState("");
  const [traceIdFilter, setTraceIdFilter] = useState("");
  const [minPii, setMinPii] = useState("");
  const [auditCreatedSort, setAuditCreatedSort] = useState<"asc" | "desc">("desc");
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

  const displayItems = useMemo(() => {
    const copy = [...items];
    copy.sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
      return auditCreatedSort === "desc" ? tb - ta : ta - tb;
    });
    return copy;
  }, [items, auditCreatedSort]);

  const openDetail = async (id: string) => {
    try {
      const res = await policyService.getAuditLog(id);
      setDetailJson(JSON.stringify(res.data.trace_json ?? res.data, null, 2));
      detailModal.onOpen();
    } catch (e: unknown) {
      toast({
        title: getPolicyApiErrorMessage(e, "Could not load log detail"),
        status: "error",
      });
    }
  };

  const formatAuditChipId = (id: string, maxLen = 14) =>
    id.length > maxLen ? `${id.slice(0, 8)}…` : id;

  const auditColumns = useMemo((): AdminTableColumn<AuditLogOut>[] => [
    {
      id: "tenant",
      header: "Tenant",
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
      cell: (row) => row.pii_count ?? "—",
    },
    {
      id: "ms",
      header: "ms",
      thProps: { isNumeric: true },
      tdProps: { isNumeric: true },
      cell: (row) => row.processing_ms ?? "—",
    },
    {
      id: "created",
      header: "Created",
      sortable: {
        label: "Created",
        direction: auditCreatedSort,
        onAsc: () => setAuditCreatedSort("asc"),
        onDesc: () => setAuditCreatedSort("desc"),
        ascAriaLabel: "Sort audit rows by created time ascending",
        descAriaLabel: "Sort audit rows by created time descending",
      },
      tdProps: { whiteSpace: "nowrap" },
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "detail",
      header: "Detail",
      thProps: { textAlign: "right" },
      tdProps: { textAlign: "right", onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <Tooltip label="View JSON detail" hasArrow placement="top">
          <IconButton
            aria-label="View audit log JSON"
            icon={<ViewIcon />}
            size="sm"
            variant="ghost"
            colorScheme="blue"
            _hover={{ bg: "blue.50" }}
            onClick={() => void openDetail(row.pii_audit_id)}
          />
        </Tooltip>
      ),
    },
  ], [auditCreatedSort, openDetail]);

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <AdminDataTable<AuditLogOut>
        items={displayItems}
        columns={auditColumns}
        getRowKey={(row) => row.pii_audit_id}
        filters={
          <VStack align="stretch" spacing={3} flex="1" w="full">
            <HStack spacing={3} align="flex-end" flexWrap="wrap" rowGap={3} w="full">
              <FormControl w={{ base: "full", sm: "200px" }}>
                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                  Tenant ID
                </FormLabel>
                <Input
                  size="sm"
                  value={tenantFilter}
                  onChange={(e) => setTenantFilter(e.target.value)}
                  placeholder="Filter…"
                  bg={cardBg}
                />
              </FormControl>
              <FormControl w={{ base: "full", sm: "200px" }}>
                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                  Policy ID
                </FormLabel>
                <Input
                  size="sm"
                  value={policyIdFilter}
                  onChange={(e) => setPolicyIdFilter(e.target.value)}
                  placeholder="UUID…"
                  bg={cardBg}
                />
              </FormControl>
              <FormControl w={{ base: "full", sm: "200px" }}>
                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                  Trace ID
                </FormLabel>
                <Input
                  size="sm"
                  value={traceIdFilter}
                  onChange={(e) => setTraceIdFilter(e.target.value)}
                  placeholder="Filter…"
                  bg={cardBg}
                />
              </FormControl>
              <FormControl w={{ base: "full", sm: "140px" }}>
                <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                  Min PII count
                </FormLabel>
                <Input
                  size="sm"
                  type="number"
                  min={0}
                  value={minPii}
                  onChange={(e) => setMinPii(e.target.value)}
                  bg={cardBg}
                />
              </FormControl>
            </HStack>
            {hasActiveFilters ? (
              <HStack spacing={2} flexWrap="wrap">
                {debouncedFilters.tenant !== "" ? (
                  <Badge
                    colorScheme="blue"
                    fontSize="xs"
                    px={2}
                    py={1}
                    cursor="pointer"
                    onClick={() => setTenantFilter("")}
                    _hover={{ opacity: 0.8 }}
                  >
                    Tenant: {debouncedFilters.tenant} ×
                  </Badge>
                ) : null}
                {debouncedFilters.policy !== "" ? (
                  <Badge
                    colorScheme="gray"
                    fontSize="xs"
                    px={2}
                    py={1}
                    cursor="pointer"
                    onClick={() => setPolicyIdFilter("")}
                    _hover={{ opacity: 0.8 }}
                  >
                    Policy: {formatAuditChipId(debouncedFilters.policy)} ×
                  </Badge>
                ) : null}
                {debouncedFilters.trace !== "" ? (
                  <Badge
                    colorScheme="gray"
                    fontSize="xs"
                    px={2}
                    py={1}
                    cursor="pointer"
                    onClick={() => setTraceIdFilter("")}
                    _hover={{ opacity: 0.8 }}
                  >
                    Trace: {formatAuditChipId(debouncedFilters.trace)} ×
                  </Badge>
                ) : null}
                {debouncedFilters.minPii !== "" ? (
                  <Badge
                    colorScheme="gray"
                    fontSize="xs"
                    px={2}
                    py={1}
                    cursor="pointer"
                    onClick={() => setMinPii("")}
                    _hover={{ opacity: 0.8 }}
                  >
                    Min PII: {debouncedFilters.minPii} ×
                  </Badge>
                ) : null}
              </HStack>
            ) : null}
          </VStack>
        }
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearAllFilters}
        filterToolbarAlign="flex-end"
        isLoading={loading}
        loadingMessage="Loading audit logs…"
        emptyMessage="No audit entries yet."
        noResultsMessage="No results found. Try adjusting your filters or pagination."
        onRowClick={(row) => void openDetail(row.pii_audit_id)}
        paginate="server"
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
