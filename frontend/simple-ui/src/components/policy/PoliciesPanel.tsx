import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  HStack,
  Switch,
  Text,
  Tooltip,
  useDisclosure,
} from "@chakra-ui/react";
import { showToast } from "../../utils/toast";
import ConfirmDialog from "../common/ConfirmDialog";
import DataTableActions from "../common/DataTableActions";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import { policyService, type PolicyOut } from "../../services/policyService";
import { INSTITUTION, INSTITUTIONS } from "../../config/constants";
import { PolicyFormModal } from "./PolicyFormModal";
import {
  EMPTY_PII_TYPES,
  PII_TYPES_QUERY_KEY,
  fetchAllPiiTypes,
  formatDt,
  getPolicyApiErrorMessage,
} from "./policyShared";

export function PoliciesPanel({
  onRegisterCreate,
}: {
  onRegisterCreate?: (open: () => void) => void;
}) {
  const [allPolicies, setAllPolicies] = useState<PolicyOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [filterGlobal, setFilterGlobal] = useState("");
  const policySortAccessors = useMemo(
    () => ({
      name: (row: PolicyOut) => row.name ?? "",
      piiTypes: (row: PolicyOut) => row.pii_types?.length ?? 0,
      languages: (row: PolicyOut) => (row.supported_languages ?? []).join(", "),
      tenants: (row: PolicyOut) =>
        row.is_global
          ? `All ${INSTITUTIONS.toLowerCase()}`
          : (row.tenant_ids ?? []).join(", "),
      created: (row: PolicyOut) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
    }),
    [],
  );
  const policySort = useDeferredColumnSort("name", policySortAccessors);
  const [tableEpoch, setTableEpoch] = useState(0);
  const modal = useDisclosure();
  const viewModal = useDisclosure();
  const confirmDeleteModal = useDisclosure();
  const [viewPolicyId, setViewPolicyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PolicyOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const queryClient = useQueryClient();
  const piiQuery = useQuery({
    queryKey: PII_TYPES_QUERY_KEY,
    queryFn: fetchAllPiiTypes,
    staleTime: 60 * 1000,
  });
  const piiOptions = piiQuery.data ?? EMPTY_PII_TYPES;
  const [policyStatusBusyId, setPolicyStatusBusyId] = useState<string | null>(null);
  const [activeStatusTooltipId, setActiveStatusTooltipId] = useState<string | null>(null);
  const statusTooltipTimeoutRef = useRef<number | null>(null);

  const bumpTablePage = useCallback(() => setTableEpoch((n) => n + 1), []);

  const ensurePiiOptions = useCallback(async () => {
    if (piiQuery.data) return;
    await queryClient.fetchQuery({
      queryKey: PII_TYPES_QUERY_KEY,
      queryFn: fetchAllPiiTypes,
    });
  }, [piiQuery.data, queryClient]);

  const reloadPolicies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const acc: PolicyOut[] = [];
      let page = 1;
      const limit = 100;
      for (;;) {
        const res = await policyService.listPolicies({ page, limit });
        acc.push(...res.data.data);
        if (acc.length >= res.data.meta.total || res.data.data.length === 0) break;
        page += 1;
      }
      setAllPolicies(acc);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load policies"));
      setAllPolicies([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadPolicies();
  }, [reloadPolicies]);

  const getSortTimestamp = (value?: string | null): number => {
    if (value == null) return 0;
    const t = new Date(value).getTime();
    return Number.isNaN(t) ? 0 : t;
  };

  const filteredPolicies = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = allPolicies.filter((row) => {
      if (q && !(row.name ?? "").toLowerCase().includes(q)) return false;
      if (filterActive === "true" && !row.is_active) return false;
      if (filterActive === "false" && row.is_active) return false;
      if (filterGlobal === "true" && !row.is_global) return false;
      if (filterGlobal === "false" && row.is_global) return false;
      return true;
    });
    const byCreatedDesc = [...filtered].sort(
      (a, b) => getSortTimestamp(b.created_at) - getSortTimestamp(a.created_at),
    );
    return policySort.apply(byCreatedDesc);
  }, [allPolicies, searchQuery, filterActive, filterGlobal, policySort]);

  const hasActiveFilters =
    filterActive !== "" || filterGlobal !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterActive("");
    setFilterGlobal("");
  };

  const openCreate = () => {
    setEditingId(null);
    modal.onOpen();
  };

  useEffect(() => {
    onRegisterCreate?.(openCreate);
  }, [onRegisterCreate, modal]);

  const openEdit = (id: string) => {
    setEditingId(id);
    modal.onOpen();
  };

  const openPolicyView = (id: string) => {
    setViewPolicyId(id);
    viewModal.onOpen();
  };

  const closePolicyView = () => {
    viewModal.onClose();
    setViewPolicyId(null);
  };

  const requestDelete = (policy: PolicyOut) => {
    setDeleteTarget(policy);
    confirmDeleteModal.onOpen();
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await policyService.deletePolicy(deleteTarget.policy_id);
      showToast({ type: "success", message: "Policy deleted" });
      confirmDeleteModal.onClose();
      if (viewPolicyId === deleteTarget.policy_id) {
        closePolicyView();
      }
      if (editingId === deleteTarget.policy_id) {
        modal.onClose();
        setEditingId(null);
      }
      setDeleteTarget(null);
      await reloadPolicies();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Could not delete policy"),
      });
    } finally {
      setDeleting(false);
    }
  };

  useEffect(() => {
    return () => {
      if (statusTooltipTimeoutRef.current != null) {
        window.clearTimeout(statusTooltipTimeoutRef.current);
      }
    };
  }, []);

  const showStatusTooltip = (policyId: string) => {
    if (statusTooltipTimeoutRef.current != null) {
      window.clearTimeout(statusTooltipTimeoutRef.current);
    }
    setActiveStatusTooltipId(policyId);
    statusTooltipTimeoutRef.current = window.setTimeout(() => {
      setActiveStatusTooltipId((current) => (current === policyId ? null : current));
      statusTooltipTimeoutRef.current = null;
    }, 1500);
  };

  const hideStatusTooltip = (policyId?: string) => {
    if (statusTooltipTimeoutRef.current != null) {
      window.clearTimeout(statusTooltipTimeoutRef.current);
      statusTooltipTimeoutRef.current = null;
    }
    setActiveStatusTooltipId((current) =>
      policyId == null || current === policyId ? null : current
    );
  };

  const handleToggleActive = async (row: PolicyOut) => {
    setPolicyStatusBusyId(row.policy_id);
    try {
      await policyService.setPolicyStatus(row.policy_id, !row.is_active);
      showToast({ type: "success", message: "Status updated" });
      void reloadPolicies();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Could not update status"),
      });
    } finally {
      setPolicyStatusBusyId(null);
    }
  };

  const policyColumns = useMemo((): DataTableColumn<PolicyOut>[] => [
    {
      id: "name",
      header: "Name",
      sortable: true,
      sortAccessor: (row) => row.name ?? "",
      cell: (row) => <Text fontWeight="medium" fontSize="sm">{row.name}</Text>,
    },
    {
      id: "piiTypes",
      header: "PII types",
      sortable: true,
      sortAccessor: (row) => row.pii_types?.length ?? 0,
      cell: (row) => row.pii_types?.length ?? 0,
    },
    {
      id: "languages",
      header: "Languages",
      sortable: true,
      sortAccessor: (row) => (row.supported_languages ?? []).join(", "),
      cell: (row) => row.supported_languages?.join(", ") || "—",
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <Badge colorScheme={row.is_active ? "green" : "gray"}>
          {row.is_active ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      id: "scope",
      header: "Scope",
      cell: (row) => (row.is_global ? "Global" : `${INSTITUTION}-scoped`),
    },
    {
      id: "tenants",
      header: INSTITUTIONS,
      tdProps: { maxW: "180px", isTruncated: true },
      sortable: true,
      sortAccessor: (row) =>
        row.is_global
          ? `All ${INSTITUTIONS.toLowerCase()}`
          : (row.tenant_ids ?? []).join(", "),
      cell: (row) => {
        const tenantLabel = row.is_global
          ? `All ${INSTITUTIONS.toLowerCase()}`
          : (row.tenant_ids?.length ?? 0) > 0
            ? row.tenant_ids!.join(", ")
            : "—";
        return (
          <Box as="span" title={(row.tenant_ids ?? []).join(", ")} display="block" isTruncated>
            {tenantLabel}
          </Box>
        );
      },
    },
    {
      id: "created",
      header: "Created",
      tdProps: { whiteSpace: "nowrap" },
      sortable: true,
      sortAccessor: (row) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "actions",
      header: "Actions",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <HStack spacing={3} align="center">
          <DataTableActions
            actions={[
              {
                id: "edit",
                label: "Edit policy",
                onClick: () => openEdit(row.policy_id),
              },
              {
                id: "delete",
                label: "Delete policy",
                onClick: () => requestDelete(row),
              },
            ]}
          />
          <Tooltip
            label={row.is_active ? "Turn off to deactivate" : "Turn on to activate"}
            hasArrow
            placement="top"
            isOpen={activeStatusTooltipId === row.policy_id}
          >
            <Box
              as="span"
              display="inline-flex"
              alignItems="center"
              onMouseEnter={() => showStatusTooltip(row.policy_id)}
              onMouseLeave={() => hideStatusTooltip(row.policy_id)}
            >
              <Switch
                size="md"
                colorScheme="green"
                isChecked={row.is_active}
                isDisabled={policyStatusBusyId === row.policy_id}
                aria-label={
                  row.is_active ? `Deactivate policy ${row.name}` : `Activate policy ${row.name}`
                }
                onChange={() => {
                  hideStatusTooltip();
                  void handleToggleActive(row);
                }}
                onClick={(e) => e.stopPropagation()}
              />
            </Box>
          </Tooltip>
        </HStack>
      ),
    },
  ], [
    activeStatusTooltipId,
    policyStatusBusyId,
    openEdit,
    requestDelete,
    showStatusTooltip,
    hideStatusTooltip,
    handleToggleActive,
  ]);

  const editForm = modal.isOpen ? (
    <PolicyFormModal
      isOpen
      onClose={() => {
        modal.onClose();
        setEditingId(null);
      }}
      policyId={editingId}
      piiOptions={piiOptions}
      refreshPiiOptions={ensurePiiOptions}
      cachedPolicy={
        editingId
          ? allPolicies.find((policy) => policy.policy_id === editingId) ?? null
          : null
      }
      onSaved={() => {
        modal.onClose();
        setEditingId(null);
        closePolicyView();
        void reloadPolicies();
        showToast({ type: "success", message: "Saved" });
      }}
      onError={(msg) => showToast({ type: "error", message: msg })}
    />
  ) : null;

  return (
    <Box>
      {editForm}
      {viewModal.isOpen && !modal.isOpen ? (
        <PolicyFormModal
          mode="view"
          isOpen
          onClose={closePolicyView}
          policyId={viewPolicyId}
          piiOptions={piiOptions}
          refreshPiiOptions={ensurePiiOptions}
          cachedPolicy={
            viewPolicyId
              ? allPolicies.find((policy) => policy.policy_id === viewPolicyId) ?? null
              : null
          }
          onSaved={() => undefined}
          onViewEdit={(id) => {
            openEdit(id);
          }}
          onViewDelete={(policy) => {
            requestDelete(policy);
          }}
          onError={(msg) => showToast({ type: "error", message: msg })}
        />
      ) : null}
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <DataTable<PolicyOut>
            layout="admin"
            key={tableEpoch}
            items={filteredPolicies}
            columns={policyColumns}
          sort={policySort.sort}
          onSortChange={(next) => { policySort.onSortChange(next); bumpTablePage(); }}
            getRowKey={(row) => row.policy_id}
            search={{
              label: "Search",
              value: searchQuery,
              onChange: setSearchQuery,
              placeholder: "Search by policy name…",
              fields: ["name"],
            }}
            filterDefs={[
              {
                id: "active",
                label: "Active",
                type: "select",
                param: "is_active",
                value: filterActive,
                onChange: setFilterActive,
                options: [
                  { label: "All", value: "" },
                  { label: "Active", value: "true" },
                  { label: "Inactive", value: "false" },
                ],
              },
              {
                id: "scope",
                label: "Scope",
                type: "select",
                param: "is_global",
                value: filterGlobal,
                onChange: setFilterGlobal,
                options: [
                  { label: "All", value: "" },
                  { label: "Global", value: "true" },
                  { label: `${INSTITUTION}-scoped`, value: "false" },
                ],
              },
            ]}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            isLoading={loading}
            loadingMessage="Loading policies…"
            emptyMessage='No policies yet. Click "Create policy" to add one.'
            noResultsMessage="No policies match the current filters."
            unfilteredCount={allPolicies.length}
            onRowClick={(row) => openPolicyView(row.policy_id)}
            paginate="client"
            paginationPosition="bottom"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            tableContainerProps={{ overflowX: "auto" }}
          />

      <ConfirmDialog
        isOpen={confirmDeleteModal.isOpen}
        onClose={() => {
          confirmDeleteModal.onClose();
          if (!deleting) setDeleteTarget(null);
        }}
        title="Delete policy definition"
        body={
          deleteTarget ? (
            <Text>
              Delete <strong>{deleteTarget.name}</strong>? This action cannot be undone.
            </Text>
          ) : null
        }
        onConfirm={() => void handleConfirmDelete()}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={deleting}
      />
    </Box>
  );
}
