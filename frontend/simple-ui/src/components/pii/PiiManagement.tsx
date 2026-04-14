import React, { useEffect, useState } from "react";
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
  Flex,
  FormControl,
  FormLabel,
  GridItem,
  Heading,
  HStack,
  IconButton,
  Input,
  InputGroup,
  InputLeftElement,
  Select,
  SimpleGrid,
  Spinner,
  Stack,
  Tab,
  Table,
  TableContainer,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Tbody,
  Td,
  Text,
  Textarea,
  Th,
  Thead,
  Tooltip,
  Tr,
  useColorModeValue,
  useDisclosure,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { DeleteIcon, EditIcon, SearchIcon } from "@chakra-ui/icons";
import { piiService } from "../../services/piiService";
import {
  TableFilterToolbar,
  TablePaginationBar,
  TableSortHeader,
  useAdminTableSurface,
} from "../common/TableControls";
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
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
  const toast = useToast();
  const { tableBg, tableHeaderBg, tableRowHoverBg, cardBg, borderColor } = useAdminTableSurface();
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
  const [newAction, setNewAction] = useState("REDACT_TAG");
  const [newExample, setNewExample] = useState("");
  const [newRegex, setNewRegex] = useState("");
  const [adminDataError, setAdminDataError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogRow[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [rulesSortDirection, setRulesSortDirection] = useState<"asc" | "desc">("asc");
  const [rulesPage, setRulesPage] = useState(1);
  const [rulesPageSize, setRulesPageSize] = useState(10);
  const [mappingSearch, setMappingSearch] = useState("");
  const [mappingSortDirection, setMappingSortDirection] = useState<"asc" | "desc">("asc");
  const [mappingPage, setMappingPage] = useState(1);
  const [mappingPageSize, setMappingPageSize] = useState(10);
  const [auditSearch, setAuditSearch] = useState("");
  const [auditSortDirection, setAuditSortDirection] = useState<"asc" | "desc">("desc");
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(10);

  useEffect(() => {
    if (!isAdmin || activeTab !== "audit") return;
    void fetchAuditLogs();
  }, [isAdmin, activeTab]);

  useEffect(() => {
    if (!isAdmin || activeTab !== "admin") return;
    void refreshAdminDataWithRetry();
  }, [isAdmin, activeTab]);

  const fetchAllDomains = async () => {
    const res = await piiService.getAllDomains();
    setAllDomains(res.data);
    const active = new Set(res.data.filter((d: Domain) => d.is_active).map((d: Domain) => d.domain_id));
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
      toast({
        title: "Domain activation updated",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      await fetchAllDomains();
    } catch {
      toast({
        title: "Failed to apply domains",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
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
    } catch (e) {
      console.error("Admin data fetch failed, retrying once...", e);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
    try {
      await Promise.all([fetchAllDomains(), fetchTenantMappings()]);
    } catch (e) {
      console.error("Admin data fetch failed after retry", e);
      setAdminDataError("Could not load domains/mappings. Please click Refresh.");
    }
  };

  const handleSaveTenantMapping = async () => {
    const tid = newMapTenantId.trim();
    if (!tid || !newMapDomainId) {
      toast({
        title: "Enter tenant ID and choose a domain",
        status: "warning",
        duration: 4000,
        isClosable: true,
      });
      return;
    }
    try {
      await piiService.upsertTenantDomainMapping(tid, newMapDomainId);
      setNewMapTenantId("");
      await fetchTenantMappings();
      toast({
        title: "Mapping saved",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch {
      toast({
        title: "Failed to save mapping (check domain exists and permissions)",
        status: "error",
        duration: 5000,
        isClosable: true,
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
      toast({
        title: "Failed to delete mapping",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleCreateDomain = async () => {
    if (!newDomainId) return;
    try {
      await piiService.createDomain(newDomainId);
      setNewDomainId("");
      await fetchAllDomains();
      toast({
        title: "Domain created",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch {
      toast({
        title: "Failed to create domain",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const loadDomainConfig = async (id: string) => {
    setEditingDomainId(id);
    try {
      const res = await piiService.getPolicy(id);
      const rules = Array.isArray(res.data.rules) ? (res.data.rules as Rule[]) : [];
      setEditingRules(rules);
    } catch {
      toast({
        title: "Failed to load policy",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const generateRegex = async () => {
    try {
      const res = await piiService.generateRegex(newExample);
      setNewRegex(res.data.regex);
    } catch {
      toast({
        title: "Regex generation failed",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const addCustomRule = () => {
    if (!newEntity) {
      toast({
        title: "Entity name required",
        status: "warning",
        duration: 4000,
        isClosable: true,
      });
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
      toast({
        title: "Select a domain to edit",
        status: "warning",
        duration: 4000,
        isClosable: true,
      });
      return;
    }
    try {
      await piiService.deployRules(editingDomainId, editingRules);
      toast({
        title: "Policy rules saved",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      await fetchAllDomains();
    } catch {
      toast({
        title: "Save failed",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const fetchAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const res = await piiService.getAuditLogs(100);
      setAuditLogs(res.data);
    } catch {
      toast({
        title: "Failed to load audit logs",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setAuditLoading(false);
    }
  };

  /** Remove by object identity — matches row in sorted/paginated view to `editingRules`. */
  const removeRuleForRow = (rule: Rule) => {
    setEditingRules((prev) => prev.filter((x) => x !== rule));
  };

  const activeDomainCount = allDomains.filter((d) => d.is_active).length;

  const sortedRules = [...editingRules].sort((a, b) => {
    const nameCmp = (a.entity_type ?? "").localeCompare(b.entity_type ?? "", undefined, {
      sensitivity: "base",
    });
    return rulesSortDirection === "asc" ? nameCmp : -nameCmp;
  });
  const rulesTotal = sortedRules.length;
  const rulesTotalPages = Math.max(1, Math.ceil(rulesTotal / rulesPageSize));
  const rulesStartRow = rulesTotal === 0 ? 0 : (rulesPage - 1) * rulesPageSize + 1;
  const rulesEndRow = Math.min(rulesPage * rulesPageSize, rulesTotal);
  const paginatedRules = sortedRules.slice((rulesPage - 1) * rulesPageSize, rulesPage * rulesPageSize);

  const filteredMappings = tenantMappings.filter((row) => {
    const q = mappingSearch.trim().toLowerCase();
    if (!q) return true;
    return (
      (row.tenant_id ?? "").toLowerCase().includes(q) || (row.domain_id ?? "").toLowerCase().includes(q)
    );
  });
  const sortedMappings = [...filteredMappings].sort((a, b) => {
    const nameCmp = (a.tenant_id ?? "").localeCompare(b.tenant_id ?? "", undefined, {
      sensitivity: "base",
    });
    return mappingSortDirection === "asc" ? nameCmp : -nameCmp;
  });
  const mappingsTotal = sortedMappings.length;
  const mappingsTotalPages = Math.max(1, Math.ceil(mappingsTotal / mappingPageSize));
  const mappingsStartRow = mappingsTotal === 0 ? 0 : (mappingPage - 1) * mappingPageSize + 1;
  const mappingsEndRow = Math.min(mappingPage * mappingPageSize, mappingsTotal);
  const paginatedMappings = sortedMappings.slice(
    (mappingPage - 1) * mappingPageSize,
    mappingPage * mappingPageSize
  );

  const filteredAuditLogs = auditLogs.filter((row) => {
    const q = auditSearch.trim().toLowerCase();
    if (!q) return true;
    return (
      (row.trace_id ?? "").toLowerCase().includes(q) ||
      (row.tenant_id ?? "").toLowerCase().includes(q) ||
      (row.domain_id ?? "").toLowerCase().includes(q) ||
      (row.target_context ?? "").toLowerCase().includes(q)
    );
  });
  const sortedAuditLogs = [...filteredAuditLogs].sort((a, b) => {
    const timeA = a.created_at ? new Date(a.created_at).getTime() : -Infinity;
    const timeB = b.created_at ? new Date(b.created_at).getTime() : -Infinity;
    return auditSortDirection === "asc" ? timeA - timeB : timeB - timeA;
  });
  const auditTotal = sortedAuditLogs.length;
  const auditTotalPages = Math.max(1, Math.ceil(auditTotal / auditPageSize));
  const auditStartRow = auditTotal === 0 ? 0 : (auditPage - 1) * auditPageSize + 1;
  const auditEndRow = Math.min(auditPage * auditPageSize, auditTotal);
  const paginatedAuditLogs = sortedAuditLogs.slice(
    (auditPage - 1) * auditPageSize,
    auditPage * auditPageSize
  );

  useEffect(() => {
    if (rulesPage > rulesTotalPages) setRulesPage(rulesTotalPages);
  }, [rulesPage, rulesTotalPages]);

  useEffect(() => {
    if (mappingPage > mappingsTotalPages) setMappingPage(mappingsTotalPages);
  }, [mappingPage, mappingsTotalPages]);

  useEffect(() => {
    if (auditPage > auditTotalPages) setAuditPage(auditTotalPages);
  }, [auditPage, auditTotalPages]);

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

                    <TableContainer flex="1" maxH="280px" overflowY="auto" mb={4} borderWidth="1px" borderRadius="md" borderColor={borderColor}>
                      <Table variant="simple" bg={tableBg} size="sm" w="100%">
                        <Thead bg={tableHeaderBg}>
                          <Tr>
                            <Th>
                              <TableSortHeader
                                label="Entity"
                                direction={rulesSortDirection}
                                onAsc={() => {
                                  setRulesSortDirection("asc");
                                  setRulesPage(1);
                                }}
                                onDesc={() => {
                                  setRulesSortDirection("desc");
                                  setRulesPage(1);
                                }}
                                ascAriaLabel="Sort rules by entity ascending"
                                descAriaLabel="Sort rules by entity descending"
                              />
                            </Th>
                            <Th>Action</Th>
                            <Th textAlign="right">Delete</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {paginatedRules.map((r) => (
                            <Tr
                              key={`${r.entity_type}-${r.action}-${r.custom_regex ?? ""}`}
                              cursor="pointer"
                              _hover={{ bg: tableRowHoverBg }}
                              onClick={() => openRuleDetail(r)}
                            >
                              <Td fontWeight="bold">{r.entity_type}</Td>
                              <Td>
                                <Badge colorScheme={actionBadgeColorScheme(r.action)} fontSize="xs">
                                  {r.action}
                                </Badge>
                              </Td>
                              <Td textAlign="right" onClick={(e) => e.stopPropagation()}>
                                <Tooltip label="Remove rule" hasArrow>
                                  <IconButton
                                    aria-label="Remove rule"
                                    icon={<DeleteIcon />}
                                    size="sm"
                                    variant="ghost"
                                    colorScheme="red"
                                    _hover={{ bg: "red.50" }}
                                    onClick={() => removeRuleForRow(r)}
                                  />
                                </Tooltip>
                              </Td>
                            </Tr>
                          ))}
                          {rulesTotal === 0 ? (
                            <Tr>
                              <Td colSpan={3} textAlign="center" color={mutedText} py={6}>
                                No rules configured for this domain.
                              </Td>
                            </Tr>
                          ) : null}
                        </Tbody>
                      </Table>
                    </TableContainer>

                    {rulesTotal > 0 ? (
                      <TablePaginationBar
                        startRow={rulesStartRow}
                        endRow={rulesEndRow}
                        totalItems={rulesTotal}
                        page={rulesPage}
                        totalPages={rulesTotalPages}
                        pageSize={rulesPageSize}
                        pageSizeOptions={PAGE_SIZE_OPTIONS}
                        onPageSizeChange={(value) => {
                          setRulesPageSize(value);
                          setRulesPage(1);
                        }}
                        onFirst={() => setRulesPage(1)}
                        onPrev={() => setRulesPage((p) => Math.max(1, p - 1))}
                        onNext={() => setRulesPage((p) => Math.min(rulesTotalPages, p + 1))}
                        onLast={() => setRulesPage(rulesTotalPages)}
                        canPrev={rulesPage > 1}
                        canNext={rulesPage < rulesTotalPages}
                        borderColor={borderColor}
                        bg={cardBg}
                      />
                    ) : null}

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
                          <Select size="sm" value={newAction} onChange={(e) => setNewAction(e.target.value)} bg={cardBg}>
                            <option>REDACT_TAG</option>
                            <option>MASK</option>
                            <option>HASH</option>
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
                    <TableFilterToolbar
                      hasActiveFilters={!!mappingSearch.trim()}
                      onClear={() => {
                        setMappingSearch("");
                        setMappingPage(1);
                      }}
                    >
                      <InputGroup size="sm" maxW="280px">
                        <InputLeftElement pointerEvents="none">
                          <SearchIcon color="gray.400" />
                        </InputLeftElement>
                        <Input
                          pl={9}
                          placeholder="Search tenant or domain…"
                          value={mappingSearch}
                          onChange={(e) => {
                            setMappingSearch(e.target.value);
                            setMappingPage(1);
                          }}
                          bg={cardBg}
                        />
                      </InputGroup>
                    </TableFilterToolbar>
                    <TableContainer maxH="50vh" overflowY="auto" mt={3}>
                      <Table variant="simple" bg={tableBg} size="sm" w="100%">
                        <Thead bg={tableHeaderBg}>
                          <Tr>
                            <Th>
                              <TableSortHeader
                                label="Tenant ID"
                                direction={mappingSortDirection}
                                onAsc={() => {
                                  setMappingSortDirection("asc");
                                  setMappingPage(1);
                                }}
                                onDesc={() => {
                                  setMappingSortDirection("desc");
                                  setMappingPage(1);
                                }}
                                ascAriaLabel="Sort mappings by tenant ascending"
                                descAriaLabel="Sort mappings by tenant descending"
                              />
                            </Th>
                            <Th>Domain</Th>
                            <Th>Updated</Th>
                            <Th textAlign="right">Actions</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {mappingsTotal === 0 ? (
                            <Tr>
                              <Td colSpan={4} textAlign="center" color={mutedText} py={6}>
                                No mappings configured.
                              </Td>
                            </Tr>
                          ) : (
                            paginatedMappings.map((row) => (
                              <Tr
                                key={row.tenant_id}
                                cursor="pointer"
                                _hover={{ bg: tableRowHoverBg }}
                                onClick={() => openMappingDetail(row)}
                              >
                                <Td fontFamily="mono" fontSize="xs">
                                  {row.tenant_id}
                                </Td>
                                <Td fontWeight="semibold">{row.domain_id}</Td>
                                <Td fontSize="xs" color={mutedText}>
                                  {row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}
                                </Td>
                                <Td textAlign="right" onClick={(e) => e.stopPropagation()}>
                                  <Tooltip label="Remove mapping" hasArrow>
                                    <IconButton
                                      aria-label="Remove mapping"
                                      icon={<DeleteIcon />}
                                      size="sm"
                                      variant="ghost"
                                      colorScheme="red"
                                      _hover={{ bg: "red.50" }}
                                      onClick={() => void handleDeleteTenantMapping(row.tenant_id)}
                                    />
                                  </Tooltip>
                                </Td>
                              </Tr>
                            ))
                          )}
                        </Tbody>
                      </Table>
                    </TableContainer>
                    {mappingsTotal > 0 ? (
                      <TablePaginationBar
                        startRow={mappingsStartRow}
                        endRow={mappingsEndRow}
                        totalItems={mappingsTotal}
                        page={mappingPage}
                        totalPages={mappingsTotalPages}
                        pageSize={mappingPageSize}
                        pageSizeOptions={PAGE_SIZE_OPTIONS}
                        onPageSizeChange={(value) => {
                          setMappingPageSize(value);
                          setMappingPage(1);
                        }}
                        onFirst={() => setMappingPage(1)}
                        onPrev={() => setMappingPage((p) => Math.max(1, p - 1))}
                        onNext={() => setMappingPage((p) => Math.min(mappingsTotalPages, p + 1))}
                        onLast={() => setMappingPage(mappingsTotalPages)}
                        canPrev={mappingPage > 1}
                        canNext={mappingPage < mappingsTotalPages}
                        borderColor={borderColor}
                        bg={cardBg}
                      />
                    ) : null}
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
                  <TableFilterToolbar
                    hasActiveFilters={!!auditSearch.trim()}
                    onClear={() => {
                      setAuditSearch("");
                      setAuditPage(1);
                    }}
                    rightContent={
                      <Button size="sm" variant="outline" onClick={() => void fetchAuditLogs()}>
                        Refresh
                      </Button>
                    }
                  >
                    <InputGroup size="sm" maxW="300px">
                      <InputLeftElement pointerEvents="none">
                        <SearchIcon color="gray.400" />
                      </InputLeftElement>
                      <Input
                        pl={9}
                        placeholder="Search trace / tenant / domain / target…"
                        value={auditSearch}
                        onChange={(e) => {
                          setAuditSearch(e.target.value);
                          setAuditPage(1);
                        }}
                        bg={cardBg}
                      />
                    </InputGroup>
                  </TableFilterToolbar>
                  <TableContainer maxH="60vh" overflowY="auto" overflowX="auto" mt={3}>
                    <Table variant="simple" bg={tableBg} size="sm" w="100%">
                      <Thead bg={tableHeaderBg}>
                        <Tr>
                          <Th>
                            <TableSortHeader
                              label="Time"
                              direction={auditSortDirection}
                              onAsc={() => {
                                setAuditSortDirection("asc");
                                setAuditPage(1);
                              }}
                              onDesc={() => {
                                setAuditSortDirection("desc");
                                setAuditPage(1);
                              }}
                              ascAriaLabel="Sort audit logs by time ascending"
                              descAriaLabel="Sort audit logs by time descending"
                            />
                          </Th>
                          <Th>Trace ID</Th>
                          <Th>Tenant</Th>
                          <Th>Domain</Th>
                          <Th>Target</Th>
                          <Th isNumeric>PII Count</Th>
                          <Th isNumeric>Latency</Th>
                        </Tr>
                      </Thead>
                      <Tbody>
                        {auditLoading ? (
                          <Tr>
                            <Td colSpan={7} textAlign="center" py={8}>
                              <Spinner mr={2} />
                              <Text as="span" color={mutedText}>
                                Loading logs…
                              </Text>
                            </Td>
                          </Tr>
                        ) : auditTotal === 0 ? (
                          <Tr>
                            <Td colSpan={7} textAlign="center" color={mutedText} py={6}>
                              No audit logs found.
                            </Td>
                          </Tr>
                        ) : (
                          paginatedAuditLogs.map((row) => (
                            <Tr
                              key={row.id}
                              cursor="pointer"
                              _hover={{ bg: tableRowHoverBg }}
                              onClick={() => openAuditTraceDetail(row)}
                            >
                              <Td fontSize="xs" color={mutedText} whiteSpace="nowrap">
                                {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                              </Td>
                              <Td fontFamily="mono" fontSize="xs">
                                {row.trace_id || "—"}
                              </Td>
                              <Td fontFamily="mono" fontSize="xs">
                                {row.tenant_id || "—"}
                              </Td>
                              <Td>{row.domain_id || "—"}</Td>
                              <Td maxW="200px" isTruncated title={row.target_context || ""}>
                                {row.target_context || "—"}
                              </Td>
                              <Td isNumeric>{row.pii_count ?? 0}</Td>
                              <Td isNumeric>{row.processing_ms ?? 0} ms</Td>
                            </Tr>
                          ))
                        )}
                      </Tbody>
                    </Table>
                  </TableContainer>
                  {!auditLoading && auditTotal > 0 ? (
                    <TablePaginationBar
                      startRow={auditStartRow}
                      endRow={auditEndRow}
                      totalItems={auditTotal}
                      page={auditPage}
                      totalPages={auditTotalPages}
                      pageSize={auditPageSize}
                      pageSizeOptions={PAGE_SIZE_OPTIONS}
                      onPageSizeChange={(value) => {
                        setAuditPageSize(value);
                        setAuditPage(1);
                      }}
                      onFirst={() => setAuditPage(1)}
                      onPrev={() => setAuditPage((p) => Math.max(1, p - 1))}
                      onNext={() => setAuditPage((p) => Math.min(auditTotalPages, p + 1))}
                      onLast={() => setAuditPage(auditTotalPages)}
                      canPrev={auditPage > 1}
                      canNext={auditPage < auditTotalPages}
                      borderColor={borderColor}
                      bg={cardBg}
                    />
                  ) : null}
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
