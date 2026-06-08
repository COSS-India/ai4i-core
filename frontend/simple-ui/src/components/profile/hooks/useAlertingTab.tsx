import React, { useRef, useEffect, useState } from "react";
import {
  Badge,
  HStack,
  IconButton,
  Switch,
  Text,
  Tooltip,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { isTenantStatus, TENANT } from "../../../config/constants";
import * as tenantService from "../../../services/tenantService";
import type { TenantView } from "../../../types/tenant";
import type { AlertDefinition, AlertHistoryItem, NotificationReceiver } from "../../../types/alerting";
import { useAlertDefinitions } from "./useAlertDefinitions";
import { useNotificationReceivers } from "./useNotificationReceivers";
import { useRoutingRules } from "./useRoutingRules";
import { useAlertHistory } from "./useAlertHistory";
import { useAdminTableSurface } from "../../common/TableControls";
import { type AdminTableColumn } from "../../common/AdminDataTable";
import { expandServices, extractServicesFromPromql, normalizeServiceValue } from "../alerting/utils";
import {
  alertTypeLabel,
  categoryColor,
  formatThreshold,
  severityColor,
  titleCase,
} from "../alerting/displayHelpers";

export interface UseAlertingTabOptions {
  isActive?: boolean;
}

export function useAlertingTab({ isActive = false }: UseAlertingTabOptions = {}) {
  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();
  const [subTabIndex, setSubTabIndex] = useState(0);
  const [createRuleDef, setCreateRuleDef] = useState("");

  // Create Routing Rule — extended form state
  const [createRuleScope, setCreateRuleScope] = useState<"" | "global" | "specific_tenant">("");
  const [createRuleTenant, setCreateRuleTenant] = useState("");
  const [createRuleErrors, setCreateRuleErrors] = useState<Record<string, string>>({});
  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);

  // Edit Routing Rule — extended form state (UI-only fields not in update API)
  const [editRuleCategory, setEditRuleCategory] = useState("");
  const [editRuleSeverity, setEditRuleSeverity] = useState("");
  const [editRuleDef, setEditRuleDef] = useState("");
  const [editRuleScope, setEditRuleScope] = useState<"global" | "specific_tenant">("global");
  const [editRuleErrors, setEditRuleErrors] = useState<Record<string, string>>({});

  const resetCreateRuleExtras = () => {
    setCreateRuleScope("");
    setCreateRuleTenant("");
    setCreateRuleErrors({});
    setCreateRuleDef("");
  };

  const resetEditRuleExtras = () => {
    setEditRuleCategory("");
    setEditRuleSeverity("");
    setEditRuleDef("");
    setEditRuleScope("global");
    setEditRuleErrors({});
  };

  const initEditRuleExtras = (item: NotificationReceiver) => {
    // Prefer direct category/severity from the receiver (backend may return them)
    const cat = item.category ?? null;
    const sev = item.severity ?? null;

    // Also try to resolve from the linked alert definition (alert_names[0])
    const firstName = item.alert_names?.[0];
    const linkedDef = firstName ? defs.definitions.find((d) => d.name === firstName) : null;

    const resolvedCat = cat ?? linkedDef?.category ?? "";
    setEditRuleCategory(resolvedCat);
    setEditRuleSeverity(sev ?? linkedDef?.severity ?? "");
    setEditRuleDef(linkedDef ? String(linkedDef.id) : "");
    setEditRuleScope(resolvedCat === "infrastructure" ? "global" : item.tenant ? "specific_tenant" : "global");
  };

  const fetchTenants = async () => {
    if (tenants.length > 0) return;
    setIsLoadingTenants(true);
    try {
      const res = await tenantService.listTenants();
      setTenants(
        (res.tenants || []).filter((t) => isTenantStatus(t.status, TENANT.STATUS.ACTIVE))
      );
    } catch {
      // ignore
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const validateAndCreate = async () => {
    const errors: Record<string, string> = {};
    const isInfrastructure = rules.createForm.category === "infrastructure";
    if (!rules.createForm.rule_name.trim()) errors.ruleName = "Rule name is required.";
    if (!rules.createForm.category) errors.category = "Please select a category.";
    if (!rules.createForm.severity) errors.severity = "Please select a severity.";
    if (!isInfrastructure && !createRuleScope) errors.scope = "Please select a scope.";
    if (!isInfrastructure && createRuleScope === "specific_tenant" && !createRuleTenant) {
      errors.tenant = "Please select a target tenant.";
    }
    setCreateRuleErrors(errors);
    if (Object.keys(errors).length > 0) return;
    const tenantName =
      isInfrastructure
        ? null
        : createRuleScope === "specific_tenant" && createRuleTenant
          ? tenants.find((t) => t.tenant_id === createRuleTenant)?.organisation ?? createRuleTenant
          : null;
    await rules.handleCreate({
      tenant: tenantName,
      // Infra rules are org-wide: tenant null, notify global admins via RBAC ADMIN (no tenant-scoped delivery).
      ...(isInfrastructure ? { tenant: null, rbac_role: "ADMIN" as const, email_to: [] as string[] } : {}),
    });
    resetCreateRuleExtras();
  };

  const defs = useAlertDefinitions();
  const recvs = useNotificationReceivers();
  const rules = useRoutingRules();
  const history = useAlertHistory(isActive && subTabIndex === 2);
  const expandedUpdateServices = (() => {
    // If form state has been initialized (including explicit empty []), always honor it.
    if (defs.updateForm.service !== undefined) {
      const raw = Array.isArray(defs.updateForm.service) ? defs.updateForm.service : [];
      return expandServices(raw).map(normalizeServiceValue).filter(Boolean);
    }
    const fromForm = expandServices(defs.updateForm.service ?? []).map(normalizeServiceValue).filter(Boolean);
    if (fromForm.length > 0) return fromForm;
    const fromItem = (defs.updateItem?.service ?? []).map(normalizeServiceValue).filter(Boolean);
    if (fromItem.length > 0) return fromItem;
    const fromExpr = extractServicesFromPromql(defs.updateItem?.promql_expr).map(normalizeServiceValue).filter(Boolean);
    return fromExpr;
  })();

  const [definitionsNameSortDirection, setDefinitionsNameSortDirection] = useState<"asc" | "desc">("asc");
  const [receiversNameSortDirection, setReceiversNameSortDirection] = useState<"asc" | "desc">("asc");
  const [rulesNameSortDirection, setRulesNameSortDirection] = useState<"asc" | "desc">("asc");
  const [historyNameSortDirection, setHistoryNameSortDirection] = useState<"asc" | "desc">("asc");
  const [receiversSearchQuery, setReceiversSearchQuery] = useState("");

  const defDeleteRef = useRef<HTMLButtonElement>(null);
  const recvDeleteRef = useRef<HTMLButtonElement>(null);
  const ruleDeleteRef = useRef<HTMLButtonElement>(null);

  // Track the item id we last initialized so we don't overwrite user changes during the same open session
  const editRuleInitRef = useRef<number | null>(null);

  useEffect(() => {
    if (isActive) {
      defs.fetchDefinitions();
      recvs.fetchReceivers();
      rules.fetchRules();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive]);

  const sortedDefinitions = React.useMemo(() => {
    return [...defs.filteredDefinitions].sort((a, b) => {
      const aName = a.name ?? "";
      const bName = b.name ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return definitionsNameSortDirection === "asc" ? nameCmp : -nameCmp;

      // Tie-breaker: newest first
      const timeA = new Date(a.created_at).getTime();
      const timeB = new Date(b.created_at).getTime();
      return timeB - timeA;
    });
  }, [defs.filteredDefinitions, definitionsNameSortDirection]);

  const filteredReceiversWithSearch = React.useMemo(() => {
    const q = receiversSearchQuery.trim().toLowerCase();
    if (!q) return recvs.filteredReceivers;
    return recvs.filteredReceivers.filter((r) => {
      const name = (r.receiver_name ?? "").toLowerCase();
      const description = (r.description ?? "").toLowerCase();
      const role = (r.rbac_role ?? "").toLowerCase();
      const emails = (r.email_to ?? []).join(" ").toLowerCase();
      return name.includes(q) || description.includes(q) || role.includes(q) || emails.includes(q);
    });
  }, [recvs.filteredReceivers, receiversSearchQuery]);

  const sortedReceivers = React.useMemo(() => {
    return [...filteredReceiversWithSearch].sort((a, b) => {
      const aName = a.receiver_name ?? "";
      const bName = b.receiver_name ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return receiversNameSortDirection === "asc" ? nameCmp : -nameCmp;

      // Tie-breaker: newest first
      const timeA = new Date(a.created_at).getTime();
      const timeB = new Date(b.created_at).getTime();
      return timeB - timeA;
    });
  }, [filteredReceiversWithSearch, receiversNameSortDirection]);

  const sortedRules = React.useMemo(() => {
    return [...rules.filteredRules].sort((a, b) => {
      const aName = (a.rule_name ?? a.receiver_name ?? "") as string;
      const bName = (b.rule_name ?? b.receiver_name ?? "") as string;
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return rulesNameSortDirection === "asc" ? nameCmp : -nameCmp;

      // Tie-breaker: stable id
      return String(a.id).localeCompare(String(b.id), undefined, { sensitivity: "base" });
    });
  }, [rules.filteredRules, rulesNameSortDirection]);

  const activeAlertDefinitions = React.useMemo(
    () => defs.definitions.filter((d) => d.enabled),
    [defs.definitions]
  );

  const sortedHistoryItems = React.useMemo(() => {
    return [...history.items].sort((a, b) => {
      const aName = a.alert_name ?? "";
      const bName = b.alert_name ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return historyNameSortDirection === "asc" ? nameCmp : -nameCmp;
      const timeA = new Date(a.triggered_at ?? a.created_at ?? "").getTime();
      const timeB = new Date(b.triggered_at ?? b.created_at ?? "").getTime();
      return timeB - timeA;
    });
  }, [history.items, historyNameSortDirection]);

  // Re-initialize edit-rule category / severity / linked-def once definitions are available
  // (they may not be loaded yet when the drawer first opens — this effect fires again once they arrive)
  useEffect(() => {
    if (!rules.isUpdateOpen) {
      editRuleInitRef.current = null;
      return;
    }
    if (!rules.updateItem) return;
    // Only initialize once per open session for this item to avoid overwriting user changes
    if (editRuleInitRef.current === rules.updateItem.id) return;
    // Wait until definitions are actually populated
    if (defs.definitions.length === 0) return;

    editRuleInitRef.current = rules.updateItem.id;
    const item = rules.updateItem;
    const cat = item.category ?? null;
    const sev = item.severity ?? null;
    const firstName = item.alert_names?.[0];
    const linkedDef = firstName
      ? (defs.definitions.find((d) => d.name === firstName) ?? null)
      : null;
    const resolvedCat = cat ?? linkedDef?.category ?? "";
    const resolvedSev = sev ?? linkedDef?.severity ?? "";
    setEditRuleCategory(resolvedCat);
    setEditRuleSeverity(resolvedSev);
    setEditRuleDef(linkedDef ? String(linkedDef.id) : "");
    setEditRuleScope(resolvedCat === "infrastructure" ? "global" : item.tenant ? "specific_tenant" : "global");
    // Keep updateForm in sync so the resolved values are included in the save payload
    rules.setUpdateForm((prev) => ({
      ...prev,
      category: resolvedCat || null,
      severity: resolvedSev || null,
      ...(resolvedCat === "infrastructure" ? { tenant: null } : {}),
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rules.isUpdateOpen, rules.updateItem, defs.definitions]);

  const definitionColumns: AdminTableColumn<AlertDefinition>[] = [
    {
      id: "name",
      header: "Name",
      sortable: {
        label: "Name",
        direction: definitionsNameSortDirection,
        onAsc: () => setDefinitionsNameSortDirection("asc"),
        onDesc: () => setDefinitionsNameSortDirection("desc"),
        ascAriaLabel: "Sort definitions by name ascending",
        descAriaLabel: "Sort definitions by name descending",
      },
      cell: (d) => <Text fontWeight="semibold">{d.name}</Text>,
    },
    {
      id: "category",
      header: "Category",
      cell: (d) => (
        <Badge colorScheme={categoryColor(d.category)} textTransform="capitalize">
          {d.category}
        </Badge>
      ),
    },
    {
      id: "severity",
      header: "Severity",
      cell: (d) => (
        <Badge colorScheme={severityColor(d.severity)} textTransform="capitalize">
          {d.severity}
        </Badge>
      ),
    },
    {
      id: "sub_category",
      header: "Subcategory",
      cell: (d) => (
        <Text fontSize="sm">
          {d.sub_category ? titleCase(d.sub_category.replace(/_/g, " ")) : "—"}
        </Text>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (d) => (
        <Badge
          colorScheme={d.enabled ? "green" : "gray"}
          variant="subtle"
          fontSize="xs"
          px={2}
          py={0.5}
          borderRadius="full"
        >
          {d.enabled ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      id: "created",
      header: "Created",
      cell: (d) => <Text fontSize="sm">{new Date(d.created_at).toLocaleDateString()}</Text>,
    },
    {
      id: "actions",
      header: "Actions",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (d) => (
        <HStack spacing={1} className="row-actions">
          <Tooltip label="View" placement="top" hasArrow>
            <IconButton
              aria-label="View"
              icon={<ViewIcon />}
              size="sm"
              variant="ghost"
              color="gray.700"
              _hover={{ color: "blue.500", bg: "blue.50" }}
              onClick={() => defs.openView(d)}
            />
          </Tooltip>
          <Tooltip label="Edit" placement="top" hasArrow>
            <IconButton
              aria-label="Edit"
              icon={<EditIcon />}
              size="sm"
              variant="ghost"
              color="gray.700"
              _hover={{ color: "green.500", bg: "green.50" }}
              onClick={() => defs.openUpdate(d)}
            />
          </Tooltip>
          <Tooltip label="Delete" placement="top" hasArrow>
            <IconButton
              aria-label="Delete"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              color="gray.700"
              _hover={{ color: "red.500", bg: "red.50" }}
              onClick={() => defs.openDelete(d)}
            />
          </Tooltip>
        </HStack>
      ),
    },
  ];

  const receiverColumns: AdminTableColumn<NotificationReceiver>[] = [
    {
      id: "name",
      header: "Name",
      sortable: {
        label: "Name",
        direction: receiversNameSortDirection,
        onAsc: () => setReceiversNameSortDirection("asc"),
        onDesc: () => setReceiversNameSortDirection("desc"),
        ascAriaLabel: "Sort receivers by name ascending",
        descAriaLabel: "Sort receivers by name descending",
      },
      cell: (r) => <Text fontWeight="semibold" fontSize="sm">{r.receiver_name}</Text>,
    },
    {
      id: "recipient",
      header: "Recipient",
      cell: (r) =>
        r.rbac_role ? (
          <Badge colorScheme="purple">Role: {r.rbac_role}</Badge>
        ) : r.email_to && r.email_to.length > 0 ? (
          <Wrap spacing={1}>
            {r.email_to.slice(0, 2).map((e) => (
              <WrapItem key={e}>
                <Badge colorScheme="blue" fontSize="xs">{e}</Badge>
              </WrapItem>
            ))}
            {r.email_to.length > 2 && (
              <WrapItem>
                <Badge colorScheme="gray" fontSize="xs">+{r.email_to.length - 2}</Badge>
              </WrapItem>
            )}
          </Wrap>
        ) : (
          <Text fontSize="sm" color="gray.500">—</Text>
        ),
    },
    {
      id: "status",
      header: "Status",
      cell: (r) => <Switch size="sm" colorScheme="green" isChecked={r.enabled} isReadOnly />,
    },
    {
      id: "created",
      header: "Created",
      cell: (r) => <Text fontSize="sm">{new Date(r.created_at).toLocaleDateString()}</Text>,
    },
    {
      id: "actions",
      header: "Actions",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (r) => (
        <HStack spacing={1} className="row-actions">
          <Tooltip label="View" placement="top" hasArrow>
            <IconButton aria-label="View" icon={<ViewIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "blue.500", bg: "blue.50" }} onClick={() => recvs.openView(r)} />
          </Tooltip>
          <Tooltip label="Edit" placement="top" hasArrow>
            <IconButton aria-label="Edit" icon={<EditIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "green.500", bg: "green.50" }} onClick={() => recvs.openUpdate(r)} />
          </Tooltip>
          <Tooltip label="Delete" placement="top" hasArrow>
            <IconButton aria-label="Delete" icon={<DeleteIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "red.500", bg: "red.50" }} onClick={() => recvs.openDelete(r)} />
          </Tooltip>
        </HStack>
      ),
    },
  ];

  const routingRuleColumns: AdminTableColumn<NotificationReceiver>[] = [
    {
      id: "name",
      header: "Rule Name",
      sortable: {
        label: "Rule Name",
        direction: rulesNameSortDirection,
        onAsc: () => setRulesNameSortDirection("asc"),
        onDesc: () => setRulesNameSortDirection("desc"),
        ascAriaLabel: "Sort rules by name ascending",
        descAriaLabel: "Sort rules by name descending",
      },
      cell: (rule) => <Text fontWeight="semibold">{rule.rule_name ?? rule.receiver_name}</Text>,
    },
    {
      id: "definitions",
      header: "Alert Definitions",
      cell: (rule) =>
        rule.alert_names && rule.alert_names.length > 0 ? (
          <Text fontSize="sm" color="gray.700">
            {rule.alert_names.slice(0, 2).join(", ")}
            {rule.alert_names.length > 2 ? ` +${rule.alert_names.length - 2}` : ""}
          </Text>
        ) : (
          <Text fontSize="sm" color="gray.500">All</Text>
        ),
    },
    {
      id: "tenant",
      header: "Tenant",
      cell: (rule) =>
        rule.tenant ? (
          <Badge colorScheme="purple" variant="subtle" textTransform="none">{rule.tenant}</Badge>
        ) : (
          <Text fontSize="sm" color="gray.500">Global</Text>
        ),
    },
    {
      id: "status",
      header: "Status",
      cell: (rule) => (
        <Badge colorScheme={rule.enabled ? "green" : "gray"} variant="subtle" fontSize="xs" px={2} py={0.5} borderRadius="full">
          {rule.enabled ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (rule) => (
        <HStack spacing={1} className="row-actions">
          <Tooltip label="View" placement="top" hasArrow>
            <IconButton aria-label="View" icon={<ViewIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "blue.500", bg: "blue.50" }} onClick={() => { defs.fetchDefinitions(); rules.openView(rule); }} />
          </Tooltip>
          <Tooltip label="Edit" placement="top" hasArrow>
            <IconButton aria-label="Edit" icon={<EditIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "green.500", bg: "green.50" }} onClick={() => {
              defs.fetchDefinitions();
              fetchTenants();
              resetEditRuleExtras();
              initEditRuleExtras(rule);
              rules.openUpdate(rule);
            }} />
          </Tooltip>
          <Tooltip label="Delete" placement="top" hasArrow>
            <IconButton aria-label="Delete" icon={<DeleteIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "red.500", bg: "red.50" }} onClick={() => rules.openDelete(rule)} />
          </Tooltip>
        </HStack>
      ),
    },
  ];

  const historyColumns: AdminTableColumn<AlertHistoryItem>[] = [
    {
      id: "name",
      header: "Name",
      sortable: {
        label: "Name",
        direction: historyNameSortDirection,
        onAsc: () => setHistoryNameSortDirection("asc"),
        onDesc: () => setHistoryNameSortDirection("desc"),
        ascAriaLabel: "Sort alert history by name ascending",
        descAriaLabel: "Sort alert history by name descending",
      },
      cell: (row) => (
        <Text fontWeight="semibold" noOfLines={2} title={row.alert_name} maxW="260px">
          {row.alert_name}
        </Text>
      ),
    },
    {
      id: "category",
      header: "Category",
      cell: (row) => (
        <Badge colorScheme={categoryColor(row.category)} textTransform="capitalize">
          {row.category || "—"}
        </Badge>
      ),
    },
    {
      id: "severity",
      header: "Severity",
      cell: (row) => (
        <Badge colorScheme={severityColor(row.severity)} textTransform="capitalize">
          {row.severity || "—"}
        </Badge>
      ),
    },
    {
      id: "triggered",
      header: "Triggered At",
      cell: (row) => <Text fontSize="sm">{row.triggered_at ?? "—"}</Text>,
    },
    {
      id: "notified",
      header: "Notified",
      cell: (row) => (
        <Text fontSize="sm" noOfLines={2} title={row.notified_display ?? undefined} maxW="220px">
          {row.notified_display || "—"}
        </Text>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (row) => (
        <HStack spacing={1} className="row-actions">
          <Tooltip label="View" placement="top" hasArrow>
            <IconButton
              aria-label="View"
              icon={<ViewIcon />}
              size="sm"
              variant="ghost"
              color="gray.700"
              _hover={{ color: "blue.500", bg: "blue.50" }}
              onClick={() => history.openView(row)}
            />
          </Tooltip>
        </HStack>
      ),
    },
  ];

  return {
    cardBg,
    cardBorder,
    subTabIndex,
    setSubTabIndex,
    createRuleDef,
    setCreateRuleDef,
    createRuleScope,
    setCreateRuleScope,
    createRuleTenant,
    setCreateRuleTenant,
    createRuleErrors,
    setCreateRuleErrors,
    tenants,
    isLoadingTenants,
    editRuleCategory,
    setEditRuleCategory,
    editRuleSeverity,
    setEditRuleSeverity,
    editRuleDef,
    setEditRuleDef,
    editRuleScope,
    setEditRuleScope,
    editRuleErrors,
    setEditRuleErrors,
    resetCreateRuleExtras,
    resetEditRuleExtras,
    initEditRuleExtras,
    fetchTenants,
    validateAndCreate,
    defs,
    recvs,
    rules,
    history,
    expandedUpdateServices,
    definitionsNameSortDirection,
    setDefinitionsNameSortDirection,
    receiversNameSortDirection,
    setReceiversNameSortDirection,
    rulesNameSortDirection,
    setRulesNameSortDirection,
    historyNameSortDirection,
    setHistoryNameSortDirection,
    receiversSearchQuery,
    setReceiversSearchQuery,
    defDeleteRef,
    recvDeleteRef,
    ruleDeleteRef,
    sortedDefinitions,
    sortedReceivers,
    sortedRules,
    sortedHistoryItems,
    activeAlertDefinitions,
    severityColor,
    categoryColor,
    titleCase,
    alertTypeLabel,
    formatThreshold,
    definitionColumns,
    receiverColumns,
    routingRuleColumns,
    historyColumns,
  };
}

export type UseAlertingTabReturn = ReturnType<typeof useAlertingTab>;
