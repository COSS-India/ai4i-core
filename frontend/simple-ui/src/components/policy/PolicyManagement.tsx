import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  CheckboxGroup,
  Flex,
  FormControl,
  Heading,
  HStack,
  IconButton,
  Input,
  Select,
  Spinner,
  Stack,
  Switch,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Textarea,
  Tooltip,
  useDisclosure,
} from "@chakra-ui/react";
import { showToast } from "../../utils/toast";
import {
  DeleteIcon,
  EditIcon,
  ViewIcon,
} from "@chakra-ui/icons";
import StandardModal, { CreateModal } from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import FieldLabel from "../common/FieldLabel";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  useAdminTableSurface,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import {
  policyService,
  type AuditLogOut,
  type MaskFormat,
  type PiiTypeOut,
  type PolicyOut,
} from "../../services/policyService";
import { INSTITUTION, INSTITUTION_ARTICLE, INSTITUTIONS, isTenantStatus, TENANT } from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import { useTenantsList } from "../../hooks/useTenantsList";

const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;

/** Set to `true` to show the Audit log tab again. */
const SHOW_POLICY_AUDIT_TAB = false;

const POLICY_TAB_CONFIG = SHOW_POLICY_AUDIT_TAB
  ? ([
      { id: "pii" as const, label: "PII type library" },
      { id: "policies" as const, label: "Policy definitions" },
      { id: "audit" as const, label: "Audit log" },
    ] as const)
  : ([
      { id: "pii" as const, label: "PII type library" },
      { id: "policies" as const, label: "Policy definitions" },
    ] as const);

type PolicySectionId = (typeof POLICY_TAB_CONFIG)[number]["id"];

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

const LANGUAGE_OPTIONS = ["en", "hi"] as const;
const MASK_OPTIONS: MaskFormat[] = ["full", "partial", "redact"];

function getPolicyApiErrorMessage(e: unknown, fallback: string): string {
  const data = (e as {
    response?: {
      data?: {
        detail?: string | { message?: string } | Array<{ msg?: string }>;
        error?: { message?: string };
        message?: string;
      };
    };
    message?: string;
  })?.response?.data;

  const detail = data?.detail;
  if (Array.isArray(detail)) {
    const validationMessage = detail
      .map((item) => item?.msg)
      .filter((msg): msg is string => typeof msg === "string" && msg.trim().length > 0)
      .join("; ");
    if (validationMessage) return validationMessage;
  }

  if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
    const detailMessage = detail.message;
    if (typeof detailMessage === "string" && detailMessage.trim()) return detailMessage;
  }

  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof data?.error?.message === "string" && data.error.message.trim()) return data.error.message;
  if (typeof data?.message === "string" && data.message.trim()) return data.message;

  const topLevelMessage = (e as { message?: string })?.message;
  if (typeof topLevelMessage === "string" && topLevelMessage.trim()) return topLevelMessage;

  return fallback;
}

function formatDt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function parseDelimitedValues(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export interface PolicyManagementProps {
  /** Platform admin (ADMIN role or superuser); required to call policy APIs. */
  canManage: boolean;
  onRegisterCreatePolicy?: (open: () => void) => void;
}

export default function PolicyManagement({
  canManage,
  onRegisterCreatePolicy,
}: PolicyManagementProps) {
  const [tab, setTab] = useState<PolicySectionId>("pii");

  useEffect(() => {
    if (!SHOW_POLICY_AUDIT_TAB && tab === "audit") {
      setTab("policies");
    }
  }, [tab]);

  if (!canManage) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        Policy Management requires adopter admin access (ADMIN role). {INSTITUTION} users cannot
        change policies here.
      </Alert>
    );
  }

  const policySubTabIndex = Math.max(
    0,
    POLICY_TAB_CONFIG.findIndex((t) => t.id === tab)
  );

  return (
    <Tabs
          variant="enclosed"
          colorScheme="blue"
          index={policySubTabIndex}
          onChange={(idx) => {
            const next = POLICY_TAB_CONFIG[idx];
            if (next) setTab(next.id);
          }}
        >
          <TabList aria-label="Policy Management sections">
            {POLICY_TAB_CONFIG.map(({ id, label }) => (
              <Tab key={id} fontWeight="semibold">
                {label}
              </Tab>
            ))}
          </TabList>
          <TabPanels>
            <TabPanel px={0} pt={6}>
              <PiiTypesPanel />
            </TabPanel>
            <TabPanel px={0} pt={6}>
              <PoliciesPanel onRegisterCreate={onRegisterCreatePolicy} />
            </TabPanel>
            {SHOW_POLICY_AUDIT_TAB ? (
              <TabPanel px={0} pt={6}>
                <AuditPanel />
              </TabPanel>
            ) : null}
          </TabPanels>
        </Tabs>
  );
}

