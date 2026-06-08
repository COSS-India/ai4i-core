import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  IconButton,
  Text,
  Tooltip,
  useColorModeValue,
  useDisclosure,
  useToast,
} from "@chakra-ui/react";
import { DeleteIcon } from "@chakra-ui/icons";
import { piiService } from "../../../services/piiService";
import { useAdminTableSurface } from "../../common/TableControls";
import { type AdminTableColumn } from "../../common/AdminDataTable";
import { actionBadgeColorScheme } from "../utils";
import type { AuditLogRow, Domain, PageTab, Rule, TenantDomainMappingRow } from "../types";

export function usePiiManagement(isAdmin: boolean) {
  const toast = useToast();
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
    void refreshAdminDataWithRetry();
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
    if (!newAction) {
      toast({
        title: "Action required",
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

  return {
    toast, tableRowHoverBg, cardBg, borderColor, pageBg, mutedText, headingColor, readOnlyInputBg,
    domainDetail, ruleDetail, mappingDetail, auditTraceDetail,
    viewDomain, viewRule, viewMapping, auditDetailJson,
    activeTab, setActiveTab, tabIndex,
    allDomains, checkedDomains, newDomainId, setNewDomainId, editingDomainId, editingRules,
    tenantMappings, newMapTenantId, setNewMapTenantId, newMapDomainId, setNewMapDomainId,
    newEntity, setNewEntity, newAction, setNewAction, newExample, setNewExample, newRegex, setNewRegex,
    adminDataError, auditLogs, auditLoading,
    rulesSortDirection, setRulesSortDirection,
    mappingSearch, setMappingSearch, mappingDomainFilter, setMappingDomainFilter, mappingSortDirection, setMappingSortDirection,
    auditSearch, setAuditSearch, auditDomainFilter, setAuditDomainFilter, auditTenantFilter, setAuditTenantFilter, auditSortDirection, setAuditSortDirection,
    handleToggleDomainActivate, applyActiveDomains, refreshAdminDataWithRetry,
    handleSaveTenantMapping, handleDeleteTenantMapping, handleCreateDomain, loadDomainConfig,
    generateRegex, addCustomRule, saveConfig, fetchAuditLogs, removeRuleForRow,
    activeDomainCount, sortedRules, sortedMappings, sortedAuditLogs,
    mappingHasActiveFilters, auditHasActiveFilters, auditDomainOptions, auditTenantOptions,
    rulesColumns, mappingColumns, auditColumns,
    openDomainDetail, closeDomainDetail, openRuleDetail, closeRuleDetail,
    openMappingDetail, closeMappingDetail, openAuditTraceDetail, closeAuditTraceDetail,
  };
}

export type UsePiiManagementReturn = ReturnType<typeof usePiiManagement>;
