import React, { useEffect, useMemo, useState } from "react";
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
  FormControl,
  FormLabel,
  GridItem,
  Heading,
  HStack,
  IconButton,
  Input,
  Select,
  SimpleGrid,
  Stack,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Textarea,
  Tooltip,
  useColorModeValue,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import { showToast } from "../../utils/toast";
import { DeleteIcon, EditIcon } from "@chakra-ui/icons";
import { piiService } from "../../services/piiService";
import { useAdminTableSurface } from "../common/TableControls";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import { PAGINATION } from "../../constants";
import StandardModal from "../common/StandardModal";

interface Rule {
  entity_type: string;
  action: string;
  config: Record<string, unknown>;
  custom_regex?: string;
}

interface Domain {
  domain_id: string;
  is_active: boolean;
  description?: string | null;
}

type PageTab = "admin" | "audit";

type TenantDomainMappingRow = { tenant_id: string; domain_id: string; updated_at?: string };

interface AuditLogRow {
  id: number;
  trace_id: string;
  tenant_id: string;
  domain_id: string;
  target_context: string;
  pii_count: number;
  processing_ms: number;
  trace_json: unknown;
  created_at: string | null;
}

export interface PiiManagementProps {
  isAdmin?: boolean;
}

function actionBadgeColorScheme(action: string): string {
  switch (action) {
    case "MASK":
      return "gray";
    case "HASH":
      return "red";
    default:
      return "blue";
  }
}

