import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Badge,
  Box,
  HStack,
  IconButton,
  Switch,
  Text,
  Tooltip,
  useDisclosure,
  useToast,
} from "@chakra-ui/react";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { type AdminTableColumn } from "../../common/AdminDataTable";
import { useAdminTableSurface } from "../../common/TableControls";
import { policyService, type PiiTypeOut, type PolicyOut } from "../../../services/policyService";
import { formatDt, getPolicyApiErrorMessage } from "../utils";

export function usePoliciesPanel(toast: ReturnType<typeof useToast>) {
  const [allPolicies, setAllPolicies] = useState<PolicyOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [filterGlobal, setFilterGlobal] = useState("");
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
  const [tableEpoch, setTableEpoch] = useState(0);
  const modal = useDisclosure();
  const viewModal = useDisclosure();
  const confirmDeleteModal = useDisclosure();
  const [viewPolicyId, setViewPolicyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PolicyOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [piiOptions, setPiiOptions] = useState<PiiTypeOut[]>([]);
  const [policyStatusBusyId, setPolicyStatusBusyId] = useState<string | null>(null);
  const [activeStatusTooltipId, setActiveStatusTooltipId] = useState<string | null>(null);
  const statusTooltipTimeoutRef = useRef<number | null>(null);

  const { cardBg, borderColor } = useAdminTableSurface();
  const bumpTablePage = useCallback(() => setTableEpoch((n) => n + 1), []);

  const loadPiiOptions = useCallback(async () => {
    try {
      const acc: PiiTypeOut[] = [];
      let page = 1;
      const limit = 100;
      for (;;) {
        const res = await policyService.listPiiTypes({ page, limit });
        acc.push(...res.data.data);
        if (acc.length >= res.data.meta.total || res.data.data.length === 0) break;
        page += 1;
      }
      setPiiOptions(acc);
    } catch (e: unknown) {
      setPiiOptions([]);
      toast({
        title: getPolicyApiErrorMessage(e, "Failed to load PII types for the policy form"),
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  }, [toast]);

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

  useEffect(() => {
    void loadPiiOptions();
  }, [loadPiiOptions]);

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
    return [...filtered].sort((a, b) => {
      const createdA = getSortTimestamp(a.created_at);
      const createdB = getSortTimestamp(b.created_at);
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });
      if (sortBy === "time") {
        if (createdB !== createdA) return createdB - createdA;
        return 0;
      }
      if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      if (createdB !== createdA) return createdB - createdA;
      return 0;
    });
  }, [allPolicies, searchQuery, filterActive, filterGlobal, sortBy, nameSortDirection]);

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
      toast({ title: "Policy deleted", status: "success", duration: 2500 });
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
      toast({
        title: getPolicyApiErrorMessage(e, "Could not delete policy"),
        status: "error",
        duration: 5000,
        isClosable: true,
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
      toast({ title: "Status updated", status: "success", duration: 2500 });
      void reloadPolicies();
    } catch (e: unknown) {
      toast({
        title: getPolicyApiErrorMessage(e, "Could not update status"),
        status: "error",
        duration: 4000,
      });
    } finally {
      setPolicyStatusBusyId(null);
    }
  };

  const policyColumns = useMemo((): AdminTableColumn<PolicyOut>[] => [
    {
      id: "name",
      header: "Name",
      sortable: {
        label: "Name",
        direction: nameSortDirection,
        onAsc: () => {
          setSortBy("name");
          setNameSortDirection("asc");
          bumpTablePage();
        },
        onDesc: () => {
          setSortBy("name");
          setNameSortDirection("desc");
          bumpTablePage();
        },
        ascAriaLabel: "Sort policies by name ascending",
        descAriaLabel: "Sort policies by name descending",
      },
      cell: (row) => <Text fontWeight="medium">{row.name}</Text>,
    },
    {
      id: "piiTypes",
      header: "PII types",
      cell: (row) => row.pii_types?.length ?? 0,
    },
    {
      id: "languages",
      header: "Languages",
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
      cell: (row) => (row.is_global ? "Global" : "Tenant-scoped"),
    },
    {
      id: "tenants",
      header: "Tenants",
      tdProps: { maxW: "180px", isTruncated: true },
      cell: (row) => {
        const tenantLabel = row.is_global
          ? "All tenants"
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
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "actions",
      header: "Actions",
      thProps: { textAlign: "right" },
      tdProps: { textAlign: "right", onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <HStack spacing={3} justify="flex-end" align="center">
          <Tooltip label="Edit policy" hasArrow placement="top">
            <IconButton
              aria-label="Edit policy"
              icon={<EditIcon />}
              size="sm"
              variant="ghost"
              colorScheme="blue"
              _hover={{ bg: "blue.50" }}
              onClick={() => openEdit(row.policy_id)}
            />
          </Tooltip>
          <Tooltip label="Delete policy" hasArrow placement="top">
            <IconButton
              aria-label="Delete policy"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              _hover={{ bg: "red.50" }}
              onClick={() => requestDelete(row)}
            />
          </Tooltip>
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
    nameSortDirection,
    bumpTablePage,
    activeStatusTooltipId,
    policyStatusBusyId,
    openEdit,
    requestDelete,
    showStatusTooltip,
    hideStatusTooltip,
    handleToggleActive,
  ]);


  return {
    toast,
    error, cardBg, borderColor, tableEpoch, filteredPolicies, policyColumns,
    searchQuery, setSearchQuery, filterActive, setFilterActive, filterGlobal, setFilterGlobal,
    hasActiveFilters, clearAllFilters, bumpTablePage, openCreate, loading, allPolicies,
    viewModal, viewPolicyId, closePolicyView, openEdit, requestDelete,
    modal, editingId, piiOptions, loadPiiOptions, reloadPolicies,
    confirmDeleteModal, deleteTarget, setDeleteTarget, deleting, handleConfirmDelete, openPolicyView,
  };
}

export type UsePoliciesPanelReturn = ReturnType<typeof usePoliciesPanel>;
