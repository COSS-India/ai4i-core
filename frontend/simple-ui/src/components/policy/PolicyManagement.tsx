import React, { useCallback, useEffect, useMemo, useState } from "react";
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
  HStack,
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
  Tr,
  useDisclosure,
  useToast,
  VStack,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { SearchIcon } from "@chakra-ui/icons";
import StandardModal from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import { TablePaginationBar } from "../common/TableControls";
import {
  policyService,
  type AuditLogOut,
  type MaskFormat,
  type PiiTypeOut,
  type PolicyOut,
} from "../../services/policyService";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

function ServerTablePagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions,
}: {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (p: number) => void;
  onPageSizeChange: (s: number) => void;
  pageSizeOptions: number[];
}) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize) || 1);
  const clampedPage = Math.min(page, totalPages);
  const startRow = totalItems === 0 ? 0 : (clampedPage - 1) * pageSize + 1;
  const endRow = Math.min(clampedPage * pageSize, totalItems);
  return (
    <TablePaginationBar
      startRow={startRow}
      endRow={endRow}
      totalItems={totalItems}
      page={clampedPage}
      totalPages={totalPages}
      pageSize={pageSize}
      pageSizeOptions={pageSizeOptions}
      onPageSizeChange={onPageSizeChange}
      onFirst={() => onPageChange(1)}
      onPrev={() => onPageChange(Math.max(1, clampedPage - 1))}
      onNext={() => onPageChange(Math.min(totalPages, clampedPage + 1))}
      onLast={() => onPageChange(totalPages)}
      canPrev={clampedPage > 1}
      canNext={clampedPage < totalPages}
    />
  );
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
          Policy definitions, PII type library, and audit trail (policy-service APIs).
        </Text>
        <HStack spacing={2} flexWrap="wrap" role="tablist" aria-label="Policy management sections">
          {(
            [
              ["policies", "Policy definitions"],
              ["pii", "PII type library"],
              ["audit", "Audit log"],
            ] as const
          ).map(([id, label]) => (
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
      {tab === "audit" && <AuditPanel toast={toast} />}
    </VStack>
  );
}

function PoliciesPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const [items, setItems] = useState<PolicyOut[]>([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterActive, setFilterActive] = useState<string>("");
  const [filterGlobal, setFilterGlobal] = useState<string>("");
  const modal = useDisclosure();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [piiOptions, setPiiOptions] = useState<PiiTypeOut[]>([]);

  const loadPiiOptions = useCallback(async () => {
    try {
      const res = await policyService.listPiiTypes({ page: 1, limit: 100 });
      setPiiOptions(res.data.data);
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof policyService.listPolicies>[0] = {
        page: meta.page,
        limit: meta.limit,
        search: search.trim() || undefined,
      };
      if (filterActive === "true") params.is_active = true;
      if (filterActive === "false") params.is_active = false;
      if (filterGlobal === "true") params.is_global = true;
      if (filterGlobal === "false") params.is_global = false;
      const res = await policyService.listPolicies(params);
      setItems(res.data.data);
      setMeta(res.data.meta);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load policies"));
    } finally {
      setLoading(false);
    }
  }, [meta.page, meta.limit, search, filterActive, filterGlobal]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadPiiOptions();
  }, [loadPiiOptions]);

  const openCreate = () => {
    setEditingId(null);
    modal.onOpen();
  };

  const openEdit = async (id: string) => {
    setEditingId(id);
    modal.onOpen();
  };

  const handleToggleActive = async (row: PolicyOut) => {
    try {
      await policyService.setPolicyStatus(row.policy_id, !row.is_active);
      toast({ title: "Status updated", status: "success", duration: 2500 });
      void load();
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

      <Stack spacing={4} mb={4}>
        <Flex gap={3} flexWrap="wrap" align="flex-end">
          <FormControl maxW="220px">
            <FormLabel fontSize="sm">Active</FormLabel>
            <Select
              size="sm"
              value={filterActive}
              onChange={(e) => {
                setFilterActive(e.target.value);
                setMeta((m) => ({ ...m, page: 1 }));
              }}
            >
              <option value="">Any</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </Select>
          </FormControl>
          <FormControl maxW="220px">
            <FormLabel fontSize="sm">Scope</FormLabel>
            <Select
              size="sm"
              value={filterGlobal}
              onChange={(e) => {
                setFilterGlobal(e.target.value);
                setMeta((m) => ({ ...m, page: 1 }));
              }}
            >
              <option value="">Any</option>
              <option value="true">Global</option>
              <option value="false">Non-global</option>
            </Select>
          </FormControl>
          <FormControl flex="1" minW="200px">
            <FormLabel fontSize="sm">Search</FormLabel>
            <InputGroup size="sm">
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Policy name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()}
              />
            </InputGroup>
          </FormControl>
          <Button size="sm" onClick={() => load()}>
            Apply
          </Button>
          <Button size="sm" colorScheme="blue" onClick={openCreate}>
            New policy
          </Button>
        </Flex>
      </Stack>

      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner />
        </Flex>
      ) : (
        <Box overflowX="auto">
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th>Name</Th>
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
              {items.map((row) => (
                <Tr key={row.policy_id}>
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
                  <Td textAlign="right">
                    <HStack justify="flex-end" spacing={2}>
                      <Button size="xs" variant="outline" onClick={() => void openEdit(row.policy_id)}>
                        Edit
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => void handleToggleActive(row)}
                      >
                        {row.is_active ? "Deactivate" : "Activate"}
                      </Button>
                    </HStack>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <ServerTablePagination
        page={meta.page}
        pageSize={meta.limit}
        totalItems={meta.total}
        onPageChange={(p) => setMeta((m) => ({ ...m, page: p }))}
        onPageSizeChange={(s) => setMeta((m) => ({ ...m, limit: s, page: 1 }))}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
      />

      <PolicyFormModal
        isOpen={modal.isOpen}
        onClose={modal.onClose}
        policyId={editingId}
        piiOptions={piiOptions}
        onSaved={() => {
          modal.onClose();
          void load();
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

function PiiTypesPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const [items, setItems] = useState<PiiTypeOut[]>([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const modal = useDisclosure();
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await policyService.listPiiTypes({
        page: meta.page,
        limit: meta.limit,
        search: search.trim() || undefined,
      });
      setItems(res.data.data);
      setMeta(res.data.meta);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load PII types"));
    } finally {
      setLoading(false);
    }
  }, [meta.page, meta.limit, search]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setLabel("");
    setRegex("");
    setExamples("");
    setMask("redact");
    modal.onOpen();
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
      void load();
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
      void load();
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

      <Flex gap={3} mb={4} flexWrap="wrap" align="flex-end">
        <FormControl flex="1" minW="200px">
          <FormLabel fontSize="sm">Search</FormLabel>
          <InputGroup size="sm">
            <InputLeftElement pointerEvents="none">
              <SearchIcon color="gray.400" />
            </InputLeftElement>
            <Input
              placeholder="Label…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
            />
          </InputGroup>
        </FormControl>
        <Button size="sm" onClick={() => load()}>
          Apply
        </Button>
        <Button size="sm" colorScheme="blue" onClick={openCreate}>
          New PII type
        </Button>
      </Flex>

      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner />
        </Flex>
      ) : (
        <Box overflowX="auto">
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th>Label</Th>
                <Th>Mask</Th>
                <Th>Regex</Th>
                <Th>Created</Th>
                <Th textAlign="right">Actions</Th>
              </Tr>
            </Thead>
            <Tbody>
              {items.map((row) => (
                <Tr key={row.pii_type_id}>
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
                  <Td textAlign="right">
                    <HStack justify="flex-end" spacing={2}>
                      <Button size="xs" variant="outline" onClick={() => openEdit(row)}>
                        Edit
                      </Button>
                      <Button size="xs" variant="outline" colorScheme="red" onClick={() => requestDelete(row)}>
                        Delete
                      </Button>
                    </HStack>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <ServerTablePagination
        page={meta.page}
        pageSize={meta.limit}
        totalItems={meta.total}
        onPageChange={(p) => setMeta((m) => ({ ...m, page: p }))}
        onPageSizeChange={(s) => setMeta((m) => ({ ...m, limit: s, page: 1 }))}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
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
  const detailModal = useDisclosure();
  const [detailJson, setDetailJson] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof policyService.listAuditLogs>[0] = {
        page: meta.page,
        limit: meta.limit,
      };
      const t = tenantFilter.trim();
      if (t) params.tenant_id = t;
      const pid = policyIdFilter.trim();
      if (pid) params.policy_id = pid;
      const tid = traceIdFilter.trim();
      if (tid) params.trace_id = tid;
      const n = minPii.trim();
      if (n !== "" && !Number.isNaN(Number(n))) params.min_pii_count = Number(n);
      const res = await policyService.listAuditLogs(params);
      setItems(res.data.data);
      setMeta(res.data.meta);
    } catch (e: unknown) {
      setError(getPolicyApiErrorMessage(e, "Failed to load audit logs"));
    } finally {
      setLoading(false);
    }
  }, [meta.page, meta.limit, tenantFilter, policyIdFilter, traceIdFilter, minPii]);

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <Wrap spacing={3} mb={4}>
        <WrapItem>
          <FormControl minW="200px">
            <FormLabel fontSize="sm">Tenant ID</FormLabel>
            <Input
              size="sm"
              value={tenantFilter}
              onChange={(e) => setTenantFilter(e.target.value)}
              placeholder="Filter…"
            />
          </FormControl>
        </WrapItem>
        <WrapItem>
          <FormControl minW="200px">
            <FormLabel fontSize="sm">Policy ID</FormLabel>
            <Input
              size="sm"
              value={policyIdFilter}
              onChange={(e) => setPolicyIdFilter(e.target.value)}
              placeholder="UUID…"
            />
          </FormControl>
        </WrapItem>
        <WrapItem>
          <FormControl minW="200px">
            <FormLabel fontSize="sm">Trace ID</FormLabel>
            <Input
              size="sm"
              value={traceIdFilter}
              onChange={(e) => setTraceIdFilter(e.target.value)}
              placeholder="Filter…"
            />
          </FormControl>
        </WrapItem>
        <WrapItem>
          <FormControl maxW="160px">
            <FormLabel fontSize="sm">Min PII count</FormLabel>
            <Input
              size="sm"
              type="number"
              min={0}
              value={minPii}
              onChange={(e) => setMinPii(e.target.value)}
            />
          </FormControl>
        </WrapItem>
        <WrapItem alignSelf="flex-end">
          <Button size="sm" onClick={() => load()}>
            Apply
          </Button>
        </WrapItem>
      </Wrap>

      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner />
        </Flex>
      ) : (
        <Box overflowX="auto">
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th>Tenant</Th>
                <Th>Policy</Th>
                <Th>Trace</Th>
                <Th>Context</Th>
                <Th isNumeric>PII #</Th>
                <Th isNumeric>ms</Th>
                <Th>Created</Th>
                <Th textAlign="right">Detail</Th>
              </Tr>
            </Thead>
            <Tbody>
              {items.map((row) => (
                <Tr key={row.pii_audit_id}>
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
                  <Td textAlign="right">
                    <Button size="xs" variant="outline" onClick={() => void openDetail(row.pii_audit_id)}>
                      JSON
                    </Button>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <ServerTablePagination
        page={meta.page}
        pageSize={meta.limit}
        totalItems={meta.total}
        onPageChange={(p) => setMeta((m) => ({ ...m, page: p }))}
        onPageSizeChange={(s) => setMeta((m) => ({ ...m, limit: s, page: 1 }))}
        pageSizeOptions={AUDIT_PAGE_SIZE_OPTIONS}
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
