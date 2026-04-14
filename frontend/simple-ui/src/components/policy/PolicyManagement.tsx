import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  CheckboxGroup,
  Flex,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  IconButton,
  Input,
  InputGroup,
  InputLeftElement,
  Select,
  Spinner,
  Stack,
  Switch,
  Table,
  Tbody,
  Td,
  Text,
  Textarea,
  Th,
  Thead,
  Tooltip,
  Tr,
  useDisclosure,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { CheckIcon, CloseIcon, DeleteIcon, EditIcon, SearchIcon, ViewIcon } from "@chakra-ui/icons";
import StandardModal from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import {
  TableFilterToolbar,
  TablePaginationBar,
  TableSortHeader,
  useAdminTableSurface,
} from "../common/TableControls";
import {
  policyService,
  type AuditLogOut,
  type MaskFormat,
  type PiiTypeOut,
  type PolicyOut,
} from "../../services/policyService";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

/** Set to `true` to show the Audit log tab again. */
const SHOW_POLICY_AUDIT_TAB = false;

const POLICY_SECTION_TABS = SHOW_POLICY_AUDIT_TAB
  ? ([
      ["policies", "Policy definitions"],
      ["pii", "PII type library"],
      ["audit", "Audit log"],
    ] as const)
  : ([
      ["policies", "Policy definitions"],
      ["pii", "PII type library"],
    ] as const);

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
  const msg = (e as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error
    ?.message;
  return typeof msg === "string" && msg.trim() ? msg : fallback;
}

function formatDt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export interface PolicyManagementProps {
  /** Platform admin (ADMIN role or superuser); required to call policy APIs. */
  canManage: boolean;
}

function PolicyServiceHealthBadge() {
  const [status, setStatus] = useState<"ok" | "error" | "loading">("loading");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const res = await policyService.health();
        if (cancelled) return;
        if (res.data?.status === "ok") {
          setStatus("ok");
          setDetail("Policy service reachable");
        } else {
          setStatus("error");
          setDetail("Unexpected health response");
        }
      } catch {
        if (!cancelled) {
          setStatus("error");
          setDetail("Health check failed (is the gateway routing /api/v1/policy-service?)");
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <HStack spacing={2} flexWrap="wrap">
      <Text fontSize="sm" color="gray.600">
        Policy service
      </Text>
      {status === "loading" && <Spinner size="sm" />}
      {status === "ok" && (
        <Badge colorScheme="green" variant="subtle">
          {detail}
        </Badge>
      )}
      {status === "error" && (
        <Badge colorScheme="red" variant="subtle">
          {detail}
        </Badge>
      )}
    </HStack>
  );
}

export default function PolicyManagement({ canManage }: PolicyManagementProps) {
  const toast = useToast();
  const [tab, setTab] = useState<"policies" | "pii" | "audit">("policies");

  useEffect(() => {
    if (!SHOW_POLICY_AUDIT_TAB && tab === "audit") {
      setTab("policies");
    }
  }, [tab]);

  if (!canManage) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        Policy management requires adopter admin access (ADMIN role). Tenant users cannot
        change policies here.
      </Alert>
    );
  }

  return (
    <VStack align="stretch" spacing={6}>
      <PolicyServiceHealthBadge />

      <Box>
        <Text fontSize="sm" color="gray.600" mb={2}>
          {SHOW_POLICY_AUDIT_TAB
            ? "Policy definitions, PII type library, and audit trail (policy-service APIs)."
            : "Policy definitions and PII type library (policy-service APIs)."}
        </Text>
        <HStack spacing={2} flexWrap="wrap" role="tablist" aria-label="Policy management sections">
          {POLICY_SECTION_TABS.map(([id, label]) => (
            <Button
              key={id}
              size="sm"
              variant={tab === id ? "solid" : "outline"}
              colorScheme={tab === id ? "blue" : "gray"}
              onClick={() => setTab(id)}
              role="tab"
              aria-selected={tab === id}
            >
              {label}
            </Button>
          ))}
        </HStack>
      </Box>

      {tab === "policies" && <PoliciesPanel toast={toast} />}
      {tab === "pii" && <PiiTypesPanel toast={toast} />}
      {SHOW_POLICY_AUDIT_TAB && tab === "audit" && <AuditPanel toast={toast} />}
    </VStack>
  );
}

function PoliciesPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const [allPolicies, setAllPolicies] = useState<PolicyOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [filterGlobal, setFilterGlobal] = useState("");
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(25);
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
  const modal = useDisclosure();
  const viewModal = useDisclosure();
  const [viewPolicyId, setViewPolicyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [piiOptions, setPiiOptions] = useState<PiiTypeOut[]>([]);

  const { tableBg, tableHeaderBg, tableRowHoverBg, cardBg } = useAdminTableSurface();

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

  const totalPolicies = filteredPolicies.length;
  const totalPages = Math.max(1, Math.ceil(totalPolicies / listPageSize) || 1);
  const startRow = totalPolicies === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const endRow = Math.min(listPage * listPageSize, totalPolicies);
  const paginatedPolicies = filteredPolicies.slice((listPage - 1) * listPageSize, listPage * listPageSize);

  useEffect(() => {
    if (listPage > totalPages && totalPages >= 1) setListPage(totalPages);
  }, [totalPolicies, listPageSize, listPage, totalPages]);

  const hasActiveFilters =
    filterActive !== "" || filterGlobal !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterActive("");
    setFilterGlobal("");
    setListPage(1);
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

  const handleToggleActive = async (row: PolicyOut) => {
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
    }
  };

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <VStack align="stretch" spacing={4} mb={4}>
        <TableFilterToolbar
          hasActiveFilters={hasActiveFilters}
          onClear={clearAllFilters}
          align="flex-end"
          rightContent={
            <Button size="sm" colorScheme="blue" onClick={openCreate}>
              New policy
            </Button>
          }
        >
          <FormControl w={{ base: "full", md: "280px" }}>
            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
              Search
            </FormLabel>
            <InputGroup>
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search by policy name…"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setListPage(1);
                }}
                bg={cardBg}
                pl={10}
                size="sm"
              />
            </InputGroup>
          </FormControl>
          <FormControl w={{ base: "full", sm: "140px" }}>
            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
              Active
            </FormLabel>
            <Select
              size="sm"
              value={filterActive}
              onChange={(e) => {
                setFilterActive(e.target.value);
                setListPage(1);
              }}
              bg={cardBg}
            >
              <option value="">All</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </Select>
          </FormControl>
          <FormControl w={{ base: "full", sm: "160px" }}>
            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
              Scope
            </FormLabel>
            <Select
              size="sm"
              value={filterGlobal}
              onChange={(e) => {
                setFilterGlobal(e.target.value);
                setListPage(1);
              }}
              bg={cardBg}
            >
              <option value="">All</option>
              <option value="true">Global</option>
              <option value="false">Tenant-scoped</option>
            </Select>
          </FormControl>
        </TableFilterToolbar>
        {hasActiveFilters && (
          <HStack spacing={2} flexWrap="wrap">
            {searchQuery.trim() && (
              <Badge
                colorScheme="blue"
                fontSize="xs"
                px={2}
                py={1}
                cursor="pointer"
                onClick={() => {
                  setSearchQuery("");
                  setListPage(1);
                }}
                _hover={{ opacity: 0.8 }}
              >
                Search: &quot;{searchQuery.trim()}&quot; ×
              </Badge>
            )}
            {filterActive && (
              <Badge
                colorScheme="gray"
                fontSize="xs"
                px={2}
                py={1}
                cursor="pointer"
                onClick={() => {
                  setFilterActive("");
                  setListPage(1);
                }}
                _hover={{ opacity: 0.8 }}
              >
                Active: {filterActive === "true" ? "Active" : "Inactive"} ×
              </Badge>
            )}
            {filterGlobal && (
              <Badge
                colorScheme="gray"
                fontSize="xs"
                px={2}
                py={1}
                cursor="pointer"
                onClick={() => {
                  setFilterGlobal("");
                  setListPage(1);
                }}
                _hover={{ opacity: 0.8 }}
              >
                Scope: {filterGlobal === "true" ? "Global" : "Tenant-scoped"} ×
              </Badge>
            )}
          </HStack>
        )}
      </VStack>

      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner />
        </Flex>
      ) : filteredPolicies.length === 0 ? (
        <Box textAlign="center" py={8}>
          <Text color="gray.500">
            No results found.
            {allPolicies.length === 0
              ? " No policies yet."
              : " Try adjusting your search or filters."}
          </Text>
        </Box>
      ) : (
        <Box maxH="60vh" overflowY="auto" overflowX="auto">
          <Table variant="simple" bg={tableBg} size="sm" w="100%">
            <Thead bg={tableHeaderBg}>
              <Tr>
                <Th>
                  <TableSortHeader
                    label="Name"
                    direction={nameSortDirection}
                    onAsc={() => {
                      setSortBy("name");
                      setNameSortDirection("asc");
                      setListPage(1);
                    }}
                    onDesc={() => {
                      setSortBy("name");
                      setNameSortDirection("desc");
                      setListPage(1);
                    }}
                    ascAriaLabel="Sort policies by name ascending"
                    descAriaLabel="Sort policies by name descending"
                  />
                </Th>
                <Th>Status</Th>
                <Th>Scope</Th>
                <Th>Tenants</Th>
                <Th>Languages</Th>
                <Th>PII types</Th>
                <Th>Created</Th>
                <Th textAlign="right">Actions</Th>
              </Tr>
            </Thead>
            <Tbody>
              {paginatedPolicies.map((row) => (
                <Tr
                  key={row.policy_id}
                  cursor="pointer"
                  _hover={{ bg: tableRowHoverBg }}
                  onClick={() => openPolicyView(row.policy_id)}
                >
                  <Td fontWeight="medium">{row.name}</Td>
                  <Td>
                    <Badge colorScheme={row.is_active ? "green" : "gray"}>
                      {row.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </Td>
                  <Td>{row.is_global ? "Global" : "Tenant-scoped"}</Td>
                  <Td maxW="180px" isTruncated title={(row.tenant_ids ?? []).join(", ")}>
                    {row.is_global
                      ? "All tenants"
                      : (row.tenant_ids?.length ?? 0) > 0
                        ? row.tenant_ids!.join(", ")
                        : "—"}
                  </Td>
                  <Td>{row.supported_languages?.join(", ") || "—"}</Td>
                  <Td>{row.pii_types?.length ?? 0}</Td>
                  <Td whiteSpace="nowrap">{formatDt(row.created_at)}</Td>
                  <Td textAlign="right" onClick={(e) => e.stopPropagation()}>
                    <HStack justify="flex-end" spacing={1}>
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
                      <Tooltip
                        label={row.is_active ? "Deactivate" : "Activate"}
                        hasArrow
                        placement="top"
                      >
                        <IconButton
                          aria-label={row.is_active ? "Deactivate policy" : "Activate policy"}
                          icon={row.is_active ? <CloseIcon /> : <CheckIcon />}
                          size="sm"
                          variant="ghost"
                          colorScheme={row.is_active ? "orange" : "green"}
                          _hover={{ bg: row.is_active ? "orange.50" : "green.50" }}
                          onClick={() => void handleToggleActive(row)}
                        />
                      </Tooltip>
                    </HStack>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <TablePaginationBar
        startRow={startRow}
        endRow={endRow}
        totalItems={totalPolicies}
        page={listPage}
        totalPages={totalPages}
        pageSize={listPageSize}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        onPageSizeChange={(s) => {
          setListPageSize(s);
          setListPage(1);
        }}
        onFirst={() => setListPage(1)}
        onPrev={() => setListPage((p) => Math.max(1, p - 1))}
        onNext={() => setListPage((p) => Math.min(totalPages, p + 1))}
        onLast={() => setListPage(totalPages)}
        canPrev={listPage > 1}
        canNext={listPage < totalPages}
        bg={cardBg}
      />

      <PolicyDetailModal
        isOpen={viewModal.isOpen}
        onClose={closePolicyView}
        policyId={viewPolicyId}
        onEdit={(id) => {
          closePolicyView();
          openEdit(id);
        }}
        onError={(msg) =>
          toast({ title: msg, status: "error", duration: 5000, isClosable: true })
        }
      />

      <PolicyFormModal
        isOpen={modal.isOpen}
        onClose={modal.onClose}
        policyId={editingId}
        piiOptions={piiOptions}
        onSaved={() => {
          modal.onClose();
          void reloadPolicies();
          void loadPiiOptions();
          toast({ title: "Saved", status: "success", duration: 2000 });
        }}
        onError={(msg) =>
          toast({ title: msg, status: "error", duration: 5000, isClosable: true })
        }
      />
    </Box>
  );
}

function PolicyDetailModal({
  isOpen,
  onClose,
  policyId,
  onEdit,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  onEdit: (id: string) => void;
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
            <Button
              colorScheme="blue"
              onClick={() => {
                onEdit(policyId);
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
              {policy.is_global ? "Global" : "Tenant-scoped"}
            </Badge>
          </HStack>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Tenants
            </Text>
            <Text fontSize="sm">
              {policy.is_global
                ? "All tenants"
                : (policy.tenant_ids?.length ?? 0) > 0
                  ? policy.tenant_ids!.join(", ")
                  : "—"}
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Languages
            </Text>
            <Text fontSize="sm">{policy.supported_languages?.join(", ") || "—"}</Text>
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
  onSaved,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  piiOptions: PiiTypeOut[];
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isGlobal, setIsGlobal] = useState(true);
  const [tenantId, setTenantId] = useState("");
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [selectedPii, setSelectedPii] = useState<string[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (!policyId) {
      setName("");
      setDescription("");
      setIsGlobal(true);
      setTenantId("");
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
        setTenantId(tids[0] ?? "");
        setLangs(p.supported_languages?.length ? p.supported_languages : ["en"]);
        setSelectedPii((p.pii_types || []).map((x) => x.pii_type_id));
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
    if (!name.trim()) {
      onError("Name is required");
      return;
    }
    if (!langs.length) {
      onError("Select at least one language");
      return;
    }
    if (!policyId && !isGlobal && !tenantId.trim()) {
      onError("Tenant ID is required for non-global policies");
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
          pii_types,
        };
        if (!isGlobal && tenantId.trim()) {
          body.tenant_id = tenantId.trim();
        }
        await policyService.updatePolicy(policyId, body);
      } else {
        await policyService.createPolicy({
          name: name.trim(),
          description: description.trim() || undefined,
          is_global: isGlobal,
          supported_languages: langs,
          tenant_id: isGlobal ? undefined : tenantId.trim(),
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
            <FormControl isRequired={!policyId}>
              <FormLabel>Tenant ID</FormLabel>
              <Input
                placeholder={
                  policyId
                    ? "Optional: assign or re-map tenant on save"
                    : "Required for non-global create"
                }
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
              />
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
          <FormControl>
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

function PiiTypesPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const [allTypes, setAllTypes] = useState<PiiTypeOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMask, setFilterMask] = useState("");
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(25);
  const [sortBy, setSortBy] = useState<"time" | "label">("time");
  const [labelSortDirection, setLabelSortDirection] = useState<"asc" | "desc">("asc");
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

  const { tableBg, tableHeaderBg, tableRowHoverBg, cardBg } = useAdminTableSurface();

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

  const totalTypes = filteredPiiTypes.length;
  const totalPages = Math.max(1, Math.ceil(totalTypes / listPageSize) || 1);
  const startRow = totalTypes === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const endRow = Math.min(listPage * listPageSize, totalTypes);
  const paginatedPiiTypes = filteredPiiTypes.slice(
    (listPage - 1) * listPageSize,
    listPage * listPageSize
  );

  useEffect(() => {
    if (listPage > totalPages && totalPages >= 1) setListPage(totalPages);
  }, [totalTypes, listPageSize, listPage, totalPages]);

  const hasActiveFilters = filterMask !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterMask("");
    setListPage(1);
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
        toast({
          title: getPolicyApiErrorMessage(e, "Could not load PII type (GET by id)"),
          status: "error",
          duration: 4000,
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
      toast({ title: "Label and regex are required", status: "warning" });
      return;
    }
    const example_values = examples
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!editing && example_values.length < 3) {
      toast({
        title: "At least three example values are required for new PII types",
        status: "warning",
      });
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await policyService.updatePiiType(editing.pii_type_id, {
          pii_type_label: label.trim(),
          regex_pattern: regex.trim(),
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
      toast({ title: "Saved", status: "success", duration: 2000 });
      modal.onClose();
      void reloadPiiTypes();
    } catch (e: unknown) {
      toast({
        title: getPolicyApiErrorMessage(e, "Save failed"),
        status: "error",
        duration: 5000,
        isClosable: true,
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
      toast({ title: "Deleted", status: "success", duration: 2000 });
      confirmDel.onClose();
      setDeleteTarget(null);
      void reloadPiiTypes();
    } catch (e: unknown) {
      toast({
        title: getPolicyApiErrorMessage(e, "Delete failed (type may be in use)"),
        status: "error",
        duration: 5000,
      });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <VStack align="stretch" spacing={4} mb={4}>
        <TableFilterToolbar
          hasActiveFilters={hasActiveFilters}
          onClear={clearAllFilters}
          align="flex-end"
          rightContent={
            <Button size="sm" colorScheme="blue" onClick={openCreate}>
              New PII type
            </Button>
          }
        >
          <FormControl w={{ base: "full", md: "280px" }}>
            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
              Search
            </FormLabel>
            <InputGroup>
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search by label or regex…"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setListPage(1);
                }}
                bg={cardBg}
                pl={10}
                size="sm"
              />
            </InputGroup>
          </FormControl>
          <FormControl w={{ base: "full", sm: "160px" }}>
            <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
              Mask format
            </FormLabel>
            <Select
              size="sm"
              value={filterMask}
              onChange={(e) => {
                setFilterMask(e.target.value);
                setListPage(1);
              }}
              bg={cardBg}
            >
              <option value="">All</option>
              {MASK_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </FormControl>
        </TableFilterToolbar>
        {hasActiveFilters && (
          <HStack spacing={2} flexWrap="wrap">
            {searchQuery.trim() && (
              <Badge
                colorScheme="blue"
                fontSize="xs"
                px={2}
                py={1}
                cursor="pointer"
                onClick={() => {
                  setSearchQuery("");
                  setListPage(1);
                }}
                _hover={{ opacity: 0.8 }}
              >
                Search: &quot;{searchQuery.trim()}&quot; ×
              </Badge>
            )}
            {filterMask && (
              <Badge
                colorScheme="gray"
                fontSize="xs"
                px={2}
                py={1}
                cursor="pointer"
                onClick={() => {
                  setFilterMask("");
                  setListPage(1);
                }}
                _hover={{ opacity: 0.8 }}
              >
                Mask: {filterMask} ×
              </Badge>
            )}
          </HStack>
        )}
      </VStack>

      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner />
        </Flex>
      ) : filteredPiiTypes.length === 0 ? (
        <Box textAlign="center" py={8}>
          <Text color="gray.500">
            No results found.
            {allTypes.length === 0
              ? " No PII types in the library yet."
              : " Try adjusting your search or filters."}
          </Text>
        </Box>
      ) : (
        <Box maxH="60vh" overflowY="auto" overflowX="auto">
          <Table variant="simple" bg={tableBg} size="sm" w="100%">
            <Thead bg={tableHeaderBg}>
              <Tr>
                <Th>
                  <TableSortHeader
                    label="Label"
                    direction={labelSortDirection}
                    onAsc={() => {
                      setSortBy("label");
                      setLabelSortDirection("asc");
                      setListPage(1);
                    }}
                    onDesc={() => {
                      setSortBy("label");
                      setLabelSortDirection("desc");
                      setListPage(1);
                    }}
                    ascAriaLabel="Sort PII types by label ascending"
                    descAriaLabel="Sort PII types by label descending"
                  />
                </Th>
                <Th>Mask</Th>
                <Th>Regex</Th>
                <Th>Created</Th>
                <Th textAlign="right">Actions</Th>
              </Tr>
            </Thead>
            <Tbody>
              {paginatedPiiTypes.map((row) => (
                <Tr
                  key={row.pii_type_id}
                  cursor="pointer"
                  _hover={{ bg: tableRowHoverBg }}
                  onClick={() => openPiiView(row)}
                >
                  <Td fontWeight="medium">{row.pii_type_label}</Td>
                  <Td>
                    <Badge>{row.mask_format}</Badge>
                  </Td>
                  <Td
                    maxW="280px"
                    title={row.regex_pattern}
                    whiteSpace="nowrap"
                    overflow="hidden"
                    textOverflow="ellipsis"
                  >
                    {row.regex_pattern}
                  </Td>
                  <Td whiteSpace="nowrap">{formatDt(row.created_at)}</Td>
                  <Td textAlign="right" onClick={(e) => e.stopPropagation()}>
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
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <TablePaginationBar
        startRow={startRow}
        endRow={endRow}
        totalItems={totalTypes}
        page={listPage}
        totalPages={totalPages}
        pageSize={listPageSize}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        onPageSizeChange={(s) => {
          setListPageSize(s);
          setListPage(1);
        }}
        onFirst={() => setListPage(1)}
        onPrev={() => setListPage((p) => Math.max(1, p - 1))}
        onNext={() => setListPage((p) => Math.min(totalPages, p + 1))}
        onLast={() => setListPage(totalPages)}
        canPrev={listPage > 1}
        canNext={listPage < totalPages}
        bg={cardBg}
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
          toast({ title: msg, status: "error", duration: 5000, isClosable: true })
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
          {!editing && (
            <FormControl isRequired>
              <FormLabel>Example values (comma or newline, min 3)</FormLabel>
              <Textarea
                value={examples}
                onChange={(e) => setExamples(e.target.value)}
                placeholder="a@b.com, test@example.org, user@mail.co"
                rows={3}
              />
            </FormControl>
          )}
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

function AuditPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
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

  const { tableBg, tableHeaderBg, tableRowHoverBg, cardBg } = useAdminTableSurface();

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

  const totalPages = Math.max(1, Math.ceil(meta.total / meta.limit) || 1);
  const startRow = meta.total === 0 ? 0 : (meta.page - 1) * meta.limit + 1;
  const endRow = Math.min(meta.page * meta.limit, meta.total);

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

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <VStack align="stretch" spacing={4} mb={4}>
        <TableFilterToolbar hasActiveFilters={hasActiveFilters} onClear={clearAllFilters} align="flex-end">
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
        </TableFilterToolbar>
        {hasActiveFilters && (
          <HStack spacing={2} flexWrap="wrap">
            {debouncedFilters.tenant !== "" && (
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
            )}
            {debouncedFilters.policy !== "" && (
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
            )}
            {debouncedFilters.trace !== "" && (
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
            )}
            {debouncedFilters.minPii !== "" && (
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
            )}
          </HStack>
        )}
      </VStack>

      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner />
        </Flex>
      ) : items.length === 0 ? (
        <Box textAlign="center" py={8}>
          <Text color="gray.500">
            No results found.
            {meta.total === 0 && !hasActiveFilters
              ? " No audit entries yet."
              : " Try adjusting your filters or pagination."}
          </Text>
        </Box>
      ) : (
        <Box maxH="60vh" overflowY="auto" overflowX="auto">
          <Table variant="simple" bg={tableBg} size="sm" w="100%">
            <Thead bg={tableHeaderBg}>
              <Tr>
                <Th>Tenant</Th>
                <Th>Policy</Th>
                <Th>Trace</Th>
                <Th>Context</Th>
                <Th isNumeric>PII #</Th>
                <Th isNumeric>ms</Th>
                <Th>
                  <TableSortHeader
                    label="Created"
                    direction={auditCreatedSort}
                    onAsc={() => setAuditCreatedSort("asc")}
                    onDesc={() => setAuditCreatedSort("desc")}
                    ascAriaLabel="Sort audit rows by created time ascending"
                    descAriaLabel="Sort audit rows by created time descending"
                  />
                </Th>
                <Th textAlign="right">Detail</Th>
              </Tr>
            </Thead>
            <Tbody>
              {displayItems.map((row) => (
                <Tr
                  key={row.pii_audit_id}
                  cursor="pointer"
                  _hover={{ bg: tableRowHoverBg }}
                  onClick={() => void openDetail(row.pii_audit_id)}
                >
                  <Td>{row.tenant_id || "—"}</Td>
                  <Td fontFamily="mono" fontSize="xs">
                    {row.policy_id || "—"}
                  </Td>
                  <Td fontFamily="mono" fontSize="xs" maxW="120px" isTruncated title={row.trace_id || ""}>
                    {row.trace_id || "—"}
                  </Td>
                  <Td maxW="200px" isTruncated title={row.target_context || ""}>
                    {row.target_context || "—"}
                  </Td>
                  <Td isNumeric>{row.pii_count ?? "—"}</Td>
                  <Td isNumeric>{row.processing_ms ?? "—"}</Td>
                  <Td whiteSpace="nowrap">{formatDt(row.created_at)}</Td>
                  <Td textAlign="right" onClick={(e) => e.stopPropagation()}>
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
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <TablePaginationBar
        startRow={startRow}
        endRow={endRow}
        totalItems={meta.total}
        page={Math.min(meta.page, totalPages)}
        totalPages={totalPages}
        pageSize={meta.limit}
        pageSizeOptions={AUDIT_PAGE_SIZE_OPTIONS}
        onPageSizeChange={(s) => setMeta((m) => ({ ...m, limit: s, page: 1 }))}
        onFirst={() => setMeta((m) => ({ ...m, page: 1 }))}
        onPrev={() => setMeta((m) => ({ ...m, page: Math.max(1, m.page - 1) }))}
        onNext={() => setMeta((m) => ({ ...m, page: Math.min(totalPages, m.page + 1) }))}
        onLast={() => setMeta((m) => ({ ...m, page: totalPages }))}
        canPrev={meta.page > 1}
        canNext={meta.page < totalPages}
        bg={cardBg}
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