export default function PiiManagement({ isAdmin = false }: PiiManagementProps) {
  const { tableRowHoverBg, cardBg, borderColor } = useAdminTableSurface();
  const pageBg = useColorModeValue("gray.50", "gray.900");
  const mutedText = useColorModeValue("gray.600", "gray.400");
  const headingColor = useColorModeValue("gray.900", "white");
  const readOnlyInputBg = useColorModeValue("gray.100", "gray.700");
  const domainDetail = useDisclosure();
  const ruleDetail = useDisclosure();
  const mappingDetail = useDisclosure();
  const auditTraceDetail = useDisclosure();
  const [viewDomain, setViewDomain] = useState<Domain | null>(null);
  const [viewRule, setViewRule] = useState<Rule | null>(null);
  const [viewMapping, setViewMapping] = useState<TenantDomainMappingRow | null>(null);
  const [auditDetailJson, setAuditDetailJson] = useState("");

  const [activeTab, setActiveTab] = useState<PageTab>("admin");
  const [allDomains, setAllDomains] = useState<Domain[]>([]);
  const [checkedDomains, setCheckedDomains] = useState<Set<string>>(new Set());
  const [newDomainId, setNewDomainId] = useState("");
  const [editingDomainId, setEditingDomainId] = useState<string | null>(null);
  const [editingRules, setEditingRules] = useState<Rule[]>([]);
  const [tenantMappings, setTenantMappings] = useState<TenantDomainMappingRow[]>([]);
  const [newMapTenantId, setNewMapTenantId] = useState("");
  const [newMapDomainId, setNewMapDomainId] = useState("");
  const [newEntity, setNewEntity] = useState("");
  const [newAction, setNewAction] = useState("");
  const [newExample, setNewExample] = useState("");
  const [newRegex, setNewRegex] = useState("");
  const [adminDataError, setAdminDataError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogRow[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [rulesSortDirection, setRulesSortDirection] = useState<"asc" | "desc">("asc");
  const [mappingSearch, setMappingSearch] = useState("");
  const [mappingDomainFilter, setMappingDomainFilter] = useState("all");
  const [mappingSortDirection, setMappingSortDirection] = useState<"asc" | "desc">("asc");
  const [auditSearch, setAuditSearch] = useState("");
  const [auditDomainFilter, setAuditDomainFilter] = useState("all");
  const [auditTenantFilter, setAuditTenantFilter] = useState("all");
  const [auditSortDirection, setAuditSortDirection] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    if (!isAdmin || activeTab !== "audit") return;
    void fetchAuditLogs();
  }, [isAdmin, activeTab]);

  useEffect(() => {
    if (!isAdmin || activeTab !== "admin") return;
    void refreshAdminDataWithRetry().catch(() => undefined);
  }, [isAdmin, activeTab]);

  const fetchAllDomains = async () => {
    const res = await piiService.getAllDomains();
    const rows = res.data as Domain[];
    setAllDomains(rows);
    const active = new Set(rows.filter((d) => d.is_active).map((d) => d.domain_id));
    setCheckedDomains(active);
  };

  const handleToggleDomainActivate = (domainId: string) => {
    const next = new Set(checkedDomains);
    if (next.has(domainId)) next.delete(domainId);
    else next.add(domainId);
    setCheckedDomains(next);
  };

  const applyActiveDomains = async () => {
    try {
      await piiService.activateDomains(Array.from(checkedDomains));
      showToast({ type: "success", message: "Domain activation updated" });
      await fetchAllDomains();
    } catch {
      showToast({ type: "error", message: "Failed to apply domains" });
    }
  };

  const fetchTenantMappings = async () => {
    const res = await piiService.listTenantDomainMappings();
    setTenantMappings(res.data);
  };

  const refreshAdminDataWithRetry = async () => {
    setAdminDataError(null);
    try {
      await Promise.all([fetchAllDomains(), fetchTenantMappings()]);
      return;
    } catch {
      console.warn("Admin data fetch failed, retrying once...");
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
    try {
      await Promise.all([fetchAllDomains(), fetchTenantMappings()]);
    } catch {
      console.warn("Admin data fetch failed after retry");
      setAdminDataError("Could not load domains/mappings. Please click Refresh.");
    }
  };

  const handleSaveTenantMapping = async () => {
    const tid = newMapTenantId.trim();
    if (!tid || !newMapDomainId) {
      showToast({ type: "warning", message: "Enter tenant ID and choose a domain" });
      return;
    }
    try {
      await piiService.upsertTenantDomainMapping(tid, newMapDomainId);
      setNewMapTenantId("");
      await fetchTenantMappings();
      showToast({ type: "success", message: "Mapping saved" });
    } catch {
      showToast({
        type: "error",
        message: "Failed to save mapping (check domain exists and permissions)",
      });
    }
  };

  const handleDeleteTenantMapping = async (tenantId: string, onSuccess?: () => void) => {
    if (typeof window !== "undefined" && !window.confirm(`Remove mapping for tenant "${tenantId}"?`))
      return;
    try {
      await piiService.deleteTenantDomainMapping(tenantId);
      await fetchTenantMappings();
      onSuccess?.();
    } catch {
      showToast({ type: "error", message: "Failed to delete mapping" });
    }
  };

  const handleCreateDomain = async () => {
    if (!newDomainId) return;
    try {
      await piiService.createDomain(newDomainId);
      setNewDomainId("");
      await fetchAllDomains();
      showToast({ type: "success", message: "Domain created" });
    } catch {
      showToast({ type: "error", message: "Failed to create domain" });
    }
  };

  const loadDomainConfig = async (id: string) => {
    setEditingDomainId(id);
    try {
      const res = await piiService.getPolicy(id);
      const rules = Array.isArray(res.data.rules) ? (res.data.rules as Rule[]) : [];
      setEditingRules(rules);
    } catch {
      showToast({ type: "error", message: "Failed to load policy" });
    }
  };

  const generateRegex = async () => {
    try {
      const res = await piiService.generateRegex(newExample);
      setNewRegex(res.data.regex);
    } catch {
      showToast({ type: "error", message: "Regex generation failed" });
    }
  };

  const addCustomRule = () => {
    if (!newEntity) {
      showToast({ type: "warning", message: "Entity name required" });
      return;
    }
    if (!newAction) {
      showToast({ type: "warning", message: "Action required" });
      return;
    }
    const rule: Rule = { entity_type: newEntity.toUpperCase(), action: newAction, config: {} };
    if (newRegex.trim()) rule.custom_regex = newRegex;

    setEditingRules([...editingRules, rule]);
    setNewEntity("");
    setNewRegex("");
    setNewExample("");
  };

  const saveConfig = async () => {
    if (!editingDomainId) {
      showToast({ type: "warning", message: "Select a domain to edit" });
      return;
    }
    try {
      await piiService.deployRules(editingDomainId, editingRules);
      showToast({ type: "success", message: "Policy rules saved" });
      await fetchAllDomains();
    } catch {
      showToast({ type: "error", message: "Save failed" });
    }
  };

  const fetchAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const res = await piiService.getAuditLogs(100);
      setAuditLogs(res.data);
    } catch {
      showToast({ type: "error", message: "Failed to load audit logs" });
    } finally {
      setAuditLoading(false);
    }
  };

  /** Remove by object identity — matches row in sorted/paginated view to `editingRules`. */
  const removeRuleForRow = (rule: Rule) => {
    setEditingRules((prev) => prev.filter((x) => x !== rule));
  };

  const activeDomainCount = allDomains.filter((d) => d.is_active).length;

  const sortedRules = useMemo(() => {
    const copy = [...editingRules];
    copy.sort((a, b) => {
      const nameCmp = (a.entity_type ?? "").localeCompare(b.entity_type ?? "", undefined, {
        sensitivity: "base",
      });
      return rulesSortDirection === "asc" ? nameCmp : -nameCmp;
    });
    return copy;
  }, [editingRules, rulesSortDirection]);

  const sortedMappings = useMemo(() => {
    const q = mappingSearch.trim().toLowerCase();
    const filtered = tenantMappings.filter((row) => {
      if (mappingDomainFilter !== "all" && row.domain_id !== mappingDomainFilter) return false;
      if (!q) return true;
      return (
        (row.tenant_id ?? "").toLowerCase().includes(q) ||
        (row.domain_id ?? "").toLowerCase().includes(q)
      );
    });
    const copy = [...filtered];
    copy.sort((a, b) => {
      const nameCmp = (a.tenant_id ?? "").localeCompare(b.tenant_id ?? "", undefined, {
        sensitivity: "base",
      });
      return mappingSortDirection === "asc" ? nameCmp : -nameCmp;
    });
    return copy;
  }, [tenantMappings, mappingSearch, mappingDomainFilter, mappingSortDirection]);

  const sortedAuditLogs = useMemo(() => {
    const q = auditSearch.trim().toLowerCase();
    const filtered = auditLogs.filter((row) => {
      if (auditDomainFilter !== "all" && row.domain_id !== auditDomainFilter) return false;
      if (auditTenantFilter !== "all" && row.tenant_id !== auditTenantFilter) return false;
      if (!q) return true;
      return (
        (row.trace_id ?? "").toLowerCase().includes(q) ||
        (row.tenant_id ?? "").toLowerCase().includes(q) ||
        (row.domain_id ?? "").toLowerCase().includes(q) ||
        (row.target_context ?? "").toLowerCase().includes(q)
      );
    });
    const copy = [...filtered];
    copy.sort((a, b) => {
      const timeA = a.created_at ? new Date(a.created_at).getTime() : -Infinity;
      const timeB = b.created_at ? new Date(b.created_at).getTime() : -Infinity;
      return auditSortDirection === "asc" ? timeA - timeB : timeB - timeA;
    });
    return copy;
  }, [auditLogs, auditSearch, auditDomainFilter, auditTenantFilter, auditSortDirection]);

  const auditDomainOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const row of auditLogs) {
      if (row.domain_id) ids.add(row.domain_id);
    }
    return Array.from(ids).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [auditLogs]);

  const auditTenantOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const row of auditLogs) {
      if (row.tenant_id) ids.add(row.tenant_id);
    }
    return Array.from(ids).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [auditLogs]);

  const mappingHasActiveFilters =
    !!mappingSearch.trim() || mappingDomainFilter !== "all";

  const auditHasActiveFilters =
    !!auditSearch.trim() || auditDomainFilter !== "all" || auditTenantFilter !== "all";

  const rulesColumns: AdminTableColumn<Rule>[] = useMemo(
    () => [
      {
        id: "entity",
        header: "Entity",
        sortable: {
          label: "Entity",
          direction: rulesSortDirection,
          onAsc: () => setRulesSortDirection("asc"),
          onDesc: () => setRulesSortDirection("desc"),
          ascAriaLabel: "Sort rules by entity ascending",
          descAriaLabel: "Sort rules by entity descending",
        },
        cell: (r) => (
          <Text fontWeight="bold" fontSize="sm">
            {r.entity_type}
          </Text>
        ),
      },
      {
        id: "action",
        header: "Action",
        cell: (r) => (
          <Badge colorScheme={actionBadgeColorScheme(r.action)} fontSize="xs">
            {r.action}
          </Badge>
        ),
      },
      {
        id: "delete",
        header: "Delete",
        thProps: { textAlign: "right" },
        tdProps: { textAlign: "right" },
        cell: (r) => (
          <Tooltip label="Remove rule" hasArrow>
            <IconButton
              aria-label="Remove rule"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              _hover={{ bg: "red.50" }}
              onClick={(e) => {
                e.stopPropagation();
                removeRuleForRow(r);
              }}
            />
          </Tooltip>
        ),
      },
    ],
    [rulesSortDirection]
  );

  const mappingColumns: AdminTableColumn<TenantDomainMappingRow>[] = useMemo(
    () => [
      {
        id: "tenant",
        header: "Tenant ID",
        sortable: {
          label: "Tenant ID",
          direction: mappingSortDirection,
          onAsc: () => setMappingSortDirection("asc"),
          onDesc: () => setMappingSortDirection("desc"),
          ascAriaLabel: "Sort mappings by tenant ascending",
          descAriaLabel: "Sort mappings by tenant descending",
        },
        cell: (row) => (
          <Text fontFamily="mono" fontSize="xs">
            {row.tenant_id}
          </Text>
        ),
      },
      {
        id: "domain",
        header: "Domain",
        cell: (row) => (
          <Text fontWeight="semibold" fontSize="sm">
            {row.domain_id}
          </Text>
        ),
      },
      {
        id: "updated",
        header: "Updated",
        cell: (row) => (
          <Text fontSize="xs" color={mutedText}>
            {row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}
          </Text>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        thProps: { textAlign: "right" },
        tdProps: { textAlign: "right" },
        cell: (row) => (
          <Tooltip label="Remove mapping" hasArrow>
            <IconButton
              aria-label="Remove mapping"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              _hover={{ bg: "red.50" }}
              onClick={(e) => {
                e.stopPropagation();
                void handleDeleteTenantMapping(row.tenant_id);
              }}
            />
          </Tooltip>
        ),
      },
    ],
    [mappingSortDirection, mutedText]
  );

  const auditColumns: AdminTableColumn<AuditLogRow>[] = useMemo(
    () => [
      {
        id: "time",
        header: "Time",
        sortable: {
          label: "Time",
          direction: auditSortDirection,
          onAsc: () => setAuditSortDirection("asc"),
          onDesc: () => setAuditSortDirection("desc"),
          ascAriaLabel: "Sort audit logs by time ascending",
          descAriaLabel: "Sort audit logs by time descending",
        },
        cell: (row) => (
          <Text fontSize="xs" color={mutedText} whiteSpace="nowrap">
            {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
          </Text>
        ),
      },
      {
        id: "trace",
        header: "Trace ID",
        cell: (row) => (
          <Text fontFamily="mono" fontSize="xs">
            {row.trace_id || "—"}
          </Text>
        ),
      },
      {
        id: "tenant",
        header: "Tenant",
        cell: (row) => (
          <Text fontFamily="mono" fontSize="xs">
            {row.tenant_id || "—"}
          </Text>
        ),
      },
      {
        id: "domain",
        header: "Domain",
        cell: (row) => (
          <Text fontSize="sm">{row.domain_id || "—"}</Text>
        ),
      },
      {
        id: "target",
        header: "Target",
        tdProps: { maxW: "200px" },
        cell: (row) => (
          <Text isTruncated title={row.target_context || ""} fontSize="sm">
            {row.target_context || "—"}
          </Text>
        ),
      },
      {
        id: "pii",
        header: "PII Count",
        thProps: { isNumeric: true },
        tdProps: { isNumeric: true },
        cell: (row) => <Text fontSize="sm">{row.pii_count ?? 0}</Text>,
      },
      {
        id: "latency",
        header: "Latency",
        thProps: { isNumeric: true },
        tdProps: { isNumeric: true },
        cell: (row) => <Text fontSize="sm">{row.processing_ms ?? 0} ms</Text>,
      },
    ],
    [auditSortDirection, mutedText]
  );

  const tabIndex = activeTab === "admin" ? 0 : 1;

  const openDomainDetail = (d: Domain) => {
    setViewDomain(d);
    domainDetail.onOpen();
  };
  const closeDomainDetail = () => {
    domainDetail.onClose();
    setViewDomain(null);
  };
  const openRuleDetail = (r: Rule) => {
    setViewRule(r);
    ruleDetail.onOpen();
  };
  const closeRuleDetail = () => {
    ruleDetail.onClose();
    setViewRule(null);
  };
  const openMappingDetail = (m: TenantDomainMappingRow) => {
    setViewMapping(m);
    mappingDetail.onOpen();
  };
  const closeMappingDetail = () => {
    mappingDetail.onClose();
    setViewMapping(null);
  };
  const openAuditTraceDetail = (row: AuditLogRow) => {
    try {
      setAuditDetailJson(JSON.stringify(row.trace_json ?? row, null, 2));
    } catch {
      setAuditDetailJson(String(row.trace_json ?? ""));
    }
    auditTraceDetail.onOpen();
  };
  const closeAuditTraceDetail = () => {
    auditTraceDetail.onClose();
    setAuditDetailJson("");
  };

  if (!isAdmin) {
    return (
      <Box bg={pageBg} minH="100vh" p={6}>
        <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
          <CardBody>
            <Heading size="sm" mb={2}>
              PII Management
            </Heading>
            <Text fontSize="sm" color={mutedText}>
              You do not have access to this page. Admin permissions are required.
            </Text>
          </CardBody>
        </Card>
      </Box>
    );
  }

  return (
    <Box bg={pageBg} minH="100vh" p={6}>
      <HStack justify="space-between" mb={2} flexWrap="wrap" gap={2}>
        <Box>
          <Heading size="lg" color={headingColor}>
            PII Management
          </Heading>
          <Badge colorScheme="blue" mt={2} fontSize="xs">
            Admin Console
          </Badge>
        </Box>
      </HStack>

      <Tabs
        index={tabIndex}
        onChange={(i) => setActiveTab(i === 0 ? "admin" : "audit")}
        colorScheme="blue"
        variant="enclosed"
        mt={6}
      >
        <TabList>
          <Tab fontWeight="semibold">Admin</Tab>
          <Tab fontWeight="semibold">Audit Logs</Tab>
        </TabList>

        <TabPanels>
          <TabPanel px={0} pt={6}>
            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={6}>
              <Card bg={cardBg} borderWidth="1px" borderColor={borderColor} h={{ base: "auto", md: "600px" }}>
                <CardBody display="flex" flexDirection="column" h="full">
                  <Text fontSize="xs" fontWeight="bold" color={mutedText} textTransform="uppercase" letterSpacing="wider" borderBottomWidth="1px" borderColor={borderColor} pb={2} mb={4}>
                    Domain Inventory
                  </Text>
                  <VStack align="stretch" spacing={2} flex="1" overflowY="auto" mb={4}>
                    {allDomains.map((d) => (
                      <HStack
                        key={d.domain_id}
                        justify="space-between"
                        p={2}
                        borderWidth="1px"
                        borderRadius="md"
                        borderColor={borderColor}
                        _hover={{ bg: tableRowHoverBg }}
                        cursor="pointer"
                        onClick={() => openDomainDetail(d)}
                      >
                        <HStack spacing={3} flex="1" minW={0}>
                          <Box onClick={(e) => e.stopPropagation()}>
                            <Checkbox
                              isChecked={checkedDomains.has(d.domain_id)}
                              onChange={() => handleToggleDomainActivate(d.domain_id)}
                            />
                          </Box>
                          <Text fontWeight="semibold" fontSize="sm" noOfLines={1}>
                            {d.domain_id.toUpperCase()}
                          </Text>
                        </HStack>
                        <Box onClick={(e) => e.stopPropagation()}>
                          <Tooltip label="Edit policy rules" hasArrow placement="top">
                            <IconButton
                              aria-label="Edit policy rules for domain"
                              icon={<EditIcon />}
                              size="sm"
                              variant="ghost"
                              colorScheme="blue"
                              _hover={{ bg: "blue.50" }}
                              onClick={() => void loadDomainConfig(d.domain_id)}
                            />
                          </Tooltip>
                        </Box>
                      </HStack>
                    ))}
                  </VStack>
                  <Button
                    colorScheme="gray"
                    isDisabled={checkedDomains.size === 0}
                    onClick={() => void applyActiveDomains()}
                    mb={4}
                  >
                    Apply Active Domains ({checkedDomains.size})
                  </Button>
                  <Box borderTopWidth="1px" borderColor={borderColor} pt={4}>
                    <Input
                      size="sm"
                      placeholder="New domain id"
                      mb={2}
                      bg={cardBg}
                      value={newDomainId}
                      onChange={(e) => setNewDomainId(e.target.value)}
                    />
                    <Button size="sm" variant="outline" w="full" onClick={() => void handleCreateDomain()}>
                      Create Domain
                    </Button>
                  </Box>
                </CardBody>
              </Card>

              <GridItem colSpan={{ base: 1, md: 2 }}>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor} h={{ base: "auto", md: "600px" }}>
                  <CardBody display="flex" flexDirection="column" h="full">
                    <HStack justify="space-between" borderBottomWidth="1px" borderColor={borderColor} pb={2} mb={4} flexWrap="wrap">
                      <Text fontSize="xs" fontWeight="bold" color={mutedText} textTransform="uppercase" letterSpacing="wider">
                        Policy Rules
                      </Text>
                      {editingDomainId ? (
                        <Badge colorScheme="yellow">Editing: {editingDomainId}</Badge>
                      ) : null}
                    </HStack>

                    <Box flex="1" mb={4}>
                      <AdminDataTable
                        key={`rules-${editingDomainId ?? "none"}-${rulesSortDirection}`}
                        items={sortedRules}
                        columns={rulesColumns}
                        getRowKey={(r) => `${r.entity_type}-${r.action}-${r.custom_regex ?? ""}`}
                        paginate="client"
                        initialPageSize={10}
                        pageSizeOptions={PAGINATION.TABLE_PAGE_SIZE_OPTIONS}
                        emptyMessage="No rules configured for this domain."
                        onRowClick={openRuleDetail}
                        maxHeight="280px"
                        tableContainerProps={{
                          borderWidth: "1px",
                          borderRadius: "md",
                          borderColor,
                        }}
                      />
                    </Box>

                    <Box borderWidth="1px" borderRadius="md" borderColor={borderColor} p={4} mb={4} bg={cardBg}>
                      <Text fontSize="sm" fontWeight="bold" color="blue.500" mb={3}>
                        Add Custom Rule
                      </Text>
                      <SimpleGrid columns={{ base: 1, md: 12 }} spacing={2} mb={2}>
                        <GridItem colSpan={{ base: 1, md: 3 }}>
                          <Input
                            size="sm"
                            placeholder="Entity (e.g., PASSPORT)"
                            value={newEntity}
                            onChange={(e) => setNewEntity(e.target.value)}
                            bg={cardBg}
                          />
                        </GridItem>
                        <GridItem colSpan={{ base: 1, md: 3 }}>
                          <Select size="sm" value={newAction} onChange={(e) => setNewAction(e.target.value)} bg={cardBg} placeholder="Select action">
                            <option value="REDACT_TAG">REDACT_TAG</option>
                            <option value="MASK">MASK</option>
                            <option value="HASH">HASH</option>
                          </Select>
                        </GridItem>
                        <GridItem colSpan={{ base: 1, md: 6 }}>
                          <HStack
                            spacing={3}
                            align="stretch"
                            flexWrap={{ base: "wrap", md: "nowrap" }}
                          >
                            <Input
                              size="sm"
                              flex="1"
                              minW={{ base: "100%", md: "140px" }}
                              placeholder="AI Example (e.g., A1234567)"
                              value={newExample}
                              onChange={(e) => setNewExample(e.target.value)}
                              bg={cardBg}
                            />
                            <Button
                              size="sm"
                              colorScheme="orange"
                              flexShrink={0}
                              whiteSpace="nowrap"
                              px={4}
                              onClick={() => void generateRegex()}
                            >
                              Generate Regex
                            </Button>
                          </HStack>
                        </GridItem>
                      </SimpleGrid>
                      <Input
                        size="sm"
                        placeholder="Generated Regex / Pattern"
                        readOnly
                        fontFamily="mono"
                        mb={2}
                        bg={readOnlyInputBg}
                        value={newRegex}
                      />
                      <Button size="sm" variant="outline" colorScheme="blue" w="full" onClick={addCustomRule}>
                        Add Rule
                      </Button>
                    </Box>

                    <Button colorScheme="green" onClick={() => void saveConfig()}>
                      Save Policy
                    </Button>
                  </CardBody>
                </Card>
              </GridItem>

              <GridItem colSpan={{ base: 1, md: 3 }}>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" fontWeight="bold" color={mutedText} textTransform="uppercase" letterSpacing="wider" borderBottomWidth="1px" borderColor={borderColor} pb={2} mb={4}>
                      Tenant to Domain Mapping
                    </Text>
                    <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3} mb={4}>
                      <FormControl>
                        <FormLabel fontSize="xs">Tenant ID</FormLabel>
                        <Input
                          size="sm"
                          placeholder="tenant uuid/slug"
                          value={newMapTenantId}
                          onChange={(e) => setNewMapTenantId(e.target.value)}
                          bg={cardBg}
                        />
                      </FormControl>
                      <FormControl>
                        <FormLabel fontSize="xs">Domain</FormLabel>
                        <Select
                          size="sm"
                          placeholder="Select domain"
                          value={newMapDomainId}
                          onChange={(e) => setNewMapDomainId(e.target.value)}
                          bg={cardBg}
                        >
                          <option value="">Select domain</option>
                          {allDomains.map((d) => (
                            <option key={d.domain_id} value={d.domain_id}>
                              {d.domain_id}
                              {d.is_active ? " (active)" : ""}
                            </option>
                          ))}
                        </Select>
                      </FormControl>
                    </SimpleGrid>
                    <HStack spacing={2} mb={4} flexWrap="wrap">
                      <Button size="sm" colorScheme="blue" onClick={() => void handleSaveTenantMapping()}>
                        Save
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => void refreshAdminDataWithRetry()}>
                        Refresh
                      </Button>
                    </HStack>
                    {adminDataError ? (
                      <Alert status="error" size="sm" borderRadius="md" mb={4}>
                        <AlertIcon />
                        <AlertDescription fontSize="xs">{adminDataError}</AlertDescription>
                      </Alert>
                    ) : null}
                    <AdminDataTable
                      key={`mappings-${mappingSortDirection}`}
                      items={sortedMappings}
                      columns={mappingColumns}
                      getRowKey={(row) => row.tenant_id}
                      paginate="client"
                      initialPageSize={10}
                      pageSizeOptions={PAGINATION.TABLE_PAGE_SIZE_OPTIONS}
                      emptyMessage="No mappings configured."
                      noResultsMessage="No mappings match the current filters."
                      unfilteredCount={tenantMappings.length}
                      onRowClick={openMappingDetail}
                      maxHeight="50vh"
                      filters={
                        <>
                          <TableSearchField
                            label="Search"
                            value={mappingSearch}
                            onChange={setMappingSearch}
                            placeholder="Search tenant or domain…"
                          />
                          <TableSelectField
                            label="Domain"
                            value={mappingDomainFilter}
                            onChange={setMappingDomainFilter}
                          >
                            <option value="all">All domains</option>
                            {allDomains.map((d) => (
                              <option key={d.domain_id} value={d.domain_id}>
                                {d.domain_id}
                              </option>
                            ))}
                          </TableSelectField>
                        </>
                      }
                      hasActiveFilters={mappingHasActiveFilters}
                      onClearFilters={() => {
                        setMappingSearch("");
                        setMappingDomainFilter("all");
                      }}
                    />
                  </CardBody>
                </Card>
              </GridItem>
            </SimpleGrid>
          </TabPanel>

          <TabPanel px={0} pt={6}>
            <VStack align="stretch" spacing={6}>
              <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                <CardBody>
                  <HStack justify="space-between" flexWrap="wrap" gap={3}>
                    <Box>
                      <Heading size="sm" mb={2}>
                        Audit Logs
                      </Heading>
                      <Text fontSize="sm" color={mutedText}>
                        Recent redact events captured by pii-service.
                      </Text>
                    </Box>
                    <Button size="sm" variant="outline" onClick={() => void fetchAuditLogs()}>
                      Refresh
                    </Button>
                  </HStack>
                </CardBody>
              </Card>
              <SimpleGrid columns={{ base: 1, md: 3 }} spacing={6}>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" color={mutedText} textTransform="uppercase" mb={2}>
                      Total Domains
                    </Text>
                    <Text fontSize="2xl" fontWeight="bold">
                      {allDomains.length}
                    </Text>
                  </CardBody>
                </Card>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" color={mutedText} textTransform="uppercase" mb={2}>
                      Active Domains
                    </Text>
                    <Text fontSize="2xl" fontWeight="bold">
                      {activeDomainCount}
                    </Text>
                  </CardBody>
                </Card>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" color={mutedText} textTransform="uppercase" mb={2}>
                      Tenant Mappings
                    </Text>
                    <Text fontSize="2xl" fontWeight="bold">
                      {tenantMappings.length}
                    </Text>
                  </CardBody>
                </Card>
              </SimpleGrid>
              <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                <CardBody>
                  <AdminDataTable
                    key={`audit-${auditSortDirection}`}
                    items={sortedAuditLogs}
                    columns={auditColumns}
                    getRowKey={(row) => String(row.id)}
                    paginate="client"
                    initialPageSize={10}
                    pageSizeOptions={PAGINATION.TABLE_PAGE_SIZE_OPTIONS}
                    isLoading={auditLoading}
                    loadingMessage="Loading logs…"
                    emptyMessage="No audit logs found."
                    noResultsMessage="No audit logs match the current filters."
                    unfilteredCount={auditLogs.length}
                    onRowClick={openAuditTraceDetail}
                    maxHeight="60vh"
                    tableContainerProps={{ overflowX: "auto" }}
                    filterToolbarRightContent={
                      <Button size="sm" variant="outline" onClick={() => void fetchAuditLogs()}>
                        Refresh
                      </Button>
                    }
                    filters={
                      <>
                        <TableSearchField
                          label="Search"
                          value={auditSearch}
                          onChange={setAuditSearch}
                          placeholder="Search trace / tenant / domain / target…"
                          formControlProps={{ w: { base: "full", md: "360px" } }}
                        />
                        <TableSelectField
                          label="Domain"
                          value={auditDomainFilter}
                          onChange={setAuditDomainFilter}
                        >
                          <option value="all">All domains</option>
                          {auditDomainOptions.map((id) => (
                            <option key={id} value={id}>
                              {id}
                            </option>
                          ))}
                        </TableSelectField>
                        <TableSelectField
                          label="Tenant"
                          value={auditTenantFilter}
                          onChange={setAuditTenantFilter}
                        >
                          <option value="all">All tenants</option>
                          {auditTenantOptions.map((id) => (
                            <option key={id} value={id}>
                              {id}
                            </option>
                          ))}
                        </TableSelectField>
                      </>
                    }
                    hasActiveFilters={auditHasActiveFilters}
                    onClearFilters={() => {
                      setAuditSearch("");
                      setAuditDomainFilter("all");
                      setAuditTenantFilter("all");
                    }}
                  />
                </CardBody>
              </Card>
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>

      <PiiDomainDetailModal
        isOpen={domainDetail.isOpen}
        onClose={closeDomainDetail}
        domain={viewDomain}
        isPendingActivation={viewDomain ? checkedDomains.has(viewDomain.domain_id) : false}
        onEditRules={(id) => {
          closeDomainDetail();
          void loadDomainConfig(id);
        }}
      />

      <PiiRuleDetailModal
        isOpen={ruleDetail.isOpen}
        onClose={closeRuleDetail}
        rule={viewRule}
        editingDomainId={editingDomainId}
        onRemove={(rule) => {
          removeRuleForRow(rule);
          closeRuleDetail();
        }}
      />

      <PiiMappingDetailModal
        isOpen={mappingDetail.isOpen}
        onClose={closeMappingDetail}
        mapping={viewMapping}
        onRemove={(tenantId) => void handleDeleteTenantMapping(tenantId, closeMappingDetail)}
      />

      <StandardModal
        isOpen={auditTraceDetail.isOpen}
        onClose={closeAuditTraceDetail}
        title="Audit trace"
        size="4xl"
        footer={
          <HStack justify="flex-end" w="full">
            <Button variant="ghost" onClick={closeAuditTraceDetail}>
              Close
            </Button>
          </HStack>
        }
      >
        <FormControl>
          <FormLabel fontSize="sm">Trace JSON</FormLabel>
          <Textarea value={auditDetailJson} readOnly fontFamily="mono" fontSize="xs" rows={18} />
        </FormControl>
      </StandardModal>
    </Box>
  );
}

