import React, { useRef, useEffect, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Heading,
  Input,
  Textarea,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Select,
  SimpleGrid,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  TableContainer,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  Drawer,
  DrawerOverlay,
  DrawerContent,
  DrawerCloseButton,
  DrawerHeader,
  DrawerBody,
  DrawerFooter,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  IconButton,
  Switch,
  Tag,
  TagLabel,
  TagCloseButton,
  Wrap,
  WrapItem,
  Checkbox,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  NumberIncrementStepper,
  NumberDecrementStepper,
  Divider,
  Tooltip,
  InputGroup,
  InputLeftElement,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  MenuDivider,
  Radio,
  RadioGroup,
  Stack,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, ViewIcon, EditIcon, SearchIcon, LockIcon } from "@chakra-ui/icons";
import * as multiTenantService from "../../services/multiTenantService";
import type { TenantView } from "../../types/multiTenant";
import type { NotificationReceiver } from "../../types/alerting";
import { useAlertDefinitions } from "./hooks/useAlertDefinitions";
import { useNotificationReceivers } from "./hooks/useNotificationReceivers";
import { useRoutingRules } from "./hooks/useRoutingRules";
import {
  CATEGORIES,
  SEVERITIES,
  URGENCIES,
  RBAC_ROLES,
  SUB_CATEGORIES_BY_CATEGORY,
  SIGNALS_BY_SUB_CATEGORY,
  SIGNAL_METRICS_BY_SIGNAL,
  TARGET_SERVICES,
  CONDITION_OPERATORS,
  LATENCY_THRESHOLD_UNITS,
  PERCENTAGE_UNIT,
} from "../../types/alerting";

const EVAL_INTERVALS = ["30s", "1m", "5m"] as const;
const FOR_DURATIONS = ["1m", "2m", "5m", "10m"] as const;

/** Allowed "For Duration" options per "Evaluation Interval" (for_duration should be >= eval interval). */
const FOR_DURATION_BY_EVAL_INTERVAL: Record<string, readonly string[]> = {
  "30s": ["1m", "2m", "5m"],
  "1m": ["2m", "5m", "10m"],
  "5m": ["5m", "10m"],
};

function getAllowedForDurations(evalInterval: string | null | undefined): string[] {
  const key = evalInterval ?? "30s";
  return [...(FOR_DURATION_BY_EVAL_INTERVAL[key] ?? FOR_DURATION_BY_EVAL_INTERVAL["30s"])];
}

const ALERT_TYPES_BY_CATEGORY: Record<string, { value: string; label: string }[]> = {
  application: [
    { value: "latency", label: "Latency" },
    { value: "error_rate", label: "Error Rate" },
  ],
  infrastructure: [
    { value: "CPU", label: "CPU" },
    { value: "Memory", label: "Memory" },
    { value: "Disk", label: "Disk" },
  ],
};

function OptionSelector({
  options,
  value,
  onChange,
}: {
  options: readonly string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <HStack spacing={2}>
      {options.map((opt) => {
        const isActive = value === opt;
        return (
          <Box
            key={opt}
            as="button"
            type="button"
            flex="1"
            py={2}
            px={3}
            fontSize="sm"
            fontWeight="semibold"
            textAlign="center"
            cursor="pointer"
            borderRadius="lg"
            borderWidth="2px"
            borderColor={isActive ? "gray.900" : "gray.200"}
            bg={isActive ? "gray.900" : "white"}
            color={isActive ? "white" : "gray.500"}
            _hover={{ bg: isActive ? "gray.800" : "gray.50", borderColor: isActive ? "gray.800" : "gray.300" }}
            transition="all 0.15s"
            onClick={() => onChange(opt)}
            textTransform="capitalize"
          >
            {opt}
          </Box>
        );
      })}
    </HStack>
  );
}

export interface AlertingTabProps {
  isActive?: boolean;
}

