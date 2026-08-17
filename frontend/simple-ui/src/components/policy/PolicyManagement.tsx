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
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Textarea,
  Tooltip,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import { showToast } from "../../utils/toast";
import {
  AddIcon,
  DeleteIcon,
  EditIcon,
  ViewIcon,
} from "@chakra-ui/icons";
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
import { INSTITUTION, INSTITUTION_ARTICLE, INSTITUTIONS, isTenantStatus, TENANT } from "../../config/constants";
import { listTenants } from "../../services/tenantService";
import type { TenantView } from "../../types/tenant";

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
}

export default function PolicyManagement({ canManage }: PolicyManagementProps) {
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
    <VStack align="stretch" spacing={6}>
      <Box>
        <Tabs
          variant="unstyled"
          index={policySubTabIndex}
          onChange={(idx) => {
            const next = POLICY_TAB_CONFIG[idx];
            if (next) setTab(next.id);
          }}
          mb={6}
        >
          <TabList borderBottom="2px solid" borderColor="gray.200" aria-label="Policy Management sections">
            {POLICY_TAB_CONFIG.map(({ id, label }, idx) => (
              <Tab
                key={id}
                fontWeight="semibold"
                fontSize="md"
                color={policySubTabIndex === idx ? "gray.800" : "gray.500"}
                pb={3}
                px={5}
                position="relative"
                _after={{
                  content: '""',
                  position: "absolute",
                  bottom: "-2px",
                  left: 0,
                  right: 0,
                  height: "3px",
                  borderRadius: "3px 3px 0 0",
                  bg: policySubTabIndex === idx ? "orange.500" : "transparent",
                  transition: "background 0.2s",
                }}
                _hover={{ color: "gray.700" }}
                _focus={{ boxShadow: "none" }}
                transition="color 0.2s"
              >
                {label}
              </Tab>
            ))}
          </TabList>
          <TabPanels>
            <TabPanel px={0} pt={6}>
              <PiiTypesPanel />
            </TabPanel>
            <TabPanel px={0} pt={6}>
              <PoliciesPanel />
            </TabPanel>
            {SHOW_POLICY_AUDIT_TAB ? (
              <TabPanel px={0} pt={6}>
                <AuditPanel />
              </TabPanel>
            ) : null}
          </TabPanels>
        </Tabs>
      </Box>
    </VStack>
  );
}

