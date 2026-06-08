// AlertReceiversSection — extracted from AlertingTab

import React from "react";
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Divider,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Heading,
  HStack,
  IconButton,
  Input,
  Menu,
  MenuButton,
  MenuDivider,
  MenuItem,
  MenuList,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  Radio,
  RadioGroup,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  Textarea,
  Tooltip,
  VStack,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, EditIcon, LockIcon, ViewIcon } from "@chakra-ui/icons";

import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../../common/AdminDataTable";
import StandardModal from "../../common/StandardModal";
import {
  CATEGORIES,
  CONDITION_OPERATORS,
  LATENCY_THRESHOLD_UNITS,
  PERCENTAGE_UNIT,
  RBAC_ROLES,
  SEVERITIES,
  SIGNAL_METRICS_BY_SIGNAL,
  SIGNALS_BY_SUB_CATEGORY,
  SUB_CATEGORIES_BY_CATEGORY,
  TARGET_SERVICES,
  URGENCIES,
} from "../../../types/alerting";
import {
  ALERT_TYPES_BY_CATEGORY,
  EVAL_INTERVALS,
  FOR_DURATIONS,
  FORM_REQUIRED_ASTERISK,
} from "./constants";
import { getAllowedForDurations } from "./utils";
import OptionSelector from "./OptionSelector";
import type { UseAlertingTabReturn } from "../hooks/useAlertingTab";


type Props = UseAlertingTabReturn;

export default function AlertReceiversSection(tab: Props) {
  const {
    cardBg,
    cardBorder,
    defs,
    recvs,
    rules,
    history,
    defDeleteRef,
    recvDeleteRef,
    ruleDeleteRef,
    sortedDefinitions,
    sortedReceivers,
    sortedRules,
    sortedHistoryItems,
    definitionColumns,
    receiverColumns,
    routingRuleColumns,
    historyColumns,
    expandedUpdateServices,
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
    activeAlertDefinitions,
    receiversSearchQuery,
    setReceiversSearchQuery,
    alertTypeLabel,
    formatThreshold,
    titleCase,
    categoryColor,
    severityColor,
  } = tab;

  return (
    <>
<Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="gray.700" userSelect="none" cursor="default">
              Notification Receivers
            </Heading>
            <HStack spacing={2}>
              <Button size="sm" colorScheme="orange" leftIcon={<AddIcon />} onClick={recvs.openCreate}>
                Create
              </Button>
              <Button size="sm" colorScheme="blue" onClick={recvs.fetchReceivers} isLoading={recvs.isLoading} loadingText="Loading...">Refresh</Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <AdminDataTable
            items={sortedReceivers}
            columns={receiverColumns}
            getRowKey={(r) => String(r.id)}
            onRowClick={recvs.openView}
            paginate="client"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            filterToolbarAlign="flex-end"
            isLoading={recvs.isLoading}
            loadingMessage="Loading receivers..."
            emptyMessage="No notification receivers found. Click 'Create' to add one."
            noResultsMessage="No receivers match the current filters."
            unfilteredCount={recvs.receivers.length}
            hasActiveFilters={recvs.filterEnabled !== "all" || !!receiversSearchQuery.trim()}
            onClearFilters={() => {
              recvs.setFilterEnabled("all");
              setReceiversSearchQuery("");
            }}
            filters={(
              <>
                <TableSearchField
                  label="Search"
                  value={receiversSearchQuery}
                  onChange={setReceiversSearchQuery}
                  placeholder="Search receivers..."
                  formControlProps={{ maxW: "260px" }}
                />
                <TableSelectField
                  label="Status"
                  value={recvs.filterEnabled}
                  onChange={recvs.setFilterEnabled}
                  formControlProps={{ maxW: "200px" }}
                >
                  <option value="all">All</option>
                  <option value="enabled">Enabled</option>
                  <option value="disabled">Disabled</option>
                </TableSelectField>
              </>
            )}
          />
        </CardBody>
      </Card>

      {/* ── Create Receiver Modal ── */}
      <StandardModal
        isOpen={recvs.isCreateOpen}
        onClose={recvs.closeCreate}
        size="lg"
        title="Create Notification Receiver"
        modalProps={{ scrollBehavior: "inside" }}
        footer={
          <>
            <Button variant="ghost" mr={3} onClick={recvs.closeCreate} isDisabled={recvs.isCreating}>Cancel</Button>
            <Button colorScheme="blue" onClick={recvs.handleCreate} isLoading={recvs.isCreating} loadingText="Creating...">Create</Button>
          </>
        }
      >
        <VStack spacing={4} align="stretch">
              <SimpleGrid columns={2} spacing={4}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Category</FormLabel>
                  <Select value={recvs.createForm.category} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, category: e.target.value })} bg="white" placeholder="Select category">
                    {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                  </Select>
                </FormControl>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Severity</FormLabel>
                  <Select value={recvs.createForm.severity} onChange={(e) => recvs.setCreateForm({ ...recvs.createForm, severity: e.target.value })} bg="white" placeholder="Select severity">
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
      </StandardModal>

      {/* ── View Receiver Modal ── */}
      <StandardModal
        isOpen={recvs.isViewOpen}
        onClose={recvs.closeView}
        size="xl"
        title="Notification Receiver Details"
        modalProps={{ scrollBehavior: "inside" }}
        footer={<Button onClick={recvs.closeView}>Close</Button>}
      >
        {recvs.viewItem && (
          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Receiver Name</Text><Text fontSize="sm">{recvs.viewItem.receiver_name}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>Status</Text><Badge colorScheme={recvs.viewItem.enabled ? "green" : "red"} fontSize="sm" p={1}>{recvs.viewItem.enabled ? "Enabled" : "Disabled"}</Badge></Box>
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
      </StandardModal>

      {/* ── Update Receiver Modal ── */}
      <StandardModal
        isOpen={recvs.isUpdateOpen}
        onClose={recvs.closeUpdate}
        size="lg"
        title="Update Notification Receiver"
        modalProps={{ scrollBehavior: "inside" }}
        footer={
          <>
            <Button variant="ghost" mr={3} onClick={recvs.closeUpdate} isDisabled={recvs.isUpdating}>Cancel</Button>
            <Button colorScheme="blue" onClick={recvs.handleUpdate} isLoading={recvs.isUpdating} loadingText="Updating...">Update</Button>
          </>
        }
      >
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
      </StandardModal>

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
}