function PiiDomainDetailModal({
  isOpen,
  onClose,
  domain,
  isPendingActivation,
  onEditRules,
}: {
  isOpen: boolean;
  onClose: () => void;
  domain: Domain | null;
  isPendingActivation: boolean;
  onEditRules: (domainId: string) => void;
}) {
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Domain details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {domain ? (
            <Button
              colorScheme="blue"
              onClick={() => {
                onEditRules(domain.domain_id);
              }}
            >
              Edit policy rules
            </Button>
          ) : null}
        </HStack>
      }
    >
      {domain ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {domain.domain_id}
          </Text>
          <Heading size="md">{domain.domain_id.toUpperCase()}</Heading>
          <HStack spacing={2}>
            <Badge colorScheme={domain.is_active ? "green" : "gray"}>
              {domain.is_active ? "Active" : "Inactive"}
            </Badge>
            <Badge colorScheme={isPendingActivation ? "blue" : "purple"}>
              {isPendingActivation ? "Selected for activation" : "Not in activation set"}
            </Badge>
          </HStack>
          {domain.description ? (
            <Text fontSize="sm" color="gray.700">
              {domain.description}
            </Text>
          ) : (
            <Text fontSize="sm" color="gray.500">
              No description
            </Text>
          )}
        </Stack>
      ) : null}
    </StandardModal>
  );
}