function PoliciesPanel({
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
  const [piiOptions, setPiiOptions] = useState<PiiTypeOut[]>([]);
  const [piiCatalogReady, setPiiCatalogReady] = useState(false);
  const [piiOptionsLoading, setPiiOptionsLoading] = useState(false);
  const [policyStatusBusyId, setPolicyStatusBusyId] = useState<string | null>(null);
  const [activeStatusTooltipId, setActiveStatusTooltipId] = useState<string | null>(null);
  const statusTooltipTimeoutRef = useRef<number | null>(null);

  const bumpTablePage = useCallback(() => setTableEpoch((n) => n + 1), []);

  const loadPiiOptions = useCallback(async () => {
    setPiiOptionsLoading(true);
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
      setPiiCatalogReady(true);
    } catch (e: unknown) {
      setPiiOptions([]);
      setPiiCatalogReady(false);
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Failed to load PII types for the policy form"),
      });
    } finally {
      setPiiOptionsLoading(false);
    }
  }, []);

  const ensurePiiOptions = useCallback(async () => {
    if (piiCatalogReady || piiOptionsLoading) return;
    await loadPiiOptions();
  }, [loadPiiOptions, piiCatalogReady, piiOptionsLoading]);

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
    activeStatusTooltipId,
    policyStatusBusyId,
    openEdit,
    requestDelete,
    showStatusTooltip,
    hideStatusTooltip,
    handleToggleActive,
  ]);

  return (
    <Box>
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
                width: { base: "full", sm: "140px" },
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
                width: { base: "full", sm: "160px" },
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

      <PolicyFormModal
        mode="view"
        isOpen={viewModal.isOpen}
        onClose={closePolicyView}
        policyId={viewPolicyId}
        piiOptions={piiOptions}
        refreshPiiOptions={ensurePiiOptions}
        onSaved={() => undefined}
        onViewEdit={(id) => {
          closePolicyView();
          openEdit(id);
        }}
        onViewDelete={(policy) => {
          closePolicyView();
          requestDelete(policy);
        }}
        onError={(msg) =>
          showToast({ type: "error", message: msg })
        }
      />

      <PolicyFormModal
        isOpen={modal.isOpen}
        onClose={modal.onClose}
        policyId={editingId}
        piiOptions={piiOptions}
        refreshPiiOptions={loadPiiOptions}
        onSaved={() => {
          modal.onClose();
          void reloadPolicies();
          void loadPiiOptions();
          showToast({ type: "success", message: "Saved" });
        }}
        onError={(msg) =>
          showToast({ type: "error", message: msg })
        }
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

function PolicyFormModal({
  isOpen,
  onClose,
  policyId,
  piiOptions,
  refreshPiiOptions,
  onSaved,
  onError,
  mode,
  onViewEdit,
  onViewDelete,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  piiOptions: PiiTypeOut[];
  refreshPiiOptions: () => Promise<void> | void;
  onSaved: () => void;
  onError: (msg: string) => void;
  mode?: "create" | "edit" | "view";
  onViewEdit?: (id: string) => void;
  onViewDelete?: (policy: PolicyOut) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isGlobal, setIsGlobal] = useState(true);
  const [tenantIds, setTenantIds] = useState<string[]>([]);
  const [tenantInput, setTenantInput] = useState("");
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [selectedPii, setSelectedPii] = useState<string[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadedPolicy, setLoadedPolicy] = useState<PolicyOut | null>(null);
  const resolvedMode = mode ?? (policyId ? "edit" : "create");
  const readOnly = resolvedMode === "view";
  const tenantsQuery = useTenantsList({ enabled: isOpen });
  const tenantsError = tenantsQuery.isError
    ? `Could not load ${INSTITUTIONS.toLowerCase()}. You can enter ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()} ID below.`
    : null;
  const tenantsLoading = tenantsQuery.isLoading;
  const tenants = useMemo(() => {
    const list = (tenantsQuery.data?.tenants ?? []).filter((tenant) =>
      isTenantStatus(tenant.status, TENANT.STATUS.ACTIVE)
    );
    return [...list].sort((a, b) =>
      (a.organisation ?? "").localeCompare(b.organisation ?? "", undefined, {
        sensitivity: "base",
      })
    );
  }, [tenantsQuery.data]);

  useEffect(() => {
    if (!isOpen) return;
    // Reuse the page catalog when it is already loaded; fetch only if mount
    // load failed or has not produced a result yet.
    void refreshPiiOptions();
  }, [isOpen, refreshPiiOptions]);

  useEffect(() => {
    if (!isOpen) return;
    if (!policyId) {
      setName("");
      setDescription("");
      setIsGlobal(true);
      setTenantIds([]);
      setTenantInput("");
      setLangs(["en"]);
      setSelectedPii([]);
      setLoadedPolicy(null);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    const run = async () => {
      try {
        const res = await policyService.getPolicy(policyId);
        if (cancelled) return;
        const p = res.data;
        setName(p.name);
        setDescription(p.description || "");
        setIsGlobal(p.is_global);
        const tids = p.tenant_ids ?? [];
        setTenantIds(tids);
        setTenantInput(tids.join(", "));
        setLangs(p.supported_languages?.length ? p.supported_languages : ["en"]);
        setSelectedPii((p.pii_types || []).map((x: { pii_type_id: string }) => x.pii_type_id));
        setLoadedPolicy(p);
      } catch (e: unknown) {
        if (!cancelled) onError(getPolicyApiErrorMessage(e, "Failed to load policy"));
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, policyId, onError]);

  const handleSubmit = async () => {
    const normalizedTenantIds =
      tenantsError || tenants.length === 0 ? parseDelimitedValues(tenantInput) : tenantIds;

    if (!name.trim()) {
      onError("Name is required");
      return;
    }
    if (!langs.length) {
      onError("Select at least one language");
      return;
    }
    if (!isGlobal && !normalizedTenantIds.length) {
      onError(`Select at least one ${INSTITUTION.toLowerCase()} for non-global policies`);
      return;
    }
    if (!selectedPii.length) {
      onError("Select at least one PII type");
      return;
    }
    const pii_types = selectedPii.map((pii_type_id) => ({ pii_type_id }));
    setSaving(true);
    try {
      if (policyId) {
        const body: Parameters<typeof policyService.updatePolicy>[1] = {
          name: name.trim(),
          description: description.trim() || null,
          supported_languages: langs,
          is_global: isGlobal,
          tenant_ids: isGlobal ? [] : normalizedTenantIds,
          pii_types,
        };
        await policyService.updatePolicy(policyId, body);
      } else {
        await policyService.createPolicy({
          name: name.trim(),
          description: description.trim() || undefined,
          is_global: isGlobal,
          supported_languages: langs,
          tenant_ids: isGlobal ? undefined : normalizedTenantIds,
          pii_types,
        });
      }
      onSaved();
    } catch (e: unknown) {
      onError(getPolicyApiErrorMessage(e, "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const piiById = useMemo(
    () => new Map(piiOptions.map((p) => [p.pii_type_id, p])),
    [piiOptions]
  );
  const tenantById = useMemo(
    () => new Map(tenants.map((tenant) => [tenant.tenant_id, tenant])),
    [tenants]
  );
  // CreateModal already scrolls; keep a nested cap only on Edit StandardModal.
  const optionListScroll = policyId
    ? { maxH: "220px" as const, overflowY: "auto" as const }
    : {};

  const formBody = loadingDetail ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : (
        <Stack spacing={4}>
          {readOnly && loadedPolicy ? (
            <Stack spacing={2}>
              <Text fontSize="xs" color="gray.500" fontFamily="mono">
                {loadedPolicy.policy_id}
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                <Badge colorScheme={loadedPolicy.is_active ? "green" : "gray"}>
                  {loadedPolicy.is_active ? "Active" : "Inactive"}
                </Badge>
                <Badge colorScheme={loadedPolicy.is_global ? "blue" : "purple"}>
                  {loadedPolicy.is_global ? "Global" : `${INSTITUTION}-scoped`}
                </Badge>
              </HStack>
              <Text fontSize="sm" color="gray.600">
                Created {formatDt(loadedPolicy.created_at)}
              </Text>
            </Stack>
          ) : null}
          <FormControl isRequired={!readOnly}>
            <FieldLabel variant={readOnly ? "inline" : undefined}>Name</FieldLabel>
            {readOnly ? (
              <Text fontSize="md">{name || "—"}</Text>
            ) : (
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            )}
          </FormControl>
          <FormControl>
            <FieldLabel variant={readOnly ? "inline" : undefined}>Description</FieldLabel>
            {readOnly ? (
              <Text fontSize="md">{description || "No description"}</Text>
            ) : (
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            )}
          </FormControl>
          <FormControl display="flex" alignItems="center">
            <FieldLabel formLabelProps={{ mb: 0 }}>Global policy</FieldLabel>
            <Switch
              isChecked={isGlobal}
              isDisabled={readOnly}
              onChange={(e) => setIsGlobal(e.target.checked)}
            />
          </FormControl>
          {!isGlobal && (
            <FormControl isRequired>
              <FieldLabel>{INSTITUTIONS}</FieldLabel>
              {tenantsLoading ? (
                <HStack spacing={2} py={2}>
                  <Spinner size="sm" />
                  <Text fontSize="sm" color="gray.600">
                    Loading {INSTITUTIONS.toLowerCase()}…
                  </Text>
                </HStack>
              ) : tenantsError || tenants.length === 0 ? (
                <>
                  {tenantsError ? (
                    <Text fontSize="sm" color="red.500" mb={2}>
                      {tenantsError}
                    </Text>
                  ) : (
                    <Text fontSize="sm" color="gray.600" mb={2}>
                      No {INSTITUTIONS.toLowerCase()} found. Enter {INSTITUTION.toLowerCase()} IDs manually.
                    </Text>
                  )}
                  <Textarea
                    placeholder={`${INSTITUTION} IDs separated by comma or newline`}
                    value={tenantInput}
                    onChange={(e) => setTenantInput(e.target.value)}
                    isReadOnly={readOnly}
                    fontFamily="mono"
                    fontSize="sm"
                    rows={3}
                  />
                  <FieldHint>{FIELD_HINTS.policy.tenantIdsManual}</FieldHint>
                </>
              ) : (
                <>
                  <Box
                    borderWidth="1px"
                    borderRadius="md"
                    p={3}
                    {...optionListScroll}
                  >
                    <CheckboxGroup value={tenantIds} onChange={(v) => setTenantIds(v as string[])}>
                      <Stack spacing={2}>
                        {tenantIds
                          .filter((id) => !tenantById.has(id))
                          .map((id) => (
                            <Checkbox key={id} value={id} isDisabled={readOnly}>
                              Current assignment - {id}
                            </Checkbox>
                          ))}
                        {tenants.map((t) => (
                          <Checkbox key={t.tenant_id} value={t.tenant_id} isDisabled={readOnly}>
                            {t.organisation || "(Unnamed)"}{" "}
                            <Text as="span" color="gray.500" fontSize="sm">
                              ({t.tenant_id})
                            </Text>
                          </Checkbox>
                        ))}
                      </Stack>
                    </CheckboxGroup>
                  </Box>
                  <FieldHint>{FIELD_HINTS.policy.tenantIdsSelect}</FieldHint>
                </>
              )}
            </FormControl>
          )}
          <FormControl>
            <FieldLabel>Supported languages</FieldLabel>
            <CheckboxGroup value={langs} onChange={(v) => setLangs(v as string[])}>
              <HStack spacing={4}>
                {LANGUAGE_OPTIONS.map((code) => (
                  <Checkbox key={code} value={code} isDisabled={readOnly}>
                    {code}
                  </Checkbox>
                ))}
              </HStack>
            </CheckboxGroup>
          </FormControl>
          <FormControl isRequired>
            <FieldLabel>PII types (policy configuration)</FieldLabel>
            <Box
              borderWidth="1px"
              borderRadius="md"
              p={3}
              {...optionListScroll}
            >
              <CheckboxGroup
                value={selectedPii}
                onChange={(v) => setSelectedPii(v as string[])}
              >
                <Stack spacing={2}>
                  {piiOptions.map((p) => (
                    <Checkbox key={p.pii_type_id} value={p.pii_type_id} isDisabled={readOnly}>
                      {p.pii_type_label}{" "}
                      <Text as="span" color="gray.500" fontSize="sm">
                        ({p.mask_format})
                      </Text>
                    </Checkbox>
                  ))}
                </Stack>
              </CheckboxGroup>
              {!piiOptions.length && (
                <Text fontSize="sm" color="gray.500">
                  No PII types yet. Add some under &quot;PII type library&quot;.
                </Text>
              )}
            </Box>
            <Text fontSize="xs" color="gray.500" mt={1}>
              {selectedPii.length} selected
              {selectedPii.some((id) => !piiById.has(id)) ? " (includes types not in current list)" : ""}
            </Text>
          </FormControl>
        </Stack>
      );

  const footer = readOnly ? (
        <HStack justify="space-between" w="full">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          {policyId ? (
            <HStack spacing={3}>
              {loadedPolicy && onViewDelete ? (
                <Button
                  colorScheme="red"
                  variant="outline"
                  onClick={() => onViewDelete(loadedPolicy)}
                >
                  Delete
                </Button>
              ) : null}
              {onViewEdit ? (
                <Button onClick={() => onViewEdit(policyId)}>Edit</Button>
              ) : null}
            </HStack>
          ) : null}
        </HStack>
      ) : (
        <FormActions
          submitLabel={policyId ? "Save Changes" : "Create Policy"}
          onCancel={onClose}
          onSubmit={() => void handleSubmit()}
          isLoading={saving}
          loadingText={policyId ? "Saving..." : "Creating..."}
          justify="space-between"
          pt={0}
        />
  );

  if (!policyId) {
    return (
      <CreateModal
        isOpen={isOpen}
        onClose={onClose}
        title="Create Policy"
        description="Define a policy and choose which PII types it covers."
        size="lg"
        footer={footer}
      >
        {formBody}
      </CreateModal>
    );
  }

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={readOnly ? "Policy Details" : "Edit Policy"}
      description={
        readOnly
          ? "View this policy's scope and PII coverage."
          : "Update who this policy applies to and which PII types it covers."
      }
      size="xl"
      scrollBehavior="inside"
      modalProps={{ blockScrollOnMount: true }}
      headerProps={{ px: 6, pt: 5, pb: 4 }}
      bodyProps={{ px: 6, py: 5 }}
      footerProps={{ px: 6, py: 4 }}
      footer={footer}
    >
      {formBody}
    </StandardModal>
  );
}

function PiiTypeDetailModal({
  isOpen,
  onClose,
  piiTypeId,
  onEdit,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  piiTypeId: string | null;
  onEdit: (row: PiiTypeOut) => void;
  onError: (msg: string) => void;
}) {
  const [detail, setDetail] = useState<PiiTypeOut | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !piiTypeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const run = async () => {
      try {
        const res = await policyService.getPiiType(piiTypeId);
        if (!cancelled) setDetail(res.data);
      } catch (e: unknown) {
        if (!cancelled) onError(getPolicyApiErrorMessage(e, "Failed to load PII type"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, piiTypeId, onError]);

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="PII type details"
      size="lg"
      footer={
        detail ? (
          <FormActions
            cancelLabel="Close"
            submitLabel="Edit"
            onCancel={onClose}
            onSubmit={() => onEdit(detail)}
            justify="space-between"
            pt={0}
          />
        ) : (
          <FormActions
            cancelLabel="Close"
            onCancel={onClose}
            hideSubmit
            justify="flex-end"
            pt={0}
          />
        )
      }
    >
      {loading ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : detail ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {detail.pii_type_id}
          </Text>
          <Heading size="md">{detail.pii_type_label}</Heading>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Mask format
            </Text>
            <Badge>{detail.mask_format}</Badge>
          </Box>
          <FormControl>
            <FieldLabel formLabelProps={{ fontSize: "sm" }}>Regex pattern</FieldLabel>
            <Textarea value={detail.regex_pattern} readOnly fontFamily="mono" rows={4} />
          </FormControl>
          <Text fontSize="sm" color="gray.600">
            Created {formatDt(detail.created_at)}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
  );
}

function PiiTypesPanel() {
  const [allTypes, setAllTypes] = useState<PiiTypeOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMask, setFilterMask] = useState("");
  const piiTypeSortAccessors = useMemo(
    () => ({
      label: (row: PiiTypeOut) => row.pii_type_label ?? "",
      regex: (row: PiiTypeOut) => row.regex_pattern ?? "",
      created: (row: PiiTypeOut) =>
        row.created_at ? new Date(row.created_at).getTime() : 0,
    }),
    [],
  );
  const piiTypeSort = useDeferredColumnSort("label", piiTypeSortAccessors);
  const [tableEpoch, setTableEpoch] = useState(0);
  const modal = useDisclosure();
  const viewModal = useDisclosure();
  const [viewPiiId, setViewPiiId] = useState<string | null>(null);
  const confirmDel = useDisclosure();
  const [editing, setEditing] = useState<PiiTypeOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PiiTypeOut | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [label, setLabel] = useState("");
  const [regex, setRegex] = useState("");
  const [examples, setExamples] = useState("");
  const [mask, setMask] = useState<MaskFormat>("redact");
  const [saving, setSaving] = useState(false);
  const [piiDetailLoading, setPiiDetailLoading] = useState(false);

  const bumpTablePage = useCallback(() => setTableEpoch((n) => n + 1), []);

  const reloadPiiTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
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
      setAllTypes(acc);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load PII types"));
      setAllTypes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadPiiTypes();
  }, [reloadPiiTypes]);

  const getSortTimestamp = (value?: string | null): number => {
    if (value == null) return 0;
    const t = new Date(value).getTime();
    return Number.isNaN(t) ? 0 : t;
  };

  const filteredPiiTypes = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = allTypes.filter((row) => {
      if (q) {
        const inLabel = (row.pii_type_label ?? "").toLowerCase().includes(q);
        const inRegex = (row.regex_pattern ?? "").toLowerCase().includes(q);
        if (!inLabel && !inRegex) return false;
      }
      if (filterMask && row.mask_format !== filterMask) return false;
      return true;
    });
    const byCreatedDesc = [...filtered].sort(
      (a, b) => getSortTimestamp(b.created_at) - getSortTimestamp(a.created_at),
    );
    return piiTypeSort.apply(byCreatedDesc);
  }, [allTypes, searchQuery, filterMask, piiTypeSort]);

  const hasActiveFilters = filterMask !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterMask("");
  };

  const openCreate = () => {
    setEditing(null);
    setLabel("");
    setRegex("");
    setExamples("");
    setMask("redact");
    modal.onOpen();
  };

  const openPiiView = (row: PiiTypeOut) => {
    setViewPiiId(row.pii_type_id);
    viewModal.onOpen();
  };

  const closePiiView = () => {
    viewModal.onClose();
    setViewPiiId(null);
  };

  const openEdit = (row: PiiTypeOut) => {
    setEditing(row);
    setExamples("");
    modal.onOpen();
    setPiiDetailLoading(true);
    const run = async () => {
      try {
        const res = await policyService.getPiiType(row.pii_type_id);
        const p = res.data;
        setLabel(p.pii_type_label);
        setRegex(p.regex_pattern);
        setMask(p.mask_format as MaskFormat);
      } catch (e: unknown) {
        showToast({
          type: "error",
          message: getPolicyApiErrorMessage(e, "Could not load PII type (GET by id)"),
        });
        setLabel(row.pii_type_label);
        setRegex(row.regex_pattern);
        setMask(row.mask_format as MaskFormat);
      } finally {
        setPiiDetailLoading(false);
      }
    };
    void run();
  };

  const save = async () => {
    if (!label.trim() || !regex.trim()) {
      showToast({ type: "warning", message: "Label and regex are required" });
      return;
    }
    const example_values = parseDelimitedValues(examples);
    if ((!editing || example_values.length > 0) && example_values.length < 3) {
      showToast({
        type: "warning",
        message: "Provide at least three example values when using the example field",
      });
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await policyService.updatePiiType(editing.pii_type_id, {
          pii_type_label: label.trim(),
          regex_pattern: regex.trim(),
          example_values: example_values.length > 0 ? example_values : undefined,
          mask_format: mask,
        });
      } else {
        await policyService.createPiiType({
          pii_type_label: label.trim(),
          regex_pattern: regex.trim(),
          example_values,
          mask_format: mask,
        });
      }
      showToast({ type: "success", message: "Saved" });
      modal.onClose();
      void reloadPiiTypes();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Save failed"),
      });
    } finally {
      setSaving(false);
    }
  };

  const requestDelete = (row: PiiTypeOut) => {
    setDeleteTarget(row);
    confirmDel.onOpen();
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await policyService.deletePiiType(deleteTarget.pii_type_id);
      showToast({ type: "success", message: "Deleted" });
      confirmDel.onClose();
      setDeleteTarget(null);
      void reloadPiiTypes();
    } catch (e: unknown) {
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Delete failed (type may be in use)"),
      });
    } finally {
      setDeleting(false);
    }
  };

  const piiColumns = useMemo((): DataTableColumn<PiiTypeOut>[] => [
    {
      id: "label",
      header: "Label",
      sortable: true,
      sortAccessor: (row) => row.pii_type_label ?? "",
      cell: (row) => <Text fontWeight="medium" fontSize="sm">{row.pii_type_label}</Text>,
    },
    {
      id: "mask",
      header: "Mask",
      cell: (row) => <Badge>{row.mask_format}</Badge>,
    },
    {
      id: "regex",
      header: "Regex",
      tdProps: { maxW: "280px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
      sortable: true,
      sortAccessor: (row) => row.regex_pattern ?? "",
      cell: (row) => (
        <Box as="span" title={row.regex_pattern} display="block" isTruncated maxW="280px">
          {row.regex_pattern}
        </Box>
      ),
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
        <HStack spacing={1}>
          <Tooltip label="Edit PII type" hasArrow placement="top">
            <IconButton
              aria-label="Edit PII type"
              icon={<EditIcon />}
              size="sm"
              variant="ghost"
              colorScheme="blue"
              _hover={{ bg: "blue.50" }}
              onClick={() => openEdit(row)}
            />
          </Tooltip>
          <Tooltip label="Delete PII type" hasArrow placement="top">
            <IconButton
              aria-label="Delete PII type"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              _hover={{ bg: "red.50" }}
              onClick={() => requestDelete(row)}
            />
          </Tooltip>
        </HStack>
      ),
    },
  ], [openEdit, requestDelete]);

  const piiTypeForm = editing && piiDetailLoading ? (
          <Flex justify="center" py={8}>
            <Spinner />
          </Flex>
        ) : (
        <Stack spacing={4}>
          <FormControl isRequired>
            <FieldLabel>Label</FieldLabel>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </FormControl>
          <FormControl isRequired>
            <FieldLabel>Regex pattern</FieldLabel>
            <Textarea value={regex} onChange={(e) => setRegex(e.target.value)} fontFamily="mono" rows={3} />
          </FormControl>
          <FormControl isRequired={!editing}>
            <FieldLabel>
              {editing
                ? "Example values (comma or newline, optional validation)"
                : "Example values (comma or newline, min 3)"}
            </FieldLabel>
            <Textarea
              value={examples}
              onChange={(e) => setExamples(e.target.value)}
              placeholder="a@b.com, test@example.org, user@mail.co"
              rows={3}
            />
          </FormControl>
          <FormControl>
            <FieldLabel>Mask format</FieldLabel>
            <Select value={mask} onChange={(e) => setMask(e.target.value as MaskFormat)}>
              {MASK_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </FormControl>
        </Stack>
        );

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <DataTable<PiiTypeOut>
            layout="admin"
            key={tableEpoch}
            items={filteredPiiTypes}
            columns={piiColumns}
          sort={piiTypeSort.sort}
          onSortChange={(next) => { piiTypeSort.onSortChange(next); bumpTablePage(); }}
            getRowKey={(row) => row.pii_type_id}
            search={{
              label: "Search",
              value: searchQuery,
              onChange: setSearchQuery,
              placeholder: "Search by label or regex…",
              fields: ["label", "regex"],
            }}
            filterDefs={[
              {
                id: "mask",
                label: "Mask format",
                type: "select",
                param: "mask_format",
                value: filterMask,
                onChange: setFilterMask,
                width: { base: "full", sm: "160px" },
                options: [
                  { label: "All", value: "" },
                  ...MASK_OPTIONS.map((m) => ({ label: m, value: m })),
                ],
              },
            ]}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            filterToolbarRightContent={
              <CreateButton onClick={openCreate}>Create PII Type</CreateButton>
            }
            isLoading={loading}
            loadingMessage="Loading PII types…"
            emptyMessage='No PII types in the library yet. Click "Create PII type" to add one.'
            noResultsMessage="No PII types match the current filters."
            unfilteredCount={allTypes.length}
            onRowClick={openPiiView}
            paginate="client"
            paginationPosition="bottom"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            tableContainerProps={{ overflowX: "auto" }}
          />

      <PiiTypeDetailModal
        isOpen={viewModal.isOpen}
        onClose={closePiiView}
        piiTypeId={viewPiiId}
        onEdit={(row) => {
          closePiiView();
          openEdit(row);
        }}
        onError={(msg) =>
          showToast({ type: "error", message: msg })
        }
      />

      <CreateModal
        isOpen={modal.isOpen && !editing}
        onClose={modal.onClose}
        title="Create PII Type"
        description="Add a PII type to the library for use in policies."
        size="md"
        footer={
          <FormActions
            submitLabel="Create PII Type"
            onCancel={modal.onClose}
            onSubmit={() => void save()}
            isLoading={saving}
            loadingText="Creating..."
            justify="space-between"
            pt={0}
          />
        }
      >
        {piiTypeForm}
      </CreateModal>

      <StandardModal
        isOpen={modal.isOpen && Boolean(editing)}
        onClose={modal.onClose}
        title="Edit PII Type"
        description="Update how this PII type is detected and labelled."
        size="lg"
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={modal.onClose}
            onSubmit={() => void save()}
            isLoading={saving}
            isDisabled={piiDetailLoading}
            loadingText="Saving..."
          />
        }
      >
        {piiTypeForm}
      </StandardModal>

      <ConfirmDialog
        isOpen={confirmDel.isOpen}
        onClose={confirmDel.onClose}
        title="Delete PII type"
        body={
          deleteTarget ? (
            <Text>
              Remove <strong>{deleteTarget.pii_type_label}</strong>? Policies referencing it may fail to
              update.
            </Text>
          ) : null
        }
        onConfirm={() => void confirmDelete()}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={deleting}
      />
    </Box>
  );
}

function AuditPanel() {
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
            width: { base: "full", sm: "140px" },
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
