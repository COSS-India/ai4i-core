import React, { useRef, useEffect, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
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
const ALERT_TYPES = ["latency", "error_rate", "downtime", "custom"] as const;

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
          bg={value === opt ? "#F9A825" : "white"}
          color={value === opt ? "white" : "gray.600"}
          borderRight="1px solid"
          borderRightColor="gray.200"
          _last={{ borderRight: "none" }}
          _hover={{ bg: value === opt ? "#F9A825" : "gray.50" }}
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

  // ═══════════════════════════════════════════════
  //  ALERT DEFINITIONS SECTION
  // ═══════════════════════════════════════════════
  const renderDefinitionsSection = () => (
    <>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardBody>
          <VStack spacing={5} align="stretch">
            {/* Search + Filters + Actions — single row */}
            <HStack spacing={3} align="flex-end" flexWrap="wrap">
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
                variant="outline"
                colorScheme="gray"
                onClick={defs.resetFilters}
                isDisabled={
                  !defs.searchQuery &&
                  defs.filterSeverity === "all" &&
                  defs.filterCategory === "all" &&
                  defs.filterEnabled === "all"
                }
              >
                Reset
              </Button>
              <Button
                size="sm"
                bg="#F9A825"
                color="white"
                _hover={{ bg: "#F57F17" }}
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
                        <Td><Badge colorScheme="purple" textTransform="capitalize">{d.category}</Badge></Td>
                        <Td><Text fontSize="sm" textTransform="capitalize">{d.alert_type || "—"}</Text></Td>
                        <Td><Badge colorScheme={severityColor(d.severity)} textTransform="capitalize">{d.severity}</Badge></Td>
                        <Td>
                          <Switch
                            size="sm"
                            colorScheme="green"
                            isChecked={d.enabled}
                            isDisabled={defs.togglingId === d.id}
                            onChange={() => defs.handleToggleEnabled(d)}
                          />
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
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Alert Definition Name</FormLabel>
                    <Input
                      placeholder="e.g. HighLatency-ASR-Production"
                      value={defs.createForm.name}
                      onChange={(e) => defs.setCreateForm({ ...defs.createForm, name: e.target.value })}
                      bg="white"
                    />
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
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                    <OptionSelector
                      options={CATEGORIES}
                      value={defs.createForm.category ?? "application"}
                      onChange={(v) => defs.setCreateForm({ ...defs.createForm, category: v })}
                    />
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">Severity</FormLabel>
                    <OptionSelector
                      options={SEVERITIES}
                      value={defs.createForm.severity}
                      onChange={(v) => defs.setCreateForm({ ...defs.createForm, severity: v })}
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
                    <Select value={defs.createForm.alert_type ?? ""} onChange={(e) => defs.setCreateForm({ ...defs.createForm, alert_type: e.target.value || null })} bg="white" placeholder="Select alert type...">
                      {ALERT_TYPES.map((t) => (<option key={t} value={t}>{t}</option>))}
                    </Select>
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel fontWeight="semibold" fontSize="sm">PromQL Expression</FormLabel>
                    <Textarea
                      placeholder="e.g. rate(http_requests_total{status='500'}[5m]) > 0.05"
                      value={defs.createForm.promql_expr}
                      onChange={(e) => defs.setCreateForm({ ...defs.createForm, promql_expr: e.target.value })}
                      bg="white"
                      rows={3}
                      fontFamily="mono"
                      fontSize="sm"
                    />
                    <Text fontSize="xs" color="gray.500" mt={1}>Prometheus query expression to evaluate this alert</Text>
                  </FormControl>
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
                </VStack>
              </Box>

              <Divider />

              {/* ── Status ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Status</Text>
                <FormControl display="flex" alignItems="center">
                  <Switch
                    colorScheme="green"
                    defaultChecked
                    mr={3}
                  />
                  <FormLabel fontWeight="semibold" fontSize="sm" mb={0}>Enable immediately</FormLabel>
                </FormControl>
              </Box>
            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={defs.closeCreate} isDisabled={defs.isCreating}>Cancel</Button>
            <Button bg="#F9A825" color="white" _hover={{ bg: "#F57F17" }} onClick={defs.handleCreate} isLoading={defs.isCreating} loadingText="Saving...">Save Alert Definition</Button>
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
                  <Badge colorScheme="purple" textTransform="capitalize">{defs.viewItem.category}</Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Severity</Text>
                  <Badge colorScheme={severityColor(defs.viewItem.severity)} textTransform="capitalize">{defs.viewItem.severity}</Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Alert Type</Text>
                  <Text textTransform="capitalize">{defs.viewItem.alert_type || "—"}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>PromQL Expression</Text>
                  <Box bg="gray.50" p={3} borderRadius="md" fontFamily="mono" fontSize="sm" whiteSpace="pre-wrap" wordBreak="break-all">{defs.viewItem.promql_expr}</Box>
                </Box>
                <SimpleGrid columns={2} spacing={4}>
                  <Box>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Eval Interval</Text>
                    <Text fontFamily="mono">{defs.viewItem.evaluation_interval}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>For Duration</Text>
                    <Text fontFamily="mono">{defs.viewItem.for_duration}</Text>
                  </Box>
                </SimpleGrid>
                <Box>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>Status</Text>
                  <Badge colorScheme={defs.viewItem.enabled ? "green" : "red"} fontSize="sm" px={2} py={0.5}>{defs.viewItem.enabled ? "Enabled" : "Disabled"}</Badge>
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
            {defs.updateItem && <Text fontSize="sm" color="gray.500" mt={1}>{defs.updateItem.name}</Text>}
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={6} align="stretch">
              {/* ── Identity ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Identity</Text>
                <VStack spacing={4} align="stretch">
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">Description</FormLabel>
                    <Textarea value={defs.updateForm.description ?? ""} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, description: e.target.value || null })} bg="white" rows={3} />
                  </FormControl>
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">Category</FormLabel>
                    <OptionSelector
                      options={CATEGORIES}
                      value={defs.updateForm.category ?? "application"}
                      onChange={(v) => defs.setUpdateForm({ ...defs.updateForm, category: v })}
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
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">Alert Type</FormLabel>
                    <Select value={defs.updateForm.alert_type ?? ""} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, alert_type: e.target.value || null })} bg="white" placeholder="Select alert type...">
                      {ALERT_TYPES.map((t) => (<option key={t} value={t}>{t}</option>))}
                    </Select>
                  </FormControl>
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">PromQL Expression</FormLabel>
                    <Textarea value={defs.updateForm.promql_expr ?? ""} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, promql_expr: e.target.value })} bg="white" rows={3} fontFamily="mono" fontSize="sm" />
                    <Text fontSize="xs" color="gray.500" mt={1}>Prometheus query expression to evaluate this alert</Text>
                  </FormControl>
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">Evaluation Interval</FormLabel>
                    <Select value={defs.updateForm.evaluation_interval ?? "30s"} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, evaluation_interval: e.target.value })} bg="white">
                      {EVAL_INTERVALS.map((v) => (<option key={v} value={v}>{v}</option>))}
                    </Select>
                    <Text fontSize="xs" color="gray.500" mt={1}>How often to check this condition</Text>
                  </FormControl>
                  <FormControl>
                    <FormLabel fontWeight="semibold" fontSize="sm">For Duration</FormLabel>
                    <Select value={defs.updateForm.for_duration ?? "5m"} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, for_duration: e.target.value })} bg="white">
                      {FOR_DURATIONS.map((v) => (<option key={v} value={v}>{v}</option>))}
                    </Select>
                    <Text fontSize="xs" color="gray.500" mt={1}>How long the condition must persist before triggering</Text>
                  </FormControl>
                </VStack>
              </Box>

              <Divider />

              {/* ── Status ── */}
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="gray.400" textTransform="uppercase" letterSpacing="wider" mb={3}>Status</Text>
                <FormControl display="flex" alignItems="center">
                  <Switch isChecked={defs.updateForm.enabled ?? true} onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, enabled: e.target.checked })} colorScheme="green" mr={3} />
                  <FormLabel fontWeight="semibold" fontSize="sm" mb={0}>{defs.updateForm.enabled ? "Enabled" : "Disabled"}</FormLabel>
                </FormControl>
              </Box>
            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={defs.closeUpdate} isDisabled={defs.isUpdating}>Cancel</Button>
            <Button bg="#F9A825" color="white" _hover={{ bg: "#F57F17" }} onClick={defs.handleUpdate} isLoading={defs.isUpdating} loadingText="Saving...">Save Changes</Button>
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
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="gray.700" userSelect="none" cursor="default">
              Routing Rules
            </Heading>
            <HStack spacing={2}>
              <Button size="sm" colorScheme="green" leftIcon={<AddIcon />} onClick={rules.openCreate}>Create</Button>
              <Button size="sm" colorScheme="blue" onClick={rules.fetchRules} isLoading={rules.isLoading} loadingText="Loading...">Refresh</Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <VStack spacing={6} align="stretch">
            <HStack>
              <FormControl maxW="200px">
                <FormLabel fontWeight="semibold">Status</FormLabel>
                <Select value={rules.filterEnabled} onChange={(e) => rules.setFilterEnabled(e.target.value)} bg="white">
                  <option value="all">All</option>
                  <option value="enabled">Enabled</option>
                  <option value="disabled">Disabled</option>
                </Select>
              </FormControl>
            </HStack>

            {rules.isLoading ? (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" color="blue.500" />
                  <Text color="gray.600">Loading routing rules...</Text>
                </VStack>
              </Center>
            ) : rules.filteredRules.length > 0 ? (
              <TableContainer>
                <Table variant="simple" size="sm">
                  <Thead>
                    <Tr>
                      <Th>Rule Name</Th>
                      <Th>Receiver</Th>
                      <Th>Match</Th>
                      <Th>Priority</Th>
                      <Th>Status</Th>
                      <Th>Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {rules.filteredRules.map((r) => (
                      <Tr
                        key={r.id}
                        _hover={{ bg: "gray.50", "& .row-actions": { opacity: 1 } }}
                        transition="background 0.15s"
                      >
                        <Td fontWeight="semibold">{r.rule_name}</Td>
                        <Td fontSize="sm">{rules.getReceiverName(r.receiver_id)}</Td>
                        <Td>
                          <Wrap spacing={1}>
                            {r.match_severity && <WrapItem><Badge colorScheme={severityColor(r.match_severity)} fontSize="xs">{r.match_severity}</Badge></WrapItem>}
                            {r.match_category && <WrapItem><Badge colorScheme="purple" fontSize="xs">{r.match_category}</Badge></WrapItem>}
                            {r.match_alert_type && <WrapItem><Badge colorScheme="gray" fontSize="xs">{r.match_alert_type}</Badge></WrapItem>}
                            {!r.match_severity && !r.match_category && !r.match_alert_type && (<WrapItem><Badge colorScheme="gray" fontSize="xs">all</Badge></WrapItem>)}
                          </Wrap>
                        </Td>
                        <Td>{r.priority}</Td>
                        <Td>
                          <Switch size="sm" colorScheme="green" isChecked={r.enabled} isReadOnly />
                        </Td>
                        <Td>
                          <HStack spacing={1} className="row-actions" opacity={0} transition="opacity 0.15s">
                            <Tooltip label="View" placement="top" hasArrow>
                              <IconButton aria-label="View" icon={<ViewIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "blue.500", bg: "blue.50" }} onClick={() => rules.openView(r)} />
                            </Tooltip>
                            <Tooltip label="Edit" placement="top" hasArrow>
                              <IconButton aria-label="Edit" icon={<EditIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "green.500", bg: "green.50" }} onClick={() => rules.openUpdate(r)} />
                            </Tooltip>
                            <Tooltip label="Delete" placement="top" hasArrow>
                              <IconButton aria-label="Delete" icon={<DeleteIcon />} size="sm" variant="ghost" color="gray.700" _hover={{ color: "red.500", bg: "red.50" }} onClick={() => rules.openDelete(r)} />
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
                    ? "No routing rules found. Click 'Create' to add one."
                    : "No rules match the current filters."}
                </AlertDescription>
              </Alert>
            )}
          </VStack>
        </CardBody>
      </Card>

      {/* ── Create Routing Rule Modal ── */}
      <Modal isOpen={rules.isCreateOpen} onClose={rules.closeCreate} size="xl" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Routing Rule</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Rule Name</FormLabel>
                <Input placeholder="e.g. critical-to-ops-team" value={rules.createForm.rule_name} onChange={(e) => rules.setCreateForm({ ...rules.createForm, rule_name: e.target.value })} bg="white" />
              </FormControl>
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Receiver</FormLabel>
                <Select value={rules.createForm.receiver_id || ""} onChange={(e) => rules.setCreateForm({ ...rules.createForm, receiver_id: parseInt(e.target.value) || 0 })} bg="white" placeholder="Select a receiver">
                  {rules.receivers.map((recv) => (<option key={recv.id} value={recv.id}>{recv.receiver_name} ({recv.organization})</option>))}
                </Select>
              </FormControl>
              <Divider />
              <Heading size="sm" color="gray.600">Match Criteria (optional — leave empty to match all)</Heading>
              <SimpleGrid columns={3} spacing={4}>
                <FormControl>
                  <FormLabel fontWeight="semibold">Severity</FormLabel>
                  <Select value={rules.createForm.match_severity ?? ""} onChange={(e) => rules.setCreateForm({ ...rules.createForm, match_severity: e.target.value || null })} bg="white" placeholder="Any">
                    {SEVERITIES.map((s) => (<option key={s} value={s}>{s}</option>))}
                  </Select>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold">Category</FormLabel>
                  <Select value={rules.createForm.match_category ?? ""} onChange={(e) => rules.setCreateForm({ ...rules.createForm, match_category: e.target.value || null })} bg="white" placeholder="Any">
                    {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                  </Select>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold">Alert Type</FormLabel>
                  <Input placeholder="e.g. latency" value={rules.createForm.match_alert_type ?? ""} onChange={(e) => rules.setCreateForm({ ...rules.createForm, match_alert_type: e.target.value || null })} bg="white" />
                </FormControl>
              </SimpleGrid>
              <Divider />
              <Heading size="sm" color="gray.600">Grouping &amp; Timing</Heading>
              <FormControl>
                <FormLabel fontWeight="semibold">Group By</FormLabel>
                <Wrap spacing={2}>
                  {["alertname", "category", "severity", "organization", "alert_type", "scope"].map((label) => (
                    <WrapItem key={label}>
                      <Checkbox
                        isChecked={(rules.createForm.group_by ?? []).includes(label)}
                        onChange={(e) => {
                          const current = rules.createForm.group_by ?? [];
                          const next = e.target.checked ? [...current, label] : current.filter((g) => g !== label);
                          rules.setCreateForm({ ...rules.createForm, group_by: next });
                        }}
                        colorScheme="blue"
                      ><Text fontSize="sm">{label}</Text></Checkbox>
                    </WrapItem>
                  ))}
                </Wrap>
              </FormControl>
              <SimpleGrid columns={3} spacing={4}>
                <FormControl><FormLabel fontWeight="semibold">Group Wait</FormLabel><Input value={rules.createForm.group_wait ?? "10s"} onChange={(e) => rules.setCreateForm({ ...rules.createForm, group_wait: e.target.value })} bg="white" /></FormControl>
                <FormControl><FormLabel fontWeight="semibold">Group Interval</FormLabel><Input value={rules.createForm.group_interval ?? "10s"} onChange={(e) => rules.setCreateForm({ ...rules.createForm, group_interval: e.target.value })} bg="white" /></FormControl>
                <FormControl><FormLabel fontWeight="semibold">Repeat Interval</FormLabel><Input value={rules.createForm.repeat_interval ?? "12h"} onChange={(e) => rules.setCreateForm({ ...rules.createForm, repeat_interval: e.target.value })} bg="white" /></FormControl>
              </SimpleGrid>
              <SimpleGrid columns={2} spacing={4}>
                <FormControl>
                  <FormLabel fontWeight="semibold">Priority</FormLabel>
                  <NumberInput value={rules.createForm.priority ?? 100} min={1} onChange={(_, val) => rules.setCreateForm({ ...rules.createForm, priority: val || 100 })}>
                    <NumberInputField bg="white" /><NumberInputStepper><NumberIncrementStepper /><NumberDecrementStepper /></NumberInputStepper>
                  </NumberInput>
                  <Text fontSize="xs" color="gray.500" mt={1}>Lower number = higher priority</Text>
                </FormControl>
                <FormControl display="flex" alignItems="center" pt={8}>
                  <FormLabel fontWeight="semibold" mb={0}>Continue Routing</FormLabel>
                  <Switch isChecked={rules.createForm.continue_routing ?? false} onChange={(e) => rules.setCreateForm({ ...rules.createForm, continue_routing: e.target.checked })} colorScheme="blue" />
                </FormControl>
              </SimpleGrid>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={rules.closeCreate} isDisabled={rules.isCreating}>Cancel</Button>
            <Button colorScheme="blue" onClick={rules.handleCreate} isLoading={rules.isCreating} loadingText="Creating...">Create</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* ── View Routing Rule Modal ── */}
      <Modal isOpen={rules.isViewOpen} onClose={rules.closeView} size="xl" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Routing Rule Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {rules.viewItem && (
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Rule Name</Text><Text>{rules.viewItem.rule_name}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Organization</Text><Text>{rules.viewItem.organization}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Receiver</Text><Text>{rules.getReceiverName(rules.viewItem.receiver_id)}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Priority</Text><Text>{rules.viewItem.priority}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Status</Text><Badge colorScheme={rules.viewItem.enabled ? "green" : "red"} fontSize="sm" p={1}>{rules.viewItem.enabled ? "Enabled" : "Disabled"}</Badge></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Continue Routing</Text><Badge colorScheme={rules.viewItem.continue_routing ? "blue" : "gray"}>{rules.viewItem.continue_routing ? "Yes" : "No"}</Badge></Box>
                <Box gridColumn={{ base: "span 1", md: "span 2" }}>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>Match Criteria</Text>
                  <Wrap spacing={2}>
                    <WrapItem><Text fontSize="sm">Severity: <Badge colorScheme={rules.viewItem.match_severity ? severityColor(rules.viewItem.match_severity) : "gray"}>{rules.viewItem.match_severity ?? "any"}</Badge></Text></WrapItem>
                    <WrapItem><Text fontSize="sm">Category: <Badge colorScheme={rules.viewItem.match_category ? "purple" : "gray"}>{rules.viewItem.match_category ?? "any"}</Badge></Text></WrapItem>
                    <WrapItem><Text fontSize="sm">Alert Type: <Badge colorScheme="gray">{rules.viewItem.match_alert_type ?? "any"}</Badge></Text></WrapItem>
                  </Wrap>
                </Box>
                <Box gridColumn={{ base: "span 1", md: "span 2" }}>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>Group By</Text>
                  <Wrap spacing={1}>{rules.viewItem.group_by.map((g) => (<WrapItem key={g}><Badge colorScheme="blue">{g}</Badge></WrapItem>))}</Wrap>
                </Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Group Wait</Text><Text fontFamily="mono">{rules.viewItem.group_wait}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Group Interval</Text><Text fontFamily="mono">{rules.viewItem.group_interval}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Repeat Interval</Text><Text fontFamily="mono">{rules.viewItem.repeat_interval}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Created By</Text><Text fontSize="sm">{rules.viewItem.created_by}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Created At</Text><Text fontSize="sm">{new Date(rules.viewItem.created_at).toLocaleString()}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Updated At</Text><Text fontSize="sm">{new Date(rules.viewItem.updated_at).toLocaleString()}</Text></Box>
              </SimpleGrid>
            )}
          </ModalBody>
          <ModalFooter><Button onClick={rules.closeView}>Close</Button></ModalFooter>
        </ModalContent>
      </Modal>

      {/* ── Update Routing Rule Modal ── */}
      <Modal isOpen={rules.isUpdateOpen} onClose={rules.closeUpdate} size="xl" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Update Routing Rule{rules.updateItem ? `: ${rules.updateItem.rule_name}` : ""}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl><FormLabel fontWeight="semibold">Rule Name</FormLabel><Input value={rules.updateForm.rule_name ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, rule_name: e.target.value })} bg="white" /></FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold">Receiver</FormLabel>
                <Select value={rules.updateForm.receiver_id ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, receiver_id: parseInt(e.target.value) || 0 })} bg="white">
                  {rules.receivers.map((recv) => (<option key={recv.id} value={recv.id}>{recv.receiver_name} ({recv.organization})</option>))}
                </Select>
              </FormControl>
              <SimpleGrid columns={3} spacing={4}>
                <FormControl><FormLabel fontWeight="semibold">Match Severity</FormLabel><Select value={rules.updateForm.match_severity ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, match_severity: e.target.value || null })} bg="white" placeholder="Any">{SEVERITIES.map((s) => (<option key={s} value={s}>{s}</option>))}</Select></FormControl>
                <FormControl><FormLabel fontWeight="semibold">Match Category</FormLabel><Select value={rules.updateForm.match_category ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, match_category: e.target.value || null })} bg="white" placeholder="Any">{CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}</Select></FormControl>
                <FormControl><FormLabel fontWeight="semibold">Match Alert Type</FormLabel><Input value={rules.updateForm.match_alert_type ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, match_alert_type: e.target.value || null })} bg="white" /></FormControl>
              </SimpleGrid>
              <FormControl>
                <FormLabel fontWeight="semibold">Group By</FormLabel>
                <Wrap spacing={2}>
                  {["alertname", "category", "severity", "organization", "alert_type", "scope"].map((label) => (
                    <WrapItem key={label}>
                      <Checkbox
                        isChecked={(rules.updateForm.group_by ?? []).includes(label)}
                        onChange={(e) => {
                          const current = rules.updateForm.group_by ?? [];
                          const next = e.target.checked ? [...current, label] : current.filter((g) => g !== label);
                          rules.setUpdateForm({ ...rules.updateForm, group_by: next });
                        }}
                        colorScheme="blue"
                      ><Text fontSize="sm">{label}</Text></Checkbox>
                    </WrapItem>
                  ))}
                </Wrap>
              </FormControl>
              <SimpleGrid columns={3} spacing={4}>
                <FormControl><FormLabel fontWeight="semibold">Group Wait</FormLabel><Input value={rules.updateForm.group_wait ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, group_wait: e.target.value })} bg="white" /></FormControl>
                <FormControl><FormLabel fontWeight="semibold">Group Interval</FormLabel><Input value={rules.updateForm.group_interval ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, group_interval: e.target.value })} bg="white" /></FormControl>
                <FormControl><FormLabel fontWeight="semibold">Repeat Interval</FormLabel><Input value={rules.updateForm.repeat_interval ?? ""} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, repeat_interval: e.target.value })} bg="white" /></FormControl>
              </SimpleGrid>
              <SimpleGrid columns={2} spacing={4}>
                <FormControl>
                  <FormLabel fontWeight="semibold">Priority</FormLabel>
                  <NumberInput value={rules.updateForm.priority ?? 100} min={1} onChange={(_, val) => rules.setUpdateForm({ ...rules.updateForm, priority: val || 100 })}>
                    <NumberInputField bg="white" /><NumberInputStepper><NumberIncrementStepper /><NumberDecrementStepper /></NumberInputStepper>
                  </NumberInput>
                </FormControl>
                <FormControl display="flex" alignItems="center" pt={8}>
                  <FormLabel fontWeight="semibold" mb={0}>Continue Routing</FormLabel>
                  <Switch isChecked={rules.updateForm.continue_routing ?? false} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, continue_routing: e.target.checked })} colorScheme="blue" />
                </FormControl>
              </SimpleGrid>
              <FormControl display="flex" alignItems="center">
                <FormLabel fontWeight="semibold" mb={0}>Enabled</FormLabel>
                <Switch isChecked={rules.updateForm.enabled ?? true} onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, enabled: e.target.checked })} colorScheme="green" />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={rules.closeUpdate} isDisabled={rules.isUpdating}>Cancel</Button>
            <Button colorScheme="blue" onClick={rules.handleUpdate} isLoading={rules.isUpdating} loadingText="Updating...">Update</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

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
          {["Alert Definitions", "Notification Routing", "Alert History"].map(
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
                  bg: subTabIndex === idx ? "#F9A825" : "transparent",
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
          <TabPanel px={0} pt={6}>
            <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
              <CardBody>
                <Center py={12}>
                  <VStack spacing={3}>
                    <Text fontSize="lg" fontWeight="semibold" color="gray.500">Alert History</Text>
                    <Text color="gray.400" fontSize="sm">Historical alert events and notifications will appear here.</Text>
                  </VStack>
                </Center>
              </CardBody>
            </Card>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