function PoliciesPanel() {
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
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Failed to load PII types for the policy form"),
      });
    }
  }, []);

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
      cell: (row) => (row.is_global ? "Global" : `${INSTITUTION}-scoped`),
    },
    {
      id: "tenants",
      header: INSTITUTIONS,
      tdProps: { maxW: "180px", isTruncated: true },
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

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <Card
        bg={cardBg}
        borderWidth="1px"
        borderColor={borderColor}
        borderRadius="lg"
        boxShadow="none"
      >
        <CardBody>
          <AdminDataTable<PolicyOut>
            key={tableEpoch}
            items={filteredPolicies}
            columns={policyColumns}
            getRowKey={(row) => row.policy_id}
            filters={
              <VStack align="stretch" spacing={3} flex="1" w="full">
                <HStack spacing={3} align="flex-end" flexWrap="wrap" rowGap={3} w="full">
                  <TableSearchField
                    label="Search"
                    value={searchQuery}
                    onChange={setSearchQuery}
                    placeholder="Search by policy name…"
                    formControlProps={{ w: { base: "full", md: "280px" } }}
                    inputProps={{ pl: 10 }}
                  />
                  <TableSelectField
                    label="Active"
                    value={filterActive}
                    onChange={setFilterActive}
                    formControlProps={{ w: { base: "full", sm: "140px" } }}
                  >
                    <option value="">All</option>
                    <option value="true">Active</option>
                    <option value="false">Inactive</option>
                  </TableSelectField>
                  <TableSelectField
                    label="Scope"
                    value={filterGlobal}
                    onChange={setFilterGlobal}
                    formControlProps={{ w: { base: "full", sm: "160px" } }}
                  >
                    <option value="">All</option>
                    <option value="true">Global</option>
                    <option value="false">{INSTITUTION}-scoped</option>
                  </TableSelectField>
                  <Box flex="1" minW={0} />
                </HStack>
                {hasActiveFilters ? (
                  <HStack spacing={2} flexWrap="wrap">
                    {searchQuery.trim() ? (
                      <Badge
                        colorScheme="blue"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setSearchQuery("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Search: &quot;{searchQuery.trim()}&quot; ×
                      </Badge>
                    ) : null}
                    {filterActive ? (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setFilterActive("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Active: {filterActive === "true" ? "Active" : "Inactive"} ×
                      </Badge>
                    ) : null}
                    {filterGlobal ? (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setFilterGlobal("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Scope: {filterGlobal === "true" ? "Global" : `${INSTITUTION}-scoped`} ×
                      </Badge>
                    ) : null}
                  </HStack>
                ) : null}
              </VStack>
            }
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            filterToolbarAlign="flex-end"
            filterToolbarRightContent={
              <Button size="sm" colorScheme="orange" leftIcon={<AddIcon />} onClick={openCreate}>
                Create policy
              </Button>
            }
            isLoading={loading}
            loadingMessage="Loading policies…"
            emptyMessage='No policies yet. Click "Create policy" to add one.'
            noResultsMessage="No policies match the current filters."
            unfilteredCount={allPolicies.length}
            onRowClick={(row) => openPolicyView(row.policy_id)}
            paginate="client"
            tableContainerProps={{ overflowX: "auto" }}
          />
        </CardBody>
      </Card>

      <PolicyDetailModal
        isOpen={viewModal.isOpen}
        onClose={closePolicyView}
        policyId={viewPolicyId}
        onEdit={(id) => {
          closePolicyView();
          openEdit(id);
        }}
        onDelete={(policy) => {
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

function PolicyDetailModal({
  isOpen,
  onClose,
  policyId,
  onEdit,
  onDelete,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  onEdit: (id: string) => void;
  onDelete: (policy: PolicyOut) => void;
  onError: (msg: string) => void;
}) {
  const [policy, setPolicy] = useState<PolicyOut | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !policyId) {
      setPolicy(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const run = async () => {
      try {
        const res = await policyService.getPolicy(policyId);
        if (!cancelled) setPolicy(res.data);
      } catch (e: unknown) {
        if (!cancelled) onError(getPolicyApiErrorMessage(e, "Failed to load policy"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, policyId, onError]);

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Policy details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {policyId ? (
            <>
              {policy ? (
                <Button colorScheme="red" variant="outline" onClick={() => onDelete(policy)}>
                  Delete
                </Button>
              ) : null}
              <Button
                colorScheme="blue"
                onClick={() => {
                  onEdit(policyId);
                }}
              >
                Edit
              </Button>
            </>
          ) : null}
        </HStack>
      }
    >
      {loading ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : policy ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {policy.policy_id}
          </Text>
          <Heading size="md">{policy.name}</Heading>
          {policy.description ? (
            <Text fontSize="sm" color="gray.700">
              {policy.description}
            </Text>
          ) : (
            <Text fontSize="sm" color="gray.500">
              No description
            </Text>
          )}
          <HStack spacing={2} flexWrap="wrap">
            <Badge colorScheme={policy.is_active ? "green" : "gray"}>
              {policy.is_active ? "Active" : "Inactive"}
            </Badge>
            <Badge colorScheme={policy.is_global ? "blue" : "purple"}>
              {policy.is_global ? "Global" : `${INSTITUTION}-scoped`}
            </Badge>
          </HStack>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              {INSTITUTIONS}
            </Text>
            <Text fontSize="sm">
              {policy.is_global
                ? `All ${INSTITUTIONS.toLowerCase()}`
                : (policy.tenant_ids?.length ?? 0) > 0
                  ? policy.tenant_ids!.join(", ")
                  : "—"}
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              PII types ({policy.pii_types?.length ?? 0})
            </Text>
            <Stack spacing={1}>
              {(policy.pii_types ?? []).map((p) => (
                <Text key={p.pii_type_id} fontSize="sm">
                  {p.pii_type_label}{" "}
                  <Text as="span" color="gray.500">
                    ({p.mask_format})
                  </Text>
                </Text>
              ))}
              {!policy.pii_types?.length && (
                <Text fontSize="sm" color="gray.500">
                  None linked
                </Text>
              )}
            </Stack>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Languages
            </Text>
            <Text fontSize="sm">{policy.supported_languages?.join(", ") || "—"}</Text>
          </Box>
          <Text fontSize="sm" color="gray.600">
            Created {formatDt(policy.created_at)}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
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
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  piiOptions: PiiTypeOut[];
  refreshPiiOptions: () => Promise<void> | void;
  onSaved: () => void;
  onError: (msg: string) => void;
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
  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(false);
  const [tenantsError, setTenantsError] = useState<string | null>(null);

  const didFetchPiiOptionsForThisOpen = useRef(false);
  useEffect(() => {
    if (!isOpen) {
      didFetchPiiOptionsForThisOpen.current = false;
      return;
    }

    // Only fetch PII options once when the modal is opened, to avoid background load.
    if (didFetchPiiOptionsForThisOpen.current) return;
    didFetchPiiOptionsForThisOpen.current = true;
    void refreshPiiOptions();
  }, [isOpen, refreshPiiOptions]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setTenantsLoading(true);
    setTenantsError(null);
    void listTenants()
      .then((res) => {
        if (cancelled) return;
        const list = (res.tenants ?? []).filter((tenant) =>
          isTenantStatus(tenant.status, TENANT.STATUS.ACTIVE)
        );
        setTenants(
          [...list].sort((a, b) =>
            (a.organisation ?? "").localeCompare(b.organisation ?? "", undefined, {
              sensitivity: "base",
            })
          )
        );
      })
      .catch(() => {
        if (!cancelled) setTenantsError(`Could not load ${INSTITUTIONS.toLowerCase()}. You can enter ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()} ID below.`);
      })
      .finally(() => {
        if (!cancelled) setTenantsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

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

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={policyId ? "Edit policy definition" : "New policy definition"}
      size="xl"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button colorScheme="blue" onClick={() => void handleSubmit()} isLoading={saving}>
            Save
          </Button>
        </HStack>
      }
    >
      {loadingDetail ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : (
        <Stack spacing={4}>
          <FormControl isRequired>
            <FormLabel>Name</FormLabel>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </FormControl>
          <FormControl>
            <FormLabel>Description</FormLabel>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </FormControl>
          <FormControl display="flex" alignItems="center">
            <FormLabel mb={0}>Global policy</FormLabel>
            <Switch isChecked={isGlobal} onChange={(e) => setIsGlobal(e.target.checked)} />
          </FormControl>
          {!isGlobal && (
            <FormControl isRequired>
              <FormLabel>{INSTITUTIONS}</FormLabel>
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
                    fontFamily="mono"
                    fontSize="sm"
                    rows={3}
                  />
                  <FormHelperText>Enter one or more {INSTITUTION.toLowerCase()} IDs.</FormHelperText>
                </>
              ) : (
                <>
                  <Box maxH="220px" overflowY="auto" borderWidth="1px" borderRadius="md" p={3}>
                    <CheckboxGroup value={tenantIds} onChange={(v) => setTenantIds(v as string[])}>
                      <Stack spacing={2}>
                        {tenantIds
                          .filter((id) => !tenantById.has(id))
                          .map((id) => (
                            <Checkbox key={id} value={id}>
                              Current assignment - {id}
                            </Checkbox>
                          ))}
                        {tenants.map((t) => (
                          <Checkbox key={t.tenant_id} value={t.tenant_id}>
                            {t.organisation || "(Unnamed)"}{" "}
                            <Text as="span" color="gray.500" fontSize="sm">
                              ({t.tenant_id})
                            </Text>
                          </Checkbox>
                        ))}
                      </Stack>
                    </CheckboxGroup>
                  </Box>
                  <FormHelperText>
                    Select one or more active {INSTITUTION.toLowerCase()} assignments for this policy.
                  </FormHelperText>
                </>
              )}
            </FormControl>
          )}
          <FormControl>
            <FormLabel>Supported languages</FormLabel>
            <CheckboxGroup value={langs} onChange={(v) => setLangs(v as string[])}>
              <HStack spacing={4}>
                {LANGUAGE_OPTIONS.map((code) => (
                  <Checkbox key={code} value={code}>
                    {code}
                  </Checkbox>
                ))}
              </HStack>
            </CheckboxGroup>
          </FormControl>
          <FormControl isRequired>
            <FormLabel>PII types (policy configuration)</FormLabel>
            <Box maxH="220px" overflowY="auto" borderWidth="1px" borderRadius="md" p={3}>
              <CheckboxGroup
                value={selectedPii}
                onChange={(v) => setSelectedPii(v as string[])}
              >
                <Stack spacing={2}>
                  {piiOptions.map((p) => (
                    <Checkbox key={p.pii_type_id} value={p.pii_type_id}>
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
      )}
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
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {detail ? (
            <Button
              colorScheme="blue"
              onClick={() => {
                onEdit(detail);
              }}
            >
              Edit
            </Button>
          ) : null}
        </HStack>
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
            <FormLabel fontSize="sm">Regex pattern</FormLabel>
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
  const [sortBy, setSortBy] = useState<"time" | "label">("time");
  const [labelSortDirection, setLabelSortDirection] = useState<"asc" | "desc">("asc");
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

  const { cardBg, borderColor } = useAdminTableSurface();
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
    return [...filtered].sort((a, b) => {
      const createdA = getSortTimestamp(a.created_at);
      const createdB = getSortTimestamp(b.created_at);
      const labelCmp = (a.pii_type_label ?? "").localeCompare(b.pii_type_label ?? "", undefined, {
        sensitivity: "base",
      });
      if (sortBy === "time") {
        if (createdB !== createdA) return createdB - createdA;
        return 0;
      }
      if (labelCmp !== 0) return labelSortDirection === "asc" ? labelCmp : -labelCmp;
      if (createdB !== createdA) return createdB - createdA;
      return 0;
    });
  }, [allTypes, searchQuery, filterMask, sortBy, labelSortDirection]);

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

  const piiColumns = useMemo((): AdminTableColumn<PiiTypeOut>[] => [
    {
      id: "label",
      header: "Label",
      sortable: {
        label: "Label",
        direction: labelSortDirection,
        onAsc: () => {
          setSortBy("label");
          setLabelSortDirection("asc");
          bumpTablePage();
        },
        onDesc: () => {
          setSortBy("label");
          setLabelSortDirection("desc");
          bumpTablePage();
        },
        ascAriaLabel: "Sort PII types by label ascending",
        descAriaLabel: "Sort PII types by label descending",
      },
      cell: (row) => <Text fontWeight="medium">{row.pii_type_label}</Text>,
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
      cell: (row) => formatDt(row.created_at),
    },
    {
      id: "actions",
      header: "Actions",
      thProps: { textAlign: "right" },
      tdProps: { textAlign: "right", onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <HStack justify="flex-end" spacing={1}>
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
  ], [labelSortDirection, bumpTablePage, openEdit, requestDelete]);

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <Card
        bg={cardBg}
        borderWidth="1px"
        borderColor={borderColor}
        borderRadius="lg"
        boxShadow="none"
      >
        <CardBody>
          <AdminDataTable<PiiTypeOut>
            key={tableEpoch}
            items={filteredPiiTypes}
            columns={piiColumns}
            getRowKey={(row) => row.pii_type_id}
            filters={
              <VStack align="stretch" spacing={3} flex="1" w="full">
                <HStack spacing={3} align="flex-end" flexWrap="wrap" rowGap={3} w="full">
                  <TableSearchField
                    label="Search"
                    value={searchQuery}
                    onChange={setSearchQuery}
                    placeholder="Search by label or regex…"
                    formControlProps={{ w: { base: "full", md: "280px" } }}
                    inputProps={{ pl: 10 }}
                  />
                  <TableSelectField
                    label="Mask format"
                    value={filterMask}
                    onChange={setFilterMask}
                    formControlProps={{ w: { base: "full", sm: "160px" } }}
                  >
                    <option value="">All</option>
                    {MASK_OPTIONS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </TableSelectField>
                  <Box flex="1" minW={0} />
                </HStack>
                {hasActiveFilters ? (
                  <HStack spacing={2} flexWrap="wrap">
                    {searchQuery.trim() ? (
                      <Badge
                        colorScheme="blue"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setSearchQuery("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Search: &quot;{searchQuery.trim()}&quot; ×
                      </Badge>
                    ) : null}
                    {filterMask ? (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setFilterMask("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Mask: {filterMask} ×
                      </Badge>
                    ) : null}
                  </HStack>
                ) : null}
              </VStack>
            }
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            filterToolbarAlign="flex-end"
            filterToolbarRightContent={
              <Button size="sm" colorScheme="orange" leftIcon={<AddIcon />} onClick={openCreate}>
                Create PII type
              </Button>
            }
            isLoading={loading}
            loadingMessage="Loading PII types…"
            emptyMessage='No PII types in the library yet. Click "Create PII type" to add one.'
            noResultsMessage="No PII types match the current filters."
            unfilteredCount={allTypes.length}
            onRowClick={openPiiView}
            paginate="client"
            tableContainerProps={{ overflowX: "auto" }}
          />
        </CardBody>
      </Card>

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

      <StandardModal
        isOpen={modal.isOpen}
        onClose={modal.onClose}
        title={editing ? "PII type configuration" : "New PII type (library)"}
        size="lg"
        footer={
          <HStack justify="flex-end" w="full">
            <Button variant="ghost" onClick={modal.onClose}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={() => void save()}
              isLoading={saving}
              isDisabled={Boolean(editing) && piiDetailLoading}
            >
              Save
            </Button>
          </HStack>
        }
      >
        {editing && piiDetailLoading ? (
          <Flex justify="center" py={8}>
            <Spinner />
          </Flex>
        ) : (
        <Stack spacing={4}>
          <FormControl isRequired>
            <FormLabel>Label</FormLabel>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </FormControl>
          <FormControl isRequired>
            <FormLabel>Regex pattern</FormLabel>
            <Textarea value={regex} onChange={(e) => setRegex(e.target.value)} fontFamily="mono" rows={3} />
          </FormControl>
          <FormControl isRequired={!editing}>
            <FormLabel>
              {editing
                ? "Example values (comma or newline, optional validation)"
                : "Example values (comma or newline, min 3)"}
            </FormLabel>
            <Textarea
              value={examples}
              onChange={(e) => setExamples(e.target.value)}
              placeholder="a@b.com, test@example.org, user@mail.co"
              rows={3}
            />
          </FormControl>
          <FormControl>
            <FormLabel>Mask format</FormLabel>
            <Select value={mask} onChange={(e) => setMask(e.target.value as MaskFormat)}>
              {MASK_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </FormControl>
        </Stack>
        )}
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
      showToast({
        type: "error",
        message: getPolicyApiErrorMessage(e, "Could not load log detail"),
      });
    }
  };

  const formatAuditChipId = (id: string, maxLen = 14) =>
    id.length > maxLen ? `${id.slice(0, 8)}…` : id;

  const auditColumns = useMemo((): AdminTableColumn<AuditLogOut>[] => [
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
                  {INSTITUTION} ID
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
                    {INSTITUTION}: {debouncedFilters.tenant} ×
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