function PiiRuleDetailModal({
  isOpen,
  onClose,
  rule,
  editingDomainId,
  onRemove,
}: {
  isOpen: boolean;
  onClose: () => void;
  rule: Rule | null;
  editingDomainId: string | null;
  onRemove: (rule: Rule) => void;
}) {
  const configStr = rule ? JSON.stringify(rule.config ?? {}, null, 2) : "";
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Rule details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {rule ? (
            <Button
              colorScheme="red"
              variant="outline"
              onClick={() => {
                onRemove(rule);
              }}
            >
              Remove rule
            </Button>
          ) : null}
        </HStack>
      }
    >
      {rule ? (
        <Stack spacing={4}>
          <Text fontSize="sm" color="gray.600">
            Domain: {editingDomainId ?? "—"}
          </Text>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Entity type
            </Text>
            <Text fontSize="sm">{rule.entity_type}</Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Action
            </Text>
            <Badge colorScheme={actionBadgeColorScheme(rule.action)}>{rule.action}</Badge>
          </Box>
          {rule.custom_regex ? (
            <FormControl>
              <FormLabel fontSize="sm">Custom regex</FormLabel>
              <Textarea readOnly fontFamily="mono" fontSize="sm" value={rule.custom_regex} rows={3} />
            </FormControl>
          ) : null}
          <FormControl>
            <FormLabel fontSize="sm">Config</FormLabel>
            <Textarea readOnly fontFamily="mono" fontSize="xs" value={configStr} rows={6} />
          </FormControl>
        </Stack>
      ) : null}
    </StandardModal>
  );
}

function PiiMappingDetailModal({
  isOpen,
  onClose,
  mapping,
  onRemove,
}: {
  isOpen: boolean;
  onClose: () => void;
  mapping: TenantDomainMappingRow | null;
  onRemove: (tenantId: string) => void;
}) {
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Tenant mapping details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {mapping ? (
            <Button
              colorScheme="red"
              variant="outline"
              onClick={() => {
                onRemove(mapping.tenant_id);
              }}
            >
              Remove mapping
            </Button>
          ) : null}
        </HStack>
      }
    >
      {mapping ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {mapping.tenant_id}
          </Text>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Tenant ID
            </Text>
            <Text fontSize="sm" fontFamily="mono">
              {mapping.tenant_id}
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Domain
            </Text>
            <Text fontSize="sm">{mapping.domain_id}</Text>
          </Box>
          <Text fontSize="sm" color="gray.600">
            Updated {mapping.updated_at ? new Date(mapping.updated_at).toLocaleString() : "—"}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
  );
}