export default function AlertingTab({ isActive = false }: AlertingTabProps) {
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const [subTabIndex, setSubTabIndex] = useState(0);
  const [createRuleDef, setCreateRuleDef] = useState("");

  // Create Routing Rule — extended form state
  const [createRuleScope, setCreateRuleScope] = useState<"global" | "specific_tenant">("global");
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
    setCreateRuleScope("global");
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
    setEditRuleScope(item.tenant ? "specific_tenant" : "global");

    // Prefer direct category/severity from the receiver (backend may return them)
    const cat = item.category ?? null;
    const sev = item.severity ?? null;

    // Also try to resolve from the linked alert definition (alert_names[0])
    const firstName = item.alert_names?.[0];
    const linkedDef = firstName ? defs.definitions.find((d) => d.name === firstName) : null;

    setEditRuleCategory(cat ?? linkedDef?.category ?? "");
    setEditRuleSeverity(sev ?? linkedDef?.severity ?? "");
    setEditRuleDef(linkedDef ? String(linkedDef.id) : "");
  };

  const fetchTenants = async () => {
    if (tenants.length > 0) return;
    setIsLoadingTenants(true);
    try {
      const res = await multiTenantService.listTenants();
      setTenants((res.tenants || []).filter((t) => t.status === "ACTIVE"));
    } catch {
      // ignore
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const validateAndCreate = async () => {
    const errors: Record<string, string> = {};
    if (!rules.createForm.rule_name.trim()) errors.ruleName = "Rule name is required.";
    if (!rules.createForm.category) errors.category = "Please select a category.";
    if (!rules.createForm.severity) errors.severity = "Please select a severity.";
    if (createRuleScope === "specific_tenant" && !createRuleTenant) errors.tenant = "Please select a target tenant.";
    setCreateRuleErrors(errors);
    if (Object.keys(errors).length > 0) return;
    await rules.handleCreate({
      tenant: createRuleScope === "specific_tenant" ? createRuleTenant || null : null,
    });
    resetCreateRuleExtras();
  };

  const defs = useAlertDefinitions();
  const recvs = useNotificationReceivers();
  const rules = useRoutingRules();

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
    setEditRuleScope(item.tenant ? "specific_tenant" : "global");
    // Keep updateForm in sync so the resolved values are included in the save payload
    rules.setUpdateForm((prev) => ({
      ...prev,
      category: resolvedCat || null,
      severity: resolvedSev || null,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rules.isUpdateOpen, rules.updateItem, defs.definitions]);

  const severityColor = (s: string) => {
    switch (s) {
      case "critical": return "red";
      case "warning": return "orange";
      case "info": return "blue";
      default: return "gray";
    }
  };
  const categoryColor = (c: string | null | undefined) => {
    if (c === "application") return "orange";
    if (c === "infrastructure") return "purple";
    return "gray";
  };

  const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

  const alertTypeLabel = (val: string | null | undefined) => {
    if (!val) return "—";
    for (const types of Object.values(ALERT_TYPES_BY_CATEGORY)) {
      const found = types.find((t) => t.value === val);
      if (found) return found.label;
    }
    return val.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const formatThreshold = (d: { threshold_value?: number | null; threshold_unit?: string | null; promql_expr?: string }) => {
    const val = d.threshold_value;
    const unit = (d.threshold_unit || "").trim().toLowerCase();
    if (typeof val === "number" && !Number.isNaN(val)) {
      if (unit === "percentage") return `${val}%`;
      if (unit === "seconds") return `${val} s`;
      if (unit) return `${val} ${(d.threshold_unit || "").trim()}`;
      return String(val);
    }
    return d.promql_expr || "—";
  };

  // ═══════════════════════════════════════════════
  //  ALERT DEFINITIONS SECTION
  // ═══════════════════════════════════════════════
  const renderDefinitionsSection = () => (
    <>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardBody>
          <VStack spacing={5} align="stretch">
            {/* Search + Filters + Actions — single row */}
            <HStack spacing={3} align="center" flexWrap="wrap">
              <InputGroup maxW="260px" size="sm">
                <InputLeftElement pointerEvents="none">
                  <SearchIcon color="gray.400" />
                </InputLeftElement>
                <Input
                  placeholder="Search alerts..."
                  value={defs.searchQuery}
                  onChange={(e) => defs.setSearchQuery(e.target.value)}
                  bg="white"
                />
              </InputGroup>
              <Select size="sm" maxW="130px" value={defs.filterSeverity} onChange={(e) => defs.setFilterSeverity(e.target.value)} bg="white">
                <option value="all">Severity</option>
                {SEVERITIES.map((s) => (<option key={s} value={s}>{s}</option>))}
              </Select>
              <Select size="sm" maxW="140px" value={defs.filterCategory} onChange={(e) => defs.setFilterCategory(e.target.value)} bg="white">
                <option value="all">Category</option>
                {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
              </Select>
              <Select size="sm" maxW="120px" value={defs.filterEnabled} onChange={(e) => defs.setFilterEnabled(e.target.value)} bg="white">
                <option value="all">Status</option>
                <option value="enabled">Active</option>
                <option value="disabled">Inactive</option>
              </Select>
              <Box flex="1" />
              <Button
                size="sm"
                variant="link"
                colorScheme="gray"
                textDecoration="underline"
                alignSelf="center"
                onClick={defs.resetFilters}
                isDisabled={
                  !defs.searchQuery &&
                  defs.filterSeverity === "all" &&
                  defs.filterCategory === "all" &&
                  defs.filterEnabled === "all"
                }
              >
                Reset Filters
              </Button>
              <Button
                size="sm"
                colorScheme="orange"
                leftIcon={<AddIcon />}
                onClick={defs.openCreate}
              >
                Create Alert Definition
              </Button>
            </HStack>

            {/* Table */}
            {defs.isLoading ? (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" color="blue.500" />
                  <Text color="gray.600">Loading alert definitions...</Text>
                </VStack>
              </Center>
            ) : defs.filteredDefinitions.length > 0 ? (
              <TableContainer>
                <Table variant="simple" size="sm">
                  <Thead>
                    <Tr>
                      <Th>Name</Th>
                      <Th>Category</Th>
                      <Th>Severity</Th>
                      <Th>Subcategory</Th>
                      <Th>Status</Th>
                      <Th>Created</Th>
                      <Th>Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {defs.filteredDefinitions.map((d) => (
                      <Tr
                        key={d.id}
                        _hover={{ bg: "gray.50", "& .row-actions": { opacity: 1 } }}
                        transition="background 0.15s"
                      >
                        <Td fontWeight="semibold">{d.name}</Td>
                        <Td><Badge colorScheme={categoryColor(d.category)} textTransform="capitalize">{d.category}</Badge></Td>
                        <Td><Badge colorScheme={severityColor(d.severity)} textTransform="capitalize">{d.severity}</Badge></Td>
                        <Td>
                          <Text fontSize="sm">
                            {d.sub_category ? titleCase(d.sub_category.replace(/_/g, " ")) : "—"}
                          </Text>
                        </Td>
                        <Td>
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
                        </Td>
                        <Td fontSize="sm">{new Date(d.created_at).toLocaleDateString()}</Td>
                        <Td>
                          <HStack spacing={1} className="row-actions" opacity={0} transition="opacity 0.15s">
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
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            ) : (
              <Alert status="info" borderRadius="md">
                <AlertIcon />
                <AlertDescription>
                  {defs.definitions.length === 0
                    ? "No alert definitions found. Click 'Create Alert Definition' to get started."
                    : "No definitions match the current filters."}
                </AlertDescription>
              </Alert>
            )}
          </VStack>
        </CardBody>
      </Card>

      {/* ── Create Definition Drawer ── */}
      <Drawer isOpen={defs.isCreateOpen} onClose={defs.closeCreate} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Create Alert Definition</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={5} align="stretch">
              <FormControl isRequired isInvalid={!!defs.createErrors?.name}>
                <FormLabel fontWeight="semibold" fontSize="sm">Alert Name</FormLabel>
                <Input
                  placeholder="e.g. High Latency — ASR Global"
                  value={defs.createForm.name}
                  onChange={(e) => defs.setCreateForm({ ...defs.createForm, name: e.target.value })}
                  bg="white"
                />
                <FormErrorMessage>{defs.createErrors?.name}</FormErrorMessage>
              </FormControl>

              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Description</FormLabel>
                <Textarea
                  placeholder="Additional context about this alert and why it exists."
                  value={defs.createForm.description ?? ""}
                  onChange={(e) => defs.setCreateForm({ ...defs.createForm, description: e.target.value || null })}
                  bg="white"
                  rows={3}
                />
              </FormControl>

              <Divider />

              <FormControl isRequired isInvalid={!!defs.createErrors?.category}>
                <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                <OptionSelector
                  options={CATEGORIES}
                  value={defs.createForm.category ?? "application"}
                  onChange={(v) => defs.setCreateForm({
                    ...defs.createForm,
                    category: v,
                    sub_category: null,
                    signal: null,
                    signal_metric: null,
                  })}
                />
                <FormErrorMessage>{defs.createErrors?.category}</FormErrorMessage>
              </FormControl>

              <FormControl isRequired isInvalid={!!defs.createErrors?.sub_category}>
                <FormLabel fontWeight="semibold" fontSize="sm">Subcategory</FormLabel>
                <Select
                  value={defs.createForm.sub_category ?? ""}
                  onChange={(e) => defs.setCreateForm({
                    ...defs.createForm,
                    sub_category: e.target.value || null,
                    signal: null,
                    signal_metric: null,
                    threshold_unit: undefined,
                  })}
                  bg="white"
                  placeholder={defs.createForm.category ? "Select subcategory..." : "Select a category first"}
                  isDisabled={!defs.createForm.category}
                >
                  {(SUB_CATEGORIES_BY_CATEGORY[defs.createForm.category ?? ""] ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <FormErrorMessage>{defs.createErrors?.sub_category}</FormErrorMessage>
              </FormControl>

              <FormControl isRequired isInvalid={!!defs.createErrors?.signal}>
                <FormLabel fontWeight="semibold" fontSize="sm">Signal</FormLabel>
                <Select
                  value={defs.createForm.signal ?? ""}
                  onChange={(e) => {
                    const sig = e.target.value || null;
                    defs.setCreateForm({
                      ...defs.createForm,
                      signal: sig,
                      signal_metric: null,
                      threshold_unit: sig === "latency" ? "ms" : sig ? PERCENTAGE_UNIT : undefined,
                    });
                  }}
                  bg="white"
                  placeholder={defs.createForm.sub_category ? "Select signal..." : "Select a subcategory first"}
                  isDisabled={!defs.createForm.sub_category}
                >
                  {(SIGNALS_BY_SUB_CATEGORY[defs.createForm.sub_category ?? ""] ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <FormErrorMessage>{defs.createErrors?.signal}</FormErrorMessage>
              </FormControl>

              <FormControl isRequired isInvalid={!!defs.createErrors?.signal_metric}>
                <FormLabel fontWeight="semibold" fontSize="sm">Signal Metric</FormLabel>
                <Select
                  value={defs.createForm.signal_metric ?? ""}
                  onChange={(e) => defs.setCreateForm({ ...defs.createForm, signal_metric: e.target.value || null })}
                  bg="white"
                  placeholder={defs.createForm.signal ? "Select metric..." : "Select a signal type first"}
                  isDisabled={!defs.createForm.signal}
                >
                  {(SIGNAL_METRICS_BY_SIGNAL[defs.createForm.signal ?? ""] ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <FormErrorMessage>{defs.createErrors?.signal_metric}</FormErrorMessage>
              </FormControl>

              <FormControl isRequired={defs.createForm.category !== "infrastructure"} isInvalid={!!defs.createErrors?.service}>
                <FormLabel fontWeight="semibold" fontSize="sm">Target</FormLabel>
                {defs.createForm.category === "infrastructure" ? (
                  <Box
                    px={3}
                    py={2}
                    bg="gray.100"
                    borderRadius="md"
                    borderWidth="1px"
                    borderColor="gray.200"
                    color="gray.600"
                    fontSize="sm"
                  >
                    All services (infrastructure monitors the full stack)
                  </Box>
                ) : (
                  <Menu closeOnSelect={false} matchWidth>
                    <MenuButton
                      as={Button}
                      w="100%"
                      bg="white"
                      borderWidth="1px"
                      borderColor="gray.200"
                      borderRadius="md"
                      fontWeight="normal"
                      textAlign="left"
                      _hover={{ borderColor: "gray.400" }}
                      _active={{ bg: "white" }}
                      rightIcon={<Text fontSize="xs" color="gray.500">▾</Text>}
                    >
                      {(() => {
                        const sel = defs.createForm.service ?? [];
                        if (sel.length === 0) {
                          return <Text color="gray.400">Select targets</Text>;
                        }
                        if (sel.length === TARGET_SERVICES.length) {
                          return <Text color="gray.400">All services selected</Text>;
                        }
                        if (sel.length === 1) {
                          const v = sel[0];
                          return <Text color="gray.400">{TARGET_SERVICES.find((t) => t.value === v)?.label ?? v}</Text>;
                        }
                        return <Text color="gray.400">{`${sel.length} services selected`}</Text>;
                      })()}
                    </MenuButton>
                    <MenuList w="100%" maxH="300px" overflowY="auto">
                      <MenuItem closeOnSelect={false} px={4} py={2}>
                        <Checkbox
                          isChecked={(defs.createForm.service ?? []).length === TARGET_SERVICES.length}
                          isIndeterminate={
                            (defs.createForm.service ?? []).length > 0 &&
                            (defs.createForm.service ?? []).length < TARGET_SERVICES.length
                          }
                          onChange={(e) => {
                            defs.setCreateForm({
                              ...defs.createForm,
                              service: e.target.checked ? TARGET_SERVICES.map((t) => t.value) : [],
                            });
                          }}
                          fontWeight="semibold"
                        >
                          All services
                        </Checkbox>
                      </MenuItem>
                      <MenuDivider my={1} />
                      {TARGET_SERVICES.map((opt) => (
                        <MenuItem key={opt.value} closeOnSelect={false} px={4} py={2}>
                          <Checkbox
                            isChecked={(defs.createForm.service ?? []).includes(opt.value)}
                            onChange={(e) => {
                              const current = defs.createForm.service ?? [];
                              defs.setCreateForm({
                                ...defs.createForm,
                                service: e.target.checked
                                  ? [...current, opt.value]
                                  : current.filter((s) => s !== opt.value),
                              });
                            }}
                          >
                            {opt.label}
                          </Checkbox>
                        </MenuItem>
                      ))}
                    </MenuList>
                  </Menu>
                )}
                <FormErrorMessage>{defs.createErrors?.service}</FormErrorMessage>
              </FormControl>

              <Divider />

              <FormControl isRequired isInvalid={!!defs.createErrors?.condition_operator || !!defs.createErrors?.threshold_value || !!defs.createErrors?.threshold_unit}>
                <FormLabel fontWeight="semibold" fontSize="sm">Condition + Threshold</FormLabel>
                <SimpleGrid columns={3} spacing={3} mb={1}>
                  <Text fontSize="xs" color="gray.500" fontWeight="medium">Condition</Text>
                  <Text fontSize="xs" color="gray.500" fontWeight="medium">Threshold</Text>
                  <Text fontSize="xs" color="gray.500" fontWeight="medium">Unit</Text>
                </SimpleGrid>
                <SimpleGrid columns={3} spacing={3}>
                  <Select
                    value={defs.createForm.condition_operator ?? ""}
                    onChange={(e) => defs.setCreateForm({ ...defs.createForm, condition_operator: e.target.value || null })}
                    bg="white"
                    placeholder="—"
                  >
                    {CONDITION_OPERATORS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </Select>
                  <NumberInput
                    value={defs.createForm.threshold_value ?? ""}
                    onChange={(_s, val) => defs.setCreateForm({ ...defs.createForm, threshold_value: Number.isNaN(val) ? null : val })}
                    min={0}
                    bg="white"
                  >
                    <NumberInputField placeholder="Enter value" />
                    <NumberInputStepper>
                      <NumberIncrementStepper />
                      <NumberDecrementStepper />
                    </NumberInputStepper>
                  </NumberInput>
                  {defs.createForm.signal === "latency" ? (
                    <Select
                      value={defs.createForm.threshold_unit ?? "ms"}
                      onChange={(e) => defs.setCreateForm({ ...defs.createForm, threshold_unit: e.target.value || "ms" })}
                      bg="white"
                    >
                      {LATENCY_THRESHOLD_UNITS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </Select>
                  ) : (
                    <Box
                      px={3}
                      py={2}
                      bg="gray.100"
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor="gray.200"
                      textAlign="center"
                      fontSize="sm"
                      color={defs.createForm.signal ? "gray.700" : "gray.400"}
                      fontWeight="medium"
                    >
                      {defs.createForm.signal ? PERCENTAGE_UNIT : "—"}
                    </Box>
                  )}
                </SimpleGrid>
                <FormErrorMessage>
                  {defs.createErrors?.condition_operator ?? defs.createErrors?.threshold_value ?? defs.createErrors?.threshold_unit}
                </FormErrorMessage>
              </FormControl>

              <Divider />

              <FormControl isRequired isInvalid={!!defs.createErrors?.severity}>
                <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                <HStack spacing={2}>
                  {SEVERITIES.map((s) => {
                    const isActive = defs.createForm.severity === s;
                    const colors = s === "critical"
                      ? { activeBg: "red.100", activeBorder: "red.600", activeText: "red.700", hoverBg: "red.50" }
                      : s === "warning"
                      ? { activeBg: "yellow.100", activeBorder: "yellow.600", activeText: "yellow.700", hoverBg: "yellow.50" }
                      : { activeBg: "blue.100", activeBorder: "blue.600", activeText: "blue.700", hoverBg: "blue.50" };
                    return (
                      <Box
                        key={s}
                        as="button"
                        type="button"
                        flex="1"
                        py={2}
                        px={3}
                        fontSize="sm"
                        fontWeight="semibold"
                        textAlign="center"
                        cursor="pointer"
                        borderRadius="full"
                        borderWidth="2px"
                        borderColor={isActive ? colors.activeBorder : "gray.200"}
                        bg={isActive ? colors.activeBg : "white"}
                        color={isActive ? colors.activeText : "gray.500"}
                        _hover={{ bg: isActive ? colors.activeBg : colors.hoverBg, borderColor: colors.activeBorder }}
                        transition="all 0.15s"
                        onClick={() => defs.setCreateForm({ ...defs.createForm, severity: s })}
                        textTransform="capitalize"
                      >
                        {s}
                      </Box>
                    );
                  })}
                </HStack>
                <FormErrorMessage>{defs.createErrors?.severity}</FormErrorMessage>
              </FormControl>

              <Divider />

              <SimpleGrid columns={2} spacing={4}>
                <FormControl isRequired isInvalid={!!defs.createErrors?.evaluation_interval}>
                  <FormLabel fontWeight="semibold" fontSize="sm">Evaluation Interval</FormLabel>
                  <Select
                    value={defs.createForm.evaluation_interval ?? "30s"}
                    onChange={(e) => {
                      const newEval = e.target.value;
                      const allowed = getAllowedForDurations(newEval);
                      const currentFor = defs.createForm.for_duration ?? "1m";
                      const newFor = allowed.includes(currentFor) ? currentFor : allowed[0];
                      defs.setCreateForm({ ...defs.createForm, evaluation_interval: newEval, for_duration: newFor });
                    }}
                    bg="white"
                  >
                    {EVAL_INTERVALS.map((v) => (<option key={v} value={v}>{v}</option>))}
                  </Select>
                  <Text fontSize="xs" color="gray.500" mt={1}>How often to check</Text>
                  <FormErrorMessage>{defs.createErrors?.evaluation_interval}</FormErrorMessage>
                </FormControl>

                <FormControl isRequired isInvalid={!!defs.createErrors?.for_duration}>
                  <FormLabel fontWeight="semibold" fontSize="sm">For Duration</FormLabel>
                  <Select
                    value={(() => {
                      const allowed = getAllowedForDurations(defs.createForm.evaluation_interval);
                      const cur = defs.createForm.for_duration ?? "1m";
                      return allowed.includes(cur) ? cur : allowed[0];
                    })()}
                    onChange={(e) => defs.setCreateForm({ ...defs.createForm, for_duration: e.target.value })}
                    bg="white"
                  >
                    {getAllowedForDurations(defs.createForm.evaluation_interval).map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </Select>
                  <Text fontSize="xs" color="gray.500" mt={1}>Alert fires only after the condition is met continuously for this duration.</Text>
                  <FormErrorMessage>{defs.createErrors?.for_duration}</FormErrorMessage>
                </FormControl>
              </SimpleGrid>

              <Divider />

              <FormControl isRequired>
                <FormLabel fontWeight="semibold" fontSize="sm">Status</FormLabel>
                <HStack>
                  <Switch
                    isChecked={defs.createForm.enabled !== false}
                    onChange={(e) => defs.setCreateForm({ ...defs.createForm, enabled: e.target.checked })}
                    colorScheme="green"
                  />
                  <Text fontSize="sm">Enable this alert</Text>
                </HStack>
              </FormControl>
            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={defs.closeCreate} isDisabled={defs.isCreating}>Cancel</Button>
            <Button colorScheme="orange" onClick={defs.handleCreate} isLoading={defs.isCreating} loadingText="Saving...">Save Alert Definition</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── View Definition Drawer ── */}
      <Drawer isOpen={defs.isViewOpen} onClose={defs.closeView} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Alert Definition Details</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            {defs.viewItem && (() => {
              const v = defs.viewItem;
              const signalMetricLabel = v.signal_metric
                ? (SIGNAL_METRICS_BY_SIGNAL[v.signal ?? ""]?.find((m) => m.value === v.signal_metric)?.label
                    ?? titleCase(v.signal_metric.replace(/_/g, " ")))
                : "—";
              const signalLabel = v.signal
                ? titleCase(v.signal.replace(/_/g, " "))
                : v.alert_type ? alertTypeLabel(v.alert_type) : "—";
              const targetLabel = v.service && v.service.length > 0
                ? v.service.map((s) => TARGET_SERVICES.find((t) => t.value === s)?.label ?? s).join(", ")
                : "All services";
              const conditionThreshold = v.condition_operator && v.threshold_value != null
                ? `${v.condition_operator} ${v.threshold_value} ${v.threshold_unit ?? ""}`.trim()
                : formatThreshold(v);
              const DetailRow = ({ label, children }: { label: string; children: React.ReactNode }) => (
                <Box borderBottomWidth="1px" borderColor="gray.100" pb={3}>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>{label}</Text>
                  {children}
                </Box>
              );
              return (
                <VStack spacing={4} align="stretch">
                  <DetailRow label="Alert Name">
                    <Text fontWeight="semibold" fontSize="md">{v.name}</Text>
                  </DetailRow>
                  <DetailRow label="Description">
                    <Text color={v.description ? "gray.800" : "gray.400"}>{v.description || "—"}</Text>
                  </DetailRow>
                  <DetailRow label="Category">
                    <Text>{titleCase(v.category)}</Text>
                  </DetailRow>
                  <DetailRow label="Severity">
                    <Badge colorScheme={severityColor(v.severity)} textTransform="capitalize" px={3} py={1} borderRadius="full" fontSize="sm">{v.severity}</Badge>
                  </DetailRow>
                  <DetailRow label="Signal">
                    <Text>{signalLabel}</Text>
                  </DetailRow>
                  <DetailRow label="Signal Metric">
                    <Text>{signalMetricLabel}</Text>
                  </DetailRow>
                  <DetailRow label="Target">
                    <Text>{targetLabel}</Text>
                  </DetailRow>
                  <DetailRow label="Condition & Threshold">
                    <Text fontFamily="mono" fontWeight="semibold" fontSize="md">{conditionThreshold}</Text>
                  </DetailRow>
                  <DetailRow label="Evaluation Interval">
                    <Text fontFamily="mono">{v.evaluation_interval}</Text>
                  </DetailRow>
                  <DetailRow label="For Duration">
                    <Text fontFamily="mono">{v.for_duration}</Text>
                  </DetailRow>
                  <DetailRow label="Status">
                    <Badge
                      colorScheme={v.enabled ? "green" : "gray"}
                      variant="subtle"
                      fontSize="sm"
                      px={3}
                      py={1}
                      borderRadius="full"
                    >
                      {v.enabled ? "Active" : "Inactive"}
                    </Badge>
                  </DetailRow>
                </VStack>
              );
            })()}
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => { defs.closeView(); if (defs.viewItem) defs.openUpdate(defs.viewItem); }}>Edit</Button>
            <Button onClick={defs.closeView}>Close</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── Update Definition Drawer ── */}
      <Drawer isOpen={defs.isUpdateOpen} onClose={defs.closeUpdate} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Update Alert Definition</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={5} align="stretch">
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Name</FormLabel>
                <Input value={defs.updateItem?.name ?? ""} isReadOnly bg="gray.50" cursor="not-allowed" />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Description</FormLabel>
                <Textarea value={defs.updateForm.description ?? ""} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, description: e.target.value || null })} bg="white" rows={3} />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                <OptionSelector
                  options={CATEGORIES}
                  value={defs.updateForm.category ?? "application"}
                  onChange={(v) => defs.setUpdateForm({ ...defs.updateForm, category: v, sub_category: undefined, signal: undefined, signal_metric: undefined })}
                />
              </FormControl>
              <Divider />
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Subcategory</FormLabel>
                <Select
                  value={defs.updateForm.sub_category ?? ""}
                  onChange={(e) => defs.setUpdateForm({
                    ...defs.updateForm,
                    sub_category: e.target.value || undefined,
                    signal: undefined,
                    signal_metric: undefined,
                    threshold_unit: undefined,
                  })}
                  bg="white"
                  placeholder={defs.updateForm.category ? "Select subcategory..." : "Select a category first"}
                  isDisabled={!defs.updateForm.category}
                >
                  {(SUB_CATEGORIES_BY_CATEGORY[defs.updateForm.category ?? ""] ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Signal</FormLabel>
                <Select
                  value={defs.updateForm.signal ?? ""}
                  onChange={(e) => {
                    const sig = e.target.value || undefined;
                    defs.setUpdateForm({
                      ...defs.updateForm,
                      signal: sig,
                      signal_metric: undefined,
                      threshold_unit: sig === "latency" ? "ms" : sig ? PERCENTAGE_UNIT : undefined,
                    });
                  }}
                  bg="white"
                  placeholder={defs.updateForm.sub_category ? "Select signal..." : "Select a subcategory first"}
                  isDisabled={!defs.updateForm.sub_category}
                >
                  {(SIGNALS_BY_SUB_CATEGORY[defs.updateForm.sub_category ?? ""] ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Signal Metric</FormLabel>
                <Select
                  value={defs.updateForm.signal_metric ?? ""}
                  onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, signal_metric: e.target.value || undefined })}
                  bg="white"
                  placeholder={defs.updateForm.signal ? "Select metric..." : "Select a signal first"}
                  isDisabled={!defs.updateForm.signal}
                >
                  {(SIGNAL_METRICS_BY_SIGNAL[defs.updateForm.signal ?? ""] ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
              </FormControl>
              <Divider />
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Target</FormLabel>
                {defs.updateForm.category === "infrastructure" ? (
                  <Box
                    px={3}
                    py={2}
                    bg="gray.100"
                    borderRadius="md"
                    borderWidth="1px"
                    borderColor="gray.200"
                    color="gray.600"
                    fontSize="sm"
                  >
                    All services (infrastructure monitors the full stack)
                  </Box>
                ) : (
                  <Menu closeOnSelect={false} matchWidth>
                    <MenuButton
                      as={Button}
                      w="100%"
                      bg="white"
                      borderWidth="1px"
                      borderColor="gray.200"
                      borderRadius="md"
                      fontWeight="normal"
                      textAlign="left"
                      _hover={{ borderColor: "gray.400" }}
                      _active={{ bg: "white" }}
                      rightIcon={<Text fontSize="xs" color="gray.500">▾</Text>}
                    >
                      {(() => {
                        const sel = defs.updateForm.service ?? [];
                        if (sel.length === 0) {
                          return <Text color="gray.400">Select targets...</Text>;
                        }
                        if (sel.length === TARGET_SERVICES.length) {
                          return "All services selected";
                        }
                        if (sel.length === 1) {
                          const v = sel[0];
                          return TARGET_SERVICES.find((t) => t.value === v)?.label ?? v;
                        }
                        return `${sel.length} services selected`;
                      })()}
                    </MenuButton>
                    <MenuList w="100%" maxH="300px" overflowY="auto">
                      <MenuItem closeOnSelect={false} px={4} py={2}>
                        <Checkbox
                          isChecked={(defs.updateForm.service ?? []).length === TARGET_SERVICES.length}
                          isIndeterminate={
                            (defs.updateForm.service ?? []).length > 0 &&
                            (defs.updateForm.service ?? []).length < TARGET_SERVICES.length
                          }
                          onChange={(e) => {
                            defs.setUpdateForm({
                              ...defs.updateForm,
                              service: e.target.checked ? TARGET_SERVICES.map((t) => t.value) : [],
                            });
                          }}
                          fontWeight="semibold"
                        >
                          All services
                        </Checkbox>
                      </MenuItem>
                      <MenuDivider my={1} />
                      {TARGET_SERVICES.map((opt) => (
                        <MenuItem key={opt.value} closeOnSelect={false} px={4} py={2}>
                          <Checkbox
                            isChecked={(defs.updateForm.service ?? []).includes(opt.value)}
                            onChange={(e) => {
                              const current = defs.updateForm.service ?? [];
                              defs.setUpdateForm({
                                ...defs.updateForm,
                                service: e.target.checked
                                  ? [...current, opt.value]
                                  : current.filter((s) => s !== opt.value),
                              });
                            }}
                          >
                            {opt.label}
                          </Checkbox>
                        </MenuItem>
                      ))}
                    </MenuList>
                  </Menu>
                )}
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Condition + Threshold</FormLabel>
                <SimpleGrid columns={3} spacing={3} mb={1}>
                  <Text fontSize="xs" color="gray.500" fontWeight="medium">Condition</Text>
                  <Text fontSize="xs" color="gray.500" fontWeight="medium">Threshold</Text>
                  <Text fontSize="xs" color="gray.500" fontWeight="medium">Unit</Text>
                </SimpleGrid>
                <SimpleGrid columns={3} spacing={3}>
                  <Select
                    value={defs.updateForm.condition_operator ?? ""}
                    onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, condition_operator: e.target.value || undefined })}
                    bg="white"
                    placeholder="—"
                  >
                    {CONDITION_OPERATORS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </Select>
                  <NumberInput
                    value={defs.updateForm.threshold_value ?? ""}
                    onChange={(_s, val) => defs.setUpdateForm({ ...defs.updateForm, threshold_value: Number.isNaN(val) ? undefined : val })}
                    min={0}
                    bg="white"
                  >
                    <NumberInputField placeholder="Value" />
                    <NumberInputStepper>
                      <NumberIncrementStepper />
                      <NumberDecrementStepper />
                    </NumberInputStepper>
                  </NumberInput>
                  {defs.updateForm.signal === "latency" ? (
                    <Select
                      value={defs.updateForm.threshold_unit ?? "ms"}
                      onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, threshold_unit: e.target.value || "ms" })}
                      bg="white"
                    >
                      {LATENCY_THRESHOLD_UNITS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </Select>
                  ) : (
                    <Box
                      px={3}
                      py={2}
                      bg="gray.100"
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor="gray.200"
                      textAlign="center"
                      fontSize="sm"
                      color={defs.updateForm.signal ? "gray.700" : "gray.400"}
                      fontWeight="medium"
                    >
                      {defs.updateForm.signal ? PERCENTAGE_UNIT : "—"}
                    </Box>
                  )}
                </SimpleGrid>
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                <HStack spacing={2}>
                  {SEVERITIES.map((s) => {
                    const isActive = (defs.updateForm.severity ?? "") === s;
                    const colors = s === "critical"
                      ? { activeBg: "red.100", activeBorder: "red.600", activeText: "red.700", hoverBg: "red.50" }
                      : s === "warning"
                      ? { activeBg: "yellow.100", activeBorder: "yellow.600", activeText: "yellow.700", hoverBg: "yellow.50" }
                      : { activeBg: "blue.100", activeBorder: "blue.600", activeText: "blue.700", hoverBg: "blue.50" };
                    return (
                      <Box
                        key={s}
                        as="button"
                        type="button"
                        flex="1"
                        py={2}
                        px={3}
                        fontSize="sm"
                        fontWeight="semibold"
                        textAlign="center"
                        cursor="pointer"
                        borderRadius="full"
                        borderWidth="2px"
                        borderColor={isActive ? colors.activeBorder : "gray.200"}
                        bg={isActive ? colors.activeBg : "white"}
                        color={isActive ? colors.activeText : "gray.500"}
                        _hover={{ bg: isActive ? colors.activeBg : colors.hoverBg, borderColor: colors.activeBorder }}
                        transition="all 0.15s"
                        onClick={() => defs.setUpdateForm({ ...defs.updateForm, severity: s })}
                        textTransform="capitalize"
                      >
                        {s}
                      </Box>
                    );
                  })}
                </HStack>
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Evaluation Interval</FormLabel>
                <Select
                  value={defs.updateForm.evaluation_interval ?? "30s"}
                  onChange={(e) => {
                    const newEval = e.target.value;
                    const allowed = getAllowedForDurations(newEval);
                    const currentFor = defs.updateForm.for_duration ?? "5m";
                    const newFor = allowed.includes(currentFor) ? currentFor : allowed[0];
                    defs.setUpdateForm({ ...defs.updateForm, evaluation_interval: newEval, for_duration: newFor });
                  }}
                  bg="white"
                >
                  {EVAL_INTERVALS.map((v) => (<option key={v} value={v}>{v}</option>))}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">For Duration</FormLabel>
                <Select
                  value={(() => {
                    const allowed = getAllowedForDurations(defs.updateForm.evaluation_interval);
                    const cur = defs.updateForm.for_duration ?? "5m";
                    return allowed.includes(cur) ? cur : allowed[0];
                  })()}
                  onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, for_duration: e.target.value })}
                  bg="white"
                >
                  {getAllowedForDurations(defs.updateForm.evaluation_interval).map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold" fontSize="sm">Status</FormLabel>
                <HStack>
                  <Switch
                    isChecked={defs.updateForm.enabled ?? true}
                    onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, enabled: e.target.checked })}
                    colorScheme="green"
                  />
                  <Text fontSize="sm">Enable this alert</Text>
                </HStack>
              </FormControl>
            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={defs.closeUpdate} isDisabled={defs.isUpdating}>Cancel</Button>
            <Button colorScheme="orange" onClick={defs.handleUpdate} isLoading={defs.isUpdating} loadingText="Saving...">Save Changes</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── Delete Definition Dialog ── */}
      <AlertDialog isOpen={defs.isDeleteOpen} leastDestructiveRef={defDeleteRef} onClose={defs.closeDelete}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">Delete Alert Definition</AlertDialogHeader>
            <AlertDialogBody><Text>Are you sure you want to delete &quot;{defs.deleteItem?.name}&quot;? This action cannot be undone.</Text></AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={defDeleteRef} onClick={defs.closeDelete} isDisabled={defs.isDeleting}>Cancel</Button>
              <Button colorScheme="red" onClick={defs.handleDelete} ml={3} isLoading={defs.isDeleting} loadingText="Deleting...">Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );

  // ═══════════════════════════════════════════════
  //  NOTIFICATION RECEIVERS SECTION
  // ═══════════════════════════════════════════════
  const renderReceiversSection = () => (
    <>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="gray.700" userSelect="none" cursor="default">
              Notification Receivers
            </Heading>
            <HStack spacing={2}>
              <Button size="sm" colorScheme="green" leftIcon={<AddIcon />} onClick={recvs.openCreate}>Create</Button>
              <Button size="sm" colorScheme="blue" onClick={recvs.fetchReceivers} isLoading={recvs.isLoading} loadingText="Loading...">Refresh</Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <VStack spacing={6} align="stretch">
            <HStack>
              <FormControl maxW="200px">
                <FormLabel fontWeight="semibold">Status</FormLabel>
                <Select value={recvs.filterEnabled} onChange={(e) => recvs.setFilterEnabled(e.target.value)} bg="white">
                  <option value="all">All</option>
                  <option value="enabled">Enabled</option>
                  <option value="disabled">Disabled</option>
                </Select>
              </FormControl>
            </HStack>

            {recvs.isLoading ? (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" color="blue.500" />
                  <Text color="gray.600">Loading receivers...</Text>
                </VStack>
              </Center>
            ) : recvs.filteredReceivers.length > 0 ? (
              <TableContainer>
                <Table variant="simple" size="sm">
                  <Thead>
                    <Tr>
                      <Th>Name</Th>
                      <Th>Recipient</Th>
                      <Th>Status</Th>
                      <Th>Organization</Th>
                      <Th>Created</Th>
                      <Th>Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {recvs.filteredReceivers.map((r) => (
                      <Tr
                        key={r.id}
                        _hover={{ bg: "gray.50", "& .row-actions": { opacity: 1 } }}
                        transition="background 0.15s"
                      >
                        <Td fontWeight="semibold" fontSize="sm">{r.receiver_name}</Td>
                        <Td>
                          {r.rbac_role ? (
                            <Badge colorScheme="purple">Role: {r.rbac_role}</Badge>
                          ) : r.email_to && r.email_to.length > 0 ? (
                            <Wrap spacing={1}>
                              {r.email_to.slice(0, 2).map((e) => (<WrapItem key={e}><Badge colorScheme="blue" fontSize="xs">{e}</Badge></WrapItem>))}
                              {r.email_to.length > 2 && (<WrapItem><Badge colorScheme="gray" fontSize="xs">+{r.email_to.length - 2}</Badge></WrapItem>)}
                            </Wrap>
                          ) : (
                            <Text fontSize="sm" color="gray.500">—</Text>
                          )}
                        </Td>
                        <Td>
                          <Switch size="sm" colorScheme="green" isChecked={r.enabled} isReadOnly />
                        </Td>
                        <Td fontSize="sm">{r.organization}</Td>
                        <Td fontSize="sm">{new Date(r.created_at).toLocaleDateString()}</Td>
                        <Td>
                          <HStack spacing={1} className="row-actions" opacity={0} transition="opacity 0.15s">
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
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            ) : (
              <Alert status="info" borderRadius="md">
                <AlertIcon />
                <AlertDescription>
                  {recvs.receivers.length === 0
                    ? "No notification receivers found. Click 'Create' to add one."
                    : "No receivers match the current filters."}
                </AlertDescription>
              </Alert>
            )}
          </VStack>
        </CardBody>
      </Card>

      {/* ── Create Receiver Modal ── */}
      <Modal isOpen={recvs.isCreateOpen} onClose={recvs.closeCreate} size="lg" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Notification Receiver</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <SimpleGrid columns={2} spacing={4}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Category</FormLabel>
                  <Select value={recvs.createForm.category} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, category: e.target.value })} bg="white">
                    {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                  </Select>
                </FormControl>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Severity</FormLabel>
                  <Select value={recvs.createForm.severity} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, severity: e.target.value })} bg="white">
                    {SEVERITIES.map((s) => (<option key={s} value={s}>{s}</option>))}
                  </Select>
                </FormControl>
              </SimpleGrid>
              <FormControl>
                <FormLabel fontWeight="semibold">Alert Type</FormLabel>
                <Input placeholder="e.g. latency (optional)" value={recvs.createForm.alert_type ?? ""} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, alert_type: e.target.value || null })} bg="white" />
              </FormControl>
              <Divider />
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Recipient Type</FormLabel>
                <RadioGroup value={recvs.recipientMode} onChange={(v) => recvs.setRecipientMode(v as "email" | "role")}>
                  <Stack direction="row" spacing={6}>
                    <Radio value="email">Email Addresses</Radio>
                    <Radio value="role">RBAC Role</Radio>
                  </Stack>
                </RadioGroup>
              </FormControl>
              {recvs.recipientMode === "email" ? (
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Email Addresses</FormLabel>
                  <HStack>
                    <Input
                      placeholder="Enter email and press Add"
                      value={recvs.emailInput}
                      onChange={(e) => recvs.setEmailInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); recvs.addEmail(recvs.emailInput); recvs.setEmailInput(""); } }}
                      bg="white"
                    />
                    <Button size="sm" colorScheme="blue" onClick={() => { recvs.addEmail(recvs.emailInput); recvs.setEmailInput(""); }}>Add</Button>
                  </HStack>
                  <Wrap mt={2} spacing={1}>
                    {(recvs.createForm.email_to ?? []).map((email) => (
                      <WrapItem key={email}>
                        <Tag size="md" colorScheme="blue" borderRadius="full"><TagLabel>{email}</TagLabel><TagCloseButton onClick={() => recvs.removeEmail(email)} /></Tag>
                      </WrapItem>
                    ))}
                  </Wrap>
                </FormControl>
              ) : (
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">RBAC Role</FormLabel>
                  <Select value={recvs.createForm.rbac_role ?? ""} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, rbac_role: e.target.value || null })} bg="white" placeholder="Select a role">
                    {RBAC_ROLES.map((r) => (<option key={r} value={r}>{r}</option>))}
                  </Select>
                </FormControl>
              )}
              <Divider />
              <FormControl>
                <FormLabel fontWeight="semibold">Email Subject Template</FormLabel>
                <Input placeholder="Optional custom subject" value={recvs.createForm.email_subject_template ?? ""} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, email_subject_template: e.target.value || null })} bg="white" />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold">Email Body Template</FormLabel>
                <Textarea placeholder="Optional HTML body template" value={recvs.createForm.email_body_template ?? ""} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, email_body_template: e.target.value || null })} bg="white" rows={3} />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={recvs.closeCreate} isDisabled={recvs.isCreating}>Cancel</Button>
            <Button colorScheme="blue" onClick={recvs.handleCreate} isLoading={recvs.isCreating} loadingText="Creating...">Create</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* ── View Receiver Modal ── */}
      <Modal isOpen={recvs.isViewOpen} onClose={recvs.closeView} size="xl" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Notification Receiver Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {recvs.viewItem && (
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Receiver Name</Text><Text fontSize="sm">{recvs.viewItem.receiver_name}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Organization</Text><Text>{recvs.viewItem.organization}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Status</Text><Badge colorScheme={recvs.viewItem.enabled ? "green" : "red"} fontSize="sm" p={1}>{recvs.viewItem.enabled ? "Enabled" : "Disabled"}</Badge></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Created By</Text><Text fontSize="sm">{recvs.viewItem.created_by}</Text></Box>
                <Box gridColumn={{ base: "span 1", md: "span 2" }}>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Recipient</Text>
                  {recvs.viewItem.rbac_role ? (
                    <Badge colorScheme="purple" fontSize="sm" p={1}>Role: {recvs.viewItem.rbac_role}</Badge>
                  ) : (
                    <Wrap spacing={1}>{(recvs.viewItem.email_to ?? []).map((e) => (<WrapItem key={e}><Badge colorScheme="blue">{e}</Badge></WrapItem>))}</Wrap>
                  )}
                </Box>
                {recvs.viewItem.email_subject_template && (
                  <Box gridColumn={{ base: "span 1", md: "span 2" }}><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Subject Template</Text><Text fontSize="sm">{recvs.viewItem.email_subject_template}</Text></Box>
                )}
                {recvs.viewItem.email_body_template && (
                  <Box gridColumn={{ base: "span 1", md: "span 2" }}><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Body Template</Text><Box bg="gray.50" p={3} borderRadius="md" fontSize="sm" whiteSpace="pre-wrap">{recvs.viewItem.email_body_template}</Box></Box>
                )}
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Created At</Text><Text fontSize="sm">{new Date(recvs.viewItem.created_at).toLocaleString()}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Updated At</Text><Text fontSize="sm">{new Date(recvs.viewItem.updated_at).toLocaleString()}</Text></Box>
              </SimpleGrid>
            )}
          </ModalBody>
          <ModalFooter><Button onClick={recvs.closeView}>Close</Button></ModalFooter>
        </ModalContent>
      </Modal>

      {/* ── Update Receiver Modal ── */}
      <Modal isOpen={recvs.isUpdateOpen} onClose={recvs.closeUpdate} size="lg" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Update Notification Receiver</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl>
                <FormLabel fontWeight="semibold">Receiver Name</FormLabel>
                <Input value={recvs.updateForm.rule_name ?? ""} onChange={(e) => recvs.setUpdateForm({ ...recvs.updateForm, rule_name: e.target.value })} bg="white" />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold">Recipient Type</FormLabel>
                <RadioGroup value={recvs.updateRecipientMode} onChange={(v) => recvs.setUpdateRecipientMode(v as "email" | "role")}>
                  <Stack direction="row" spacing={6}><Radio value="email">Email Addresses</Radio><Radio value="role">RBAC Role</Radio></Stack>
                </RadioGroup>
              </FormControl>
              {recvs.updateRecipientMode === "email" ? (
                <FormControl>
                  <FormLabel fontWeight="semibold">Email Addresses</FormLabel>
                  <HStack>
                    <Input
                      placeholder="Enter email and press Add"
                      value={recvs.updateEmailInput}
                      onChange={(e) => recvs.setUpdateEmailInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); recvs.addUpdateEmail(recvs.updateEmailInput); recvs.setUpdateEmailInput(""); } }}
                      bg="white"
                    />
                    <Button size="sm" colorScheme="blue" onClick={() => { recvs.addUpdateEmail(recvs.updateEmailInput); recvs.setUpdateEmailInput(""); }}>Add</Button>
                  </HStack>
                  <Wrap mt={2} spacing={1}>
                    {(recvs.updateForm.email_to ?? []).map((email) => (
                      <WrapItem key={email}><Tag size="md" colorScheme="blue" borderRadius="full"><TagLabel>{email}</TagLabel><TagCloseButton onClick={() => recvs.removeUpdateEmail(email)} /></Tag></WrapItem>
                    ))}
                  </Wrap>
                </FormControl>
              ) : (
                <FormControl>
                  <FormLabel fontWeight="semibold">RBAC Role</FormLabel>
                  <Select value={recvs.updateForm.rbac_role ?? ""} onChange={(e) => recvs.setUpdateForm({ ...recvs.updateForm, rbac_role: e.target.value || null })} bg="white" placeholder="Select a role">
                    {RBAC_ROLES.map((r) => (<option key={r} value={r}>{r}</option>))}
                  </Select>
                </FormControl>
              )}
              <FormControl>
                <FormLabel fontWeight="semibold">Email Subject Template</FormLabel>
                <Input value={recvs.updateForm.email_subject_template ?? ""} onChange={(e) => recvs.setUpdateForm({ ...recvs.updateForm, email_subject_template: e.target.value || null })} bg="white" />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold">Email Body Template</FormLabel>
                <Textarea value={recvs.updateForm.email_body_template ?? ""} onChange={(e) => recvs.setUpdateForm({ ...recvs.updateForm, email_body_template: e.target.value || null })} bg="white" rows={3} />
              </FormControl>
              <FormControl display="flex" alignItems="center">
                <FormLabel fontWeight="semibold" mb={0}>Enabled</FormLabel>
                <Switch isChecked={recvs.updateForm.enabled ?? true} onChange={(e) => recvs.setUpdateForm({ ...recvs.updateForm, enabled: e.target.checked })} colorScheme="green" />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={recvs.closeUpdate} isDisabled={recvs.isUpdating}>Cancel</Button>
            <Button colorScheme="blue" onClick={recvs.handleUpdate} isLoading={recvs.isUpdating} loadingText="Updating...">Update</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* ── Delete Receiver Dialog ── */}
      <AlertDialog isOpen={recvs.isDeleteOpen} leastDestructiveRef={recvDeleteRef} onClose={recvs.closeDelete}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">Delete Notification Receiver</AlertDialogHeader>
            <AlertDialogBody><Text>Are you sure you want to delete &quot;{recvs.deleteItem?.receiver_name}&quot;? This action cannot be undone.</Text></AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={recvDeleteRef} onClick={recvs.closeDelete} isDisabled={recvs.isDeleting}>Cancel</Button>
              <Button colorScheme="red" onClick={recvs.handleDelete} ml={3} isLoading={recvs.isDeleting} loadingText="Deleting...">Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );

  // ═══════════════════════════════════════════════
  //  ROUTING RULES SECTION
  // ═══════════════════════════════════════════════
  const renderRoutingRulesSection = () => (
    <>
      <Box bg={cardBg} borderColor={cardBorder} borderWidth="1px" borderRadius="lg" p={4}>
      <VStack spacing={5} align="stretch">
        {/* Search + Filters + Actions */}
        <HStack spacing={3} justify="space-between" align="center" w="100%">
          <HStack spacing={3}>
            <InputGroup maxW="280px" size="sm">
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search routing rules..."
                value={rules.searchQuery}
                onChange={(e) => rules.setSearchQuery(e.target.value)}
                bg="white"
              />
            </InputGroup>
            <Select size="sm" maxW="120px" value={rules.filterEnabled} onChange={(e) => rules.setFilterEnabled(e.target.value)} bg="white">
              <option value="all">Status</option>
              <option value="enabled">Active</option>
              <option value="disabled">Inactive</option>
            </Select>
          </HStack>
          <HStack spacing={3}>
            <Button
              size="sm"
              variant="link"
              colorScheme="gray"
              textDecoration="underline"
              onClick={() => { rules.setSearchQuery(""); rules.setFilterEnabled("all"); }}
              isDisabled={!rules.searchQuery && rules.filterEnabled === "all"}
            >
              Reset Filters
            </Button>
            <Button
              size="sm"
              colorScheme="orange"
              leftIcon={<AddIcon />}
              onClick={() => { resetCreateRuleExtras(); defs.fetchDefinitions(); fetchTenants(); rules.openCreate(); }}
            >
              Create Routing Rule
            </Button>
          </HStack>
        </HStack>

        {rules.isLoading ? (
          <Center py={8}>
            <VStack spacing={4}>
              <Spinner size="lg" color="orange.500" />
              <Text color="gray.600">Loading alert routing...</Text>
            </VStack>
          </Center>
        ) : rules.filteredRules.length > 0 ? (
          <TableContainer>
            <Table variant="simple" size="sm" w="100%">
              <Thead>
                <Tr>
                  <Th>Rule Name</Th>
                  <Th>Alert Definitions</Th>
                  <Th>Tenant</Th>
                  <Th>Status</Th>
                  <Th>Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {rules.filteredRules.map((rule) => (
                    <Tr
                      key={rule.id}
                      _hover={{ bg: "gray.50", "& .row-actions": { opacity: 1 } }}
                      transition="background 0.15s"
                    >
                      <Td fontWeight="semibold">{rule.rule_name ?? rule.receiver_name}</Td>
                      <Td>
                        {rule.alert_names && rule.alert_names.length > 0 ? (
                          <Text fontSize="sm" color="gray.700">
                            {rule.alert_names.slice(0, 2).join(", ")}
                            {rule.alert_names.length > 2 ? ` +${rule.alert_names.length - 2}` : ""}
                          </Text>
                        ) : (
                          <Text fontSize="sm" color="gray.500">All</Text>
                        )}
                      </Td>
                      <Td>
                        {rule.tenant ? (
                          <Badge colorScheme="purple" variant="subtle" textTransform="none">{rule.tenant}</Badge>
                        ) : (
                          <Text fontSize="sm" color="gray.500">Global</Text>
                        )}
                      </Td>
                      <Td>
                        <Badge colorScheme={rule.enabled ? "green" : "gray"} variant="subtle" fontSize="xs" px={2} py={0.5} borderRadius="full">
                          {rule.enabled ? "Active" : "Inactive"}
                        </Badge>
                      </Td>
                      <Td>
                        <HStack spacing={1} className="row-actions" opacity={0} transition="opacity 0.15s">
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
                      </Td>
                    </Tr>
                  ))}
              </Tbody>
            </Table>
          </TableContainer>
        ) : (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>
              {rules.rules.length === 0
                ? "No alert routing configured. Click 'Create Routing Rule' to add one."
                : "No entries match the current filters."}
            </AlertDescription>
          </Alert>
        )}
      </VStack>
      </Box>

      {/* ── Create Routing Rule Drawer ── */}
      <Drawer isOpen={rules.isCreateOpen} onClose={() => { rules.closeCreate(); resetCreateRuleExtras(); }} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Create Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={0} align="stretch">

              {/* ── Rule Name + Description ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!createRuleErrors.ruleName}>
                  <FormLabel fontWeight="semibold" fontSize="sm">Rule Name</FormLabel>
                  <Input
                    placeholder="e.g. Route Critical ASR Alerts"
                    value={rules.createForm.rule_name}
                    onChange={(e) => { rules.setCreateForm({ ...rules.createForm, rule_name: e.target.value }); if (e.target.value.trim()) setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.ruleName; return n; }); }}
                    bg="white"
                  />
                  <FormErrorMessage>{createRuleErrors.ruleName}</FormErrorMessage>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Category + Severity + Alert Definition ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!createRuleErrors.category}>
                  <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                  <OptionSelector
                    options={CATEGORIES}
                    value={rules.createForm.category ?? ""}
                    onChange={(v) => { rules.setCreateForm({ ...rules.createForm, category: v }); setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.category; return n; }); }}
                  />
                  <FormErrorMessage>{createRuleErrors.category}</FormErrorMessage>
                </FormControl>
                <FormControl isRequired isInvalid={!!createRuleErrors.severity}>
                  <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                  <HStack spacing={2}>
                    {SEVERITIES.map((s) => {
                      const isActive = rules.createForm.severity === s;
                      const colors = s === "critical"
                        ? { activeBg: "red.100", activeBorder: "red.600", activeText: "red.700", hoverBg: "red.50" }
                        : s === "warning"
                        ? { activeBg: "yellow.100", activeBorder: "yellow.600", activeText: "yellow.700", hoverBg: "yellow.50" }
                        : { activeBg: "blue.100", activeBorder: "blue.600", activeText: "blue.700", hoverBg: "blue.50" };
                      return (
                        <Box
                          key={s}
                          as="button"
                          type="button"
                          flex="1"
                          py={2}
                          px={3}
                          fontSize="sm"
                          fontWeight="semibold"
                          textAlign="center"
                          cursor="pointer"
                          borderRadius="full"
                          borderWidth="2px"
                          borderColor={isActive ? colors.activeBorder : "gray.200"}
                          bg={isActive ? colors.activeBg : "white"}
                          color={isActive ? colors.activeText : "gray.500"}
                          _hover={{ bg: isActive ? colors.activeBg : colors.hoverBg, borderColor: colors.activeBorder }}
                          transition="all 0.15s"
                          onClick={() => { rules.setCreateForm({ ...rules.createForm, severity: s }); setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.severity; return n; }); }}
                          textTransform="capitalize"
                        >
                          {s}
                        </Box>
                      );
                    })}
                  </HStack>
                  <FormErrorMessage>{createRuleErrors.severity}</FormErrorMessage>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Alert Definitions</FormLabel>
                  {(() => {
                    const cat = rules.createForm.category;
                    const sev = rules.createForm.severity;
                    const hasFilter = !!cat && !!sev;
                    const matchingDefs = defs.definitions.filter((d) =>
                      (!cat || d.category === cat) && (!sev || d.severity === sev)
                    );
                    return (
                      <Select
                        bg="white"
                        value={createRuleDef}
                        isDisabled={!hasFilter}
                        onChange={(e) => setCreateRuleDef(e.target.value)}
                        placeholder={!hasFilter ? "Select Category and Severity first" : matchingDefs.length === 0 ? "No definitions match" : `${matchingDefs.length} alert definition${matchingDefs.length !== 1 ? "s" : ""} affected`}
                      >
                        {matchingDefs.map((d) => (
                          <option key={d.id} value={String(d.id)}>{d.name}</option>
                        ))}
                      </Select>
                    );
                  })()}
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Scope ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">Scope</FormLabel>
                  <Select
                    value={createRuleScope}
                    onChange={(e) => { setCreateRuleScope(e.target.value as "global" | "specific_tenant"); setCreateRuleTenant(""); setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; }); }}
                    bg="white"
                  >
                    <option value="global">Global</option>
                    <option value="specific_tenant">Specific Tenant</option>
                  </Select>
                </FormControl>
                {createRuleScope === "specific_tenant" && (
                  <FormControl isRequired isInvalid={!!createRuleErrors.tenant}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Target Tenant</FormLabel>
                    <Select
                      value={createRuleTenant}
                      onChange={(e) => { setCreateRuleTenant(e.target.value); if (e.target.value) setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; }); }}
                      bg="white"
                      placeholder="Select tenant"
                      isDisabled={isLoadingTenants}
                    >
                      {tenants.map((t) => (
                        <option key={t.tenant_id} value={t.tenant_id}>{t.organization_name || t.tenant_id}</option>
                      ))}
                    </Select>
                    <FormErrorMessage>{createRuleErrors.tenant}</FormErrorMessage>
                  </FormControl>
                )}
              </VStack>

              <Divider mb={6} />

              {/* ── Delivery Channel ── */}
              <VStack spacing={2} align="stretch" pb={6}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">Delivery Channel</FormLabel>
                  <Box
                    bg="gray.50"
                    border="1px solid"
                    borderColor="gray.200"
                    borderRadius="md"
                    px={4}
                    py={3}
                    cursor="not-allowed"
                  >
                    <HStack spacing={2}>
                      <LockIcon color="gray.400" boxSize={3} />
                      <Text fontSize="sm" color="gray.400" fontWeight="medium">Email</Text>
                    </HStack>
                  </Box>
                  <Text fontSize="xs" color="gray.500" mt={1}>Email delivery is automatically configured. Additional channels coming soon.</Text>
                </FormControl>
              </VStack>

            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => { rules.closeCreate(); resetCreateRuleExtras(); }} isDisabled={rules.isCreating}>Cancel</Button>
            <Button colorScheme="orange" onClick={validateAndCreate} isLoading={rules.isCreating} loadingText="Saving...">Save Routing Rule</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── View Routing Rule Drawer ── */}
      <Drawer isOpen={rules.isViewOpen} onClose={rules.closeView} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">View Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            {rules.viewItem && (() => {
              const item = rules.viewItem;
              const firstName = item.alert_names?.[0];
              const linkedDef = firstName
                ? (defs.definitions.find((d) => d.name === firstName) ?? null)
                : null;
              const category = item.category ?? linkedDef?.category ?? null;
              const severity = item.severity ?? linkedDef?.severity ?? null;
              const sevColors =
                severity === "critical" ? { bg: "red.100", color: "red.700", border: "red.300" }
                : severity === "warning" ? { bg: "yellow.100", color: "yellow.700", border: "yellow.300" }
                : severity === "info" ? { bg: "blue.100", color: "blue.700", border: "blue.300" }
                : { bg: "gray.100", color: "gray.600", border: "gray.300" };
              const catColor = category === "application" ? "orange" : category === "infrastructure" ? "purple" : "gray";
              return (
                <VStack spacing={0} align="stretch">

                  {/* Rule Name */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={1}>Rule Name</Text>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.800">{item.rule_name ?? item.receiver_name}</Text>
                  </Box>

                  <Divider mb={5} />

                  {/* Category + Severity */}
                  <SimpleGrid columns={2} spacing={5} pb={5}>
                    <Box>
                      <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Category</Text>
                      {category ? (
                        <Badge colorScheme={catColor} variant="subtle" textTransform="capitalize" fontSize="xs" px={2} py={0.5} borderRadius="full">{category}</Badge>
                      ) : (
                        <Text fontSize="sm" color="gray.400">—</Text>
                      )}
                    </Box>
                    <Box>
                      <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Severity</Text>
                      {severity ? (
                        <Box
                          display="inline-block"
                          bg={sevColors.bg}
                          color={sevColors.color}
                          fontSize="xs"
                          fontWeight="semibold"
                          px={2}
                          py={0.5}
                          borderRadius="full"
                          textTransform="capitalize"
                          border="1px solid"
                          borderColor={sevColors.border}
                        >{severity}</Box>
                      ) : (
                        <Text fontSize="sm" color="gray.400">—</Text>
                      )}
                    </Box>
                  </SimpleGrid>

                  {/* Alert Definition */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Alert Definition</Text>
                    {item.alert_names && item.alert_names.length > 0 ? (
                      <VStack spacing={1} align="stretch">
                        {item.alert_names.map((name) => (
                          <Text key={name} fontSize="sm" color="gray.700">{name}</Text>
                        ))}
                      </VStack>
                    ) : (() => {
                      const matchCount = defs.definitions.filter(
                        (d) => (!category || d.category === category) && (!severity || d.severity === severity)
                      ).length;
                      const hasFilter = category || severity;
                      return (
                        <HStack spacing={2}>
                          <Text fontSize="sm" color="gray.500">
                            {hasFilter
                              ? `All matching definitions`
                              : "All definitions"}
                          </Text>
                          {matchCount > 0 && (
                            <Badge colorScheme="gray" variant="subtle" fontSize="xs">{matchCount}</Badge>
                          )}
                        </HStack>
                      );
                    })()}
                  </Box>

                  <Divider mb={5} />

                  {/* Scope */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Scope</Text>
                    {item.tenant ? (
                      <HStack spacing={1.5}>
                        <Text fontSize="sm" color="gray.700" fontWeight="medium">Specific Tenant</Text>
                        <Text fontSize="sm" color="gray.400">—</Text>
                        <Badge colorScheme="purple" variant="subtle" textTransform="none" fontSize="xs">{item.tenant}</Badge>
                      </HStack>
                    ) : (
                      <HStack spacing={1.5}>
                        <Badge colorScheme="gray" variant="subtle" fontSize="xs" textTransform="none">Global</Badge>
                        <Text fontSize="xs" color="gray.400">All tenants</Text>
                      </HStack>
                    )}
                  </Box>

                  {/* Notify — only show when there is meaningful recipient info */}
                  {((item.rbac_role && item.tenant) || (item.email_to && item.email_to.length > 0)) && (
                    <Box pb={5}>
                      <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Notify</Text>
                      {item.rbac_role && item.tenant ? (
                        <HStack spacing={1.5}>
                          <Badge colorScheme="blue" variant="subtle" fontSize="xs" textTransform="capitalize">{item.rbac_role}</Badge>
                          <Text fontSize="sm" color="gray.400">—</Text>
                          <Text fontSize="sm" color="gray.600" fontWeight="medium">{item.tenant}</Text>
                        </HStack>
                      ) : (
                        <Wrap spacing={1}>
                          {(item.email_to ?? []).map((e) => (
                            <WrapItem key={e}><Badge colorScheme="blue" variant="subtle" fontSize="xs">{e}</Badge></WrapItem>
                          ))}
                        </Wrap>
                      )}
                    </Box>
                  )}

                  <Divider mb={5} />

                  {/* Delivery Channel */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Delivery Channel</Text>
                    <HStack spacing={2}>
                      <LockIcon color="gray.400" boxSize={3} />
                      <Text fontSize="sm" color="gray.700" fontWeight="medium">Email</Text>
                    </HStack>
                  </Box>

                  {/* Status */}
                  <Box>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Status</Text>
                    <Badge
                      colorScheme={item.enabled ? "green" : "gray"}
                      variant="subtle"
                      fontSize="xs"
                      px={2}
                      py={0.5}
                      borderRadius="full"
                    >{item.enabled ? "Active" : "Inactive"}</Badge>
                  </Box>

                </VStack>
              );
            })()}
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => {
                rules.closeView();
                if (rules.viewItem) {
                  defs.fetchDefinitions();
                  fetchTenants();
                  resetEditRuleExtras();
                  initEditRuleExtras(rules.viewItem);
                  rules.openUpdate(rules.viewItem);
                }
              }}>Edit</Button>
            <Button onClick={rules.closeView}>Close</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── Update Routing Rule Drawer ── */}
      <Drawer isOpen={rules.isUpdateOpen} onClose={() => { rules.closeUpdate(); resetEditRuleExtras(); }} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Edit Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={0} align="stretch">

              {/* ── Rule Name ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!editRuleErrors.ruleName}>
                  <FormLabel fontWeight="semibold" fontSize="sm">Rule Name *</FormLabel>
                  <Input
                    value={rules.updateForm.rule_name ?? ""}
                    onChange={(e) => {
                      rules.setUpdateForm({ ...rules.updateForm, rule_name: e.target.value });
                      if (e.target.value.trim()) setEditRuleErrors((prev) => { const n = { ...prev }; delete n.ruleName; return n; });
                    }}
                    bg="white"
                    placeholder="e.g. Route Critical ASR Alerts"
                  />
                  <FormErrorMessage>{editRuleErrors.ruleName}</FormErrorMessage>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Category + Severity + Alert Definition ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                  <OptionSelector
                    options={CATEGORIES}
                    value={editRuleCategory}
                    onChange={(v) => {
                      setEditRuleCategory(v);
                      setEditRuleDef("");
                      rules.setUpdateForm({ ...rules.updateForm, category: v || null, alert_names: null });
                    }}
                  />
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                  <HStack spacing={2}>
                    {SEVERITIES.map((s) => {
                      const isActive = editRuleSeverity === s;
                      const colors = s === "critical"
                        ? { activeBg: "red.100", activeBorder: "red.600", activeText: "red.700", hoverBg: "red.50" }
                        : s === "warning"
                        ? { activeBg: "yellow.100", activeBorder: "yellow.600", activeText: "yellow.700", hoverBg: "yellow.50" }
                        : { activeBg: "blue.100", activeBorder: "blue.600", activeText: "blue.700", hoverBg: "blue.50" };
                      return (
                        <Box
                          key={s}
                          as="button"
                          type="button"
                          flex="1"
                          py={2}
                          px={3}
                          fontSize="sm"
                          fontWeight="semibold"
                          textAlign="center"
                          cursor="pointer"
                          borderRadius="full"
                          borderWidth="2px"
                          borderColor={isActive ? colors.activeBorder : "gray.200"}
                          bg={isActive ? colors.activeBg : "white"}
                          color={isActive ? colors.activeText : "gray.500"}
                          _hover={{ bg: isActive ? colors.activeBg : colors.hoverBg, borderColor: colors.activeBorder }}
                          transition="all 0.15s"
                          onClick={() => {
                            setEditRuleSeverity(s);
                            setEditRuleDef("");
                            rules.setUpdateForm({ ...rules.updateForm, severity: s, alert_names: null });
                          }}
                          textTransform="capitalize"
                        >
                          {s}
                        </Box>
                      );
                    })}
                  </HStack>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Alert Definition</FormLabel>
                  {(() => {
                    const cat = editRuleCategory;
                    const sev = editRuleSeverity;
                    const filtered = defs.definitions.filter((d) =>
                      (!cat || d.category === cat) && (!sev || d.severity === sev)
                    );
                    const displayDefs = cat || sev ? filtered : defs.definitions;
                    return (
                      <Select
                        bg="white"
                        value={editRuleDef}
                        onChange={(e) => {
                          setEditRuleDef(e.target.value);
                          const chosen = defs.definitions.find((d) => String(d.id) === e.target.value);
                          rules.setUpdateForm({
                            ...rules.updateForm,
                            alert_names: chosen ? [chosen.name] : null,
                            category: chosen ? chosen.category : (rules.updateForm.category ?? null),
                            severity: chosen ? chosen.severity : (rules.updateForm.severity ?? null),
                          });
                        }}
                        placeholder={displayDefs.length === 0 ? "No definitions match" : `${displayDefs.length} alert definition${displayDefs.length !== 1 ? "s" : ""} affected`}
                      >
                        {displayDefs.map((d) => (
                          <option key={d.id} value={String(d.id)}>{d.name}</option>
                        ))}
                      </Select>
                    );
                  })()}
                  <Text fontSize="xs" color="gray.500" mt={1}>Filter by category/severity, then select a specific definition (optional).</Text>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Scope ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">Scope *</FormLabel>
                  <Select
                    value={editRuleScope}
                    onChange={(e) => {
                      const v = e.target.value as "global" | "specific_tenant";
                      setEditRuleScope(v);
                      if (v === "global") {
                        rules.setUpdateForm({ ...rules.updateForm, tenant: null });
                        setEditRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; });
                      } else {
                        rules.setUpdateForm({ ...rules.updateForm, tenant: rules.updateItem?.tenant ?? "" });
                      }
                    }}
                    bg="white"
                  >
                    <option value="global">Global</option>
                    <option value="specific_tenant">Specific Tenant</option>
                  </Select>
                </FormControl>
                {editRuleScope === "specific_tenant" && (
                  <FormControl isRequired isInvalid={!!editRuleErrors.tenant}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Target Tenant *</FormLabel>
                    <Select
                      value={rules.updateForm.tenant ?? ""}
                      onChange={(e) => {
                        rules.setUpdateForm({ ...rules.updateForm, tenant: e.target.value || null });
                        if (e.target.value) setEditRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; });
                      }}
                      bg="white"
                      placeholder="Select tenant"
                      isDisabled={isLoadingTenants}
                    >
                      {tenants.map((t) => (
                        <option key={t.tenant_id} value={t.tenant_id}>{t.organization_name || t.tenant_id}</option>
                      ))}
                    </Select>
                    <FormErrorMessage>{editRuleErrors.tenant}</FormErrorMessage>
                  </FormControl>
                )}
              </VStack>

              <Divider mb={6} />

              {/* ── Delivery Channel ── */}
              <VStack spacing={2} align="stretch" pb={6}>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Delivery Channel</FormLabel>
                  <Box
                    bg="gray.50"
                    border="1px solid"
                    borderColor="gray.200"
                    borderRadius="md"
                    px={4}
                    py={3}
                    cursor="not-allowed"
                  >
                    <HStack spacing={2}>
                      <LockIcon color="gray.400" boxSize={3} />
                      <Text fontSize="sm" color="gray.400" fontWeight="medium">Email</Text>
                    </HStack>
                  </Box>
                  <Text fontSize="xs" color="gray.500" mt={1}>Email delivery is automatically configured. Additional channels coming soon.</Text>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Status ── */}
              <VStack spacing={2} align="stretch">
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">Status *</FormLabel>
                  <HStack>
                    <Switch
                      isChecked={rules.updateForm.enabled ?? true}
                      onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, enabled: e.target.checked })}
                      colorScheme="green"
                    />
                    <Text fontSize="sm">Enable this rule</Text>
                  </HStack>
                </FormControl>
              </VStack>

            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button
              variant="outline"
              mr={3}
              onClick={() => { rules.closeUpdate(); resetEditRuleExtras(); }}
              isDisabled={rules.isUpdating}
            >
              Cancel
            </Button>
            <Button
              colorScheme="orange"
              isLoading={rules.isUpdating}
              loadingText="Saving..."
              onClick={() => {
                const errors: Record<string, string> = {};
                if (!rules.updateForm.rule_name?.trim()) errors.ruleName = "Rule name is required.";
                if (editRuleScope === "specific_tenant" && !rules.updateForm.tenant) errors.tenant = "Please select a target tenant.";
                setEditRuleErrors(errors);
                if (Object.keys(errors).length > 0) return;
                rules.handleUpdate();
              }}
            >
              Save Changes
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── Delete Routing Rule Dialog ── */}
      <AlertDialog isOpen={rules.isDeleteOpen} leastDestructiveRef={ruleDeleteRef} onClose={rules.closeDelete}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">Delete Routing Rule</AlertDialogHeader>
            <AlertDialogBody><Text>Are you sure you want to delete &quot;{rules.deleteItem?.rule_name}&quot;? This action cannot be undone.</Text></AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={ruleDeleteRef} onClick={rules.closeDelete} isDisabled={rules.isDeleting}>Cancel</Button>
              <Button colorScheme="red" onClick={rules.handleDelete} ml={3} isLoading={rules.isDeleting} loadingText="Deleting...">Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );

  // ═══════════════════════════════════════════════
  //  MAIN RENDER — underline tabs with yellow indicator
  // ═══════════════════════════════════════════════
  return (
    <Box>
      <Tabs
        variant="unstyled"
        index={subTabIndex}
        onChange={setSubTabIndex}
        mb={6}
      >
        <TabList borderBottom="2px solid" borderColor="gray.200">
          {["Alert Definitions", "Alert Routing"].map(
            (label, idx) => (
              <Tab
                key={label}
                fontWeight="semibold"
                fontSize="md"
                color={subTabIndex === idx ? "gray.800" : "gray.500"}
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
                  bg: subTabIndex === idx ? "orange.500" : "transparent",
                  transition: "background 0.2s",
                }}
                _hover={{ color: "gray.700" }}
                _focus={{ boxShadow: "none" }}
                transition="color 0.2s"
              >
                {label}
              </Tab>
            )
          )}
        </TabList>
        <TabPanels>
          <TabPanel px={0} pt={6}>{renderDefinitionsSection()}</TabPanel>
          <TabPanel px={0} pt={6}>
            <VStack spacing={8} align="stretch">
              {/* {renderReceiversSection()} */}
              {renderRoutingRulesSection()}
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
