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
  Radio,
  RadioGroup,
  Stack,
  Tooltip,
  InputGroup,
  InputLeftElement,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, ViewIcon, EditIcon, SearchIcon } from "@chakra-ui/icons";
import { useAlertDefinitions } from "./hooks/useAlertDefinitions";
import { useNotificationReceivers } from "./hooks/useNotificationReceivers";
import { useRoutingRules } from "./hooks/useRoutingRules";
import {
  CATEGORIES,
  SEVERITIES,
  URGENCIES,
  RBAC_ROLES,
} from "../../types/alerting";

const EVAL_INTERVALS = ["15s", "30s", "1m", "5m"] as const;
const FOR_DURATIONS = ["1m", "2m", "5m", "10m"] as const;
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
const THRESHOLD_UNITS = ["seconds", "percentage"] as const;

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
    <HStack spacing={0} borderWidth="1px" borderColor="gray.200" borderRadius="md" overflow="hidden">
      {options.map((opt) => (
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
          bg={value === opt ? "orange.500" : "white"}
          color={value === opt ? "white" : "gray.600"}
          borderRight="1px solid"
          borderRightColor="gray.200"
          _last={{ borderRight: "none" }}
          _hover={{ bg: value === opt ? "orange.600" : "gray.50" }}
          transition="all 0.15s"
          onClick={() => onChange(opt)}
          textTransform="capitalize"
        >
          {opt}
        </Box>
      ))}
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
  const [createRuleRole, setCreateRuleRole] = useState("");
  const [updateRuleRole, setUpdateRuleRole] = useState("");
  const [createRuleDef, setCreateRuleDef] = useState("");
  const [updateRuleDef, setUpdateRuleDef] = useState("");
  const [viewRuleDef, setViewRuleDef] = useState("");

  const defs = useAlertDefinitions();
  const recvs = useNotificationReceivers();
  const rules = useRoutingRules();

  const defDeleteRef = useRef<HTMLButtonElement>(null);
  const recvDeleteRef = useRef<HTMLButtonElement>(null);
  const ruleDeleteRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isActive) {
      defs.fetchDefinitions();
      recvs.fetchReceivers();
      rules.fetchRules();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive]);

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
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
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
                      <Th>Alert Definition</Th>
                      <Th>Category</Th>
                      <Th>Alert Type</Th>
                      <Th>Severity</Th>
                      <Th>Status</Th>
                      <Th>Created On</Th>
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
                        <Td><Text fontSize="sm">{alertTypeLabel(d.alert_type)}</Text></Td>
                        <Td><Badge colorScheme={severityColor(d.severity)} textTransform="capitalize">{d.severity}</Badge></Td>
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
            <VStack spacing={6} align="stretch">
              {/* ── Identity ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Identity</Text>
                <VStack spacing={4} align="stretch">
                  <FormControl isRequired isInvalid={!!defs.createErrors?.name}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Alert Definition Name</FormLabel>
                    <Input
                      placeholder="e.g. HighLatency-ASR-Production"
                      value={defs.createForm.name}
                      onChange={(e) => defs.setCreateForm({ ...defs.createForm, name: e.target.value })}
                      bg="white"
                    />
                    <FormErrorMessage>{defs.createErrors?.name}</FormErrorMessage>
                  </FormControl>
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">Description</FormLabel>
                    <Textarea
                      placeholder="Optional description..."
                      value={defs.createForm.description ?? ""}
                      onChange={(e) => defs.setCreateForm({ ...defs.createForm, description: e.target.value || null })}
                      bg="white"
                      rows={3}
                    />
                  </FormControl>
                  <FormControl isRequired isInvalid={!!defs.createErrors?.category}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                    <OptionSelector
                      options={CATEGORIES}
                      value={defs.createForm.category ?? "application"}
                      onChange={(v) => defs.setCreateForm({ ...defs.createForm, category: v, alert_type: null })}
                    />
                    <FormErrorMessage>{defs.createErrors?.category}</FormErrorMessage>
                  </FormControl>
                  <FormControl isRequired isInvalid={!!defs.createErrors?.severity}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                    <OptionSelector
                      options={SEVERITIES}
                      value={defs.createForm.severity}
                      onChange={(v) => defs.setCreateForm({ ...defs.createForm, severity: v })}
                    />
                    <FormErrorMessage>{defs.createErrors?.severity}</FormErrorMessage>
                  </FormControl>
                </VStack>
              </Box>

              <Divider />

              {/* ── Detection ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Detection</Text>
                <VStack spacing={4} align="stretch">
                  <FormControl isRequired isInvalid={!!defs.createErrors?.alert_type}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Alert Type</FormLabel>
                    <Select
                      value={defs.createForm.alert_type ?? ""}
                      onChange={(e) => defs.setCreateForm({ ...defs.createForm, alert_type: e.target.value || null })}
                      bg="white"
                      placeholder="Select alert type..."
                    >
                      {(ALERT_TYPES_BY_CATEGORY[defs.createForm.category ?? "application"] || []).map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </Select>
                    <FormErrorMessage>{defs.createErrors?.alert_type}</FormErrorMessage>
                  </FormControl>
                  <FormControl isRequired isInvalid={!!defs.createErrors?.threshold_value}>
                    <FormLabel fontWeight="semibold" fontSize="sm">Threshold Configuration</FormLabel>
                    <SimpleGrid columns={2} spacing={3}>
                      <NumberInput
                        value={defs.createForm.promql_expr}
                        onChange={(val) => defs.setCreateForm({ ...defs.createForm, promql_expr: val })}
                        min={0}
                        bg="white"
                      >
                        <NumberInputField placeholder="Enter value (e.g., 500, 85, 95)" />
                        <NumberInputStepper>
                          <NumberIncrementStepper />
                          <NumberDecrementStepper />
                        </NumberInputStepper>
                      </NumberInput>
                      <Select value={defs.createForm.scope ?? "seconds"} onChange={(e) => defs.setCreateForm({ ...defs.createForm, scope: e.target.value })} bg="white">
                        {THRESHOLD_UNITS.map((u) => (<option key={u} value={u}>{u.charAt(0).toUpperCase() + u.slice(1)}</option>))}
                      </Select>
                    </SimpleGrid>
                    <FormErrorMessage>{defs.createErrors?.threshold_value}</FormErrorMessage>
                  </FormControl>
                  <SimpleGrid columns={2} spacing={4}>
                    <FormControl isRequired>
                      <FormLabel fontWeight="semibold" fontSize="sm">Evaluation Interval</FormLabel>
                      <Select value={defs.createForm.evaluation_interval ?? "30s"} onChange={(e) => defs.setCreateForm({ ...defs.createForm, evaluation_interval: e.target.value })} bg="white">
                        {EVAL_INTERVALS.map((v) => (<option key={v} value={v}>{v}</option>))}
                      </Select>
                      <Text fontSize="xs" color="gray.500" mt={1}>How often to check this condition</Text>
                    </FormControl>
                    <FormControl isRequired>
                      <FormLabel fontWeight="semibold" fontSize="sm">For Duration</FormLabel>
                      <Select value={defs.createForm.for_duration ?? "5m"} onChange={(e) => defs.setCreateForm({ ...defs.createForm, for_duration: e.target.value })} bg="white">
                        {FOR_DURATIONS.map((v) => (<option key={v} value={v}>{v}</option>))}
                      </Select>
                      <Text fontSize="xs" color="gray.500" mt={1}>How long the condition must persist before triggering</Text>
                    </FormControl>
                  </SimpleGrid>
                </VStack>
              </Box>

              <Divider />

              {/* ── Status ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Status</Text>
                <FormControl isRequired>
                  <RadioGroup value={(defs.createForm.enabled !== false) ? "active" : "inactive"} onChange={(val) => defs.setCreateForm({ ...defs.createForm, enabled: val === "active" })}>
                    <HStack spacing={4}>
                      <Radio value="active" colorScheme="green">
                        <Text fontSize="sm" fontWeight="medium">Active</Text>
                      </Radio>
                      <Radio value="inactive" colorScheme="gray">
                        <Text fontSize="sm" fontWeight="medium">Inactive</Text>
                      </Radio>
                    </HStack>
                  </RadioGroup>
                </FormControl>
              </Box>
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
            {defs.viewItem && (
              <VStack spacing={5} align="stretch">
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Name</Text>
                  <Text fontWeight="medium">{defs.viewItem.name}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Description</Text>
                  <Text>{defs.viewItem.description || "—"}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Category</Text>
                  <Text>{titleCase(defs.viewItem.category)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Severity</Text>
                  <Badge colorScheme={severityColor(defs.viewItem.severity)} textTransform="capitalize">{defs.viewItem.severity}</Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Alert Type</Text>
                  <Text>{alertTypeLabel(defs.viewItem.alert_type)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Threshold</Text>
                  <Text>{formatThreshold(defs.viewItem)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Eval Interval</Text>
                  <Text fontFamily="mono">{defs.viewItem.evaluation_interval}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>For Duration</Text>
                  <Text fontFamily="mono">{defs.viewItem.for_duration}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Status</Text>
                  <Badge colorScheme={defs.viewItem.enabled ? "green" : "gray"} variant="subtle" fontSize="sm" px={2} py={0.5} borderRadius="full">{defs.viewItem.enabled ? "Active" : "Inactive"}</Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Created On</Text>
                  <Text fontSize="sm">{new Date(defs.viewItem.created_at).toLocaleDateString()}</Text>
                </Box>
              </VStack>
            )}
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
            <VStack spacing={6} align="stretch">
              {/* ── Identity ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Identity</Text>
                <VStack spacing={4} align="stretch">
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
                      onChange={(v) => defs.setUpdateForm({ ...defs.updateForm, category: v, alert_type: null })}
                    />
                  </FormControl>
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                    <OptionSelector
                      options={SEVERITIES}
                      value={defs.updateForm.severity ?? "warning"}
                      onChange={(v) => defs.setUpdateForm({ ...defs.updateForm, severity: v })}
                    />
                  </FormControl>
                </VStack>
              </Box>

              <Divider />

              {/* ── Detection ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Detection</Text>
                <VStack spacing={4} align="stretch">
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Alert Type</FormLabel>
                    <Select
                      value={defs.updateForm.alert_type ?? ""}
                      onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, alert_type: e.target.value || null })}
                      bg="white"
                      placeholder="Select alert type..."
                    >
                      {(ALERT_TYPES_BY_CATEGORY[defs.updateForm.category ?? "application"] || []).map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Threshold Configuration</FormLabel>
                    <SimpleGrid columns={2} spacing={3}>
                      <NumberInput
                        value={defs.updateForm.promql_expr ?? ""}
                        onChange={(val) => defs.setUpdateForm({ ...defs.updateForm, promql_expr: val })}
                        min={0}
                        bg="white"
                      >
                        <NumberInputField placeholder="Enter value (e.g., 500, 85, 95)" />
                        <NumberInputStepper>
                          <NumberIncrementStepper />
                          <NumberDecrementStepper />
                        </NumberInputStepper>
                      </NumberInput>
                      <Select value={defs.updateForm.scope ?? "seconds"} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, scope: e.target.value })} bg="white">
                        {THRESHOLD_UNITS.map((u) => (<option key={u} value={u}>{u.charAt(0).toUpperCase() + u.slice(1)}</option>))}
                      </Select>
                    </SimpleGrid>
                  </FormControl>
                  <SimpleGrid columns={2} spacing={4}>
                    <FormControl isRequired>
                      <FormLabel fontWeight="semibold" fontSize="sm">Evaluation Interval</FormLabel>
                      <Select value={defs.updateForm.evaluation_interval ?? "30s"} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, evaluation_interval: e.target.value })} bg="white">
                        {EVAL_INTERVALS.map((v) => (<option key={v} value={v}>{v}</option>))}
                      </Select>
                      <Text fontSize="xs" color="gray.500" mt={1}>How often to check this condition</Text>
                    </FormControl>
                    <FormControl isRequired>
                      <FormLabel fontWeight="semibold" fontSize="sm">For Duration</FormLabel>
                      <Select value={defs.updateForm.for_duration ?? "5m"} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, for_duration: e.target.value })} bg="white">
                        {FOR_DURATIONS.map((v) => (<option key={v} value={v}>{v}</option>))}
                      </Select>
                      <Text fontSize="xs" color="gray.500" mt={1}>How long the condition must persist before triggering</Text>
                    </FormControl>
                  </SimpleGrid>
                </VStack>
              </Box>

              <Divider />

              {/* ── Status ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Status</Text>
                <FormControl isRequired>
                  <RadioGroup value={(defs.updateForm.enabled ?? true) ? "active" : "inactive"} onChange={(val) => defs.setUpdateForm({ ...defs.updateForm, enabled: val === "active" })}>
                    <HStack spacing={4}>
                      <Radio value="active" colorScheme="green">
                        <Text fontSize="sm" fontWeight="medium">Active</Text>
                      </Radio>
                      <Radio value="inactive" colorScheme="gray">
                        <Text fontSize="sm" fontWeight="medium">Inactive</Text>
                      </Radio>
                    </HStack>
                  </RadioGroup>
                </FormControl>
              </Box>
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
                <Input value={recvs.updateForm.receiver_name ?? ""} onChange={(e) => recvs.setUpdateForm({ ...recvs.updateForm, receiver_name: e.target.value })} bg="white" />
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
            <Select size="sm" maxW="140px" value={rules.filterRole} onChange={(e) => rules.setFilterRole(e.target.value)} bg="white">
              <option value="all">Role</option>
              {RBAC_ROLES.map((role) => (
                <option key={role} value={role}>{titleCase(role)}</option>
              ))}
            </Select>
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
              onClick={() => { rules.setSearchQuery(""); rules.setFilterRole("all"); rules.setFilterEnabled("all"); }}
              isDisabled={!rules.searchQuery && rules.filterRole === "all" && rules.filterEnabled === "all"}
            >
              Reset Filters
            </Button>
            <Button
              size="sm"
              colorScheme="orange"
              leftIcon={<AddIcon />}
              onClick={() => { setCreateRuleRole(""); defs.fetchDefinitions(); rules.openCreate(); }}
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
        ) : rules.filteredReceivers.filter((rv) => rules.getRuleForReceiver(rv.id)).length > 0 ? (
          <TableContainer>
            <Table variant="simple" size="sm" w="100%">
              <Thead>
                <Tr>
                  <Th>Rule Name</Th>
                  <Th>Category</Th>
                  <Th>Severity</Th>
                  <Th>Definitions</Th>
                  <Th>Assigned Role</Th>
                  <Th>Status</Th>
                  <Th>Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {rules.filteredReceivers.filter((rv) => rules.getRuleForReceiver(rv.id)).map((rv) => {
                  const linkedRule = rules.getRuleForReceiver(rv.id);
                  const parts = rv.receiver_name.split("-");
                  const rowSeverity = linkedRule?.match_severity || (parts.length >= 1 ? parts[0] : null);
                  const rowCategory = linkedRule?.match_category || (parts.length >= 2 ? parts[1] : null);
                  const matchingDefs = defs.definitions.filter(
                    (d) =>
                      (!rowCategory || d.category === rowCategory) &&
                      (!rowSeverity || d.severity === rowSeverity)
                  );
                  return (
                    <Tr
                      key={rv.id}
                      _hover={{ bg: "gray.50", "& .row-actions": { opacity: 1 } }}
                      transition="background 0.15s"
                    >
                      <Td fontWeight="semibold">{linkedRule?.rule_name ?? <Text as="span" color="gray.400" fontStyle="italic">—</Text>}</Td>
                      <Td><Badge colorScheme={categoryColor(rowCategory)} textTransform="capitalize">{rowCategory ?? "All"}</Badge></Td>
                      <Td>{rowSeverity ? <Badge colorScheme={severityColor(rowSeverity)} textTransform="capitalize">{rowSeverity}</Badge> : <Text fontSize="sm" color="gray.500">All</Text>}</Td>
                      <Td>
                        {matchingDefs.length > 0 ? (
                          <Text fontSize="sm" color="gray.700">
                            {matchingDefs.slice(0, 2).map((d) => d.name).join(", ")}
                            {matchingDefs.length > 2 ? ` +${matchingDefs.length - 2}` : ""}
                          </Text>
                        ) : (
                          <Text fontSize="sm" color="gray.500">—</Text>
                        )}
                      </Td>
                      <Td>{rv.rbac_role ? <Badge colorScheme="purple">{titleCase(rv.rbac_role)}</Badge> : <Text fontSize="sm" color="gray.500">—</Text>}</Td>
                      <Td>
                        <Badge colorScheme={rv.enabled ? "green" : "gray"} variant="subtle" fontSize="xs" px={2} py={0.5} borderRadius="full">
                          {rv.enabled ? "Active" : "Inactive"}
                        </Badge>
                      </Td>
                      <Td>
                        <HStack spacing={1} className="row-actions" opacity={0} transition="opacity 0.15s">
                          <Tooltip label="View" placement="top" hasArrow>
                            <IconButton aria-label="View" icon={<ViewIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "blue.500", bg: "blue.50" }} onClick={() => { setViewRuleDef(""); defs.fetchDefinitions(); if (linkedRule) rules.openView(linkedRule); }} />
                          </Tooltip>
                          <Tooltip label="Edit" placement="top" hasArrow>
                            <IconButton aria-label="Edit" icon={<EditIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "green.500", bg: "green.50" }} onClick={() => { setUpdateRuleRole(rv.rbac_role ?? ""); setUpdateRuleDef(""); defs.fetchDefinitions(); if (linkedRule) rules.openUpdate(linkedRule); }} />
                          </Tooltip>
                          <Tooltip label="Delete" placement="top" hasArrow>
                            <IconButton aria-label="Delete" icon={<DeleteIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "red.500", bg: "red.50" }} onClick={() => { if (linkedRule) rules.openDelete(linkedRule); }} />
                          </Tooltip>
                        </HStack>
                      </Td>
                    </Tr>
                  );
                })}
              </Tbody>
            </Table>
          </TableContainer>
        ) : (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>
              {rules.receivers.length === 0
                ? "No alert routing configured. Click 'Create Routing Rule' to add one."
                : "No entries match the current filters."}
            </AlertDescription>
          </Alert>
        )}
      </VStack>
      </Box>

      {/* ── Create Routing Rule Drawer ── */}
      <Drawer isOpen={rules.isCreateOpen} onClose={rules.closeCreate} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Create Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={6} align="stretch">
              {/* ── Identity ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Identity</Text>
                <VStack spacing={4} align="stretch">
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Rule Name</FormLabel>
                    <Input placeholder="e.g. Critical-to-SRE" value={rules.createForm.rule_name} onChange={(e) => rules.setCreateForm({ ...rules.createForm, rule_name: e.target.value })} bg="white" />
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                    <OptionSelector
                      options={CATEGORIES}
                      value={rules.createForm.match_category ?? "application"}
                      onChange={(v) => rules.setCreateForm({ ...rules.createForm, match_category: v })}
                    />
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                    <OptionSelector
                      options={SEVERITIES}
                      value={rules.createForm.match_severity ?? "critical"}
                      onChange={(v) => rules.setCreateForm({ ...rules.createForm, match_severity: v })}
                    />
                  </FormControl>
                </VStack>
              </Box>

              <Divider />

              {/* ── Alert Definitions Preview ── */}
              <Box>
                <HStack justify="space-between" mb={3}>
                  <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider">View Alert Definitions</Text>
                  <Badge colorScheme="orange" fontSize="xs" borderRadius="full" px={2}>{defs.definitions.filter((d) => (!rules.createForm.match_category || d.category === rules.createForm.match_category) && (!rules.createForm.match_severity || d.severity === rules.createForm.match_severity)).length}</Badge>
                </HStack>
                {(() => {
                  const matchingDefs = defs.definitions.filter((d) =>
                    (!rules.createForm.match_category || d.category === rules.createForm.match_category) &&
                    (!rules.createForm.match_severity || d.severity === rules.createForm.match_severity)
                  );
                  return (
                    <Select
                      bg="white"
                      size="sm"
                      value={createRuleDef}
                      onChange={(e) => setCreateRuleDef(e.target.value)}
                      placeholder={`${matchingDefs.length} alert definition${matchingDefs.length !== 1 ? "s" : ""}`}
                    >
                      {matchingDefs.map((d) => (
                        <option key={d.id} value={String(d.id)}>{d.name}</option>
                      ))}
                    </Select>
                  );
                })()}
              </Box>

              <Divider />

              {/* ── Assign Role ── */}
              <Box>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">Assign to Role</FormLabel>
                  <Select
                    value={createRuleRole}
                    onChange={(e) => setCreateRuleRole(e.target.value)}
                    bg="white"
                    placeholder="Select a role..."
                  >
                    {RBAC_ROLES.map((role) => (
                      <option key={role} value={role}>{titleCase(role)}</option>
                    ))}
                  </Select>
                  <Text fontSize="xs" color="gray.500" mt={1}>The user with selected role will receive matching alerts.</Text>
                </FormControl>
              </Box>

              <Divider />

              {/* ── Status ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Status</Text>
                <FormControl isRequired>
                  <RadioGroup defaultValue="active">
                    <HStack spacing={4}>
                      <Radio value="active" colorScheme="green">
                        <Text fontSize="sm" fontWeight="medium">Active</Text>
                      </Radio>
                      <Radio value="inactive" colorScheme="gray">
                        <Text fontSize="sm" fontWeight="medium">Inactive</Text>
                      </Radio>
                    </HStack>
                  </RadioGroup>
                </FormControl>
              </Box>
            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={rules.closeCreate} isDisabled={rules.isCreating}>Cancel</Button>
            <Button colorScheme="orange" onClick={() => rules.handleCreate(createRuleRole || undefined)} isLoading={rules.isCreating} loadingText="Saving...">Save Routing Rule</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── View Routing Rule Drawer ── */}
      <Drawer isOpen={rules.isViewOpen} onClose={rules.closeView} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Alert Routing Details</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            {rules.viewItem && (() => {
              const viewReceiver = rules.receivers.find((rv) => rv.id === rules.viewItem!.receiver_id);
              const nameParts = (viewReceiver?.receiver_name ?? "").split("-");
              const viewSeverity = rules.viewItem.match_severity || (nameParts.length >= 1 ? nameParts[0] : null);
              const viewCategory = rules.viewItem.match_category || (nameParts.length >= 2 ? nameParts[1] : null);
              const viewMatchDefs = defs.definitions.filter((d) => (!viewCategory || d.category === viewCategory) && (!viewSeverity || d.severity === viewSeverity));
              return (
                <VStack spacing={5} align="stretch">
                  <Box><Text fontWeight="semibold" color="gray.500" fontSize="xs" mb={1}>Rule Name</Text><Text fontWeight="medium">{rules.viewItem.rule_name}</Text></Box>
                  <Box><Text fontWeight="semibold" color="gray.500" fontSize="xs" mb={1}>Category</Text><Badge colorScheme="purple" textTransform="capitalize">{viewCategory ?? "All"}</Badge></Box>
                  <Box><Text fontWeight="semibold" color="gray.500" fontSize="xs" mb={1}>Severity</Text><Badge colorScheme={viewSeverity ? severityColor(viewSeverity) : "gray"} textTransform="capitalize">{viewSeverity ?? "All"}</Badge></Box>
                  <Box>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" mb={2}>Matching Alert Definitions</Text>
                    {viewMatchDefs.length > 0 ? (
                      <VStack spacing={1} align="stretch">
                        {viewMatchDefs.map((d) => (
                          <HStack key={d.id} spacing={2}>
                            <Text fontSize="sm" color="gray.700">• {d.name}</Text>
                          </HStack>
                        ))}
                      </VStack>
                    ) : (
                      <Text fontSize="sm" color="gray.400">No matching definitions</Text>
                    )}
                  </Box>
                  <Box><Text fontWeight="semibold" color="gray.500" fontSize="xs" mb={1}>Assigned Role</Text><Text fontSize="sm" fontWeight="medium">{viewReceiver?.rbac_role ? titleCase(viewReceiver.rbac_role) : "—"}</Text></Box>
                  <Box>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" mb={1}>Status</Text>
                    <Badge colorScheme={viewReceiver?.enabled ? "green" : "gray"} variant="subtle" fontSize="xs" px={2} py={0.5} borderRadius="full">{viewReceiver?.enabled ? "Active" : "Inactive"}</Badge>
                  </Box>
                </VStack>
              );
            })()}
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => { rules.closeView(); if (rules.viewItem) { const recv = rules.receivers.find((r) => r.id === rules.viewItem!.receiver_id); setUpdateRuleRole(recv?.rbac_role ?? ""); setUpdateRuleDef(""); defs.fetchDefinitions(); rules.openUpdate(rules.viewItem); } }}>Edit</Button>
            <Button onClick={rules.closeView}>Close</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── Update Routing Rule Drawer ── */}
      <Drawer isOpen={rules.isUpdateOpen} onClose={rules.closeUpdate} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Edit Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={6} align="stretch">
              {/* ── Identity ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Identity</Text>
                <VStack spacing={4} align="stretch">
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Rule Name</FormLabel>
                    <Input value={rules.updateForm.rule_name ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, rule_name: e.target.value })} bg="white" />
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                    <OptionSelector
                      options={CATEGORIES}
                      value={rules.updateForm.match_category ?? "application"}
                      onChange={(v) => rules.setUpdateForm({ ...rules.updateForm, match_category: v })}
                    />
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                    <OptionSelector
                      options={SEVERITIES}
                      value={rules.updateForm.match_severity ?? "critical"}
                      onChange={(v) => rules.setUpdateForm({ ...rules.updateForm, match_severity: v })}
                    />
                  </FormControl>
                </VStack>
              </Box>

              <Divider />

              {/* ── Alert Definitions Preview ── */}
              <Box>
                <HStack justify="space-between" mb={3}>
                  <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider">View Alert Definitions</Text>
                  <Badge colorScheme="orange" fontSize="xs" borderRadius="full" px={2}>{defs.definitions.filter((d) => (!rules.updateForm.match_category || d.category === rules.updateForm.match_category) && (!rules.updateForm.match_severity || d.severity === rules.updateForm.match_severity)).length}</Badge>
                </HStack>
                {(() => {
                  const editMatchDefs = defs.definitions.filter((d) =>
                    (!rules.updateForm.match_category || d.category === rules.updateForm.match_category) &&
                    (!rules.updateForm.match_severity || d.severity === rules.updateForm.match_severity)
                  );
                  return (
                    <Select
                      bg="white"
                      size="sm"
                      value={updateRuleDef}
                      onChange={(e) => setUpdateRuleDef(e.target.value)}
                      placeholder={`${editMatchDefs.length} alert definition${editMatchDefs.length !== 1 ? "s" : ""}`}
                    >
                      {editMatchDefs.map((d) => (
                        <option key={d.id} value={String(d.id)}>{d.name}</option>
                      ))}
                    </Select>
                  );
                })()}
              </Box>

              <Divider />

              {/* ── Assign Role ── */}
              <Box>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">Assign to Role</FormLabel>
                  <Select
                    value={updateRuleRole}
                    onChange={(e) => setUpdateRuleRole(e.target.value)}
                    bg="white"
                    placeholder="Select a role..."
                  >
                    {RBAC_ROLES.map((role) => (
                      <option key={role} value={role}>{titleCase(role)}</option>
                    ))}
                  </Select>
                  <Text fontSize="xs" color="gray.500" mt={1}>The user with selected role will receive matching alerts.</Text>
                </FormControl>
              </Box>

              <Divider />

              {/* ── Status ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Status</Text>
                <FormControl isRequired>
                  <RadioGroup value={rules.updateForm.enabled === false ? "inactive" : "active"} onChange={(v) => rules.setUpdateForm({ ...rules.updateForm, enabled: v === "active" })}>
                    <HStack spacing={4}>
                      <Radio value="active" colorScheme="green">
                        <Text fontSize="sm" fontWeight="medium">Active</Text>
                      </Radio>
                      <Radio value="inactive" colorScheme="gray">
                        <Text fontSize="sm" fontWeight="medium">Inactive</Text>
                      </Radio>
                    </HStack>
                  </RadioGroup>
                </FormControl>
              </Box>
            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={rules.closeUpdate} isDisabled={rules.isUpdating}>Cancel</Button>
            <Button colorScheme="orange" onClick={rules.handleUpdate} isLoading={rules.isUpdating} loadingText="Saving...">Save Changes</Button>
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
